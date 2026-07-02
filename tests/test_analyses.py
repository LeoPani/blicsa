import unittest
import pandas as pd
import networkx as nx
from core.matrix_builders import NetworkGenerator

class TestNewAnalyses(unittest.TestCase):

    def test_callon_thematic_map(self):
        # Create a simple co-occurrence network with 2 clusters (communities)
        df = pd.DataFrame([
            {"title": "P1", "year": 2021, "citations": 5, "keywords": "deep learning; neural networks"},
            {"title": "P2", "year": 2022, "citations": 10, "keywords": "blockchain; smart contracts"},
            {"title": "P3", "year": 2023, "citations": 2, "keywords": "deep learning; smart contracts"} # cross-link
        ])
        
        gen = NetworkGenerator(df)
        gen.build_keyword_cooccurrence(min_occurrence=1, normalize_strength=False)
        
        thematic_data = gen.get_thematic_map()
        self.assertIsNotNone(thematic_data)
        
        # Verify cluster structure
        for grp, info in thematic_data.items():
            self.assertIn("label", info)
            self.assertIn("centrality", info)
            self.assertIn("density", info)
            self.assertIn("size", info)

    def test_three_field_sankey_data(self):
        df = pd.DataFrame([
            {"source": "Journal A", "authors": "Author 1; Author 2", "keywords": "deep learning; blockchain"},
            {"source": "Journal B", "authors": "Author 2; Author 3", "keywords": "blockchain; smart contracts"}
        ])
        
        gen = NetworkGenerator(df)
        sankey = gen.get_sankey_data(left_field="source", middle_field="authors", right_field="keywords", top_n=5)
        
        self.assertIn("nodes", sankey)
        self.assertIn("sources", sankey)
        self.assertIn("targets", sankey)
        self.assertIn("values", sankey)
        
        # Total nodes should be the union of top values in all 3 fields
        self.assertTrue(len(sankey["nodes"]) > 0)
        self.assertEqual(len(sankey["sources"]), len(sankey["targets"]))

if __name__ == '__main__':
    unittest.main()
