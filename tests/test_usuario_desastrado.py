"""Cenários de "usuário que faz tudo errado" (auditoria 2026-09, parte 2).

Cada teste reproduz algo que um usuário real faz — arquivo errado, clique fora de ordem,
campo preenchido com texto, filtro que zera tudo — e verifica três coisas:

1. **Não trava nem quebra em silêncio.** Nenhuma exceção escapa para o Tk (que só imprime no
   terminal: o usuário clica e nada acontece) nem para uma thread de trabalho.
2. **Explica em português.** Se falhar, aparece uma caixa com mensagem para gente, sem jargão
   de Python ("invalid literal", "KeyError", "NoneType"...).
3. **Resultado certo.** Onde há número (contagens, arestas, deduplicação), confere o número.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "docs" / "sample_dataset.csv"

JARGAO = re.compile(
    r"Traceback|invalid literal|KeyError|IndexError|NoneType|AttributeError|"
    r"object has no attribute|could not convert|Errno|not subscriptable|unexpected keyword|"
    r"ParserError|UnicodeDecodeError|codec can't|No columns to parse|Error tokenizing",
    re.I)


# ── Infraestrutura ──────────────────────────────────────────────────────────────

class Registro:
    """Tudo o que o usuário veria ou que escaparia em silêncio."""

    def __init__(self):
        self.caixas: list[tuple[str, str, str]] = []   # (tipo, título, mensagem)
        self.excecoes: list[str] = []                   # exceções que escaparam

    def erros(self):
        return [c for c in self.caixas if c[0] == "showerror"]

    def avisos(self):
        return [c for c in self.caixas if c[0] in ("showerror", "showwarning", "showinfo")]

    def texto(self):
        return " | ".join(f"{a}: {b}" for _, a, b in self.caixas)


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    import main as M
    reg = Registro()

    def caixa(tipo):
        def f(title="", message="", *a, **k):
            reg.caixas.append((tipo, str(title), str(message)))
            return True if tipo.startswith("ask") else "ok"
        return f

    for nome in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
        monkeypatch.setattr(M.messagebox, nome, caixa(nome))
    monkeypatch.setattr(M.webbrowser, "open", lambda *a, **k: True)
    monkeypatch.setattr(M, "REPORTS_DIR", tmp_path / "reports", raising=False)

    antigo_hook = threading.excepthook
    threading.excepthook = lambda args: reg.excecoes.append(
        f"thread: {args.exc_type.__name__}: {args.exc_value}")
    try:
        app = M.BlicsaApp()
    except Exception as exc:
        threading.excepthook = antigo_hook
        pytest.skip(f"Tk indisponível: {exc}")
    app.report_callback_exception = lambda et, ev, tb: reg.excecoes.append(
        f"callback Tk: {et.__name__}: {ev}")
    app._demo_no_browser = True
    app.withdraw()
    yield M, app, reg, tmp_path
    threading.excepthook = antigo_hook
    for fn in (app._on_app_close, app.destroy):
        try:
            fn()
        except Exception:
            pass


def bombear(app, seg=0.3):
    fim = time.time() + seg
    while time.time() < fim:
        app.update()
        time.sleep(0.01)


def esperar_workers(app, seg=60):
    fim = time.time() + seg
    while time.time() < fim:
        app.update()
        if not any(t.is_alive() and "worker" in getattr(getattr(t, "_target", None),
                                                        "__name__", "")
                   for t in threading.enumerate()):
            break
        time.sleep(0.05)
    bombear(app, 0.3)


def importar(app, *arquivos, formato=None):
    """Mesmo caminho do botão "Carregar e Combinar"."""
    app._file_paths = [str(a) for a in arquivos]
    app._file_formats = [formato or app._auto_detect_format(str(a)) for a in arquivos]
    try:
        app._load_worker()
    except Exception as exc:  # o worker nunca deveria deixar escapar
        raise AssertionError(f"_load_worker deixou escapar {type(exc).__name__}: {exc}")
    bombear(app)


def gerar_mapa(app):
    try:
        app._mapping_worker(None)
    except Exception as exc:
        raise AssertionError(f"_mapping_worker deixou escapar {type(exc).__name__}: {exc}")
    bombear(app, 0.5)


def chamar(app, reg, metodo, *a):
    """Chama um botão como o Tk chamaria: exceção vira registro, não falha do teste."""
    try:
        getattr(app, metodo)(*a)
    except Exception as exc:
        reg.excecoes.append(f"{metodo}: {type(exc).__name__}: {exc}")
    esperar_workers(app)


def sem_quebra(reg):
    assert not reg.excecoes, "escapou sem mensagem ao usuário: " + "; ".join(reg.excecoes)
    for tipo, titulo, msg in reg.caixas:
        assert not JARGAO.search(titulo + " " + msg), f"mensagem com jargão técnico: {msg!r}"


def csv_blicsa(tmp_path, linhas, nome="corpus.csv"):
    df = pd.DataFrame(linhas)
    p = tmp_path / nome
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


def registro(i, kws, ano=2020, autores="Silva, A.; Souza, B.", doi=None, titulo=None,
             refs=""):
    return {"authors": autores, "title": titulo or f"Artigo {i}", "year": ano,
            "source": "Revista X", "keywords": "; ".join(kws), "abstract": "resumo",
            "citations": i, "doi": doi or f"10.1000/x{i}", "references": refs,
            "origin": "teste"}


# ── 1. Importação: arquivos ruins ───────────────────────────────────────────────

@pytest.mark.parametrize("conteudo,nome", [
    (b"", "vazio.csv"),
    (b"Authors,Title,Year\n", "so_cabecalho.csv"),
    (bytes(range(256)) * 40, "lixo_binario.csv"),
    (b"{nao e json", "quebrado.json"),
    (b"@article{x, title={sem fechar", "quebrado.bib"),
    (b"TY  - JOUR\n", "incompleto.ris"),
    (b"\n\n\n", "linhas_vazias.txt"),
])
def test_arquivo_ruim_da_mensagem_clara_e_nao_muda_o_corpus(ambiente, conteudo, nome):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    n_antes = len(app._dataframe)
    reg.caixas.clear()
    ruim = tmp / nome
    ruim.write_bytes(conteudo)
    importar(app, ruim)
    sem_quebra(reg)
    assert reg.erros(), f"{nome}: nenhuma mensagem de erro; o usuário não sabe o que houve"
    assert app._dataframe is not None and len(app._dataframe) == n_antes, \
        "arquivo ruim apagou o corpus que já estava carregado"


def test_formato_errado_escolhido_no_seletor(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE, formato="bibtex")          # CSV lido como BibTeX
    sem_quebra(reg)
    assert reg.erros()


def test_arquivo_apagado_entre_adicionar_e_carregar(ambiente):
    M, app, reg, tmp = ambiente
    p = csv_blicsa(tmp, [registro(1, ["a", "b"])])
    app._file_paths, app._file_formats = [str(p)], ["blicsa"]
    p.unlink()
    app._load_worker()
    bombear(app)
    sem_quebra(reg)
    assert reg.erros()


def test_scopus_salvo_pelo_excel_brasileiro(ambiente):
    """Excel em pt-BR grava CSV com ';' e em Windows-1252 (acentos)."""
    M, app, reg, tmp = ambiente
    p = tmp / "scopus_excel.csv"
    linhas = ["Authors;Title;Year;Source title;Author Keywords;Cited by;DOI",
              "Conceição, M.;Gestão da inovação;2021;Revista Ação;inovação; gestão;3;10.1/a",
              "Araújo, J.;Educação empreendedora;2022;Revista Ação;empreendedorismo;1;10.1/b"]
    p.write_bytes("\n".join(linhas).encode("cp1252"))
    importar(app, p)
    sem_quebra(reg)
    if not reg.erros():
        assert len(app._dataframe) == 2
        assert "Conceição, M." in set(app._dataframe["authors"])


def test_mesmo_arquivo_duas_vezes_nao_duplica(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE, SAMPLE)
    sem_quebra(reg)
    assert len(app._dataframe) == len(pd.read_csv(SAMPLE))


def test_dois_arquivos_com_mesmo_doi_em_caixa_diferente(ambiente, monkeypatch):
    """Juntar arquivos mantém quase-duplicatas para revisão (decisão de projeto); o botão
    Deduplicar tem de achá-las mesmo com DOI em caixa/prefixo diferentes."""
    M, app, reg, tmp = ambiente
    a = csv_blicsa(tmp, [registro(1, ["x"], doi="10.1000/ABC")], "a.csv")
    b = csv_blicsa(tmp, [registro(2, ["y"], doi="https://doi.org/10.1000/abc")], "b.csv")
    importar(app, a, b)
    capturado = {}
    monkeypatch.setattr(M, "DedupPreviewDialog",
                        lambda parent, df, dupes, aplicar, **k: capturado.update(
                            dupes=dupes, aplicar=aplicar))
    chamar(app, reg, "_run_dedup")
    sem_quebra(reg)
    assert len(capturado.get("dupes", [])) == 1, "Deduplicar não achou o DOI repetido"
    capturado["aplicar"](capturado["dupes"])
    bombear(app)
    assert len(app._dataframe) == 1


def test_acentos_aspas_e_emoji_nos_termos(ambiente):
    M, app, reg, tmp = ambiente
    kws = ['inovação', 'gestão "ágil"', 'C:\\dados', 'emoji 🚀', "d'água", 'a;b']
    linhas = [registro(i, kws[: 3 + i % 3]) for i in range(12)]
    importar(app, csv_blicsa(tmp, linhas))
    app._min_occ_var.set(1)
    gerar_mapa(app)
    sem_quebra(reg)
    assert app._graph is not None
    assert "inovação" in app._graph.nodes


def test_anos_bagunçados(ambiente):
    M, app, reg, tmp = ambiente
    linhas = [registro(i, ["a", "b"], ano=ano) for i, ano in
              enumerate(["2020", "", "s.d.", "2021a", "0", "-5", "3000", "2019.0"])]
    importar(app, csv_blicsa(tmp, linhas))
    sem_quebra(reg)
    anos = set(app._dataframe["year"])
    assert all(isinstance(a, (int,)) or hasattr(a, "item") for a in anos)


# ── 2. Mapa: parâmetros absurdos e ordem errada ─────────────────────────────────

def test_gerar_mapa_sem_dados(ambiente):
    M, app, reg, tmp = ambiente
    chamar(app, reg, "_run_mapping")
    sem_quebra(reg)
    assert reg.avisos(), "clicou Gerar Mapa sem dados e nada aconteceu"


@pytest.mark.parametrize("campo,valor", [
    ("_max_nodes_var", "abc"),
    ("_max_nodes_var", "-10"),
    ("_max_nodes_var", "10.5"),
    ("_max_pct_var", "50%"),
    ("_max_pct_var", "abc"),
    ("_max_pct_var", "500"),
    ("_year_min_var", "dois mil"),
    ("_extra_sw_var", ",,,;;;"),
])
def test_campos_com_texto_invalido(ambiente, campo, valor):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    reg.caixas.clear()
    getattr(app, campo).set(valor)
    gerar_mapa(app)
    sem_quebra(reg)
    assert app._graph is not None or reg.avisos(), "falhou sem dizer nada"


def test_ano_inicial_maior_que_final(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    reg.caixas.clear()
    app._year_min_var.set("2030")
    app._year_max_var.set("2000")
    gerar_mapa(app)
    sem_quebra(reg)
    assert reg.avisos(), "período vazio gerou mapa ou falhou em silêncio"


def test_ocorrencia_minima_altissima(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    reg.caixas.clear()
    app._min_occ_var.set(100000)
    gerar_mapa(app)
    sem_quebra(reg)
    assert reg.avisos()


def test_stopwords_que_removem_tudo(ambiente):
    M, app, reg, tmp = ambiente
    linhas = [registro(i, ["alfa", "beta"]) for i in range(5)]
    importar(app, csv_blicsa(tmp, linhas))
    app._min_occ_var.set(1)
    app._extra_sw_var.set("alfa, beta")
    gerar_mapa(app)
    sem_quebra(reg)
    assert reg.avisos()


def test_corpus_de_um_registro(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, csv_blicsa(tmp, [registro(1, ["solo", "unico"])]))
    app._min_occ_var.set(1)
    gerar_mapa(app)
    sem_quebra(reg)


def test_corpus_sem_nenhuma_palavra_chave(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, csv_blicsa(tmp, [registro(i, []) for i in range(5)]))
    app._min_occ_var.set(1)
    gerar_mapa(app)
    sem_quebra(reg)
    assert reg.avisos()


@pytest.mark.parametrize("indice", range(7))
def test_todos_os_tipos_de_mapa_com_corpus_pobre(ambiente, indice):
    """Sem referências, sem IPC, autores únicos: cada tipo tem de explicar, não quebrar."""
    M, app, reg, tmp = ambiente
    linhas = [registro(i, ["a", "b"], autores=f"Autor {i}") for i in range(6)]
    importar(app, csv_blicsa(tmp, linhas))
    app._min_occ_var.set(1)
    app._map_type_var.set(M.MAP_TYPES[indice])
    gerar_mapa(app)
    sem_quebra(reg)
    assert app._graph is not None or reg.avisos()


def test_clique_duplo_em_gerar_mapa(ambiente):
    """Segundo clique enquanto o primeiro mapa ainda calcula tem de ser ignorado."""
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    assert app._mapping_lock.acquire(blocking=False)   # simula um cálculo em andamento
    try:
        app._graph = None
        app._mapping_worker(None)                        # o "segundo clique"
        bombear(app)
        assert app._graph is None, "segundo cálculo rodou em paralelo ao primeiro"
    finally:
        app._mapping_lock.release()
    gerar_mapa(app)                                      # depois de liberar, funciona
    sem_quebra(reg)
    assert app._graph is not None
    assert set(app._graph.nodes) == set(app._positions)


def test_trocar_de_corpus_nao_deixa_mapa_velho(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    assert app._graph is not None
    importar(app, csv_blicsa(tmp, [registro(i, ["novo", "corpus"]) for i in range(4)]))
    reg.caixas.clear()
    chamar(app, reg, "_export_png")
    sem_quebra(reg)
    assert reg.avisos(), "exportou o mapa do corpus ANTERIOR sem avisar"


def test_reclusterizar_depois_de_gerar(ambiente):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    app._demo_no_browser = False            # como o usuário real: abre o navegador
    app._cluster_res_var.set(2.0)
    chamar(app, reg, "_recluster_only")
    sem_quebra(reg)


# ── 3. Exportação: lugares ruins ────────────────────────────────────────────────

EXPORTS = ["_export_nodes_csv", "_export_edges_csv", "_export_df_csv", "_export_clusters_txt",
           "_export_excel", "_export_gml", "_export_gexf", "_export_pajek", "_export_json",
           "_export_vosviewer", "_export_png", "_export_plotly_html"]


@pytest.mark.parametrize("metodo", EXPORTS)
def test_exportar_sem_mapa_avisa(ambiente, metodo):
    M, app, reg, tmp = ambiente
    chamar(app, reg, metodo)
    sem_quebra(reg)
    assert reg.avisos(), f"{metodo} sem dados: nada aconteceu"


@pytest.mark.parametrize("metodo", EXPORTS)
def test_exportar_para_pasta_que_nao_existe(ambiente, monkeypatch, metodo):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    reg.caixas.clear()
    ext = {"_export_png": ".png", "_export_excel": ".xlsx", "_export_gml": ".gml",
           "_export_gexf": ".gexf", "_export_pajek": ".net", "_export_json": ".json",
           "_export_vosviewer": ".txt", "_export_clusters_txt": ".txt",
           "_export_plotly_html": ".html"}.get(metodo, ".csv")
    destino = str(tmp / "nao_existe" / "sub" / f"saida{ext}")
    monkeypatch.setattr(M.filedialog, "asksaveasfilename", lambda *a, **k: destino)
    chamar(app, reg, metodo)
    sem_quebra(reg)
    assert reg.erros(), f"{metodo}: falhou ao gravar e o usuário não foi avisado"


@pytest.mark.parametrize("metodo", ["_export_nodes_csv", "_export_df_csv", "_export_png"])
def test_exportar_com_nome_acentuado_e_espacos(ambiente, monkeypatch, metodo):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    ext = ".png" if metodo == "_export_png" else ".csv"
    destino = tmp / "Minha Pasta Ação" / f"relatório final (v2){ext}"
    destino.parent.mkdir()
    monkeypatch.setattr(M.filedialog, "asksaveasfilename", lambda *a, **k: str(destino))
    chamar(app, reg, metodo)
    sem_quebra(reg)
    assert destino.exists() and destino.stat().st_size > 0


def test_exportar_por_cima_de_arquivo_aberto_no_excel(ambiente, monkeypatch):
    """No Windows, o Excel trava o arquivo aberto e a gravação dá PermissionError."""
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    reg.caixas.clear()
    monkeypatch.setattr(M.filedialog, "asksaveasfilename", lambda *a, **k: str(tmp / "x.xlsx"))

    def travado(*a, **k):
        raise PermissionError(13, "Permission denied", str(tmp / "x.xlsx"))
    monkeypatch.setattr(type(app._generator), "export_excel", travado)
    chamar(app, reg, "_export_excel")
    sem_quebra(reg)
    assert reg.erros() and "Excel" in reg.erros()[0][2]


def test_cancelar_a_janela_de_salvar(ambiente, monkeypatch):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    reg.caixas.clear()
    monkeypatch.setattr(M.filedialog, "asksaveasfilename", lambda *a, **k: "")
    for metodo in EXPORTS:
        chamar(app, reg, metodo)
    sem_quebra(reg)
    assert not reg.erros(), "cancelar a janela de salvar não é erro"


# ── 4. Projeto: arquivos que não são projeto ────────────────────────────────────

@pytest.mark.parametrize("conteudo", [b"", b"texto qualquer", b"PK\x03\x04quebrado"])
def test_abrir_projeto_falso(ambiente, monkeypatch, conteudo):
    M, app, reg, tmp = ambiente
    falso = tmp / "falso.blicsa"
    falso.write_bytes(conteudo)
    monkeypatch.setattr(M.filedialog, "askopenfilename", lambda *a, **k: str(falso))
    chamar(app, reg, "_load_project_gui")
    sem_quebra(reg)
    assert reg.erros()


def test_projeto_salvo_e_reaberto_da_o_mesmo_mapa(ambiente, monkeypatch):
    M, app, reg, tmp = ambiente
    importar(app, SAMPLE)
    gerar_mapa(app)
    nos, arestas = set(app._graph.nodes), set(map(frozenset, app._graph.edges))
    destino = tmp / "proj.blicsa"
    monkeypatch.setattr(M.filedialog, "asksaveasfilename", lambda *a, **k: str(destino))
    monkeypatch.setattr(M.filedialog, "askopenfilename", lambda *a, **k: str(destino))
    chamar(app, reg, "_save_project_gui")
    app._dataframe = app._generator = app._graph = None
    chamar(app, reg, "_load_project_gui")
    sem_quebra(reg)
    assert set(app._graph.nodes) == nos
    assert set(map(frozenset, app._graph.edges)) == arestas


# ── 5. Resultado correto: contagens conferidas à mão ────────────────────────────

def test_coocorrencia_confere_com_contagem_manual(ambiente):
    """3 artigos:  {a,b,c}, {a,b}, {a,d}.
    Ocorrências: a=3, b=2, c=1, d=1.  Coocorrências: a–b=2, a–c=1, b–c=1, a–d=1."""
    M, app, reg, tmp = ambiente
    linhas = [registro(1, ["a", "b", "c"]), registro(2, ["a", "b"]), registro(3, ["a", "d"])]
    importar(app, csv_blicsa(tmp, linhas))
    app._min_occ_var.set(1)
    app._prune_isolated_var.set(False)
    gerar_mapa(app)
    sem_quebra(reg)
    G = app._graph
    occ = {n: G.nodes[n].get("occurrence") for n in G.nodes}
    assert occ == {"a": 3, "b": 2, "c": 1, "d": 1}, occ
    peso = {frozenset(e): d.get("weight_raw", d.get("weight")) for *e, d in G.edges(data=True)}
    assert peso[frozenset("ab")] == 2
    assert peso[frozenset("ac")] == 1 and peso[frozenset("bc")] == 1 and peso[frozenset("ad")] == 1
    assert frozenset("cd") not in peso and frozenset("bd") not in peso


def test_palavra_chave_com_caixa_diferente_e_um_termo_so(ambiente):
    M, app, reg, tmp = ambiente
    linhas = [registro(1, ["Bibliometrics", "x"]), registro(2, ["bibliometrics", "x"]),
              registro(3, ["BIBLIOMETRICS ", "x"])]
    importar(app, csv_blicsa(tmp, linhas))
    app._min_occ_var.set(1)
    gerar_mapa(app)
    sem_quebra(reg)
    nos = [n for n in app._graph.nodes if n.strip().lower() == "bibliometrics"]
    assert len(nos) == 1, f"o mesmo termo virou vários nós: {nos}"
    assert app._graph.nodes[nos[0]]["occurrence"] == 3


def test_filtro_de_periodo_realmente_filtra(ambiente):
    M, app, reg, tmp = ambiente
    linhas = ([registro(i, ["velho", "comum"], ano=2000) for i in range(4)] +
              [registro(10 + i, ["novo", "comum"], ano=2020) for i in range(4)])
    importar(app, csv_blicsa(tmp, linhas))
    app._min_occ_var.set(1)
    app._year_min_var.set("2015")
    app._year_max_var.set("2025")
    gerar_mapa(app)
    sem_quebra(reg)
    assert "velho" not in app._graph.nodes
    assert app._graph.nodes["comum"]["occurrence"] == 4
