#!/usr/bin/env python3
"""Percurso do usuário novo, executado de verdade e cronometrado — Auditoria 1, Fase 2.

Dirige a **aplicação real** (`BlicsaApp`), não uma simulação: cada passo chama o método que o
botão chamaria, e o relógio mede o que o usuário esperaria.

Offline de propósito, a partir de `docs/sample_dataset.csv`. Um percurso que depende de rede
mede a rede, não o app — e não pode ser refeito daqui a um ano com o mesmo resultado. Os
passos que exigem rede (busca e IA) estão marcados como tal e ficam para o relatório.

    python3 scripts/audit_fluxo.py
"""
from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CSV = RAIZ / "docs" / "sample_dataset.csv"


class Percurso:
    """Cronômetro + registro de atritos. Um passo que levanta não interrompe o percurso —
    o ponto é chegar ao fim e ver *quantos* pontos quebram, não parar no primeiro."""

    def __init__(self):
        self.passos: list[dict] = []
        self.atritos: list[str] = []

    def passo(self, nome: str, fn, *, essencial: bool = True):
        t0 = time.perf_counter()
        erro = None
        resultado = None
        try:
            resultado = fn()
        except Exception as e:
            erro = f"{type(e).__name__}: {e}"
            self.atritos.append(f"{nome}: {erro}")
            if essencial:
                traceback.print_exc(limit=3)
        dt = time.perf_counter() - t0
        self.passos.append({"nome": nome, "s": round(dt, 2), "erro": erro,
                            "nota": resultado if isinstance(resultado, str) else None})
        marca = "FALHA" if erro else "OK  "
        extra = f" — {resultado}" if isinstance(resultado, str) else ""
        print(f"  [{marca}] {dt:6.2f}s  {nome}{extra}")
        if erro:
            print(f"            → {erro[:110]}")
        return resultado


def main() -> int:
    if not CSV.exists():
        print(f"sem {CSV} — o percurso precisa do corpus de exemplo do repositório")
        return 2

    import pandas as pd

    import main as blicsa
    from core.matrix_builders import NetworkGenerator
    from core.project import load_blicsa_project, save_blicsa_project
    from core.sigma_exporter import export_sigma_json
    from core.visualizer import compute_fa2_layout

    p = Percurso()
    tmp = Path(tempfile.mkdtemp())
    estado: dict = {}

    print("PERCURSO DO USUÁRIO NOVO — sem projeto, sem chave de IA, offline\n")

    app = p.passo("abrir o app pela primeira vez", lambda: (
        estado.__setitem__("app", blicsa.BlicsaApp()),
        estado["app"].withdraw(),
        estado["app"].update_idletasks(),
        f"{len(estado['app']._tabs)} abas montadas",
    )[-1])
    app = estado["app"]

    p.passo("tela de boas-vindas está na frente",
            lambda: "sim" if app._welcome_frame.winfo_manager() == "place" else "NÃO — usuário cai numa tela vazia")

    p.passo("escolher 'abrir projeto' (sai das boas-vindas)", lambda: (
        app._dispensa_boas_vindas(), app._switch_tab("projects"), app.update_idletasks(),
        f"aba = {app._current_tab_key}")[-1])

    p.passo("importar CSV de exemplo", lambda: (
        estado.__setitem__("df", pd.read_csv(CSV)),
        f"{len(estado['df'])} registros")[-1])

    p.passo("corpus vai para o app", lambda: (
        setattr(app, "_dataframe", estado["df"]),
        app._switch_tab("corpus"), app.update_idletasks(),
        f"aba = {app._current_tab_key}")[-1])

    def gera_mapa():
        gen = NetworkGenerator(estado["df"])
        G = gen.build_keyword_cooccurrence(min_occurrence=3)
        gen.apply_clustering()
        estado["gen"], estado["G"] = gen, G
        return f"{G.number_of_nodes()} nós · {G.number_of_edges()} arestas"

    p.passo("gerar o grafo", gera_mapa)

    p.passo("calcular o layout (500 iterações)", lambda: (
        estado.__setitem__("pos", compute_fa2_layout(estado["G"], iterations=500)),
        f"{len(estado['pos'])} posições")[-1])

    p.passo("publicar o mapa para a tela", lambda: (
        estado.__setitem__("payload", export_sigma_json(
            estado["G"], estado["pos"], str(tmp / "graph.json"))),
        f"{estado['payload']['meta']['nodes_total']} nós no payload")[-1])

    p.passo("rótulos de cluster sem chave de IA", lambda: _sem_chave(estado["gen"]))

    p.passo("exportar (GML, GEXF, Pajek, VOSviewer)", lambda: _exporta(estado["gen"], estado["pos"], tmp))

    p.passo("salvar o projeto", lambda: (
        save_blicsa_project(str(tmp / "meu.blicsa"), estado["df"],
                            {"name": "auditoria", "min_occurrence": 3},
                            estado["pos"], estado["G"], {}),
        f"{(tmp / 'meu.blicsa').stat().st_size / 1024:.0f} KB")[-1])

    p.passo("fechar o app", lambda: (app.destroy(), "janela fechada")[-1])

    p.passo("reabrir o app", lambda: (
        estado.__setitem__("app2", blicsa.BlicsaApp()),
        estado["app2"].withdraw(), estado["app2"].update_idletasks(), "aberto")[-1])

    def recarrega():
        d = load_blicsa_project(str(tmp / "meu.blicsa"))
        estado["app2"]._restore_project_data(d)
        estado["app2"].update_idletasks()
        return (f"{d['G'].number_of_nodes()} nós · {len(d['df'])} registros · "
                f"aba = {estado['app2']._current_tab_key}")

    p.passo("carregar o projeto salvo", recarrega)
    p.passo("fechar", lambda: (estado["app2"].destroy(), "fechado")[-1])

    total = sum(x["s"] for x in p.passos)
    print(f"\n{'─' * 62}\ntotal: {total:.2f}s em {len(p.passos)} passos")
    if p.atritos:
        print(f"\n{len(p.atritos)} atrito(s):")
        for a in p.atritos:
            print(f"  - {a}")
        return 1
    print("percurso completo sem atrito")
    return 0


def _sem_chave(gen):
    """O usuário novo NÃO tem chave. O app não pode quebrar nem mentir por causa disso."""
    import os

    from ai.client import AIAnalyst, AIClientError

    guardadas = {k: os.environ.pop(k, None) for k in ("AI_API_KEY", "GROQ_API_KEY")}
    try:
        AIAnalyst(api_key=None).label_clusters(gen.get_cluster_report())
        return "FURO: não avisou que falta a chave"
    except AIClientError as e:
        return f"recusa clara — {e}"
    finally:
        for k, v in guardadas.items():
            if v:
                os.environ[k] = v


def _exporta(gen, pos, tmp: Path) -> str:
    import networkx as nx

    gen.export_gml(str(tmp / "r.gml"))
    gen.export_gexf(str(tmp / "r.gexf"))
    gen.export_pajek(str(tmp / "r.net"))
    gen.export_vosviewer(str(tmp / "m.txt"), str(tmp / "n.txt"), pos)
    lidos = {
        "GML": nx.read_gml(str(tmp / "r.gml")).number_of_nodes(),
        "GEXF": nx.read_gexf(str(tmp / "r.gexf")).number_of_nodes(),
        "Pajek": nx.read_pajek(str(tmp / "r.net")).number_of_nodes(),
    }
    esperado = gen.G.number_of_nodes()
    ruins = [k for k, v in lidos.items() if v != esperado]
    return f"4 formatos, todos relidos com {esperado} nós" if not ruins else f"DIVERGEM: {ruins}"


if __name__ == "__main__":
    sys.exit(main())
