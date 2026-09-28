"""Exporta mapas complementares de acoplamento bibliográfico da qualificação."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.matrix_builders import NetworkGenerator
from core.project import open_project
from core.visualizer import compute_fa2_layout
from scripts.exportar_mapas_rebusca import export_map


PROJECTS = (
    ("qualificacao-2026-patentbert-rebusca", 3),
    ("qualificacao-2026-dsr-e-pi-rebusca", 2),
)


def main() -> None:
    for slug, minimum in PROJECTS:
        state = open_project(slug)
        generator = NetworkGenerator(state["df"])
        generator.build_bibliographic_coupling(min_shared_refs=minimum)
        if not generator.G.number_of_edges():
            print(json.dumps({"slug": slug, "skipped": "sem ligações"}))
            continue
        positions = compute_fa2_layout(generator.G, iterations=180)
        export_map(
            slug, "acoplamento", generator, positions,
            f"Acoplamento bibliográfico · ≥{minimum} referências compartilhadas",
        )


if __name__ == "__main__":
    main()
