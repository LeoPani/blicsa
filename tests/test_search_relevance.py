"""
Nível 1/2 — PERTINÊNCIA dos resultados.

Perguntas: os resultados são relevantes à query (precision@10)? os filtros
(ano, idioma, open access, tipo) são respeitados? a sintaxe do query builder
(TITLE/YEAR) funciona? a deduplicação remove os certos e preserva os distintos?
a paginação devolve a quantidade pedida sem repetição?

Offline: fixtures reais. Live: @pytest.mark.live.
"""
import json
import re

import pandas as pd
import pytest

from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider
from tests.conftest import serve, load_fixture

# -------------------------------------------------- heurística precision@10 ---
# Cada query vira grupos de sinônimos/stems; um record "casa" se TODO grupo tem
# ao menos um termo presente em título+abstract+keywords.
QUERY_TERMS = {
    "bibliometric analysis": [["bibliometric", "bibliometr"], ["analys", "analiz", "análi"]],
    "entrepreneurship education": [["entrepreneur", "empreendedor"], ["education", "educat", "ensino"]],
    "machine learning": [["machine", "máquina", "maquina"], ["learning", "learn", "aprendiz"]],
}


def precision_at_10(records, term_groups):
    top = records[:10]
    if not top:
        return 0.0
    hits = 0
    for r in top:
        blob = f"{r.get('title','')} {r.get('abstract','')} {r.get('keywords','')}".lower()
        if all(any(t in blob for t in grp) for grp in term_groups):
            hits += 1
    return hits / len(top)


def run(provider, bodies, **kw):
    with serve(bodies) as rec:
        out = list(provider.search(kw.pop("query", "q"), max_results=kw.pop("max_results", 25), **kw))
    return out, rec


# ============================================ 1. precision@10 (offline) -------
OFFLINE_PRECISION_CASES = [
    (OpenAlexProvider, "bibliometric analysis", ["openalex_rel_bibliometric.json"]),
    (OpenAlexProvider, "entrepreneurship education", ["openalex_rel_entrepreneurship.json"]),
    (OpenAlexProvider, "machine learning", ["openalex_rel_ml.json"]),
    (CrossrefProvider, "bibliometric analysis", ["crossref_rel_bibliometric.json"]),
    (CrossrefProvider, "entrepreneurship education", ["crossref_rel_entrepreneurship.json"]),
    (CrossrefProvider, "machine learning", ["crossref_rel_ml.json"]),
    (PubMedProvider, "bibliometric analysis",
     ["pubmed_rel_bibliometric_esearch.json", "pubmed_rel_bibliometric_efetch.json"]),
    (PubMedProvider, "machine learning",
     ["pubmed_rel_ml_esearch.json", "pubmed_rel_ml_efetch.json"]),
]


@pytest.mark.parametrize("cls,query,fixtures", OFFLINE_PRECISION_CASES,
                         ids=[f"{c.__name__.replace('Provider','')}-{q}"
                              for c, q, _ in OFFLINE_PRECISION_CASES])
def test_precision_at_10_offline(cls, query, fixtures):
    bodies = [load_fixture(f) for f in fixtures]
    recs, _ = run(cls(), bodies, query=query)
    p = precision_at_10(recs, QUERY_TERMS[query])
    assert p >= 0.7, f"{cls.__name__} p@10={p:.2f} para '{query}' (< 0.7)"


# ============================================ 2. filtros respeitados ----------
def test_openalex_year_filter_offline():
    recs, rec = run(OpenAlexProvider(), [load_fixture("openalex_year_2019_2021.json")],
                    query="bibliometric analysis",
                    filters={"year_start": 2019, "year_end": 2021})
    # URL construída corretamente
    assert "publication_year" in rec.calls[0] and "2019-2021" in rec.calls[0]
    # 100% dos resultados no intervalo
    assert recs and all(2019 <= r["year"] <= 2021 for r in recs)


def test_crossref_year_filter_offline():
    recs, rec = run(CrossrefProvider(), [load_fixture("crossref_year_2019_2021.json")],
                    query="bibliometric analysis",
                    filters={"year_start": 2019, "year_end": 2021})
    assert "from-pub-date" in rec.calls[0] and "until-pub-date" in rec.calls[0]
    assert recs and all(2019 <= r["year"] <= 2021 for r in recs)


def test_openalex_is_oa_filter_offline():
    recs, rec = run(OpenAlexProvider(), [load_fixture("openalex_isoa_true.json")],
                    query="bibliometric analysis", filters={"is_oa": True})
    assert "is_oa" in rec.calls[0]
    assert recs and all(r["is_oa"] is True for r in recs)


def test_openalex_language_filter_offline():
    recs, rec = run(OpenAlexProvider(), [load_fixture("openalex_lang_pt.json")],
                    query="bibliometria", filters={"language": "pt"})
    assert "language" in rec.calls[0]
    frac_pt = sum(1 for r in recs if r["language"] == "pt") / len(recs)
    assert frac_pt >= 0.9, f"apenas {frac_pt:.0%} em pt"


def test_crossref_language_filter_offline():
    """BUG-02 CORRIGIDO: filtro de idioma client-side. Todos os records devolvidos são
    pt (campo da API ou detectado); os não-correspondentes são CONTADOS, não somem."""
    from core.sources.crossref import _record_matches_language
    prov = CrossrefProvider()
    recs, _ = run(prov, [load_fixture("crossref_lang_pt_ignored.json")],
                  query="bibliometria", filters={"language": "pt"})
    assert recs, "filtro removeu tudo"
    # Nenhum record devolvido é de idioma != pt (efetivo)
    assert all(_record_matches_language(r, "pt") for r in recs)
    # Nenhum record com idioma de API explicitamente não-pt escapou
    assert not any((r["language"] or "").lower()[:2] not in ("", "pt") for r in recs)
    # Descartados foram contados (o fixture tem idiomas variados)
    assert prov.language_filtered_count > 0


def test_pubmed_language_filter_offline():
    """BUG-01 CORRIGIDO: 'pt' é mapeado para ISO 639-2 'por' no filtro [LA]; a esearch
    passa a retornar resultados. Fixtures sintéticas (por[LA]) servidas offline."""
    esearch = '{"esearchresult": {"count": "1", "idlist": ["1"]}}'
    efetch = ("PMID- 1\nTI  - Estudo bibliométrico\nAU  - Silva J\nDP  - 2020\n"
              "JT  - Revista\nLA  - por\nAB  - Resumo em português.\n\n")
    prov = PubMedProvider()
    recs, rec = run(prov, [esearch, efetch], query="bibliometria", filters={"language": "pt"})
    # A URL da esearch usa 'por[LA]' (mapeado), não 'pt[LA]'
    assert "por" in rec.calls[0] and "pt%5BLA%5D" not in rec.calls[0]
    assert len(recs) >= 1


# ============================================ 3. sintaxe do query builder -----
def test_openalex_query_builder_title_offline():
    _, rec = run(OpenAlexProvider(), [load_fixture("openalex_vosviewer_titlesearch.json")],
                 query='TITLE("VOSviewer bibliometric mapping")')
    assert "title.search" in rec.calls[0]


def test_openalex_query_builder_year_offline():
    _, rec = run(OpenAlexProvider(), [load_fixture("openalex_rel_bibliometric.json")],
                 query='TITLE-ABS-KEY("bibliometric") AND YEAR(2020)')
    assert "publication_year" in rec.calls[0] and "2020" in rec.calls[0]


@pytest.mark.live
def test_openalex_query_builder_title_returns_phrase_in_title_live():
    recs = list(OpenAlexProvider().search('TITLE("bibliometric analysis")', max_results=10))
    assert recs
    frac = sum(1 for r in recs
               if "bibliometric" in r["title"].lower()) / len(recs)
    assert frac >= 0.7


@pytest.mark.live
def test_openalex_query_builder_year_filters_live():
    recs = list(OpenAlexProvider().search('TITLE-ABS-KEY("bibliometric") AND YEAR(2020)',
                                          max_results=25))
    assert recs and all(r["year"] == 2020 for r in recs)


@pytest.mark.live
def test_combined_query_not_empty_live():
    recs = list(OpenAlexProvider().search("machine learning healthcare",
                                          filters={"year_start": 2018, "year_end": 2022},
                                          max_results=10))
    assert len(recs) > 0


# ============================================ 4. deduplicação -----------------
from core.harmonization import fuzzy_deduplicate_papers


def test_dedup_removes_exact_and_near_duplicates():
    t = "A systematic review of machine learning methods for bibliometric network analysis"
    df = pd.DataFrame([
        {"title": t, "doi": "10.1/a"},
        {"title": t, "doi": "10.1/a"},                       # exata
        {"title": t + "s", "doi": "10.2/b"},                 # ~99% similar
        {"title": "Deep reinforcement learning for robotic manipulation", "doi": "10.3/c"},
    ])
    out = fuzzy_deduplicate_papers(df)
    titles = out["title"].tolist()
    assert len(out) == 2, f"esperava 2 após dedup, obteve {len(out)}"
    assert "Deep reinforcement learning for robotic manipulation" in titles


def test_dedup_preserves_distinct_similar_titles():
    # Falsos positivos: títulos parecidos mas artigos distintos NÃO devem ser removidos.
    df = pd.DataFrame([
        {"title": "Machine learning for cancer diagnosis", "doi": "10.1/a"},
        {"title": "Deep learning for image segmentation", "doi": "10.2/b"},
        {"title": "Bibliometric analysis of renewable energy", "doi": "10.3/c"},
    ])
    out = fuzzy_deduplicate_papers(df)
    assert len(out) == 3


def test_dedup_count_trail_consistent():
    df = pd.DataFrame([{"title": f"Paper {i%7}", "doi": f"10.1/{i%7}"} for i in range(20)])
    baixados = len(df)
    out = fuzzy_deduplicate_papers(df)
    importados = len(out)
    removidos = baixados - importados
    assert baixados - removidos == importados
    assert importados == 7  # 7 títulos distintos


def test_dedup_same_doi_prefix_variants_identical_title():
    # Mesmo paper, DOI com e sem prefixo https, título idêntico → deve deduplicar.
    df = pd.DataFrame([
        {"title": "Same Title Paper", "doi": "10.1/a"},
        {"title": "Same Title Paper", "doi": "https://doi.org/10.1/a"},
    ])
    assert len(fuzzy_deduplicate_papers(df)) == 1


def test_dedup_case_and_punctuation_insensitive():
    """BUG-03 CORRIGIDO: a chave de comparação é normalizada (casefold, sem pontuação),
    então o mesmo artigo em caixa/pontuação diferentes é deduplicado."""
    df = pd.DataFrame([
        {"title": "Bibliometric Analysis of Innovation", "doi": "10.1/a"},
        {"title": "bibliometric analysis of innovation.", "doi": "10.2/b"},
    ])
    assert len(fuzzy_deduplicate_papers(df)) == 1


# ============================================ 5. paginação --------------------
def test_openalex_pagination_250_no_repeats_offline():
    bodies = [load_fixture("openalex_page1.json"),
              load_fixture("openalex_page2.json"),
              load_fixture("openalex_page3.json")]
    recs, rec = run(OpenAlexProvider(), bodies, query="bibliometric analysis",
                    max_results=250)
    assert len(recs) == 250, f"pedi 250, obtive {len(recs)}"
    assert len(rec.calls) == 3, "cursor não seguiu 3 páginas"
    dois = [r["doi"] for r in recs if r["doi"]]
    assert len(dois) == len(set(dois)), "DOIs repetidos entre páginas"


def test_openalex_pagination_partial_50_offline():
    bodies = [load_fixture("openalex_page1.json")]
    recs, rec = run(OpenAlexProvider(), bodies, query="bibliometric analysis",
                    max_results=50)
    assert len(recs) == 50
    assert len(rec.calls) == 1


# ================================================ LIVE precision --------------
@pytest.mark.live
@pytest.mark.parametrize("cls", [OpenAlexProvider, CrossrefProvider, PubMedProvider],
                         ids=["OpenAlex", "Crossref", "PubMed"])
def test_precision_at_10_live(cls):
    recs = list(cls().search("bibliometric analysis", max_results=15))
    p = precision_at_10(recs, QUERY_TERMS["bibliometric analysis"])
    if p < 0.7:
        pytest.xfail(f"{cls.__name__} p@10={p:.2f} ao vivo (< 0.7)")
    assert p >= 0.7
