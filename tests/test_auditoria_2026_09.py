"""Regressões da auditoria de setembro de 2026 (docs/AUDITORIA-2026-09.md).

Cada teste falha no código anterior às correções e passa depois. Os que precisam da janela
Tk usam o mesmo padrão de `test_passo2.py` (Xvfb no CI).
"""

from __future__ import annotations

import json
import re
import subprocess
import shutil
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from core.parsers import BibliometricParser

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "docs" / "sample_dataset.csv"


# ── B1: CSV no schema do Blicsa ─────────────────────────────────────────────────

def test_b1_cabecalho_blicsa_e_reconhecido_e_scopus_nao():
    assert BibliometricParser.is_blicsa_csv_header("authors,title,year,source,keywords")
    assert BibliometricParser.is_blicsa_csv_header('﻿"authors","title","year"')
    assert not BibliometricParser.is_blicsa_csv_header("Authors,Title,Year,Source title")


def test_b1_sample_dataset_carrega_os_200_registros():
    df = BibliometricParser(SAMPLE).load_blicsa_csv()
    esperado = len(pd.read_csv(SAMPLE))
    assert len(df) == esperado >= 200
    assert df["year"].dtype.kind == "i" and (df["year"] > 1900).all()
    assert df["keywords"].str.len().gt(0).mean() > 0.9


def test_b1_csv_exportado_pelo_blicsa_reimporta_igual(tmp_path):
    original = BibliometricParser(SAMPLE).load_blicsa_csv()
    saida = tmp_path / "corpus.csv"
    # Mesma chamada de "Exportar corpus (CSV)" em main._export_df_csv
    original.to_csv(saida, index=False, encoding="utf-8-sig")
    de_novo = BibliometricParser(saida).load_blicsa_csv()
    assert len(de_novo) == len(original)
    assert list(de_novo["title"]) == list(original["title"])


# ── B5: PDF sem pdfplumber ──────────────────────────────────────────────────────

def test_b5_pdf_sem_pdfplumber_da_mensagem_e_nao_unboundlocal(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pdfplumber", None)   # simula extra não instalado
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(RuntimeError) as exc:
        BibliometricParser(pdf).load_pdf()
    assert "pdfplumber" in str(exc.value)


# ── B7: dados da galeria com caracteres especiais ───────────────────────────────

def test_b7_inline_preserva_json_com_aspas_e_barras():
    from core.sigma_exporter import inline_graph_data
    map_js = (REPO / "assets" / "map.js").read_text(encoding="utf-8")
    grafo = {"nodes": [{"key": 'termo "entre aspas"', "attributes": {"label": "a\\b\nc"}}],
             "edges": []}
    graph_json = json.dumps(grafo, ensure_ascii=False)
    saida = inline_graph_data(map_js, graph_json)
    assert 'fetch("graph.json")' not in saida
    m = re.search(r"data = (\{.*?\});\n", saida, flags=re.S)
    assert m and json.loads(m.group(1)) == grafo


@pytest.mark.skipif(shutil.which("node") is None, reason="node ausente")
def test_b7_map_js_com_dados_embutidos_e_javascript_valido(tmp_path):
    from core.sigma_exporter import inline_graph_data
    map_js = (REPO / "assets" / "map.js").read_text(encoding="utf-8")
    js = tmp_path / "m.js"
    js.write_text(inline_graph_data(map_js, json.dumps({"nodes": [{"key": 'x\\"y'}]})),
                  encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── Testes com a janela real ────────────────────────────────────────────────────

@pytest.fixture
def app(monkeypatch, tmp_path):
    import main as blicsa_main
    for nome in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(blicsa_main.messagebox, nome, lambda *a, **k: None)
    monkeypatch.setattr(blicsa_main.webbrowser, "open", lambda *a, **k: True)
    try:
        a = blicsa_main.BlicsaApp()
    except Exception as exc:  # sem display
        pytest.skip(f"Tk indisponível: {exc}")
    a._demo_no_browser = True
    a.withdraw()
    yield a
    try:
        a._on_app_close()
    except Exception:
        pass
    try:
        a.destroy()
    except Exception:
        pass


def _carregar_e_mapear(app):
    app._file_paths = [str(SAMPLE)]
    app._file_formats = [app._auto_detect_format(str(SAMPLE))]
    app._load_worker()
    app.update()
    app._min_occ_var.set(3)
    app._mapping_worker(None)
    app.update()


def test_b1_b2_deteccao_e_carga_pela_janela(app):
    assert app._auto_detect_format(str(SAMPLE)) == "blicsa"
    _carregar_e_mapear(app)
    assert app._dataframe is not None and len(app._dataframe) >= 200


def test_b2_arquivo_sem_registros_avisa_erro(app, tmp_path, monkeypatch):
    import main as blicsa_main
    erros = []
    monkeypatch.setattr(blicsa_main.messagebox, "showerror",
                        lambda t, m, *a, **k: erros.append(m))
    vazio = tmp_path / "vazio.csv"
    vazio.write_text("Authors,Title,Year\n", encoding="utf-8")
    app._file_paths, app._file_formats = [str(vazio)], ["scopus"]
    app._load_worker()
    app.update()
    assert erros and "Nenhum registro" in erros[0]
    assert app._dataframe is None


def test_b3_b4_b8_exportacoes_com_mapa_gerado(app, tmp_path, monkeypatch):
    import main as blicsa_main
    _carregar_e_mapear(app)
    assert app._graph is not None and app._graph.number_of_nodes() > 0          # B3

    saidas = iter(str(tmp_path / f"f{i}{ext}") for i, ext in
                  enumerate([".png", ".svg", ".pdf", ".html"]))
    monkeypatch.setattr(blicsa_main.filedialog, "asksaveasfilename",
                        lambda *a, **k: next(saidas))
    app._export_png(); app._export_svg(); app._export_pdf(); app._export_plotly_html()
    for i, ext in enumerate([".png", ".svg", ".pdf", ".html"]):                   # B8
        f = tmp_path / f"f{i}{ext}"
        assert f.exists() and f.stat().st_size > 10_000, f"{ext} não gerado"

    # B4: relatório de clusters da Exportação em Lote é texto legível
    monkeypatch.setattr(blicsa_main, "REPORTS_DIR", tmp_path / "reports")
    import customtkinter as ctk
    pilha, botao = [app], None
    while pilha:
        w = pilha.pop()
        if isinstance(w, ctk.CTkButton) and "Exportar Selecionados" in (w.cget("text") or ""):
            botao = w
        pilha.extend(w.winfo_children())
    botao._command()
    relatorio = next((tmp_path / "reports").glob("ai_report_*.txt")).read_text("utf-8")
    assert relatorio.startswith("Cluster ")
    assert list((tmp_path / "reports").glob("rede_*.gml"))


def test_b6_embeddings_nao_gera_mapa_de_ipc(app, monkeypatch):
    import main as blicsa_main
    erros = []
    monkeypatch.setattr(blicsa_main.messagebox, "showerror",
                        lambda t, m, *a, **k: erros.append(m))
    _carregar_e_mapear(app)
    app._generator = None
    app._map_type_var.set(blicsa_main.MAP_TYPES[6])
    app._mapping_worker(None)
    app.update()
    assert app._generator is None
    assert erros and "não está disponível" in erros[-1] and "IPC" not in erros[-1]


def test_b10_executavel_grava_fora_da_pasta_do_programa():
    import main as blicsa_main
    # Rodando do código-fonte: comportamento de sempre.
    assert blicsa_main.WORK_DIR == blicsa_main.OUTPUT_DIR
    assert blicsa_main.REPORTS_DIR == Path("reports")
    fonte = (REPO / "main.py").read_text(encoding="utf-8")
    assert 'Path.home() / "Blicsa" / "saidas"' in fonte
    # Nenhuma saída gerada volta a ser gravada direto na pasta do programa.
    assert not re.search(r'str\(OUTPUT_DIR / f?"blicsa_', fonte)
    assert '"reports/' not in fonte


# ── D3: stopwords extras valem para palavras-chave (resultado incorreto) ────────

def test_d3_stopwords_extras_removem_palavras_chave():
    from core.matrix_builders import _extract_term_lists
    df = pd.DataFrame({"keywords": ["Alfa; Beta; Gama", "alfa; gama"]})
    listas = _extract_term_lists(df, "keywords", {}, {"alfa", " BETA "})
    assert all("alfa" not in l and "beta" not in l for l in listas), listas
    assert sum("gama" in l for l in listas) == 2
    # Sem stopwords, nada muda (comportamento anterior preservado)
    assert _extract_term_lists(df, "keywords", {}, None)[0] == ["alfa", "beta", "gama"]


def test_d2_campo_numerico_aceita_formato_brasileiro_e_recusa_texto():
    import main as M
    assert M._numero_do_campo("10,5", "x") == 10.5
    assert M._numero_do_campo(" 50% ", "x") == 50
    assert M._numero_do_campo("", "x") is None
    with pytest.raises(M.CampoInvalido) as exc:
        M._numero_do_campo("abc", "Máx. de nós")
    assert "Máx. de nós" in str(exc.value) and "abc" in str(exc.value)


def test_d6_reclusterizar_importa_time():
    fonte = (REPO / "main.py").read_text(encoding="utf-8")
    i = fonte.index("    def _recluster_only")
    corpo = fonte[i:fonte.index("\n    def ", i + 10)]
    assert "time.time()" not in corpo or "import time" in corpo
