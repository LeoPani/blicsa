"""
Nível 1/2 — CORREÇÃO dos dados retornados pelas buscas.

Pergunta respondida: os campos normalizados (título, ano, DOI, autor, fonte,
citações, idioma, abstract) batem com valores conhecidos de artigos-âncora?

Ground truth (DOI estável, um por área):
  - OpenAlex : van Eck & Waltman, "Software survey: VOSviewer" — 10.1007/s11192-009-0146-3
  - Crossref : Shane & Venkataraman (2000), "The Promise of Entrepreneurship
               as a Field of Research" — 10.5465/amr.2000.2791611
  - PubMed   : Livak & Schmittgen (2001), "Analysis of relative gene expression
               data ... 2^-ddCt Method" — PMID 11846609 / 10.1006/meth.2001.1262

Offline: fixtures reais gravadas (tests/fixtures). Live: @pytest.mark.live.
"""
import difflib
import re

import pytest

from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider
from tests.conftest import serve, load_fixture

# ---------------------------------------------------------------- helpers ----
PROVIDER_KEYS = {
    "authors", "title", "year", "source", "keywords", "abstract",
    "citations", "doi", "references", "origin", "language", "is_oa", "oa_url",
}
STRING_FIELDS = {"authors", "title", "source", "keywords", "abstract",
                 "doi", "references", "origin", "language", "oa_url"}


def norm_doi(doi: str) -> str:
    """Normaliza DOI: remove prefixo de URL e caixa."""
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def fuzzy(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def first_author(rec: dict) -> str:
    return (rec.get("authors", "") or "").split(";")[0].strip()


def one(provider, fixture_bodies):
    """Roda o provider contra as fixtures e devolve a lista de records."""
    with serve(fixture_bodies):
        return list(provider.search("ground truth query", max_results=25))


# =========================================================== OpenAlex (offline)
def test_openalex_vosviewer_fields_offline():
    recs = one(OpenAlexProvider(), load_fixture("openalex_vosviewer.json"))
    assert recs, "fixture VOSviewer não produziu records"
    r = recs[0]
    assert fuzzy(r["title"], "Software survey: VOSviewer, a computer program "
                             "for bibliometric mapping") >= 0.9
    assert r["year"] == 2009
    assert norm_doi(r["doi"]) == "10.1007/s11192-009-0146-3"
    assert first_author(r) == "Nees Jan van Eck"
    assert r["source"] == "Scientometrics"
    assert r["citations"] > 1000
    assert r["language"] == "en"


def test_openalex_vosviewer_in_top3_offline():
    recs = one(OpenAlexProvider(),
               load_fixture("openalex_vosviewer_titlesearch.json"))
    top3 = recs[:3]
    assert any(norm_doi(r["doi"]) == "10.1007/s11192-009-0146-3" for r in top3), \
        "artigo-âncora não apareceu no top 3 da busca por título (OpenAlex)"


def test_openalex_abstract_inverted_index_reconstruction_offline():
    """
    Reconstrução do abstract a partir do inverted index:
    não-vazio, começa com palavra plausível, e igual a uma reconstrução
    independente (sem palavras em posições trocadas / duplicadas).
    """
    import json
    raw = json.loads(load_fixture("openalex_vosviewer.json"))
    inv = raw["results"][0]["abstract_inverted_index"]
    # Reconstrução independente (referência)
    word_pos = [(p, w) for w, ps in inv.items() for p in ps]
    expected = " ".join(w for _, w in sorted(word_pos))

    recs = one(OpenAlexProvider(), load_fixture("openalex_vosviewer.json"))
    abstract = recs[0]["abstract"]

    assert abstract, "abstract reconstruído está vazio"
    assert abstract == expected, "reconstrução do provider difere da referência"
    assert abstract.split()[0][0].isupper(), "abstract não começa com palavra plausível"
    assert abstract.lower().startswith("we present vosviewer")


# =========================================================== Crossref (offline)
def test_crossref_shane_fields_offline():
    recs = one(CrossrefProvider(), load_fixture("crossref_shane_doifilter.json"))
    assert recs, "fixture Shane (DOI) não produziu records"
    r = recs[0]
    assert fuzzy(r["title"],
                 "The Promise of Entrepreneurship as a Field of Research") >= 0.9
    assert r["year"] == 2000
    assert norm_doi(r["doi"]) == "10.5465/amr.2000.2791611"
    assert first_author(r).lower().startswith("shane")
    assert r["source"] == "Academy of Management Review"
    assert r["citations"] > 1000
    assert r["language"] == "en"


@pytest.mark.xfail(
    reason="OBS-03: a busca bibliográfica do Crossref rankeia reimpressões/derivados "
           "(capítulos de livro 2007, 'discussion' 2017) acima do artigo seminal; "
           "o DOI canônico 10.5465/amr.2000.2791611 fica fora do top 3. "
           "Ver docs/BUGS-ENCONTRADOS-BUSCA.md",
    strict=True,
)
def test_crossref_shane_in_top3_offline_xfail():
    recs = one(CrossrefProvider(),
               load_fixture("crossref_shane_titlesearch.json"))
    top3 = recs[:3]
    assert any(norm_doi(r["doi"]) == "10.5465/amr.2000.2791611" for r in top3)


# ============================================================= PubMed (offline)
def test_pubmed_livak_fields_offline():
    recs = one(PubMedProvider(),
               [load_fixture("pubmed_livak_esearch.json"),
                load_fixture("pubmed_livak_efetch.json")])
    target = [r for r in recs if norm_doi(r["doi"]) == "10.1006/meth.2001.1262"]
    assert target, "artigo-âncora (Livak) não encontrado nos records do PubMed"
    r = target[0]
    assert fuzzy(r["title"], "Analysis of relative gene expression data using "
                             "real-time quantitative PCR and the 2(-Delta Delta "
                             "C(T)) Method") >= 0.9
    assert r["year"] == 2001
    assert first_author(r).lower().startswith("livak")
    assert "Methods" in r["source"]
    assert r["language"] == "eng"


def test_pubmed_livak_in_top3_offline():
    recs = one(PubMedProvider(),
               [load_fixture("pubmed_livak_esearch.json"),
                load_fixture("pubmed_livak_efetch.json")])
    top3 = recs[:3]
    assert any(norm_doi(r["doi"]) == "10.1006/meth.2001.1262" for r in top3), \
        "artigo-âncora não apareceu no top 3 (PubMed)"


# =================================================== schema entre providers ---
def test_schema_consistency_across_providers_offline():
    oa = one(OpenAlexProvider(), load_fixture("openalex_vosviewer.json"))[0]
    cr = one(CrossrefProvider(), load_fixture("crossref_shane_doifilter.json"))[0]
    pm = one(PubMedProvider(),
             [load_fixture("pubmed_livak_esearch.json"),
              load_fixture("pubmed_livak_efetch.json")])[0]

    # Os 3 providers emitem EXATAMENTE o mesmo conjunto de chaves.
    assert set(oa) == set(cr) == set(pm) == PROVIDER_KEYS

    # NOTA (OBS-05): 'language_source' NÃO é emitido pelos providers; é adicionado
    # depois, na camada de enriquecimento em main.py. O contrato de provider tem 13 chaves.
    for rec in (oa, cr, pm):
        assert "language_source" not in rec


def test_schema_types_no_none_in_string_fields_offline():
    oa = one(OpenAlexProvider(), load_fixture("openalex_vosviewer.json"))[0]
    cr = one(CrossrefProvider(), load_fixture("crossref_shane_doifilter.json"))[0]
    pm = one(PubMedProvider(),
             [load_fixture("pubmed_livak_esearch.json"),
              load_fixture("pubmed_livak_efetch.json")])[0]
    for rec in (oa, cr, pm):
        for f in STRING_FIELDS:
            assert isinstance(rec[f], str), f"{rec['origin']}.{f} deveria ser str"
        assert isinstance(rec["year"], int)
        assert isinstance(rec["citations"], int)
        assert isinstance(rec["is_oa"], bool)


# ============================= fallback de idioma (espelha main.py:1745-1767) ---
# main.py enriquece o DataFrame pós-busca: se 'language' estiver vazio, detecta via
# langdetect e marca language_source='detected'; senão, mantém e marca 'api'.
# A lógica vive dentro de uma thread de UI (não isolável sem refatorar produção,
# o que é proibido aqui), então replicamos EXATAMENTE o algoritmo para validar o
# comportamento. Ver recomendação de extração no relatório.
def _enrich_language_like_main(df):
    import pandas as pd
    if "language" not in df.columns:
        df["language"] = ""
    if "language_source" not in df.columns:
        df["language_source"] = "api"
    import langdetect
    langdetect.DetectorFactory.seed = 0  # determinismo
    for idx, row in df.iterrows():
        lang = row.get("language", "")
        if pd.isna(lang) or not str(lang).strip():
            text = f"{row.get('title', '')} {row.get('abstract', '')}".strip()
            if text:
                try:
                    detected = langdetect.detect(text)
                    df.at[idx, "language"] = detected
                    df.at[idx, "language_source"] = "detected"
                except Exception:
                    df.at[idx, "language"] = ""
                    df.at[idx, "language_source"] = "api"
        else:
            df.at[idx, "language_source"] = "api"
    return df


def test_language_fallback_detects_portuguese_offline():
    import pandas as pd
    df = pd.DataFrame([{
        "title": "Análise bibliométrica da produção científica brasileira",
        "abstract": "Este estudo apresenta uma revisão sistemática da literatura "
                    "sobre inovação e empreendedorismo nas universidades do Brasil.",
        "language": "",
    }])
    out = _enrich_language_like_main(df)
    assert out.at[0, "language"] == "pt"
    assert out.at[0, "language_source"] == "detected"


def test_language_source_api_when_present_offline():
    import pandas as pd
    df = pd.DataFrame([{
        "title": "Software survey: VOSviewer",
        "abstract": "We present VOSviewer, a computer program for bibliometric mapping.",
        "language": "en",
    }])
    out = _enrich_language_like_main(df)
    assert out.at[0, "language"] == "en"
    assert out.at[0, "language_source"] == "api"


# ================================================================ LIVE ---------
@pytest.mark.live
def test_openalex_vosviewer_fields_live():
    recs = list(OpenAlexProvider().search('TITLE("VOSviewer bibliometric mapping")',
                                           max_results=5))
    hit = [r for r in recs if norm_doi(r["doi"]) == "10.1007/s11192-009-0146-3"]
    assert hit, "VOSviewer não retornado ao vivo pelo OpenAlex"
    r = hit[0]
    assert r["year"] == 2009
    assert r["citations"] > 1000
    assert r["language"] == "en"
    assert first_author(r) == "Nees Jan van Eck"


@pytest.mark.live
def test_crossref_shane_fields_live():
    recs = list(CrossrefProvider().search(
        "The Promise of Entrepreneurship as a Field of Research", max_results=10))
    hit = [r for r in recs if norm_doi(r["doi"]) == "10.5465/amr.2000.2791611"]
    if not hit:
        pytest.xfail("OBS-03: Crossref não retorna o DOI canônico entre os 10 "
                     "primeiros da busca bibliográfica.")
    r = hit[0]
    assert r["year"] == 2000
    assert first_author(r).lower().startswith("shane")


@pytest.mark.live
def test_pubmed_livak_fields_live():
    recs = list(PubMedProvider().search(
        "Analysis of relative gene expression data using real-time quantitative "
        "PCR and the 2(-Delta Delta C(T)) Method", max_results=5))
    hit = [r for r in recs if norm_doi(r["doi"]) == "10.1006/meth.2001.1262"]
    assert hit, "Livak não retornado ao vivo pelo PubMed"
    r = hit[0]
    assert r["year"] == 2001
    assert first_author(r).lower().startswith("livak")
