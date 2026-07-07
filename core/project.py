import json
import zipfile
import gzip
import os
import time
import pandas as pd
import networkx as nx

CURRENT_MANIFEST_VERSION = "1.0"

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
