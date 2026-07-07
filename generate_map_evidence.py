import os
import networkx as nx
from core.visualizer import build_plotly_map, compute_fa2_layout

os.makedirs("docs/evidence", exist_ok=True)

G = nx.connected_caveman_graph(3, 20)
for u, v in G.edges():
    G[u][v]["weight"] = 1.0
for i, n in enumerate(G.nodes()):
    G.nodes[n]["weight"] = G.degree(n)
    G.nodes[n]["group"] = i // 20
    G.nodes[n]["label"] = f"Node {n}"

positions = compute_fa2_layout(G)
fig = build_plotly_map(G, positions, color_mode="cluster")
fig.write_image("docs/evidence/map_before.png", width=1200, height=800)
