"""
BUG-A: paginação não pode morrer em silêncio.
- Erro transitório numa página é recuperado pelo retry com backoff do fetch_url.
- Erro persistente (esgota retries) NÃO é silencioso: a busca retorna parcial e o
  provider expõe stop_error/stop_reason ao chamador.
Mocka urllib.request.urlopen (nível real) para exercitar o retry do fetch_url.
"""
import json
import urllib.error
from unittest.mock import patch, MagicMock

from core.sources import OpenAlexProvider


def _page(start, count, next_cursor):
    return json.dumps({
        "meta": {"count": 500, "next_cursor": next_cursor},
        "results": [
            {"title": f"T{i}", "doi": f"10.1/{i}", "publication_year": 2020,
             "authorships": [{"author": {"display_name": f"A{i}"}}]}
            for i in range(start, start + count)
        ],
    }).encode("utf-8")


def _resp(body):
    m = MagicMock()
    m.read.return_value = body
    m.__enter__.return_value = m
    return m


def test_transient_error_recovered_by_retry():
    """Página 3 dá 429 uma vez; o retry do fetch_url recupera → 5 páginas completas."""
    pages = [_page(i * 100, 100, f"c{i+1}" if i < 4 else None) for i in range(5)]
    err429 = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    # ordem de urlopen: p1, p2, [429 na p3], p3, p4, p5
    side = [_resp(pages[0]), _resp(pages[1]), err429, _resp(pages[2]), _resp(pages[3]), _resp(pages[4])]

    with patch("urllib.request.urlopen", side_effect=side), patch("time.sleep"):
        prov = OpenAlexProvider()
        recs = list(prov.search("x", max_results=500))

    assert len(recs) == 500, f"esperava 500 (recuperou o erro transitório), obteve {len(recs)}"
    assert prov.stop_error is False
    assert "cursor encerrado" in prov.stop_reason


def test_persistent_error_is_not_silent():
    """Página 3 dá 429 além dos retries → busca retorna parcial (200) E sinaliza o erro."""
    pages = [_page(0, 100, "c1"), _page(100, 100, "c2")]
    err429 = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    # p1, p2, depois 3x 429 na p3 (esgota os 3 retries do fetch_url)
    side = [_resp(pages[0]), _resp(pages[1]), err429, err429, err429]

    with patch("urllib.request.urlopen", side_effect=side), patch("time.sleep"):
        prov = OpenAlexProvider()
        recs = list(prov.search("x", max_results=500))

    assert len(recs) == 200, f"esperava 200 parciais, obteve {len(recs)}"
    assert prov.stop_error is True, "erro persistente deveria ser sinalizado (não silencioso)"
    assert "erro de rede na página 3" in prov.stop_reason
