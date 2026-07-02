import unittest
import os
import tempfile
import pandas as pd
import networkx as nx
from core.project import save_blicsa_project, load_blicsa_project

class TestProjectSaveLoad(unittest.TestCase):

    def test_round_trip_project_save_load(self):
        # Create temp project file path
        fd, temp_path = tempfile.mkstemp(suffix=".blicsa")
        os.close(fd)

        try:
            # Create synthetic dataframe
            df = pd.DataFrame([
                {"title": "Paper 1", "year": 2021, "citations": 5},
                {"title": "Paper 2", "year": 2022, "citations": 10}
            ])

            # Create dummy config
            config = {
                "map_type": "co-occurrence",
                "field": "keywords"
            }

            # Create dummy positions
            positions = {
                "Node A": [1.0, 2.0],
                "Node B": [-1.0, 3.5]
            }

            # Create dummy graph
            G = nx.Graph()
            G.add_node("Node A", size=10, group=0)
            G.add_node("Node B", size=15, group=1)
            G.add_edge("Node A", "Node B", weight=2.0)

            # Create dummy cluster labels
            cluster_labels = {
                0: "AI",
                1: "Blockchain"
            }

            # Save project
            save_blicsa_project(
                temp_path,
                df=df,
                config=config,
                positions=positions,
                G=G,
                cluster_labels=cluster_labels
            )

            # Load project
            loaded = load_blicsa_project(temp_path)

            # Assertions
            self.assertIsNotNone(loaded["df"])
            self.assertEqual(len(loaded["df"]), 2)
            self.assertEqual(loaded["df"].iloc[0]["title"], "Paper 1")
            
            self.assertEqual(loaded["config"]["map_type"], "co-occurrence")
            
            self.assertEqual(loaded["positions"]["Node A"], [1.0, 2.0])
            self.assertEqual(loaded["positions"]["Node B"], [-1.0, 3.5])
            
            self.assertIsNotNone(loaded["G"])
            self.assertTrue(loaded["G"].has_edge("Node A", "Node B"))
            self.assertEqual(loaded["G"].nodes["Node A"]["group"], 0)
            
            self.assertEqual(loaded["cluster_labels"][0], "AI")
            self.assertEqual(loaded["cluster_labels"][1], "Blockchain")

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == '__main__':
    unittest.main()
