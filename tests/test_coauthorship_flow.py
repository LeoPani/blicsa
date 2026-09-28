"""Regressions for author identities, small coauthorship maps and map pruning."""

from __future__ import annotations

import pandas as pd
import networkx as nx
from types import SimpleNamespace
import json

from core.map_controls import prune_network
from core.matrix_builders import NetworkGenerator, parse_author_list


def _corpus(*author_fields: str) -> pd.DataFrame:
    return pd.DataFrame({
        "authors": list(author_fields),
        "title": [f"Work {i}" for i in range(len(author_fields))],
        "keywords": [""] * len(author_fields),
        "year": [2020 + i for i in range(len(author_fields))],
        "citations": [2 + i for i in range(len(author_fields))],
    })


def test_surname_comma_initial_is_one_author_without_false_collaboration():
    gen = NetworkGenerator(_corpus("Silva, J."))
    graph = gen.build_coauthorship_network(min_publications=1)

    assert list(graph.nodes) == ["Silva, J."]
    assert graph.number_of_edges() == 0
    assert gen.get_top_authors() == [("Silva, J.", 1)]
    assert graph.nodes["Silva, J."]["citations_mean"] == 2.0
    assert graph.nodes["Silva, J."]["year_mean"] == 2020.0


def test_bibtex_and_semicolon_lists_form_real_collaboration_only():
    assert parse_author_list("Silva, J. and Costa, M.") == ["Silva, J.", "Costa, M."]
    assert parse_author_list("Silva, J.; Silva, J.; Costa, M.") == ["Silva, J.", "Costa, M."]

    gen = NetworkGenerator(_corpus(
        "Silva, J. and Costa, M.",
        "Silva, J.; Costa, M.; Costa, M.",
    ))
    graph = gen.build_coauthorship_network(min_publications=2)

    assert set(graph.nodes) == {"Silva, J.", "Costa, M."}
    assert graph["Silva, J."]["Costa, M."]["weight"] == 2
    assert not list(nx.selfloop_edges(graph))
    assert gen.get_top_authors() == [("Silva, J.", 2), ("Costa, M.", 2)]


def test_coauthorship_max_nodes_uses_link_strength_with_stable_ties():
    gen = NetworkGenerator(_corpus(
        "Ada; Bruno; Clara", "Ada; Bruno", "Ada; Clara", "Bruno; Clara",
    ))
    graph = gen.build_coauthorship_network(min_publications=1, max_nodes=2)

    assert set(graph.nodes) == {"Ada", "Bruno"}
    assert graph.number_of_edges() == 1
    assert graph["Ada"]["Bruno"]["weight"] == 2


def test_coauthorship_cap_keeps_collaborators_before_prolific_solo_author():
    gen = NetworkGenerator(_corpus(
        "Solo", "Solo", "Solo", "Solo", "Ada; Bruno", "Ada; Bruno", "Ada; Bruno",
    ))
    graph = gen.build_coauthorship_network(min_publications=1, max_nodes=2)

    assert set(graph.nodes) == {"Ada", "Bruno"}
    assert graph["Ada"]["Bruno"]["weight"] == 3


def test_pruning_empty_graph_and_all_isolates_is_safe():
    empty = nx.Graph()
    assert prune_network(empty, remove_isolated=True, largest_component=True) == (0, 0)

    isolated = nx.Graph()
    isolated.add_nodes_from(["a", "b"])
    assert prune_network(isolated, remove_isolated=True, largest_component=True) == (2, 0)
    assert isolated.number_of_nodes() == 0


def test_pruning_largest_component_keeps_connected_collaborators():
    graph = nx.Graph()
    graph.add_edges_from([("a", "b"), ("b", "c"), ("d", "e")])
    assert prune_network(graph, largest_component=True) == (0, 2)
    assert set(graph.nodes) == {"a", "b", "c"}


def test_recluster_publishes_updated_sigma_map_without_changing_positions(tmp_path):
    from main import BlicsaApp

    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    generator = NetworkGenerator(_corpus("Ada; Bruno", "Ada; Bruno"))
    generator.build_coauthorship_network(min_publications=1)
    positions = {"Ada": (0.0, 0.0), "Bruno": (1.0, 1.0)}
    (tmp_path / "assets").mkdir()
    app = SimpleNamespace(
        _generator=generator,
        _graph=generator.G,
        _positions=positions,
        _serve_dir=tmp_path,
        _cluster_res_var=Value(1.2),
        _cluster_alg_var=Value("louvain"),
        _demo_no_browser=True,
    )
    app._publish_sigma_map = lambda: BlicsaApp._publish_sigma_map(app)

    BlicsaApp._recluster_only(app)

    payload = json.loads((tmp_path / "assets" / "graph.json").read_text(encoding="utf-8"))
    assert {n["key"] for n in payload["nodes"]} == {"Ada", "Bruno"}
    assert (tmp_path / "assets" / "i18n.json").exists()
    assert positions == {"Ada": (0.0, 0.0), "Bruno": (1.0, 1.0)}
