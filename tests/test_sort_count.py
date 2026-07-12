"""Ordenação server-side + count barato (aviso de contagem)."""
import json
from unittest.mock import patch, MagicMock

from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider


def _resp(body: str):
    m = MagicMock()
    m.read.return_value = body.encode("utf-8")
    m.__enter__.return_value = m
    return m


def test_openalex_count_one_request():
    body = json.dumps({"meta": {"count": 212340}, "results": [{}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        n = OpenAlexProvider().count("innovation", {"year_start": 2020, "is_oa": True})
    assert n == 212340 and mock.call_count == 1
    url = mock.call_args[0][0].full_url
    assert "per_page=1" in url and "publication_year" in url and "is_oa" in url


def test_openalex_sort_citations_and_date():
    body = json.dumps({"meta": {"count": 1, "next_cursor": None},
                       "results": [{"title": "T", "publication_year": 2020}]})
    for key, expect in [("citations", "cited_by_count%3Adesc"), ("date", "publication_date%3Adesc")]:
        with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
            list(OpenAlexProvider().search("x", filters={"sort": key}, max_results=1))
        assert expect in mock.call_args_list[0][0][0].full_url, key


def test_openalex_sort_relevance_is_default_no_param():
    body = json.dumps({"meta": {"count": 1, "next_cursor": None},
                       "results": [{"title": "T", "publication_year": 2020}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        list(OpenAlexProvider().search("x", filters={"sort": "relevance"}, max_results=1))
    assert "sort=" not in mock.call_args_list[0][0][0].full_url


def test_crossref_sort_citations():
    body = json.dumps({"message": {"total-results": 1, "next-cursor": None,
                                    "items": [{"title": ["T"], "DOI": "10/x"}]}})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        list(CrossrefProvider().search("x", filters={"sort": "citations"}, max_results=1))
    url = mock.call_args_list[0][0][0].full_url
    assert "is-referenced-by-count" in url and "order=desc" in url


def test_pubmed_sort_date():
    es = json.dumps({"esearchresult": {"count": "1", "idlist": ["1"]}})
    ef = "PMID- 1\nTI  - T\nAU  - X\nDP  - 2020\n\n"
    with patch("urllib.request.urlopen", side_effect=[_resp(es), _resp(ef)]) as mock:
        list(PubMedProvider().search("x", filters={"sort": "date"}, max_results=1))
    assert "sort=pub_date" in mock.call_args_list[0][0][0].full_url


def test_sort_key_not_leaked_into_filter():
    """'sort' em filters não pode virar filtro (só parâmetro de ordenação)."""
    body = json.dumps({"meta": {"count": 1, "next_cursor": None},
                       "results": [{"title": "T", "publication_year": 2020}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        list(OpenAlexProvider().search("x", filters={"sort": "citations"}, max_results=1))
    url = mock.call_args_list[0][0][0].full_url
    assert "sort%3A" not in url and "filter=sort" not in url


def test_crossref_count_rows_zero():
    body = json.dumps({"message": {"total-results": 3450869}})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        n = CrossrefProvider().count("saude", {"year_start": 2020})
    assert n == 3450869
    url = mock.call_args[0][0].full_url
    assert "rows=0" in url and "from-pub-date" in url


def test_pubmed_count_retmax_zero():
    body = json.dumps({"esearchresult": {"count": "45231"}})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        n = PubMedProvider().count("saude")
    assert n == 45231
    assert "retmax=0" in mock.call_args[0][0].full_url


def test_browse_field_search_and_paging():
    body = json.dumps({"meta": {"count": 3402}, "results": [
        {"title": "Inovação X", "publication_year": 2023, "cited_by_count": 40,
         "authorships": [{"author": {"display_name": "Silva"}}], "doi": "10/x"}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        recs, total = OpenAlexProvider().browse(
            "", filters={"fields": [("title", "inovação"), ("author", "silva")], "sort": "citations"},
            page=2, per_page=25)
    assert total == 3402 and len(recs) == 1 and recs[0]["citations"] == 40
    url = mock.call_args[0][0].full_url
    assert "title.search" in url and "display_name.search" in url
    assert "page=2" in url and "cited_by_count" in url


def test_browse_per_page_capped_200():
    body = json.dumps({"meta": {"count": 1}, "results": []})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        OpenAlexProvider().browse("x", per_page=999)
    assert "per_page=200" in mock.call_args[0][0].full_url
