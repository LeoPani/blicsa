"""Fase 1 — core/term_extraction.py (extração de termos no padrão VOSviewer).

Regra desta suíte (aprendida com três bugs que passaram por testes verdes): toda checagem
tem a variante POBRE do dado, não só o caso feliz. Registro sem ano, sem citações, abstract
vazio, corpus de um único ano, um único termo, valores todos iguais (divisão por zero) e
valores extremos aparecem abaixo de propósito.
"""
import time

import pandas as pd
import pytest

from core.term_extraction import (
    ExtractionResult,
    compute_relevance,
    detect_corpus_language,
    extract_noun_phrases,
    extract_terms,
    normalize_phrase,
    resolve_method,
    singularize,
    split_keywords,
    suggest_threshold,
    threshold_preview,
)


def _doc(title="", abstract="", keywords="", year=2020, citations=0, language="en"):
    return {"title": title, "abstract": abstract, "keywords": keywords,
            "year": year, "citations": citations, "language": language}


# ─────────────────────────── extração e contagem ───────────────────────────

def test_known_terms_are_extracted_exactly():
    """Corpus sintético com termos plantados → os termos esperados aparecem."""
    df = pd.DataFrame([
        _doc(title="Regional innovation systems in Brazil",
             abstract="The regional innovation system depends on public policy."),
        _doc(title="Public policy for regional innovation",
             abstract="Regional innovation systems and public policy interact."),
    ])
    r = extract_terms(df, fields="title_abstract", min_occurrences=2)
    nomes = set(r.term_names)
    for esperado in ("regional innovation", "public policy", "innovation"):
        assert esperado in nomes, f"termo esperado ausente: {esperado!r} (obtidos: {sorted(nomes)})"


def test_binary_vs_total_counting_differ_correctly():
    """Documento que repete o termo 5x: binário conta 1, total conta 5."""
    texto = "innovation " * 5
    df = pd.DataFrame([_doc(title="innovation", abstract=texto)])

    binario = extract_terms(df, fields="title_abstract", binary_count=True)
    total = extract_terms(df, fields="title_abstract", binary_count=False)

    b = {t.term: t.occurrences for t in binario.terms}
    o = {t.term: t.occurrences for t in total.terms}
    assert b["innovation"] == 1, f"contagem binária deveria ser 1, foi {b['innovation']}"
    assert o["innovation"] == 6, f"contagem total deveria ser 6 (1 título + 5), foi {o['innovation']}"
    # `documents` é sempre binário, nos dois modos.
    assert all(t.documents == 1 for t in binario.terms + total.terms)


def test_singular_and_plural_are_unified():
    """"medical unit" e "medical units" viram um termo só (o VOSviewer funde as variantes)."""
    df = pd.DataFrame([
        _doc(title="The medical units", abstract="medical units everywhere"),
        _doc(title="The medical unit", abstract="a single medical unit"),
    ])
    r = extract_terms(df, fields="title_abstract", min_occurrences=1)
    nomes = r.term_names
    assert "medical unit" in nomes
    assert "medical units" not in nomes, "plural não foi unificado ao singular"
    termo = next(t for t in r.terms if t.term == "medical unit")
    assert termo.documents == 2, "as duas variantes deveriam somar no mesmo termo"


@pytest.mark.parametrize("plural,singular", [
    ("units", "unit"), ("studies", "study"), ("boxes", "box"), ("cities", "city"),
    ("lives", "life"), ("children", "child"), ("analyses", "analysis"), ("sizes", "size"),
    # Casos que NÃO podem ser mexidos (singulares terminados em s) nem estragados:
    ("analysis", "analysis"), ("business", "business"), ("series", "series"),
    ("improves", "improve"),   # a regra cega "ves"→"fe" fazia "improfe"
])
def test_singularize_rules(plural, singular):
    assert singularize(plural) == singular


def test_generic_words_get_low_relevance():
    """Termo genérico (espalhado por tudo) fica com relevância abaixo do específico.

    "generic" aparece em todos os documentos e coocorre com todo mundo — distribuição igual
    à marginal → relevância baixa. Os pares específicos concentram coocorrência → alta.
    """
    docs = []
    for a, b in (("alpha", "beta"), ("alpha", "beta"), ("gamma", "delta"), ("gamma", "delta")):
        docs.append(_doc(keywords=f"generic; {a}; {b}"))
    r = extract_terms(pd.DataFrame(docs), fields="keywords", min_occurrences=1)
    rel = {t.term: t.relevance for t in r.terms}
    assert rel["generic"] < rel["alpha"], (
        f"o termo genérico deveria ter relevância menor: generic={rel['generic']:.3f} "
        f"alpha={rel['alpha']:.3f}")
    assert rel["generic"] < rel["gamma"]


def test_relevance_compares_against_the_corpus_marginal():
    """A comparação é com a distribuição MARGINAL, não com uma uniforme.

    Este caso é o que distingue as duas: "companheiro" coocorre só com "dominante", o termo
    mais frequente do corpus. Coocorrer com o que todo mundo cita não é sinal de
    especificidade, então a relevância dele tem de ficar ABAIXO de um termo que coocorre com
    parceiros raros. Trocar a marginal por uma distribuição uniforme inverte essa ordem —
    era o furo que a matriz de reinjeção encontrou nas asserções acima.
    """
    docs = ([{"keywords": "dominante; companheiro"}] * 20
            + [{"keywords": "dominante; satelite"}] * 4
            + [{"keywords": "raro_a; raro_b"}] * 4
            + [{"keywords": "dominante; companheiro; raro_a"}] * 2)
    r = extract_terms(pd.DataFrame(docs), fields="keywords", min_occurrences=1)
    rel = {t.term: t.relevance for t in r.terms}
    assert rel["companheiro"] < rel["raro_a"], (
        "quem só coocorre com o termo mais frequente do corpus não é específico: "
        f"companheiro={rel['companheiro']:.3f} raro_a={rel['raro_a']:.3f}")


def test_stopwords_never_become_terms():
    """Palavras funcionais e genéricas de artigo científico não viram termo."""
    df = pd.DataFrame([_doc(
        title="The results of this study show that the method is used",
        abstract="In this paper we present an approach based on the data of the analysis")])
    r = extract_terms(df, fields="title_abstract", min_occurrences=1)
    nomes = set(r.term_names)
    for lixo in ("the", "this", "study", "results", "paper", "approach", "method", "data"):
        assert lixo not in nomes, f"stopword virou termo: {lixo!r}"


def test_threshold_counts_decrease_monotonically():
    """Três limiares → contagens monotonicamente decrescentes."""
    docs = []
    for i in range(12):
        docs.append(_doc(keywords=f"comum; frequente{i % 3}; raro{i}"))
    preview = threshold_preview(pd.DataFrame(docs), thresholds=(1, 2, 4, 8), fields="keywords")
    valores = [preview[k] for k in sorted(preview)]
    assert valores == sorted(valores, reverse=True), f"não é decrescente: {preview}"
    assert valores[0] > valores[-1], "o limiar mais alto deveria cortar termos"
    # E bate com a extração real no mesmo limiar (o preview não pode mentir).
    real = extract_terms(pd.DataFrame(docs), fields="keywords", min_occurrences=4)
    assert len(real) == preview[4], f"preview={preview[4]} mas extração deu {len(real)}"


def test_suggest_threshold_targets_the_recommended_range():
    """O guia recomenda 1.000–2.000 termos; a sugestão persegue o alvo pedido."""
    docs = [_doc(keywords="; ".join(f"t{i}_{j}" for j in range(5))) for i in range(40)]
    df = pd.DataFrame(docs)
    limiar = suggest_threshold(df, target=10, fields="keywords")
    resultado = extract_terms(df, fields="keywords", min_occurrences=limiar)
    assert len(resultado) <= 10, f"limiar {limiar} deveria deixar <=10 termos, deixou {len(resultado)}"


# ─────────────────────────── idioma e avisos ───────────────────────────

def test_portuguese_corpus_warns_and_keywords_still_work():
    """Corpus em português → aviso emitido (nunca em silêncio); keywords seguem funcionando."""
    docs = [_doc(title="Empreendedorismo e inovação regional",
                 abstract="O empreendedorismo regional depende de política pública.",
                 keywords="empreendedorismo; inovação", language="pt") for _ in range(2)]
    df = pd.DataFrame(docs)

    com_texto = extract_terms(df, fields="title_abstract")
    assert "map.warn_non_english" in com_texto.warnings, (
        f"deveria avisar sobre extração em não-inglês; avisos={com_texto.warnings}")

    # Pelo caminho de keywords não há dependência de gramática — nada de aviso de idioma.
    so_kw = extract_terms(df, fields="keywords", min_occurrences=1)
    assert "map.warn_non_english" not in so_kw.warnings
    assert "empreendedorismo" in so_kw.term_names
    assert "inovação" in so_kw.term_names


def test_language_detection_falls_back_without_column():
    """Sem coluna `language`, detecta pelo texto — e não explode se não houver texto."""
    df_en = pd.DataFrame([{"title": "regional innovation systems and public policy in cities"}])
    assert detect_corpus_language(df_en) == "en"
    assert detect_corpus_language(pd.DataFrame([{"title": ""}])) == ""
    assert detect_corpus_language(pd.DataFrame()) == ""


# ─────────────────────────── thesaurus ───────────────────────────

def test_thesaurus_merges_variants_into_one_term():
    """"ml" e "machine learning" viram um termo só."""
    df = pd.DataFrame([
        _doc(keywords="machine learning; health"),
        _doc(keywords="ml; health"),
        _doc(keywords="ML; health"),
    ])
    th = {"ml": "machine learning"}
    r = extract_terms(df, fields="keywords", min_occurrences=1, thesaurus=th)
    nomes = r.term_names
    assert "ml" not in nomes, "a variante deveria ter sido fundida"
    termo = next(t for t in r.terms if t.term == "machine learning")
    assert termo.documents == 3, f"os 3 documentos deveriam somar no termo canônico, deu {termo.documents}"


# ─────────────────────────── dados pobres e extremos ───────────────────────────

def test_empty_abstract_still_yields_title_terms():
    """Abstract vazio não quebra: os termos vêm só do título."""
    df = pd.DataFrame([
        _doc(title="Regional innovation systems", abstract=""),
        _doc(title="Regional innovation policy", abstract=None),
    ])
    r = extract_terms(df, fields="title_abstract", min_occurrences=1)
    assert "regional innovation" in r.term_names
    assert len(r) > 0


def test_empty_dataframe_returns_empty_structure():
    """df vazio → estrutura vazia, sem exceção."""
    for vazio in (pd.DataFrame(), None, pd.DataFrame(columns=["title", "keywords"])):
        r = extract_terms(vazio)
        assert isinstance(r, ExtractionResult)
        assert len(r) == 0 and r.terms == [] and r.doc_terms == []


def test_records_without_year_or_citations_report_none_not_zero():
    """Sem ano/citações, as métricas do overlay são None — 0 mentiria (seria "ano 0")."""
    df = pd.DataFrame([
        {"keywords": "alpha; beta"},                       # sem year, sem citations
        {"keywords": "alpha; beta", "year": 0, "citations": None},
    ])
    r = extract_terms(df, fields="keywords", min_occurrences=1)
    assert r.terms, "deveria extrair os termos mesmo sem ano/citações"
    for t in r.terms:
        assert t.avg_year is None, f"{t.term}: avg_year deveria ser None, é {t.avg_year!r}"
        assert t.avg_citations is None, f"{t.term}: avg_citations deveria ser None"
        assert t.first_year is None


def test_single_year_corpus_does_not_divide_by_zero():
    """Corpus com um único ano (o bug do slider de anos): média = aquele ano, sem erro."""
    df = pd.DataFrame([_doc(keywords="alpha; beta", year=2021) for _ in range(3)])
    r = extract_terms(df, fields="keywords", min_occurrences=1)
    assert all(t.avg_year == 2021.0 for t in r.terms)
    assert all(t.first_year == 2021 for t in r.terms)


def test_single_term_corpus_has_no_cooccurrence_and_uniform_relevance():
    """Um único termo no corpus → zero coocorrência. Relevância uniforme, sem divisão por zero."""
    df = pd.DataFrame([_doc(keywords="solo") for _ in range(4)])
    r = extract_terms(df, fields="keywords", min_occurrences=1)
    assert len(r) == 1 and r.terms[0].term == "solo"
    assert r.terms[0].relevance == 1.0, "sem sinal de coocorrência, a relevância é uniforme"

    # E diretamente na função de relevância, com todos os valores iguais:
    assert compute_relevance([["a"], ["a"], ["a"]]) == {"a": 1.0}
    assert compute_relevance([]) == {}


def test_extreme_threshold_yields_empty_with_explicit_warning():
    """Limiar altíssimo → zero termos COM aviso (não silenciosamente vazio)."""
    df = pd.DataFrame([_doc(keywords="alpha; beta")])
    r = extract_terms(df, fields="keywords", min_occurrences=9999)
    assert len(r) == 0
    assert "map.warn_threshold_empty" in r.warnings, (
        f"o corte total tem de ser explicado; avisos={r.warnings}")
    assert r.total_unique_before_threshold == 2, "deve informar quantos havia antes do corte"


def test_both_fields_do_not_duplicate_a_term_present_in_two_fields():
    """`both`: termo que está na keyword E no título conta UMA vez por documento."""
    df = pd.DataFrame([_doc(title="Regional innovation matters",
                            abstract="regional innovation again",
                            keywords="regional innovation")])
    r = extract_terms(df, fields="both", binary_count=True, min_occurrences=1)
    termo = next(t for t in r.terms if t.term == "regional innovation")
    assert termo.occurrences == 1, (
        f"contagem binária com `both` deveria ser 1, foi {termo.occurrences}")
    assert termo.documents == 1
    # E a união é de verdade: keyword exclusiva e termo exclusivo do texto convivem.
    df2 = pd.DataFrame([_doc(title="Public policy", keywords="somente keyword")])
    r2 = extract_terms(df2, fields="both", min_occurrences=1)
    nomes = set(r2.term_names)
    assert "somente keyword" in nomes and "public policy" in nomes


# ─────────────────────────── determinismo e desempenho ───────────────────────────

def test_extraction_is_deterministic():
    """Mesma entrada → mesma saída, sem depender de ordem de dict/set."""
    docs = [_doc(title=f"Innovation system {i}", abstract="regional innovation policy",
                 keywords="innovation; policy") for i in range(15)]
    df = pd.DataFrame(docs)
    saidas = [extract_terms(df, fields="both", min_occurrences=2).as_dicts() for _ in range(3)]
    assert saidas[0] == saidas[1] == saidas[2], "extração não determinística"


def test_performance_5000_documents_under_30s(capsys):
    """5.000 documentos processados em < 30s (tempo real registrado na saída)."""
    docs = [_doc(title=f"Regional innovation systems study number {i}",
                 abstract=("Public policy and regional innovation drive economic "
                           "development in emerging markets with technology transfer."),
                 keywords="innovation; policy; development")
            for i in range(5000)]
    df = pd.DataFrame(docs)
    t0 = time.perf_counter()
    r = extract_terms(df, fields="both", min_occurrences=10)
    dt = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\n[perf] 5.000 docs · {dt:.2f}s · {len(r)} termos "
              f"(de {r.total_unique_before_threshold} únicos) · backend={r.method_used}")
    assert len(r) > 0, "deveria extrair termos"
    assert dt < 30.0, f"extração levou {dt:.1f}s (meta < 30s)"


# ─────────────────────────── utilitários ───────────────────────────

def test_split_keywords_handles_both_separators_and_junk():
    assert split_keywords("a; b;c") == ["a", "b", "c"]
    assert split_keywords("a, b , c") == ["a", "b", "c"]
    assert split_keywords("") == [] and split_keywords(None) == []
    assert split_keywords("; ;") == []


def test_normalize_phrase_collapses_and_singularizes_head():
    assert normalize_phrase("  Medical   UNITS ") == "medical unit"
    assert normalize_phrase("") == ""


def test_resolve_method_falls_back_to_builtin():
    """Backend pedido e ausente cai no embutido, sem exceção; método inválido levanta."""
    assert resolve_method("ngram") == "ngram"
    assert resolve_method("auto") in ("spacy", "nltk", "ngram")
    assert resolve_method("spacy") in ("spacy", "ngram")   # "ngram" se spaCy não estiver lá
    with pytest.raises(ValueError):
        resolve_method("inexistente")


def test_noun_phrase_extraction_rejects_verb_spanning_phrases():
    """Frase nominal não atravessa o verbo: "hospital showed rapid" não é termo."""
    frases = extract_noun_phrases("The hospital showed rapid improvement of medical units.")
    assert "medical unit" in frases
    for lixo in ("hospital showed rapid", "showed rapid"):
        assert lixo not in frases, f"frase atravessando verbo virou termo: {lixo!r}"
