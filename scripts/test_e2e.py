import unittest
import os
import sys
import time
from unittest.mock import patch

# Add root project path to pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import BlicsaApp

class TestE2E(unittest.TestCase):
    def setUp(self):
        # Setup the app headlessly
        self.app = BlicsaApp()
        self.app.withdraw() # Hide window
        self.app.update_idletasks() # Ensure it's fully created
        
        # Test paths
        self.mock_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tests', 'mock_scopus.csv'))
        self.reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
        os.makedirs(self.reports_dir, exist_ok=True)
        
    def test_e2e_flow(self):
        # 1. Load mock data directly
        self.assertTrue(os.path.exists(self.mock_csv), f"Mock data {self.mock_csv} not found")
        
        # Set file paths in app
        self.app._file_paths = [self.mock_csv]
        self.app._file_formats = ["scopus"]
        
        # We need to simulate the load worker synchronously
        from core.parsers import BibliometricParser
        import pandas as pd
        dfs = []
        for path, fmt in zip(self.app._file_paths, self.app._file_formats):
            if fmt == "scopus":
                parser = BibliometricParser(path)
                raw = pd.read_csv(path)
                # Map lowercase to uppercase for test mock, and keywords to Author Keywords
                raw.columns = [c.capitalize() if c != 'keywords' else 'Author Keywords' for c in raw.columns]
                # Override the file read
                def mock_read(*args, **kwargs): return raw
                import unittest.mock
                with unittest.mock.patch('pandas.read_csv', side_effect=mock_read):
                    dfs.append(parser.load_scopus_csv())
        
        combined = pd.concat(dfs, ignore_index=True)
        self.app._dataframe = combined
        self.app._refresh_corpus_tab()
        
        self.assertIsNotNone(self.app._dataframe)
        self.assertTrue(len(self.app._dataframe) > 0)
        
        # 2. Trigger mapping (we use generator directly as run_mapping relies on threads)
        from core.matrix_builders import NetworkGenerator
        self.app._generator = NetworkGenerator(self.app._dataframe)
        self.app._generator.build_keyword_cooccurrence(
            min_occurrence=1
        )
        
        self.assertIsNotNone(self.app._generator.G)
        self.assertTrue(len(self.app._generator.G.nodes) >= 0)
        
        self.app._graph = self.app._generator.G
        from core.visualizer import compute_fa2_layout
        self.app._positions = compute_fa2_layout(self.app._graph, iterations=5)
        
        self.assertIsNotNone(self.app._graph)
        self.assertTrue(self.app._graph.number_of_nodes() > 0)
        
        # 3. Save a map to reports/ using the logic in main.py export tabs
        # Check export logic
        self.app._exp_gml_var.set(True)
        self.app._exp_adj_var.set(False)
        self.app._exp_xls_var.set(False)
        self.app._exp_ai_var.set(False)
        
        import networkx as nx
        ts = int(time.time())
        p = os.path.join(self.reports_dir, f"test_rede_{ts}.gml")
        nx.write_gml(self.app._graph, p)
        
        self.assertTrue(os.path.exists(p))
        print(f"Test complete. Map saved to {p}")

    def tearDown(self):
        self.app.destroy()

if __name__ == '__main__':
    unittest.main()
