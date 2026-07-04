import json
import networkx as nx

def export_sigma_json(G: nx.Graph, positions: dict, filepath: str):
    nodes = []
    edges = []
    
    # Pre-calculate sizes
    raw_sizes = nx.get_node_attributes(G, "size")
    if raw_sizes:
        min_sz, max_sz = min(raw_sizes.values()), max(raw_sizes.values())
        span = max_sz - min_sz if max_sz != min_sz else 1
    else:
        min_sz, span = 0, 1

    for node in G.nodes():
        attr = G.nodes[node]
        x, y = positions.get(node, (0, 0))
        
        raw_sz = raw_sizes.get(node, 10)
        # normalize size for sigma.js (e.g., 2 to 15)
        sigma_size = 3 + 15 * (raw_sz - min_sz) / span
        
        nodes.append({
            "key": str(node),
            "attributes": {
                "x": float(x),
                "y": float(y),
                "size": float(sigma_size),
                "color": attr.get("color", "#1E4DA0"),
                "label": str(attr.get("label", node)),
                "cluster": attr.get("group", 0),
                "occurrence": attr.get("occurrence", 0)
            }
        })
        
    for idx, (u, v, data) in enumerate(G.edges(data=True)):
        edges.append({
            "key": f"e{idx}",
            "source": str(u),
            "target": str(v),
            "attributes": {
                "size": float(data.get("weight", 1)),
                "color": "rgba(20,20,20,0.15)"
            }
        })
        
    graph_data = {
        "options": {
            "type": "undirected",
            "multi": False,
            "allowSelfLoops": False
        },
        "nodes": nodes,
        "edges": edges
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False)

