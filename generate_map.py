import pandas as pd
from core.matrix_builders import NetworkGenerator
from core.visualizer import compute_fa2_layout
from core.sigma_exporter import export_sigma_json
import time

print("Loading dataset...")
df = pd.read_csv("docs/sample_dataset.csv")
print("Building matrix...")
net = NetworkGenerator(df)
G = net.build_keyword_cooccurrence(min_occurrence=1)
term_counts = net._term_counts
print("Computing layout...")
pos = compute_fa2_layout(G, iterations=100)
print("Exporting to JSON...")
export_sigma_json(G, pos, "assets/graph.json")
print("Done!")
