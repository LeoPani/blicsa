#!/usr/bin/env python3
"""Benchmark de fps do canvas Sigma (Fase 5) — 500, 2.000 e 5.000 nós.

Abre o mapa real no pywebview (WebGL de verdade, o mesmo caminho do app), roda pan/zoom
automatizado por ~10s em cada tamanho e lê o contador de quadros do próprio JS. Nada de
estimativa: o número vem do `requestAnimationFrame` da página.

Uso:
    python3 scripts/benchmark_fps.py
    python3 scripts/benchmark_fps.py --nodes 500 2000
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import math
import random
import shutil
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent


def grafo_sintetico(n_nos: int, seed: int = 7):
    """Grafo com comunidades e grau realista (nem árvore, nem completo)."""
    import networkx as nx

    from core.matrix_builders import CLUSTER_PALETTE

    rnd = random.Random(seed)
    comunidades = max(4, n_nos // 120)
    G = nx.Graph()
    for i in range(n_nos):
        c = i % comunidades
        G.add_node(f"n{i}", label=f"termo {i}", size=8 + rnd.randint(0, 24),
                   group=c, color=CLUSTER_PALETTE[c % len(CLUSTER_PALETTE)],
                   occurrence=1 + rnd.randint(0, 60),
                   year_mean=float(2005 + rnd.randint(0, 19)),
                   citations_mean=float(rnd.randint(0, 300)),
                   first_year=2005 + rnd.randint(0, 19))
    # ~6 arestas por nó: dentro da comunidade na maior parte, com pontes entre elas.
    for i in range(n_nos):
        for _ in range(6):
            if rnd.random() < 0.85:
                j = (i + comunidades * rnd.randint(1, max(1, n_nos // comunidades - 1))) % n_nos
            else:
                j = rnd.randrange(n_nos)
            if i != j:
                G.add_edge(f"n{i}", f"n{j}", weight=1.0 + rnd.random() * 5)

    # Layout em espiral por comunidade — barato e determinístico (o custo do FA2 não é o
    # que está sendo medido aqui; o alvo é o renderizador).
    pos = {}
    for i, n in enumerate(G.nodes()):
        c = G.nodes[n]["group"]
        ang = (i / max(n_nos, 1)) * math.tau * 6 + c
        raio = 0.15 + 0.85 * (i / max(n_nos, 1))
        pos[n] = (raio * math.cos(ang) + 0.6 * math.cos(c), raio * math.sin(ang) + 0.6 * math.sin(c))
    return G, pos


def prepara_dir(G, pos, destino: Path) -> Path:
    from core.i18n import get_map_i18n
    from core.sigma_exporter import export_sigma_json

    (destino / "assets" / "vendor").mkdir(parents=True, exist_ok=True)
    export_sigma_json(G, pos, str(destino / "assets" / "graph.json"), max_edges=0)
    for nome in ("map_template.html", "map.js"):
        shutil.copy(REPO / "assets" / nome, destino / "assets" / nome)
    shutil.copy(REPO / "assets/vendor/blicsa-vendor.min.js", destino / "assets/vendor/")
    (destino / "assets" / "i18n.json").write_text(
        json.dumps(get_map_i18n(), ensure_ascii=False), encoding="utf-8")
    return destino


def mede(n_nos: int, segundos: float = 10.0) -> dict:
    import webview

    G, pos = grafo_sintetico(n_nos)
    tmp = Path(tempfile.mkdtemp(prefix=f"blicsa_fps_{n_nos}_"))
    prepara_dir(G, pos, tmp)

    class Quieto(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(Quieto, directory=str(tmp)))
    porta = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    resultado: dict = {"nos": G.number_of_nodes(), "arestas": G.number_of_edges()}

    def rotina(window):
        time.sleep(5.0)                                   # carga + primeiro paint
        window.evaluate_js("window.BlicsaMap.setReduceMotion(true)")   # sem transições
        quadros = max(30, int(segundos * 12))
        for modo in ("network", "overlay", "density"):
            window.evaluate_js(f"window.BlicsaMap.setMode('{modo}')")
            time.sleep(1.0)
            # Métrica principal: tempo de render por quadro em laço fechado (ver a nota em
            # benchRenderTime no map.js — o fps por rAF é estrangulado pelo sistema quando a
            # janela não está em primeiro plano, e sai vazio em vez de sair baixo).
            bruto = window.evaluate_js(
                f"JSON.stringify(window.BlicsaMap.benchRenderTime({quadros}))")
            resultado[modo] = json.loads(bruto)
            # Secundária: fps observado via rAF, quando o sistema deixa medir.
            window.evaluate_js("window.BlicsaMap.fpsReset()")
            window.evaluate_js(f"window.BlicsaMap.benchPan({int(segundos * 60)})")
            time.sleep(segundos + 0.5)
            obs = json.loads(window.evaluate_js("JSON.stringify(window.BlicsaMap.fpsStats())"))
            resultado[modo]["fps_observado"] = obs.get("media") if obs.get("n") else None
        window.destroy()

    # on_top: o macOS SUSPENDE o requestAnimationFrame de janela em segundo plano, e o
    # contador de quadros simplesmente não recebe nada — a medição sai vazia (não sai baixa,
    # sai vazia). A janela precisa estar visível e na frente durante o benchmark.
    w = webview.create_window(f"fps {n_nos}",
                              f"http://127.0.0.1:{porta}/assets/map_template.html",
                              width=1200, height=800, on_top=True)
    webview.start(rotina, w)
    httpd.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nodes", type=int, nargs="*", default=[500, 2000, 5000])
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()

    # pywebview só roda um `start()` por processo: cada tamanho vai num subprocesso.
    if len(args.nodes) > 1:
        import subprocess
        for n in args.nodes:
            subprocess.run([sys.executable, __file__, "--nodes", str(n),
                            "--seconds", str(args.seconds)], check=False)
        return 0

    n = args.nodes[0]
    r = mede(n, args.seconds)
    print(f"\n=== {r['nos']} nós · {r['arestas']} arestas ===")
    for modo in ("network", "overlay", "density"):
        s = r.get(modo, {})
        if not s.get("n"):
            print(f"  {modo:<8} sem amostras")
            continue
        obs = s.get("fps_observado")
        obs_txt = f"{obs:.1f} fps observados" if obs else "rAF estrangulado pelo sistema"
        print(f"  {modo:<8} {s['ms_media']:>6.2f} ms/quadro (p95 {s['ms_p95']:>6.2f}) → "
              f"{s['fps_equivalente']:>6.1f} fps equiv. · {obs_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
