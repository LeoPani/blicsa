import os
import networkx as nx
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('Agg')

os.makedirs("docs/evidence", exist_ok=True)

G = nx.connected_caveman_graph(3, 20)
for u, v in G.edges():
    G[u][v]["weight"] = 1.0
for i, n in enumerate(G.nodes()):
    G.nodes[n]["weight"] = G.degree(n)
    G.nodes[n]["group"] = i // 20
    G.nodes[n]["label"] = f"Node {n}"

from core.visualizer import compute_fa2_layout
positions = compute_fa2_layout(G)

# Create a mock MapCanvas instance
class MockMapCanvas:
    def __init__(self):
        self._fig, self._ax = plt.subplots(figsize=(11, 7), dpi=130)
        self._canvas = type('MockCanvas', (), {'draw': lambda self: None})()
        
    def _redraw(self, G, pos, mode, node_scale, edge_opacity):
        pass # This will be the patched code

# We'll import MapCanvas and patch its draw to not require Tkinter
from ui.components import MapCanvas
MapCanvas.__init__ = MockMapCanvas.__init__

canvas = MapCanvas()
canvas._redraw(G, positions, "Clusters", 1.0, 1.0)
canvas._fig.savefig("docs/evidence/map_after.png", facecolor="#F6F4EE", edgecolor="#141414", bbox_inches="tight")
print("Saved docs/evidence/map_after.png")
