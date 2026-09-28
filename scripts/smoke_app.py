"""Smoke test de ponta a ponta do app real (sem rede), para auditoria.

Dirige a `BlicsaApp` de verdade sob Xvfb: importa o dataset de exemplo, gera cada tipo de
mapa, abre as análises, roda todas as exportações e salva/reabre o projeto. Toda caixa de
erro ou aviso é registrada e aparece no relatório final — nada falha em silêncio.

Uso:
    xvfb-run -a python scripts/smoke_app.py [saida_dir]

Sai com código 1 se algum passo levantou exceção ou mostrou caixa de erro.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="blicsa_smoke_"))
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("GROQ_API_KEY", "")

import webbrowser  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

eventos: list[tuple[str, str, str]] = []   # (passo, tipo, texto)
passo_atual = ["init"]


def _mb(kind):
    def f(title="", message="", *a, **k):
        eventos.append((passo_atual[0], kind, f"{title}: {message}"))
        return True if kind.startswith("ask") else "ok"
    return f


for _k in ("showerror", "showwarning", "showinfo", "askyesno", "askokcancel", "askyesnocancel"):
    setattr(messagebox, _k, _mb(_k))

_contador = [0]


def _save_as(*a, defaultextension="", **k):
    _contador[0] += 1
    return str(OUT / f"export_{_contador[0]:02d}{defaultextension}")


filedialog.asksaveasfilename = _save_as
filedialog.askdirectory = lambda *a, **k: str(OUT)
webbrowser.open = lambda *a, **k: True

import main as M  # noqa: E402

for nome in ("messagebox", "filedialog"):
    if hasattr(M, nome):
        setattr(getattr(M, nome), "showerror", messagebox.showerror)
M.messagebox = messagebox
M.filedialog = filedialog
M.webbrowser = webbrowser

app = M.BlicsaApp()
app._demo_no_browser = True
app.update()

resultados: list[tuple[str, str, str]] = []

# Mensagens de erro que são a resposta CORRETA para o dataset de exemplo (sem patentes).
ESPERADOS = ("Coluna de códigos IPC não encontrada",
             "ainda não está disponível nesta versão")


def roteiro():


    def pump(seg=0.6):
        fim = time.time() + seg
        while time.time() < fim:
            app.update()
            time.sleep(0.02)


    def esperar_threads(seg=90):
        """Espera os workers em thread (`*_worker`) terminarem, bombeando a fila do Tk."""
        fim = time.time() + seg
        while time.time() < fim:
            app.update()
            if not any(t.is_alive() and "worker" in getattr(getattr(t, "_target", None),
                                                            "__name__", "")
                       for t in threading.enumerate()):
                break
            time.sleep(0.05)
        pump(0.5)

    def _hook(args):
        eventos.append((passo_atual[0], "showerror",
                        f"exceção em thread: {args.exc_type.__name__}: {args.exc_value}"))
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = _hook


    def passo(nome, fn):
        passo_atual[0] = nome
        antes = len(eventos)
        try:
            fn()
            pump(0.4)
            erros = [e for e in eventos[antes:] if e[1] == "showerror"
                     and not any(m in e[2] for m in ESPERADOS)]
            resultados.append((nome, "ERRO-UI" if erros else "ok",
                               "; ".join(e[2] for e in eventos[antes:])[:300]))
        except Exception as exc:
            resultados.append((nome, "EXCEÇÃO", f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()


    # 1. Importar o dataset de exemplo pelo worker real
    def importar():
        app._file_paths = [str(RAIZ / "docs" / "sample_dataset.csv")]
        app._file_formats = [app._auto_detect_format(app._file_paths[0])]
        app._load_worker()
        pump(1)
        assert app._dataframe is not None and len(app._dataframe) > 0, "dataset não carregou"


    passo("importar sample_dataset.csv", importar)
    passo("aba estatísticas", lambda: app._update_stats_tab())

    # 2. Cada tipo de mapa
    app._min_occ_var.set(2)
    for i, tipo in enumerate(M.MAP_TYPES):
        def gerar(tipo=tipo):
            app._generator = None
            app._map_type_var.set(tipo)
            app._mapping_worker(None)
            pump(1)
        passo(f"mapa: {tipo}", gerar)

    # Volta para coocorrência e deixa um mapa válido para as exportações
    app._map_type_var.set(M.MAP_TYPES[0])
    passo("mapa final: coocorrência", lambda: (app._mapping_worker(None), pump(1)))
    passo("ranking", lambda: app._show_ranking() if hasattr(app, "_show_ranking") else None)

    for nome in ("_open_plotly", "_open_sankey", "_open_timeline", "_open_bursts",
                 "_open_thematic_map", "_open_historiograph", "_open_trends", "_show_wordcloud",
                 "_auto_label_clusters", "_open_term_review", "_refresh_corpus_tab",
                 "_update_stats_tab", "_refresh_hist_tab"):
        passo(nome, lambda n=nome: (getattr(app, n)(), esperar_threads(60)))

    for nome in ("_export_nodes_csv", "_export_edges_csv", "_export_df_csv", "_export_clusters_txt",
                 "_export_plotly_html", "_export_pyvis_html", "_export_png", "_export_svg",
                 "_export_pdf", "_export_excel", "_export_gml", "_export_gexf", "_export_pajek",
                 "_export_json", "_export_vosviewer"):
        passo(nome, lambda n=nome: getattr(app, n)())


    # Botões internos: "Salvar na Galeria" e "Exportar Selecionados" (closures nos builders)
    def achar_botao(texto):
        import customtkinter as ctk
        pilha = [app]
        while pilha:
            w = pilha.pop()
            if isinstance(w, ctk.CTkButton) and texto in (w.cget("text") or ""):
                return w
            pilha.extend(w.winfo_children())
        return None


    cwd_antes = os.getcwd()
    os.chdir(OUT)
    for rotulo in ("Salvar na Galeria", "Exportar Selecionados"):
        def clicar(r=rotulo):
            b = achar_botao(r)
            assert b is not None, f"botão '{r}' não encontrado"
            b._command()
        passo(f"botão: {rotulo}", clicar)
    passo("galeria", lambda: app._refresh_gallery())
    os.chdir(cwd_antes)

    passo("deduplicação", lambda: app._run_dedup())


    # Projeto avulso: salvar em arquivo e reabrir pelo "Carregar projeto"
    def salvar_reabrir_avulso():
        app._save_project_gui()
        pump(1)
        salvo = OUT / f"export_{_contador[0]:02d}.blicsa"
        assert salvo.exists(), f"projeto não foi gravado em {salvo}"
        n_antes = len(app._dataframe)
        app._dataframe, app._generator = None, None
        filedialog.askopenfilename = lambda *a, **k: str(salvo)
        app._load_project_gui()
        pump(1)
        assert app._dataframe is not None and len(app._dataframe) == n_antes, "corpus não voltou"
        assert app._generator is not None and app._generator.G.number_of_nodes() > 0, "mapa não voltou"


    passo("projeto avulso: salvar e reabrir", salvar_reabrir_avulso)


    # Projeto em pasta (fluxo "Novo projeto"): criar, importar, gerar, salvar, reabrir
    def projeto_em_pasta():
        from core.project import create_project
        slug = create_project("Smoke Auditoria")
        app._set_active_project(slug)
        importar()
        app._mapping_worker(None)
        pump(1)
        app._save_project_gui()
        pump(1)
        n = len(app._dataframe)
        app._dataframe, app._generator = None, None
        app._open_project_slug(slug)
        pump(1)
        assert app._dataframe is not None and len(app._dataframe) == n, "corpus do projeto não voltou"
        assert app._generator is not None, "mapa do projeto não voltou"
        app._mapping_worker(None)
        pump(1)


    passo("projeto em pasta: criar → importar → mapa → salvar → reabrir → mapa", projeto_em_pasta)

    # Relatório
    largura = max(len(r[0]) for r in resultados)
    print("\n" + "=" * 90)
    falhas = 0
    for nome, status, det in resultados:
        if status != "ok":
            falhas += 1
        print(f"{status:9} {nome:{largura}}  {det}")
    print("=" * 90)
    print(f"{len(resultados)} passos · {falhas} com problema · saídas em {OUT}")
    arquivos = sorted(p.name for p in OUT.rglob("*") if p.is_file())
    print(f"{len(arquivos)} arquivos gerados")
    try:
        app._on_app_close()
    except Exception:
        pass
    os._exit(1 if falhas else 0)


# Roda dentro do mainloop, como no app real: workers em thread leem variáveis Tk.
app.after(300, roteiro)
app.mainloop()
