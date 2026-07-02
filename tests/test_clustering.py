import unittest
import networkx as nx
import pandas as pd
from core.matrix_builders import NetworkGenerator, _apply_clustering

class TestClusteringAndOverlay(unittest.TestCase):

    def test_apply_clustering_louvain(self):
        # Create a barbell graph with two clear communities of size 10
        G = nx.barbell_graph(10, 0)
        # Add weights
        for u, v in G.edges():
            G[u][v]["weight"] = 1.0
            
        partition = _apply_clustering(G, algorithm="louvain", resolution=1.0)
        self.assertEqual(len(partition), 20)
        # Nodes 0-9 should be in one community, 10-19 in the other (or at least partitioned cleanly)
        comm_a = set(partition[i] for i in range(10))
        comm_b = set(partition[i] for i in range(10, 20))
        # Usually they should not overlap much
        self.assertEqual(len(comm_a), 1)
        self.assertEqual(len(comm_b), 1)
        self.assertNotEqual(comm_a, comm_b)

    def test_apply_clustering_leiden_fallback(self):
        # If leidenalg/igraph is not installed, it falls back to louvain and succeeds
        G = nx.barbell_graph(5, 0)
        for u, v in G.edges():
            G[u][v]["weight"] = 1.0
            
        partition = _apply_clustering(G, algorithm="leiden", resolution=1.0)
        self.assertEqual(len(partition), 10)

    def test_overlay_scores_calculation(self):
        # Create a dummy dataframe
        df = pd.DataFrame([
            {"title": "Paper One", "authors": "Author A; Author B", "year": 2020, "citations": 10, "keywords": "deep learning; neural networks"},
            {"title": "Paper Two", "authors": "Author B; Author C", "year": 2022, "citations": 20, "keywords": "deep learning; machine learning"}
        ])
        
        gen = NetworkGenerator(df)
        # Build simple graph manually
        gen.G.add_node("Author B")
        gen.G.add_node("deep learning")
        
        gen.compute_overlay_scores()
        
        # Verify overlay scores
        self.assertIn("year_mean", gen.G.nodes["Author B"])
        self.assertEqual(gen.G.nodes["Author B"]["year_mean"], 2021.0) # (2020 + 2022) / 2
        self.assertEqual(gen.G.nodes["Author B"]["citations_mean"], 15.0) # (10 + 20) / 2
        self.assertEqual(gen.G.nodes["Author B"]["citations_sum"], 30) # 10 + 20
        
        self.assertEqual(gen.G.nodes["deep learning"]["year_mean"], 2021.0)
        self.assertEqual(gen.G.nodes["deep learning"]["citations_sum"], 30)

if __name__ == '__main__':
    # Add igraph/leidenalg if they exist, but tests should pass either way
    unittest.main()
