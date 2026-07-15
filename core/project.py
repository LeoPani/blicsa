import json
import zipfile
import gzip
import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import networkx as nx

logger = logging.getLogger("blicsa.project")

CURRENT_MANIFEST_VERSION = "1.0"

# ── Projeto = PASTA (~/Blicsa/projects/<slug>/) ─────────────────────────────
#   project.blicsa   snapshot salvo (formato ZIP atual, intocado)
#   backlog.jsonl    APPEND-ONLY, uma linha JSON por ação (fora do ZIP de
#                    propósito: reescrever ZIP a cada ação convida corrupção)
#   searches/        JSON bruto de cada busca (search_<ts>.json) p/ reuso offline
#   exports/         saídas geradas (mapas, CSV, GML, XLSX)

PROJECTS_DIR = Path.home() / "Blicsa" / "projects"

BACKLOG_ACTIONS = ("search", "import", "dedup", "corpus_add", "analysis",
                   "export", "map", "extension_add")


def slugify(name: str) -> str:
    """Nome legível → slug de pasta (ascii, minúsculo, hífens)."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "projeto"


def project_dir(slug: str, projects_dir=None) -> Path:
    return Path(projects_dir or PROJECTS_DIR) / slug


def _unique_slug(name: str, base: Path) -> str:
    slug = slugify(name)
    candidate, n = slug, 2
    while (base / candidate).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def _scaffold(d: Path):
    (d / "searches").mkdir(parents=True, exist_ok=True)
    (d / "exports").mkdir(parents=True, exist_ok=True)
    (d / "backlog.jsonl").touch()


def create_project(name: str, projects_dir=None) -> str:
    """Cria a pasta do projeto com snapshot vazio + backlog. Retorna o slug."""
    base = Path(projects_dir or PROJECTS_DIR)
    base.mkdir(parents=True, exist_ok=True)
    slug = _unique_slug(name, base)
    d = base / slug
    _scaffold(d)
    save_blicsa_project(str(d / "project.blicsa"), df=None,
                        config={"name": name}, positions=None, G=None,
                        cluster_labels=None)
    return slug


def open_project(slug: str, projects_dir=None) -> dict:
    """Abre <slug>/project.blicsa e devolve o estado + backlog + caminhos."""
    d = project_dir(slug, projects_dir)
    data = load_blicsa_project(str(d / "project.blicsa"))
    data["slug"] = slug
    data["path"] = str(d)
    data["backlog"] = load_backlog(slug, projects_dir)
    return data


def append_backlog(slug: str, action: str, detail: dict, projects_dir=None) -> dict:
    """Acrescenta UMA linha ao backlog.jsonl (append-only, nunca reescreve)."""
    d = project_dir(slug, projects_dir)
    _scaffold(d)  # tolera projetos migrados sem subpastas
    entry = {"ts": datetime.now().isoformat(timespec="seconds"),
             "action": action, "detail": detail or {}}
    with open(d / "backlog.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_backlog(slug: str, projects_dir=None) -> list:
    """Lê o backlog inteiro; linha corrompida é PULADA com warning (as demais
    continuam legíveis — resiliência do append-only)."""
    path = project_dir(slug, projects_dir) / "backlog.jsonl"
    entries = []
    if not path.exists():
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                logger.warning(f"[Backlog] linha {n} corrompida em {path} — pulada")
    return entries


def save_search_raw(slug: str, records: list, projects_dir=None) -> str:
    """Grava o JSON bruto de uma busca em searches/search_<ts>.json.
    Retorna o caminho RELATIVO à pasta do projeto (vai no backlog)."""
    d = project_dir(slug, projects_dir)
    _scaffold(d)
    rel = f"searches/search_{int(time.time())}.json"
    with open(d / rel, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return rel


def load_search_raw(slug: str, rel_path: str, projects_dir=None) -> list:
    """Carrega os resultados salvos de uma busca (local-first, sem rede)."""
    with open(project_dir(slug, projects_dir) / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_loose_projects(projects_dir=None) -> list:
    """MIGRAÇÃO SUAVE: cada *.blicsa solto em projects/ vira uma pasta
    <slug>/project.blicsa (arquivo preservado via move). Retorna slugs criados."""
    base = Path(projects_dir or PROJECTS_DIR)
    migrated = []
    if not base.exists():
        return migrated
    for f in sorted(base.glob("*.blicsa")):
        if not f.is_file():
            continue
        slug = _unique_slug(f.stem, base)
        d = base / slug
        _scaffold(d)
        f.rename(d / "project.blicsa")
        migrated.append(slug)
        logger.info(f"[Projects] migrado: {f.name} -> {slug}/project.blicsa")
    return migrated


def list_projects(projects_dir=None) -> list:
    """Slugs das pastas de projeto existentes (com project.blicsa), mais recente 1º."""
    base = Path(projects_dir or PROJECTS_DIR)
    if not base.exists():
        return []
    dirs = [d for d in base.iterdir() if d.is_dir() and (d / "project.blicsa").exists()]
    dirs.sort(key=lambda d: (d / "project.blicsa").stat().st_mtime, reverse=True)
    return [d.name for d in dirs]

def save_blicsa_project(
    path: str,
    df: pd.DataFrame | None,
    config: dict,
    positions: dict | None,
    G: nx.Graph | None,
    cluster_labels: dict | None,
    searches: list | None = None,
    thumbnail_path: str | None = None
):
    """Save full Blicsa project to a .blicsa ZIP archive."""
    manifest = {
        "version": CURRENT_MANIFEST_VERSION,
        "app": "PyBibliomics Blicsa",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Temporary directory or direct writing to zip
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        # Searches
        if searches is not None:
            zf.writestr("searches.json", json.dumps(searches, indent=2, ensure_ascii=False))
            
        # Thumbnail
        if thumbnail_path and os.path.exists(thumbnail_path):
            zf.write(thumbnail_path, "thumbnail.png")

        # 2. Config
        zf.writestr("config.json", json.dumps(config, indent=2, ensure_ascii=False))

        # 3. Dataset (JSON Gzipped)
        if df is not None and not df.empty:
            df_json = df.to_json(orient="records", force_ascii=False)
            compressed_df = gzip.compress(df_json.encode("utf-8"))
            zf.writestr("dataset.json.gz", compressed_df)

        # 4. Layout (Positions)
        if positions:
            # Convert node names to string and positions to list for JSON serialization
            serialized_pos = {str(node): [float(c) for c in coords] for node, coords in positions.items()}
            zf.writestr("layout.json", json.dumps(serialized_pos, indent=2))

        # 5. Network (Graph G)
        if G is not None:
            network_data = {
                "nodes": [{"id": str(n), "attributes": data} for n, data in G.nodes(data=True)],
                "edges": [{"source": str(u), "target": str(v), "attributes": data} for u, v, data in G.edges(data=True)]
            }
            zf.writestr("network.json", json.dumps(network_data, indent=2, ensure_ascii=False))

        # 6. Clusters (Labels)
        if cluster_labels:
            serialized_clusters = {str(k): str(v) for k, v in cluster_labels.items()}
            zf.writestr("clusters.json", json.dumps(serialized_clusters, indent=2, ensure_ascii=False))


def load_blicsa_project(path: str) -> dict:
    """Load full Blicsa project from a .blicsa ZIP archive, with version migration hook."""
    result = {
        "df": None,
        "config": {},
        "positions": {},
        "G": None,
        "cluster_labels": {}
    }

    with zipfile.ZipFile(path, "r") as zf:
        # Read Manifest
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        version = manifest.get("version", "1.0")

        # Version Migration Hook
        if version != CURRENT_MANIFEST_VERSION:
            print(f"[Project] Migrating project version from {version} to {CURRENT_MANIFEST_VERSION}")
            # Insert migrations here if schema ever changes

        # Read Config
        if "config.json" in zf.namelist():
            result["config"] = json.loads(zf.read("config.json").decode("utf-8"))

        # Read Dataset
        if "dataset.json.gz" in zf.namelist():
            import io
            compressed_df = zf.read("dataset.json.gz")
            df_json = gzip.decompress(compressed_df).decode("utf-8")
            result["df"] = pd.read_json(io.StringIO(df_json), orient="records")

        # Read Layout
        if "layout.json" in zf.namelist():
            serialized_pos = json.loads(zf.read("layout.json").decode("utf-8"))
            result["positions"] = {k: v for k, v in serialized_pos.items()}

        # Read Network (Graph)
        if "network.json" in zf.namelist():
            network_data = json.loads(zf.read("network.json").decode("utf-8"))
            G = nx.Graph()
            for node in network_data.get("nodes", []):
                G.add_node(node["id"], **node.get("attributes", {}))
            for edge in network_data.get("edges", []):
                G.add_edge(edge["source"], edge["target"], **edge.get("attributes", {}))
            result["G"] = G
            
        # Read Searches
        if "searches.json" in zf.namelist():
            result["searches"] = json.loads(zf.read("searches.json").decode("utf-8"))
        else:
            result["searches"] = []

        # Read Clusters (Labels)
        if "clusters.json" in zf.namelist():
            serialized_clusters = json.loads(zf.read("clusters.json").decode("utf-8"))
            # Convert keys back to integers for cluster IDs
            result["cluster_labels"] = {int(k): v for k, v in serialized_clusters.items()}

    return result
