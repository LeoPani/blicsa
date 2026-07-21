"""Passo 7 — exercita build_plotly_density.

Nenhum teste chamava esta função, por isso o `titlefont` (incompatível com
plotly 6.x, que levanta ValueError no colorbar) sobreviveu. Este teste constrói
a figura E escreve o HTML offline — teria pegado o bug.
"""
import os
import tempfile

import networkx as nx

from core.visualizer import build_plotly_density


def _graph():
    G = nx.Graph()
    G.add_node("a", size=10)
    G.add_node("b", size=20)
    G.add_node("c", size=5)
    G.add_edge("a", "b")
    return G, {"a": (0.0, 0.0), "b": (1.0, 1.0), "c": (2.0, 0.0)}


def test_density_builds_without_raising():
    G, pos = _graph()
    fig = build_plotly_density(G, pos)  # levantava ValueError com titlefont
    # 2 traces: contorno de densidade + scatter dos nós
    assert len(fig.data) == 2
    # colorbar com título no formato novo (title.text), não o antigo titlefont
    assert fig.data[0].colorbar.title.text


def test_density_writes_offline_html():
    G, pos = _graph()
    fig = build_plotly_density(G, pos)
    path = os.path.join(tempfile.mkdtemp(), "density.html")
    fig.write_html(path, include_plotlyjs=True)  # plotly.js embutido, sem CDN
    assert os.path.getsize(path) > 100_000


def test_density_empty_positions():
    G = nx.Graph()
    fig = build_plotly_density(G, {})
    assert len(fig.data) == 0
