"""Passo 3 — backlog de projeto: ciclo completo, gravação na busca real
(provider mockado com fixture), recarga offline, migração e resiliência."""
import json
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

import core.project as cp

FIXTURES = Path(__file__).parent / "fixtures"


def _rec(i, year=2020):
    return {"title": f"Artigo {i}", "year": year, "authors": f"Autor {i}", "source": "Rev",
            "citations": 0, "abstract": "resumo", "doi": f"10.1/{i}", "language": "en",
            "keywords": "", "references": "", "origin": "OpenAlex", "is_oa": False, "oa_url": ""}


# ── ciclo: criar → 3 ações → fechar → reabrir → tudo intacto ────────────────
def test_full_cycle_create_act_close_reopen(tmp_path):
    slug = cp.create_project("Ciclo Completo", projects_dir=tmp_path)
    cp.append_backlog(slug, "search", {"provider": "openalex", "query": "a"}, tmp_path)
    cp.append_backlog(slug, "import", {"registros": 5, "total_corpus": 5}, tmp_path)
    cp.append_backlog(slug, "dedup", {"pares": 1, "aplicado": True}, tmp_path)

    df = pd.DataFrame([_rec(i) for i in range(5)])
    cp.save_blicsa_project(str(cp.project_dir(slug, tmp_path) / "project.blicsa"),
                           df=df, config={"name": "Ciclo Completo"}, positions=None,
                           G=None, cluster_labels=None)
    # "fechar" = nada em memória; reabrir do disco:
    data = cp.open_project(slug, tmp_path)
    assert len(data["df"]) == 5
    assert [e["action"] for e in data["backlog"]] == ["search", "import", "dedup"]
    assert data["config"]["name"] == "Ciclo Completo"


# ── busca com projeto ativo grava backlog + JSON bruto (fixture real) ───────
def _fixture_resp():
    fx = json.loads((FIXTURES / "openalex_page1.json").read_text())
    payload = json.loads(fx["body"])
    payload["meta"]["next_cursor"] = None
    m = MagicMock()
    m.read.return_value = json.dumps(payload).encode("utf-8")
    m.__enter__.return_value = m
    return m


def _make_app(monkeypatch, tmp_path):
    pytest.importorskip("customtkinter")
    import main as blicsa_main
    monkeypatch.setattr(cp, "PROJECTS_DIR", Path(tmp_path))
    monkeypatch.setattr(blicsa_main.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(blicsa_main.messagebox, "showwarning", lambda *a, **k: None)
    try:
        app = blicsa_main.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    app.withdraw()
    return app


def test_search_with_active_project_writes_backlog_and_raw(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path)
    try:
        slug = cp.create_project("Busca Gravada", projects_dir=tmp_path)
        app._set_active_project(slug)
        with patch("urllib.request.urlopen", return_value=_fixture_resp()):
            app._search_worker('"bibliometric analysis"', "openalex", 10, {}, threading.Event())
        app.update()

        bl = cp.load_backlog(slug, tmp_path)
        searches = [e for e in bl if e["action"] == "search"]
        assert len(searches) == 1, f"backlog: {bl}"
        d = searches[0]["detail"]
        assert d["provider"] == "openalex" and d["baixados"] == 10
        assert d["stop_reason"], "motivo de parada deve ser registrado"
        raw = cp.load_search_raw(slug, d["arquivo"], tmp_path)
        assert len(raw) == 10 and raw[0]["title"]
    finally:
        app.destroy()


# ── "Recarregar resultados" NÃO toca a rede ─────────────────────────────────
def test_reload_results_is_offline(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path)
    try:
        slug = cp.create_project("Offline", projects_dir=tmp_path)
        app._set_active_project(slug)
        recs = [_rec(i) for i in range(7)]
        rel = cp.save_search_raw(slug, recs, tmp_path)
        entry = cp.append_backlog(slug, "search", {"provider": "openalex", "query": "q",
                                                   "arquivo": rel}, tmp_path)

        def rede_morta(*a, **k):
            raise AssertionError("Recarregar tocou a rede!")
        monkeypatch.setattr(urllib.request, "urlopen", rede_morta)

        app._reload_search_entry(entry)
        app.update()
        assert len(app.search_feed_view.records) == 7
        assert "offline" in app.search_feed_view.trail_lbl.cget("text").lower()
    finally:
        app.destroy()


# ── migração: .blicsa solto vira pasta sem perda ────────────────────────────
def test_migration_wraps_loose_blicsa_without_loss(tmp_path):
    df = pd.DataFrame([_rec(1), _rec(2)])
    loose = tmp_path / "Pesquisa Antiga.blicsa"
    cp.save_blicsa_project(str(loose), df=df, config={"x": 1}, positions=None,
                           G=None, cluster_labels=None)
    migrated = cp.migrate_loose_projects(tmp_path)
    assert migrated == ["pesquisa-antiga"]
    assert not loose.exists()
    d = cp.project_dir("pesquisa-antiga", tmp_path)
    assert (d / "project.blicsa").exists()
    assert (d / "backlog.jsonl").exists() and (d / "searches").is_dir()
    data = cp.open_project("pesquisa-antiga", tmp_path)
    assert len(data["df"]) == 2 and data["config"]["x"] == 1


# ── resiliência: linha corrompida no meio não derruba o load ────────────────
def test_load_backlog_skips_corrupted_line(tmp_path):
    slug = cp.create_project("Resiliente", projects_dir=tmp_path)
    cp.append_backlog(slug, "search", {"q": 1}, tmp_path)
    cp.append_backlog(slug, "import", {"n": 2}, tmp_path)
    path = cp.project_dir(slug, tmp_path) / "backlog.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"ts": "2026-07-15T00:00:00", "action": "dedup", TRUNCADO NO MEIO\n')
    cp.append_backlog(slug, "export", {"formato": "csv"}, tmp_path)

    entries = cp.load_backlog(slug, tmp_path)
    assert [e["action"] for e in entries] == ["search", "import", "export"], \
        "linha corrompida deve ser pulada sem derrubar as demais"
