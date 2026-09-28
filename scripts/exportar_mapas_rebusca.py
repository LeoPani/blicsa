"""Gera mapas Sigma portáteis de termos e coautoria dos três novos projetos."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.i18n import get_map_i18n
from core.map_controls import prune_network
from core.matrix_builders import NetworkGenerator
from core.project import append_backlog, open_project, project_dir, save_blicsa_project
from core.sigma_exporter import export_sigma_json
from core.visualizer import compute_fa2_layout


ROOT = Path(__file__).resolve().parents[1]
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PROJECTS = (
    ("qualificacao-2026-patentbert-rebusca", 2),
    ("qualificacao-2026-dsr-e-pi-rebusca", 1),
    ("qualificacao-2026-grace-period-rebusca", 1),
)
PROJECT_BY_NAME = {
    "patentbert": PROJECTS[0][0],
    "dsr-pi": PROJECTS[1][0],
    "grace-period": PROJECTS[2][0],
}

# Seleção editorial explícita para os mapas exploratórios. A planilha de triagem
# preserva o corpus inteiro; aqui removemos só nós de baixo valor analítico.
GENERIC_TERMS = {
    "abstract", "achieves", "address", "addresses", "allow", "allows",
    "application", "applications", "approach", "approaches", "article",
    "available", "based", "challenges", "comprehensive", "contributes",
    "current", "demonstrates", "development", "different", "effective",
    "effectiveness", "evaluation", "experimental", "experiments", "field",
    "findings", "focus", "further", "furthermore", "future", "important",
    "information", "introduce", "issues", "method", "methods", "most",
    "need", "often", "only", "out", "over", "paper", "performance",
    "potential", "presents", "process", "processes", "provides", "related",
    "research", "result", "results", "role", "some", "studies", "study",
    "support", "system", "systems", "task", "tasks", "technical", "there",
    "time", "under", "used", "using", "via", "work",
}
PROJECT_TERM_EXCLUSIONS = {
    "qualificacao-2026-patentbert-rebusca": {
        "patents", "models", "model", "language", "documents", "text",
        "framework", "technology", "technologies", "models llms",
    },
    "qualificacao-2026-dsr-e-pi-rebusca": {
        "design", "science", "innovation", "management", "intellectual",
        "property", "science dsr", "science methodology",
    },
    "qualificacao-2026-grace-period-rebusca": {
        "grace", "period", "patents", "property", "intellectual",
        "states", "united", "invents", "america", "art",
    },
}


def choose_terms(generator: NetworkGenerator, maximum: int = 70,
                 slug: str = "") -> set[str]:
    """Prefere locuções temáticas e limita palavras isoladas no mapa exploratório."""
    _, _, doc_freq, _ = generator.get_candidate_terms(field="titles_abstracts")
    excluded = GENERIC_TERMS | PROJECT_TERM_EXCLUSIONS.get(slug, set())
    ranked = sorted(
        (term for term, documents in doc_freq.items()
         if documents >= 3 and term.casefold() not in excluded),
        key=lambda term: (
            -doc_freq[term] * (1 + 0.45 * (len(term.split()) - 1)),
            -doc_freq[term], term,
        ),
    )
    phrases = [term for term in ranked if len(term.split()) > 1]
    singles = [term for term in ranked if len(term.split()) == 1]
    # Uma locução com a frequência quase igual à de sua palavra componente
    # explica melhor o tema sem ocupar dois nós com a mesma evidência.
    singles = [term for term in singles if not any(
        term in phrase.split() and doc_freq[phrase] >= 0.8 * doc_freq[term]
        for phrase in phrases[:200]
    )]
    result = singles[:min(16, maximum)] + phrases[:max(0, maximum - 16)]
    if len(result) < maximum:
        selected = set(result)
        result += [term for term in singles + phrases
                   if term not in selected][:maximum-len(result)]
    return set(result)


def safe_json(data: object) -> str:
    return (json.dumps(data, ensure_ascii=False, allow_nan=False)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def render_png(html_path: Path, png_path: Path) -> None:
    if not CHROME.exists():
        raise RuntimeError("Chrome não encontrado para renderizar o PNG")
    profile = png_path.parent / ".chrome-profile"
    command = [
        str(CHROME), "--headless=new", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        "--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader", f"--user-data-dir={profile}",
        "--window-size=1440,900", "--virtual-time-budget=6000",
        f"--screenshot={png_path}", html_path.as_uri(),
    ]
    if png_path.exists():
        png_path.unlink()
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    last_size = 0
    try:
        for _ in range(30):
            time.sleep(1)
            size = png_path.stat().st_size if png_path.exists() else 0
            if size > 10_000 and size == last_size:
                break
            last_size = size
        else:
            raise RuntimeError(f"Chrome não exportou {png_path} em 30 segundos")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    shutil.rmtree(profile, ignore_errors=True)


def export_map(slug: str, kind: str, generator: NetworkGenerator,
               positions: dict, subtitle: str) -> dict:
    folder = project_dir(slug) / "exports" / kind
    folder.mkdir(parents=True, exist_ok=True)
    for asset in ("map.js",):
        shutil.copyfile(ROOT / "assets" / asset, folder / asset)
    (folder / "vendor").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "assets" / "vendor" / "blicsa-vendor.min.js",
                    folder / "vendor" / "blicsa-vendor.min.js")
    payload = export_sigma_json(generator.G, positions, str(folder / "graph.json"),
                                max_edges=3000)
    i18n = get_map_i18n()
    i18n["map_title"] = subtitle
    template = (ROOT / "assets" / "map_template.html").read_text(encoding="utf-8")
    embedded = ("<script>window.BLICSA_GRAPH=" + safe_json(payload)
                + ";window.BLICSA_I18N=" + safe_json(i18n) + ";</script>")
    template = template.replace('  <script src="vendor/blicsa-vendor.min.js"></script>',
                                embedded + '\n  <script src="vendor/blicsa-vendor.min.js"></script>')
    html_path = folder / "mapa.html"
    html_path.write_text(template, encoding="utf-8")
    (folder / "i18n.json").write_text(json.dumps(i18n, ensure_ascii=False), encoding="utf-8")
    generator.export_rankings_csv(str(folder / "nos.csv"))
    generator.export_edges_csv(str(folder / "arestas.csv"))
    graphml = nx.Graph()
    graphml.add_nodes_from((node, {key: value for key, value in attrs.items()
                                   if value is not None})
                           for node, attrs in generator.G.nodes(data=True))
    graphml.add_edges_from((u, v, {key: value for key, value in attrs.items()
                                  if value is not None})
                           for u, v, attrs in generator.G.edges(data=True))
    nx.write_graphml(graphml, folder / "rede.graphml")
    png_path = folder / "mapa.png"
    render_png(html_path, png_path)
    report = {
        "kind": kind,
        "nodes": generator.G.number_of_nodes(),
        "edges": generator.G.number_of_edges(),
        "components": nx.number_connected_components(generator.G)
        if generator.G.number_of_nodes() else 0,
        "html": str(html_path), "png": str(png_path),
    }
    append_backlog(slug, "map", report)
    append_backlog(slug, "export", {"kind": kind, "path": f"exports/{kind}/mapa.html"})
    print(json.dumps({"slug": slug} | report, ensure_ascii=False), flush=True)
    return report


def selected_projects(name: str) -> tuple[tuple[str, int], ...]:
    """Traduz o nome da opção para o slug real, sem sucesso vazio silencioso."""
    if name == "all":
        return PROJECTS
    return tuple(item for item in PROJECTS if item[0] == PROJECT_BY_NAME[name])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", choices=("all", "patentbert", "dsr-pi", "grace-period"),
                        default="all")
    args = parser.parse_args()
    for slug, min_publications in selected_projects(args.name):
        state = open_project(slug)
        df = state["df"]

        terms = NetworkGenerator(df)
        allowed = choose_terms(terms, slug=slug)
        terms.build_keyword_cooccurrence(
            min_occurrence=3, field="titles_abstracts", allowed_terms=allowed,
            normalize_strength=False,
        )
        # Resumos longos fazem quase todos os 70 termos coocorrerem. O mapa de
        # 2.000+ arestas vira um bloco visual; preservar as 350 ligações mais
        # frequentes mantém a rede e a seleção verificáveis em arestas.csv.
        strongest = sorted(
            terms.G.edges(data=True),
            key=lambda edge: (-edge[2].get("weight", 0), str(edge[0]), str(edge[1])),
        )[:350]
        keep_edges = {frozenset((u, v)) for u, v, _ in strongest}
        terms.G.remove_edges_from(
            (u, v) for u, v in list(terms.G.edges())
            if frozenset((u, v)) not in keep_edges
        )
        prune_network(terms.G, remove_isolated=True)
        terms.apply_clustering()
        for node in terms.G:
            documents = int(terms.G.nodes[node].get("doc_freq") or 0)
            terms.G.nodes[node]["size"] = 10 + 2 * documents
            terms.G.nodes[node]["occurrence"] = documents
        term_positions = compute_fa2_layout(terms.G, iterations=160)
        export_map(slug, "termos", terms, term_positions, "Termos · títulos e resumos")

        coauth = NetworkGenerator(df)
        coauth.build_coauthorship_network(
            min_publications=min_publications, max_nodes=100,
        )
        prune_network(coauth.G, remove_isolated=True)
        if coauth.G.number_of_edges():
            coauth_positions = compute_fa2_layout(coauth.G, iterations=160)
            label = ("Coautoria · autores com ≥2 trabalhos" if min_publications == 2
                     else "Coautoria · autores com ≥1 trabalho")
            export_map(slug, "coautoria", coauth, coauth_positions, label)

        config = state["config"] | {
            "map_type": "Coocorrência de Palavras-chave",
            "field": "titles_abstracts",
            "min_occ": 3,
            "max_nodes": 70,
            "assoc_strength": False,
            "fa2_iter": 160,
            "map_params": {
                "fields": "title_abstract", "binary_count": True,
                "min_occurrences": 3,
            },
            "term_selection": {
                "maximum": 70, "minimum_documents": 3,
                "maximum_single_words": 16,
                "excluded": sorted(GENERIC_TERMS | PROJECT_TERM_EXCLUSIONS.get(slug, set())),
                "selected": sorted(allowed),
            },
        }
        thumbnail = project_dir(slug) / "exports" / "termos" / "mapa.png"
        save_blicsa_project(
            str(project_dir(slug) / "project.blicsa"), df, config,
            term_positions, terms.G, cluster_labels=None,
            searches=state.get("searches"), thumbnail_path=str(thumbnail),
        )
        append_backlog(slug, "analysis", {
            "active_map": "termos", "terms": len(allowed),
            "coauth_min_publications": min_publications,
            "coauth_interpretation": (
                "colaboração recorrente" if min_publications == 2
                else "equipes de artigos; não implica colaboração recorrente"
            ),
        })


if __name__ == "__main__":
    main()
