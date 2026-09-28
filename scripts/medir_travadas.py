"""Mede quanto tempo a janela do Blicsa fica congelada em cada ação comum.

Um "batimento" agendado no Tk a cada 20 ms marca o relógio. Enquanto o código roda na thread
da interface, o batimento não acontece; o maior intervalo entre dois batimentos durante uma
ação é o tempo em que a janela ficou sem responder a clique, rolagem ou redesenho.

Referência de percepção: até ~100 ms passa despercebido; 200–500 ms é "travadinha";
acima de 1 s o usuário acha que o programa travou.

Uso:
    xvfb-run -a python scripts/medir_travadas.py [n_registros_extra] [saida.json]
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
N_GRANDE = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
SAIDA = sys.argv[2] if len(sys.argv) > 2 else None
TMP = Path(tempfile.mkdtemp(prefix="blicsa_travadas_"))

import pandas as pd  # noqa: E402
import webbrowser  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

for _k in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, _k, lambda *a, **k: "ok")
for _k in ("askyesno", "askokcancel"):
    setattr(messagebox, _k, lambda *a, **k: True)
webbrowser.open = lambda *a, **k: True
_n = [0]


def _salvar(*a, defaultextension="", **k):
    _n[0] += 1
    return str(TMP / f"saida_{_n[0]:02d}{defaultextension}")


filedialog.asksaveasfilename = _salvar

import main as M  # noqa: E402

M.webbrowser = webbrowser


def corpus_grande(n: int) -> Path:
    """Corpus sintético de n registros a partir do exemplo real (termos reais recombinados)."""
    base = pd.read_csv(RAIZ / "docs" / "sample_dataset.csv")
    termos = sorted({k.strip() for ks in base["keywords"].dropna() for k in str(ks).split(";")
                     if k.strip()})
    rnd = random.Random(42)
    linhas = []
    for i in range(n):
        r = base.iloc[i % len(base)].to_dict()
        r["title"] = f"{r['title']} ({i})"
        r["doi"] = f"10.9999/sint.{i}"
        r["keywords"] = "; ".join(rnd.sample(termos, k=min(len(termos), rnd.randint(4, 9))))
        r["year"] = rnd.randint(1995, 2025)
        linhas.append(r)
    p = TMP / f"corpus_{n}.csv"
    pd.DataFrame(linhas).to_csv(p, index=False, encoding="utf-8-sig")
    return p


app = M.BlicsaApp()
app._demo_no_browser = True
app.geometry("1380x880+0+0")
app.deiconify()

batidas: list[float] = []


def bater():
    batidas.append(time.perf_counter())
    app.after(20, bater)


def fechar_janelas_extras():
    for w in list(app.winfo_children()):
        if w.winfo_class() in ("Toplevel", "CTkToplevel") and w.winfo_exists():
            if w is getattr(app, "_static_canvas_host", None):
                continue
            try:
                w.destroy()
            except Exception:
                pass


def workers_vivos():
    return [t for t in threading.enumerate()
            if t.is_alive() and "worker" in getattr(getattr(t, "_target", None), "__name__", "")]


def importar(caminho):
    def f():
        app._file_paths = [str(caminho)]
        app._file_formats = [app._auto_detect_format(str(caminho))]
        app._load_data()
    return f


def aba(nome):
    return lambda: app._switch_tab(nome)


def gerar_mapa():
    app._min_occ_var.set(3)
    threading.Thread(target=app._mapping_worker, args=(None,), daemon=True).start()


def chamar(nome):
    return lambda: getattr(app, nome)()


def botao(texto):
    def f():
        import customtkinter as ctk
        pilha = [app]
        while pilha:
            w = pilha.pop()
            if isinstance(w, ctk.CTkButton) and texto in (w.cget("text") or ""):
                return w._command()
            pilha.extend(w.winfo_children())
        raise RuntimeError(f"botão {texto!r} não encontrado")
    return f


ABAS = ["import", "corpus", "stats", "analises", "hist", "relatorio", "galeria",
        "export", "home", "projects", "credenciais"]


def roteiro(rotulo, caminho):
    passos = [(f"{rotulo}: importar", importar(caminho))]
    passos += [(f"{rotulo}: aba {a}", aba(a)) for a in ABAS]
    passos += [
        (f"{rotulo}: Gerar Mapa (abre revisão de termos)", chamar("_run_mapping")),
        (f"{rotulo}: fechar revisão", fechar_janelas_extras),
        (f"{rotulo}: gerar mapa (cálculo)", gerar_mapa),
        (f"{rotulo}: aba corpus (com mapa)", aba("corpus")),
        (f"{rotulo}: aba estatisticas (com mapa)", aba("stats")),
        (f"{rotulo}: aba analises (com mapa)", aba("analises")),
        (f"{rotulo}: Revisar termos", chamar("_open_term_review")),
        (f"{rotulo}: fechar revisão", fechar_janelas_extras),
        (f"{rotulo}: Rankings", chamar("_show_ranking")),
        (f"{rotulo}: reclusterizar", chamar("_recluster_only")),
        (f"{rotulo}: Abrir Plotly", chamar("_open_plotly")),
        (f"{rotulo}: Sankey", chamar("_open_sankey")),
        (f"{rotulo}: Linha do Tempo", chamar("_open_timeline")),
        (f"{rotulo}: Surtos", chamar("_open_bursts")),
        (f"{rotulo}: Mapa Temático", chamar("_open_thematic_map")),
        (f"{rotulo}: Historiografia", chamar("_open_historiograph")),
        (f"{rotulo}: Tendências", chamar("_open_trends")),
        (f"{rotulo}: Word Cloud", chamar("_show_wordcloud")),
        (f"{rotulo}: fechar janelas", fechar_janelas_extras),
        (f"{rotulo}: Deduplicar", chamar("_run_dedup")),
        (f"{rotulo}: fechar janelas", fechar_janelas_extras),
        (f"{rotulo}: Salvar na Galeria", botao("Salvar na Galeria")),
        (f"{rotulo}: Exportar PNG", chamar("_export_png")),
        (f"{rotulo}: Exportar Excel", chamar("_export_excel")),
        (f"{rotulo}: Exportar Selecionados (lote)", botao("Exportar Selecionados")),
        (f"{rotulo}: Salvar projeto", chamar("_save_project_gui")),
    ]
    return passos


passos = roteiro("200 registros", RAIZ / "docs" / "sample_dataset.csv")
passos += roteiro(f"{N_GRANDE} registros", corpus_grande(N_GRANDE))
resultados = []
estado = {"i": -1, "t0": 0.0, "n0": 0, "erro": None}


def proximo():
    # fecha o passo anterior
    if estado["i"] >= 0:
        ts = [t for t in batidas if t >= estado["t0"]]
        ts = [estado["t0"]] + ts + [time.perf_counter()]
        maior = max(b - a for a, b in zip(ts, ts[1:]))
        resultados.append({"acao": passos[estado["i"]][0], "congelado_ms": round(maior * 1000),
                           "total_ms": round((time.perf_counter() - estado["t0"]) * 1000),
                           "erro": estado["erro"]})
        print(f"{resultados[-1]['congelado_ms']:>7} ms congelado  "
              f"{resultados[-1]['total_ms']:>7} ms total  {passos[estado['i']][0]}"
              + (f"  [ERRO {estado['erro']}]" if estado["erro"] else ""), flush=True)
    estado["i"] += 1
    if estado["i"] >= len(passos):
        return terminar()
    estado["erro"] = None
    estado["t0"] = time.perf_counter()
    try:
        passos[estado["i"]][1]()
    except Exception as exc:
        estado["erro"] = f"{type(exc).__name__}: {exc}"[:120]
    app.after(50, esperar, time.perf_counter())


def esperar(inicio):
    if workers_vivos() and time.perf_counter() - inicio < 180:
        return app.after(50, esperar, inicio)
    # meio segundo de folga para os after(0, ...) que os workers agendam no fim
    if time.perf_counter() - inicio < 0.6:
        return app.after(50, esperar, inicio)
    proximo()


def terminar():
    if SAIDA:
        Path(SAIDA).write_text(json.dumps(resultados, ensure_ascii=False, indent=1), "utf-8")
    ruins = [r for r in resultados if r["congelado_ms"] >= 500]
    print(f"\n{len(resultados)} ações · {len(ruins)} com congelamento ≥ 500 ms")
    try:
        app._on_app_close()
    except Exception:
        pass
    os._exit(0)


app.after(1500, bater)
app.after(2500, proximo)
app.mainloop()
