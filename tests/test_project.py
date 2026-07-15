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

class TestProjectFolders(unittest.TestCase):
    """Passo 3: projeto = pasta (project.blicsa + backlog.jsonl + searches/ + exports/)."""

    def setUp(self):
        import tempfile
        self.base = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.base, ignore_errors=True)

    def test_create_project_scaffold(self):
        from core.project import create_project, project_dir
        slug = create_project("Minha Pesquisa Ágil!", projects_dir=self.base)
        self.assertEqual(slug, "minha-pesquisa-agil")
        d = project_dir(slug, self.base)
        self.assertTrue((d / "project.blicsa").exists())
        self.assertTrue((d / "backlog.jsonl").exists())
        self.assertTrue((d / "searches").is_dir())
        self.assertTrue((d / "exports").is_dir())

    def test_create_project_slug_collision(self):
        from core.project import create_project
        s1 = create_project("Teste", projects_dir=self.base)
        s2 = create_project("Teste", projects_dir=self.base)
        self.assertEqual((s1, s2), ("teste", "teste-2"))

    def test_backlog_roundtrip_and_open(self):
        from core.project import (create_project, append_backlog, load_backlog,
                                  open_project, save_blicsa_project, project_dir)
        slug = create_project("P", projects_dir=self.base)
        append_backlog(slug, "search", {"provider": "openalex", "query": "x"}, self.base)
        append_backlog(slug, "import", {"registros": 10}, self.base)
        append_backlog(slug, "dedup", {"pares": 3, "aplicado": True}, self.base)
        bl = load_backlog(slug, self.base)
        self.assertEqual([e["action"] for e in bl], ["search", "import", "dedup"])
        self.assertTrue(all("ts" in e for e in bl))

        df = pd.DataFrame([{"title": "T", "year": 2020, "citations": 1}])
        save_blicsa_project(str(project_dir(slug, self.base) / "project.blicsa"),
                            df=df, config={"name": "P"}, positions=None, G=None,
                            cluster_labels=None)
        data = open_project(slug, self.base)
        self.assertEqual(len(data["df"]), 1)
        self.assertEqual(len(data["backlog"]), 3)
        self.assertEqual(data["slug"], slug)

    def test_search_raw_roundtrip(self):
        from core.project import create_project, save_search_raw, load_search_raw
        slug = create_project("P", projects_dir=self.base)
        recs = [{"title": "A", "doi": "10.1/a"}, {"title": "B", "doi": "10.1/b"}]
        rel = save_search_raw(slug, recs, self.base)
        self.assertTrue(rel.startswith("searches/search_"))
        self.assertEqual(load_search_raw(slug, rel, self.base), recs)

    def test_old_loose_blicsa_still_opens(self):
        """Formato .blicsa antigo (pré-migração) continua abrível."""
        from core.project import save_blicsa_project, load_blicsa_project
        old = os.path.join(self.base, "Antigo.blicsa")
        df = pd.DataFrame([{"title": "Velho", "year": 2019, "citations": 2}])
        save_blicsa_project(old, df=df, config={"a": 1}, positions=None, G=None,
                            cluster_labels=None)
        loaded = load_blicsa_project(old)
        self.assertEqual(loaded["df"].iloc[0]["title"], "Velho")
        self.assertEqual(loaded["config"]["a"], 1)


if __name__ == '__main__':
    unittest.main()
