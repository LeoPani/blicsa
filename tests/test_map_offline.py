"""Passo 5 — mapa offline (local-first).

Garante que:
 (i)   prepare_serve_dir copia os vendors e que o HTML/JS servido não referencia
       nenhuma URL externa (varredura por "http", exceto comentários/licenças);
 (ii)  graph.json e i18n.json carregam o bloco de strings do idioma ativo;
 (iii) o repositório não voltou a depender de esm.sh / plotly CDN.
"""
import json
import os
import re
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from core import i18n
from core.local_server import prepare_serve_dir
from core.sigma_exporter import export_sigma_json

REPO_ROOT = Path(__file__).resolve().parent.parent

# Linhas que são só comentário/licença podem conter URLs (ex.: vendors).
_COMMENT_PREFIXES = ("//", "/*", "*", "<!--", "#")


def _external_urls(text: str) -> list[str]:
    urls = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_COMMENT_PREFIXES):
            continue
        urls += re.findall(r'https?://[^\s"\'\)]+', line)
    return urls


@pytest.fixture
def serve_dir():
    tmp = Path(tempfile.mkdtemp())
    yield prepare_serve_dir(str(REPO_ROOT), tmp)


# ── (i) vendors copiados + zero URL externa no que é servido ────────────────
def test_prepare_serve_dir_copies_vendors(serve_dir):
    vendor_dir = serve_dir / "assets" / "vendor"
    assert vendor_dir.is_dir(), "vendor/ não foi copiado para o diretório servido"
    vendored = list(vendor_dir.glob("*.js"))
    assert vendored, "nenhum vendor .js copiado (graphology/sigma faltando)"


def test_served_html_and_js_have_no_external_urls(serve_dir):
    for name in ("map_template.html", "map_template_empty.html", "map.js"):
        text = (serve_dir / "assets" / name).read_text(encoding="utf-8")
        urls = _external_urls(text)
        assert not urls, f"{name} referencia URL externa (viola local-first): {urls}"


def test_map_template_loads_local_vendor_and_map(serve_dir):
    html = (serve_dir / "assets" / "map_template.html").read_text(encoding="utf-8")
    assert 'src="vendor/blicsa-vendor.min.js"' in html
    assert 'src="map.js"' in html
    assert "esm.sh" not in html
    assert "fonts.googleapis.com" not in html


# ── (ii) i18n do mapa no idioma ativo (graph.json + i18n.json) ──────────────
def _tiny_graph():
    G = nx.Graph()
    G.add_node("a", group=0, occurrence=5, size=10, label="a")
    G.add_node("b", group=1, occurrence=3, size=8, label="b")
    G.add_edge("a", "b", weight=2)
    return G


def test_i18n_json_carries_active_language(tmp_path):
    original = i18n.get_lang()
    try:
        i18n.load_locales("pt_BR")
        block = i18n.get_map_i18n()
        # todas as chaves que o JS usa devem estar presentes
        for key in i18n.MAP_I18N_KEYS:
            assert key in block and block[key], f"chave do mapa ausente: {key}"
        assert block["map_empty"] == "Nenhum dado para exibir"

        i18n_path = tmp_path / "i18n.json"
        i18n_path.write_text(json.dumps(block, ensure_ascii=False), encoding="utf-8")
        reloaded = json.loads(i18n_path.read_text(encoding="utf-8"))
        assert reloaded["map_title"] == "Mapeamento"

        # troca de idioma reflete no bloco (fallback en para o estado vazio)
        i18n.load_locales("en")
        assert i18n.get_map_i18n()["map_empty"] == "No data to display"
    finally:
        i18n.load_locales(original)


def test_graph_json_is_valid_sigma_payload(tmp_path):
    path = tmp_path / "graph.json"
    export_sigma_json(_tiny_graph(), {"a": (0.0, 0.0), "b": (1.0, 1.0)}, str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["nodes"] and data["edges"]
    assert {n["key"] for n in data["nodes"]} == {"a", "b"}
    # nenhum texto PT hardcoded no payload do grafo
    assert "http" not in path.read_text(encoding="utf-8")


# ── (iii) auditoria: sem esm.sh / plotly CDN no código-fonte ────────────────
def test_no_external_cdn_in_sources():
    targets = [
        REPO_ROOT / "assets" / "map.js",
        REPO_ROOT / "assets" / "map_template.html",
        REPO_ROOT / "assets" / "map_template_empty.html",
        REPO_ROOT / "core" / "visualizer.py",
        REPO_ROOT / "main.py",
    ]
    forbidden = ("esm.sh", 'include_plotlyjs="cdn"', "cdn.plot.ly", "fonts.googleapis.com")
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.name} ainda contém '{needle}'"
