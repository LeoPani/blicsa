"""Tipo de publicação preservado até as estatísticas do corpus."""

import pandas as pd

from core.document_types import document_type_counts, normalize_document_type
from core.parsers import BibliometricParser
from core.sources.crossref import CrossrefProvider
from core.sources.openalex import OpenAlexProvider
from core.sources.pubmed import PubMedProvider


def test_tipos_de_periodico_e_congresso_sao_distintos():
    assert normalize_document_type("journal-article") == "article"
    assert normalize_document_type("proceedings-article") == "conference-paper"
    assert normalize_document_type("Article; Proceedings Paper") == "conference-paper"
    assert normalize_document_type("Review") == "review"

    df = pd.DataFrame({"document_type": ["article", "review", "conference-paper", ""]})
    assert document_type_counts(df) == {
        "article": 1, "conference-paper": 1, "review": 1, "unknown": 1,
    }
    assert document_type_counts(pd.DataFrame({"title": ["Projeto antigo"]})) == {"unknown": 1}


def test_providers_preservam_tipo_informado_pela_base():
    oa = OpenAlexProvider(api_key="")._normalize_work({
        "title": "Conference work", "type": "conference-paper"})
    cr = CrossrefProvider()._normalize_item({
        "title": ["Conference work"], "type": "proceedings-article"})
    pm = PubMedProvider()._record_from_medline({
        "TI": "Review work", "PT": "Review"})
    assert oa["document_type"] == "conference-paper"
    assert cr["document_type"] == "conference-paper"
    assert pm["document_type"] == "review"


def test_importacao_scopus_e_wos_preserva_tipo(tmp_path):
    csv_path = tmp_path / "scopus.csv"
    pd.DataFrame({
        "Title": ["Work A", "Work B"], "Year": [2023, 2024],
        "Document Type": ["Article", "Conference Paper"],
    }).to_csv(csv_path, index=False)
    scopus = BibliometricParser(str(csv_path)).load_scopus_csv()
    assert scopus["document_type"].tolist() == ["article", "conference-paper"]

    wos_path = tmp_path / "wos.txt"
    wos_path.write_text(
        "FN Clarivate\nVR 1.0\nPT J\nTI Work C\nPY 2024\nTC 0\n"
        "DT Article; Proceedings Paper\nER\nEF\n",
        encoding="utf-8",
    )
    wos = BibliometricParser(str(wos_path)).load_wos_txt()
    assert wos["document_type"].tolist() == ["conference-paper"]
