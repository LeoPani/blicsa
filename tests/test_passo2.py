"""Passo 2 — testes dos contratos novos:

(i)   browse() e search() produzem o MESMO registro normalizado para o mesmo work;
(ii)  a trilha de contagem é renderizada na UI do feed;
(iii) find_duplicates NÃO roda no caminho busca/importação e RODA na ação Deduplicar;
(iv)  o HTTP server local não serve nada fora do diretório dedicado.
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.sources import OpenAlexProvider

FIXTURES = Path(__file__).parent / "fixtures"


def _resp(body: str):
    m = MagicMock()
    m.read.return_value = body.encode("utf-8")
    m.__enter__.return_value = m
    return m


def _rec(i, year=2020):
    return {"title": f"Artigo {i}", "year": year, "authors": f"Autor {i}", "source": "Rev",
            "citations": 0, "abstract": "resumo", "doi": f"10.1/{i}", "language": "en",
            "keywords": "", "references": "", "origin": "OpenAlex", "is_oa": False, "oa_url": ""}


# ── (i) browse == search para o mesmo work ──────────────────────────────────
def test_browse_and_search_normalize_identically():
    fx = json.loads((FIXTURES / "openalex_page1.json").read_text())
    payload = json.loads(fx["body"])
    payload["meta"]["next_cursor"] = None  # 1 página só
    body = json.dumps(payload)

    with patch("urllib.request.urlopen", return_value=_resp(body)):
        search_recs = list(OpenAlexProvider().search("bibliometric analysis", max_results=10))
    with patch("urllib.request.urlopen", return_value=_resp(body)):
        browse_recs, total = OpenAlexProvider().browse("bibliometric analysis", per_page=10)

    assert search_recs, "fixture deveria render registros"
    assert total == payload["meta"]["count"]
    for a, b in zip(search_recs, browse_recs):
        assert a == b, "search() e browse() devem normalizar o work identicamente"


# ── (ii) trilha de contagem renderizada na UI ───────────────────────────────
def _make_view():
    ctk = pytest.importorskip("customtkinter")
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    root.withdraw()
    from ui.search_feed import SearchFeedView
    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None)
    fv.pack()
    return root, fv


def test_count_trail_rendered_in_feed_ui():
    root, fv = _make_view()
    try:
        trail = "Encontrados 327499 · baixados 200 de 200 (limite) · atingiu limite"
        fv.load_results([_rec(i) for i in range(5)], trail)
        root.update()
        assert trail in fv.trail_lbl.cget("text"), "trilha deve estar VISÍVEL na UI"
    finally:
        root.destroy()


# ── (iii) dedup só na ação explícita do Corpus ──────────────────────────────
def test_find_duplicates_only_on_explicit_action(monkeypatch):
    ctk = pytest.importorskip("customtkinter")
    import main as blicsa_main

    calls = []
    def spy(df, **kw):
        calls.append(len(df))
        return []
    monkeypatch.setattr(blicsa_main, "find_duplicates", spy)
    monkeypatch.setattr(blicsa_main.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(blicsa_main.messagebox, "showwarning", lambda *a, **k: None)

    def fake_search(self, query, filters=None, max_results=100, progress_cb=None, cancel_event=None):
        self.stop_reason, self.stop_error, self.pages_fetched = "atingiu limite", False, 1
        recs = [_rec(i) for i in range(6)]
        if progress_cb:
            progress_cb(len(recs), len(recs))
        yield from recs
    monkeypatch.setattr("core.sources.openalex.OpenAlexProvider.search", fake_search)

    try:
        app = blicsa_main.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    try:
        app.withdraw()
        import threading
        # busca completa (worker síncrono no main thread + flush dos after())
        app._search_worker("x", "openalex", 100, {}, threading.Event())
        app.update()
        assert calls == [], "busca NÃO pode chamar find_duplicates"

        # importa o MESMO conjunto 2x — permitido, sem dedup
        recs = [_rec(i) for i in range(6)]
        app._feed_cbs["import"](recs, False)
        app.update()
        app._feed_cbs["import"](recs, False)
        app.update()
        assert calls == [], "importação NÃO pode chamar find_duplicates"
        assert len(app._dataframe) == 12, "importar 2x deve manter os 12 (dedup é sob demanda)"

        # ação explícita do Corpus
        app._run_dedup()
        app.update()
        assert calls == [12], "Deduplicar deve chamar find_duplicates exatamente uma vez"
    finally:
        app.destroy()


# ── (iv) HTTP server confinado ao diretório dedicado ────────────────────────
def _http_code(port, path):
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def test_local_server_serves_only_dedicated_dir(tmp_path):
    from core.local_server import prepare_serve_dir, start_server
    repo_root = Path(__file__).parent.parent
    serve_dir = prepare_serve_dir(repo_root, tmp_path / ".serve")
    port, httpd = start_server(serve_dir)
    try:
        assert _http_code(port, "/assets/map_template.html") == 200
        # nada do repo (código, settings) pode vazar
        assert _http_code(port, "/main.py") == 404
        assert _http_code(port, "/.blicsa_settings.json") == 404
        assert _http_code(port, "/core/parsers.py") == 404
        assert _http_code(port, "/../main.py") == 404  # traversal
    finally:
        httpd.shutdown()
        httpd.server_close()
