"""Metadados usados nos mapas e na identificação de obras do OpenAlex."""

import json

from core.sources.openalex import OpenAlexProvider
from core.sources.crossref import CrossrefProvider


def test_keywords_especificas_precedem_conceitos_legados():
    work = {
        "id": "https://openalex.org/W123",
        "title": "Patent classification with BERT",
        "keywords": [{"display_name": "Patent classification"}, {"display_name": "BERT"}],
        "concepts": [{"display_name": "Computer science"}],
    }

    record = OpenAlexProvider(api_key="")._normalize_work(work)

    assert record["keywords"] == "Patent classification; BERT"
    assert record["openalex_id"] == "https://openalex.org/W123"


def test_conceitos_antigos_ainda_sao_lidos_sem_keywords():
    record = OpenAlexProvider(api_key="")._normalize_work({
        "title": "Older record",
        "concepts": [{"display_name": "Bibliometrics"}],
    })

    assert record["keywords"] == "Bibliometrics"
    assert record["openalex_id"] == ""


def test_crossref_confere_doi_exato_sem_busca_textual(monkeypatch):
    provider = CrossrefProvider()
    urls = []

    def fake_fetch(url, **kwargs):
        urls.append(url)
        return json.dumps({"message": {
            "title": ["Qualitative Spatial Question Answering"],
            "issued": {"date-parts": [[2022]]}, "DOI": "10.4230/lipics.cosit.2022.18",
        }})

    monkeypatch.setattr(provider, "fetch_url", fake_fetch)
    record = provider.get_by_doi("https://doi.org/10.4230/lipics.cosit.2022.18")

    assert "query" not in urls[0]
    assert "/works/10.4230%2Flipics.cosit.2022.18" in urls[0]
    assert record["title"] == "Qualitative Spatial Question Answering"
