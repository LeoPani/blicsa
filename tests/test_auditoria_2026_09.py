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


# ── T1/T2: travadas de interface (medidas com scripts/medir_travadas.py) ───────

def test_t1_estatisticas_so_calculam_com_a_aba_aberta(app, monkeypatch):
    import main as M
    import threading
    import time
    chamadas = []
    original = M.BlicsaApp._compor_estatisticas
    monkeypatch.setattr(M.BlicsaApp, "_compor_estatisticas",
                        lambda self, *a, **k: chamadas.append(1) or original(self, *a, **k))
    app._switch_tab("corpus")
    _carregar_e_mapear(app)
    app._update_stats_tab()
    assert chamadas == [], "abrir projeto/importar não pode recalcular estatísticas fora da aba"
    app._switch_tab("stats")
    fim = time.time() + 30
    while any(t.name == "stats_worker" and t.is_alive() for t in threading.enumerate()) \
            and time.time() < fim:
        time.sleep(0.05)
    assert chamadas, "ao abrir a aba Estatísticas o cálculo tem de acontecer"


def test_t2_revisar_termos_nao_congela_a_janela(app, monkeypatch):
    import time
    import core.term_extraction as TE
    _carregar_e_mapear(app)
    original = TE.extract_terms

    def lento(*a, **k):
        time.sleep(1.5)
        return original(*a, **k)
    monkeypatch.setattr(TE, "extract_terms", lento)
    inicio = time.perf_counter()
    app._open_term_review()
    assert time.perf_counter() - inicio < 0.3, "a extração de termos voltou a rodar na tela"


# ── M1–M3: fluxo de geração de mapas (matriz de 350 combinações nos projetos reais) ──

def _df_refs(n=30, refs_por=12, universo=40, seed=1):
    import random
    rnd = random.Random(seed)
    linhas = []
    for i in range(n):
        refs = "; ".join(f"https://openalex.org/W{rnd.randint(1, universo)}"
                         for _ in range(refs_por))
        linhas.append({"authors": f"Autor {i % 7}; Autor {(i + 3) % 11}", "title": f"T{i}",
                       "year": 2020, "keywords": "a; b", "references": refs, "doi": f"10.1/{i}",
                       "citations": i, "source": "Revista X", "abstract": ""})
    return pd.DataFrame(linhas)


def test_m2_viabilidade_explica_antes_de_clicar():
    from core.map_controls import viabilidade_tipo
    df = _df_refs()
    assert viabilidade_tipo(0, df) is None
    assert viabilidade_tipo(2, df) is None                      # cocitação: tem referências
    assert viabilidade_tipo(4, df) == "map.inviavel_citdir_openalex"
    assert viabilidade_tipo(5, df) == "map.inviavel_sem_ipc"
    assert viabilidade_tipo(6, df) == "map.inviavel_embeddings"
    sem_refs = df.assign(references="")
    assert viabilidade_tipo(3, sem_refs) == "map.inviavel_sem_referencias"
    com_ids = df.assign(openalex_id=[f"https://openalex.org/W{i}" for i in range(len(df))])
    assert viabilidade_tipo(4, com_ids) is None


def test_m1_limite_de_nos_vale_para_cocitacao_e_acoplamento():
    from core.matrix_builders import NetworkGenerator
    df = _df_refs(n=60, refs_por=15, universo=300)
    G = NetworkGenerator(df).build_cocitation_network(min_cocitations=1, max_nodes=25)
    assert 0 < G.number_of_nodes() <= 25
    G = NetworkGenerator(df).build_bibliographic_coupling(min_shared_refs=1, max_nodes=10)
    assert 0 < G.number_of_nodes() <= 10
    # sem limite, o comportamento antigo continua igual
    assert NetworkGenerator(df).build_cocitation_network(min_cocitations=1).number_of_nodes() > 25


def test_m1_rotulo_de_referencia_openalex_curto():
    from core.matrix_builders import _rotulo_ref
    assert _rotulo_ref("https://openalex.org/W1496449353") == "W1496449353"
    assert _rotulo_ref("SMITH J, 2001, RES POLICY, V30, P1") == "SMITH J, 2001, RES POLICY, V30, P1"[:40]


def test_m3_limiar_alto_demais_e_ajustado_com_aviso(app, monkeypatch):
    import main as M
    infos = []
    monkeypatch.setattr(M.messagebox, "showinfo", lambda t, m, *a, **k: infos.append(m))
    avisos = []
    monkeypatch.setattr(M.messagebox, "showwarning", lambda t, m, *a, **k: avisos.append(m))
    _carregar_e_mapear(app)
    app._map_type_var.set(M.MAP_TYPES[1])                        # coautoria
    app._min_occ_var.set(50)                                      # ninguém tem 50 artigos
    app._graph = None
    app._mapping_worker(None)
    app.update()
    assert app._graph is not None and app._graph.number_of_nodes() > 0, avisos
    assert infos and "50" in infos[-1], "ajustou o limiar sem avisar"
    assert app._min_occ_var.get() < 50, "o controle não mostra o limiar realmente usado"


def test_m2_tipo_inviavel_avisa_antes_e_nao_calcula(app, monkeypatch):
    import main as M
    avisos = []
    monkeypatch.setattr(M.messagebox, "showwarning", lambda t, m, *a, **k: avisos.append(m))
    _carregar_e_mapear(app)
    app._map_type_var.set(M.MAP_TYPES[5])                        # IPC sem patentes
    app._atualizar_tipo_de_mapa()
    assert "patentes" in app._aviso_tipo_lbl.cget("text")
    app._graph = None
    app._run_mapping()
    assert avisos and "patentes" in avisos[-1]
    assert app._graph is None
    app._map_type_var.set(M.MAP_TYPES[0])
    app._atualizar_tipo_de_mapa()
    assert app._aviso_tipo_lbl.cget("text") == ""
    assert "termo" in app._lbl_freq.cget("text")


def _df_openalex_que_se_cita():
    """Corpus do OpenAlex em que os artigos citam uns aos outros pelo ID (sem DOI nas refs)."""
    linhas = []
    for i in range(12):
        refs = [f"https://openalex.org/W{9000 + j}" for j in range(i)]      # cita os anteriores
        refs += [f"https://openalex.org/W{i * 100 + k}" for k in range(3)]  # e obras de fora
        linhas.append({"authors": f"Silva{i}, A.", "title": f"T{i}", "year": 2010 + i,
                       "keywords": "a; b", "references": "; ".join(refs), "doi": "",
                       "openalex_id": f"https://openalex.org/W{9000 + i}",
                       "citations": i, "source": "R", "abstract": ""})
    return pd.DataFrame(linhas)


def test_m4_citacao_direta_casa_pelo_id_do_openalex():
    from core.matrix_builders import NetworkGenerator
    from core.map_controls import viabilidade_tipo
    df = _df_openalex_que_se_cita()
    assert viabilidade_tipo(4, df) is None
    G = NetworkGenerator(df).build_direct_citation_network(min_citations=1)
    assert G.number_of_nodes() == 12 and G.number_of_edges() == 66     # 12·11/2 pares


def test_m4_viabilidade_conta_so_quem_tem_referencia():
    """Metade do corpus sem referência não pode esconder que as referências são do OpenAlex."""
    from core.map_controls import viabilidade_tipo
    df = _df_refs(n=10)
    vazios = _df_refs(n=12).assign(references="")
    assert viabilidade_tipo(4, pd.concat([df, vazios])) == "map.inviavel_citdir_openalex"


def test_m4_mapa_vazio_explica_a_causa_certa(app, monkeypatch):
    import main as M
    avisos = []
    monkeypatch.setattr(M.messagebox, "showwarning", lambda t, m, *a, **k: avisos.append(m))
    monkeypatch.setattr(M.messagebox, "showinfo", lambda *a, **k: None)
    df = _df_openalex_que_se_cita().assign(openalex_id="https://openalex.org/W7777777")   # ninguém do corpus é citado
    app._dataframe = df
    app._map_type_var.set(M.MAP_TYPES[4])
    app._min_occ_var.set(5)
    app._graph = None
    app._mapping_worker(None)
    app.update()
    assert app._graph is None
    assert avisos and "cita outro artigo" in avisos[-1], avisos
    assert "Reduza a frequência" not in avisos[-1]


def test_selo_do_corpus_mostra_quantos_registros(app):
    """O selo da barra lateral dizia "Nenhum corpus" para sempre, mesmo com corpus aberto."""
    app._dataframe = _df_refs(n=30)
    app._refresh_candidate_counts()
    app.update()
    assert app._corpus_badge.cget("text").startswith("30 ")


def test_importacao_nao_mexe_em_widget_fora_da_thread_da_interface(app, monkeypatch):
    """_refresh_candidate_counts é chamada pela thread de importação: não pode configurar
    widget ali (Tk não é thread-safe — travamento aleatório no Windows/Mac)."""
    import threading
    fora = []
    original = app._atualizar_tipo_de_mapa
    def espiao():
        if threading.current_thread() is not threading.main_thread():
            fora.append(1)
        return original()
    monkeypatch.setattr(app, "_atualizar_tipo_de_mapa", espiao)
    app._dataframe = _df_refs(n=10)
    # Com o mainloop rodando, como no app de verdade: a importação acontece durante ele.
    app.after(20, lambda: threading.Thread(target=app._refresh_candidate_counts).start())
    app.after(600, app.quit)
    app.mainloop()
    assert not fora
    assert app._corpus_badge.cget("text").startswith("10 ")


def test_tipos_de_mapa_agrupados_por_pergunta(app):
    import main as M
    valores = app._tipo_combo.cget("values")
    assert valores[0] == "SOBRE O QUE SE ESCREVE?"
    assert [v for v in valores if v in M.MAP_TYPES] == M.MAP_TYPES   # mesmos 7, mesma ordem
    app._map_type_var.set(M.MAP_TYPES[2])
    app._ao_escolher_tipo_de_mapa(M.MAP_TYPES[2])
    assert "citadas juntas" in app._desc_tipo_lbl.cget("text")
    # clicar num título de grupo não troca o tipo
    app._map_type_var.set("QUEM ESCREVE COM QUEM?")
    app._ao_escolher_tipo_de_mapa("QUEM ESCREVE COM QUEM?")
    assert app._map_type_var.get() == M.MAP_TYPES[2]
    # projeto aberto muda o tipo por fora do seletor: o título também volta a ele
    app._map_type_var.set(M.MAP_TYPES[1])
    app._map_type_var.set("EM QUE O CAMPO SE APOIA?")
    app._ao_escolher_tipo_de_mapa("EM QUE O CAMPO SE APOIA?")
    assert app._map_type_var.get() == M.MAP_TYPES[1]


def test_lixo_de_janela_fechada_nao_e_coletado_na_thread_de_trabalho(app):
    """Tk abortava o programa ("Tcl_AsyncDelete") quando a coleta automática do Python apagava
    variáveis/imagens de uma janela fechada dentro de uma thread de trabalho."""
    import gc
    import sys
    import threading
    import tkinter as tk
    import main as M
    fora = []
    original = sys.unraisablehook
    sys.unraisablehook = lambda u: fora.append(str(u.exc_value))
    try:
        gc.disable()                                  # só a coleta que provocarmos conta
        top = tk.Toplevel(app)
        for _ in range(20):
            v = tk.StringVar(top, value="x")
            v.ciclo = v                               # ciclo: só a coleta de lixo o desfaz
        top.destroy()
        del top, v
        th = M._ThreadDaTela(target=gc.collect, daemon=True)   # coleta DENTRO da thread
        th.start()
        th.join(5)
    finally:
        gc.enable()
        sys.unraisablehook = original
    assert not [e for e in fora if "main thread is not in main loop" in e], fora


def test_fonte_e_variavel_apagadas_em_outra_thread_nao_travam(app, monkeypatch):
    """Uma página da busca em paralelo ficou parada em `tkinter/font.py __del__`: a coleta de
    lixo rodou na thread da busca e apagou uma fonte do Tk ali. Nenhum finalizador pode
    chamar o Tk fora da thread da tela."""
    import gc
    import threading
    import tkinter as tk
    import tkinter.font as tkfont
    chamadas_fora = []
    original_call = app.tk.call

    class Espiao:
        def __getattr__(self, nome):
            return getattr(app.tk, nome)

        def call(self, *a):
            if threading.current_thread() is not threading.main_thread():
                chamadas_fora.append(a[:2])
            return original_call(*a)
    espiao = Espiao()
    objs = [tkfont.Font(app, family="Helvetica", size=11), tk.StringVar(app, value="x"),
            tk.PhotoImage(master=app, width=2, height=2)]
    for o in objs:
        o.tk = espiao                       # Variable/Image usam self._tk/self.tk
        if hasattr(o, "_tk"):
            o._tk = espiao
        o.ciclo = o
    objs[0]._call = espiao.call             # Font usa self._call
    del o
    gc.disable()
    try:
        caixa = {"objs": objs}
        del objs

        def apagar():
            caixa.clear()
            gc.collect()
        th = threading.Thread(target=apagar, daemon=True)
        th.start()
        th.join(10)
        assert not th.is_alive(), "o finalizador do Tk travou a thread de trabalho"
    finally:
        gc.enable()
    assert not chamadas_fora, f"finalizador chamou o Tk fora da thread da tela: {chamadas_fora}"


def test_galeria_mostra_titulo_legivel(app, tmp_path, monkeypatch):
    import main as M
    monkeypatch.setattr(M, "REPORTS_DIR", tmp_path)
    (tmp_path / "blicsa_mapa_1700000000.html").write_text("<html><head></head></html>", encoding="utf-8")
    novo = tmp_path / "blicsa_mapa_1800000000.html"
    novo.write_text("<html><head>\n" + M._meta_titulo('Coautoria · Projeto "A&B"') + "</head></html>",
                    encoding="utf-8")
    assert M.titulo_da_galeria(novo) == 'Coautoria · Projeto "A&B"'
    assert M.titulo_da_galeria(tmp_path / "blicsa_mapa_1700000000.html") == "Mapa 1700000000"
