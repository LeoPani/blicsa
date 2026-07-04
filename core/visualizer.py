import math
import numpy as np
import networkx as nx
import plotly.graph_objects as go
from fa2_modified import ForceAtlas2

from .matrix_builders import CLUSTER_PALETTE

DARK_BG    = "#ffffff"
PAPER_BG   = "#f8f9fa"
ACCENT     = "#0f172a"
TEXT_COLOR = "#334155"


def compute_fa2_layout(G: nx.Graph, iterations: int = 500, linlog: bool = False) -> dict:
    if G.number_of_nodes() == 0:
        return {}
    if G.number_of_nodes() == 1:
        return {list(G.nodes())[0]: np.array([0.0, 0.0])}

    fa2 = ForceAtlas2(
        outboundAttractionDistribution=True,
        linLogMode=linlog,
        adjustSizes=False,
        edgeWeightInfluence=1.0,
        jitterTolerance=1.0,
        barnesHutOptimize=True,
        barnesHutTheta=1.2,
        multiThreaded=False,
        scalingRatio=2.0,
        strongGravityMode=False,
        gravity=1.0,
        verbose=False,
    )
    return fa2.forceatlas2_networkx_layout(G, pos=None, iterations=iterations)


def build_plotly_map(
    G: nx.Graph,
    positions: dict,
    title: str = "Blicsa — Mapeamento Bibliométrico",
    color_mode: str = "cluster",
    df=None,
) -> go.Figure:
    PAPER = "#F6F4EE"
    INK = "#141414"
    CLUSTER_PALETTE = ["#DF3117", "#1E4DA0", "#F5BE00", "#141414", "#7A9E7E", "#B65CA2", "#5CB0B8", "#C97B2D"]
    
    if not positions or G.number_of_nodes() == 0:
        fig = go.Figure()
        fig.update_layout(paper_bgcolor=PAPER, plot_bgcolor=PAPER, font_color=INK)
        return fig

    partition = nx.get_node_attributes(G, "group")
    nodes = list(G.nodes())
    
    # Calculate top N nodes for labels (default 25)
    weights = {n: G.nodes[n].get("weight", G.degree(n)) for n in nodes}
    top_nodes = set(sorted(nodes, key=lambda n: weights[n], reverse=True)[:25])

    # Nodes
    xs = [positions[n][0] for n in nodes]
    ys = [positions[n][1] for n in nodes]
    node_w = np.array([weights[n] for n in nodes], float)
    mn, mx = node_w.min(), node_w.max()
    span = mx - mn if mx != mn else 1
    # size scaled
    node_px = 10 + 40 * ((node_w - mn) / span)
    
    node_colors = [CLUSTER_PALETTE[partition.get(n, 0) % len(CLUSTER_PALETTE)] for n in nodes]

    traces = []
    
    # Flat cluster panels
    # To do this in Plotly without complex shapes, we can just omit or use scatter convex hulls. We'll skip complex convex hull for Plotly and focus on edges/nodes unless specifically required.
    
    # Edges
    if G.number_of_edges() > 0:
        edges_data = [(u, v, G[u][v].get("weight", 1)) for u, v in G.edges()]
        edges_data.sort(key=lambda x: x[2], reverse=True)
        # top 20%
        top_k = max(1, int(len(edges_data) * 0.2))
        top_edges = edges_data[:top_k]
        
        edge_x = []
        edge_y = []
        
        for u, v, w in top_edges:
            edge_x.extend([positions[u][0], positions[v][0], None])
            edge_y.extend([positions[u][1], positions[v][1], None])
            
        traces.append(go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line=dict(width=1, color="rgba(0,0,0,0.1)"),
            hoverinfo="none",
            showlegend=False,
        ))

    # Labels
    texts = [n if n in top_nodes else "" for n in nodes]
    text_sizes = [max(9, int(px/2)) for px in node_px]
    
    hover_texts = []
    for n in nodes:
        occur = G.nodes[n].get("occurrence", G.nodes[n].get("weight", 0))
        hover_texts.append(f"{n}<br>Cluster: {partition.get(n,0)}<br>Occurrences: {occur}")
    
    traces.append(go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        text=texts,
        textposition="top center",
        textfont=dict(color=INK, size=text_sizes, family="Inter, sans-serif"),
        marker=dict(
            size=node_px,
            color=node_colors,
            line=dict(width=3, color=PAPER),
            opacity=1.0,
        ),
        hoverinfo="text",
        hovertext=hover_texts,
        showlegend=False,
    ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        paper_bgcolor=PAPER,
        plot_bgcolor=PAPER,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, ticks=""),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, ticks="", scaleanchor="x"),
        margin=dict(l=3, r=3, t=3, b=3),
        showlegend=False,
        coloraxis_showscale=False,
    )
    # 3px ink border -> in plot_bgcolor/paper_bgcolor or via CSS? Plotly layout border:
    fig.update_xaxes(showline=True, linewidth=3, linecolor=INK, mirror=True)
    fig.update_yaxes(showline=True, linewidth=3, linecolor=INK, mirror=True)
    
    return fig


    partition = nx.get_node_attributes(G, "group")
    raw_sizes = nx.get_node_attributes(G, "size")
    year_means = nx.get_node_attributes(G, "year_mean")
    nodes = list(G.nodes())
    xs = [positions[n][0] for n in nodes]
    ys = [positions[n][1] for n in nodes]

    raw = [raw_sizes.get(n, 20) for n in nodes]
    mn, mx = min(raw), max(raw)
    span = mx - mn if mx != mn else 1
    node_px = [10 + 30 * (v - mn) / span for v in raw]

    # ── Color determination ───────────────────────────────────────────
    if color_mode == "cluster":
        node_colors = [
            CLUSTER_PALETTE[partition.get(n, 0) % len(CLUSTER_PALETTE)]
            for n in nodes
        ]
        colorbar_cfg = None
        use_colorscale = False
    elif color_mode == "degree":
        degrees = [G.degree(n, weight="weight") for n in nodes]
        node_colors = degrees
        colorbar_cfg = dict(
            title="Grau ponderado",
            tickfont=dict(color=TEXT_COLOR),
            titlefont=dict(color=TEXT_COLOR),
        )
        use_colorscale = True
    elif color_mode == "year":
        yrs = [year_means.get(n, 0) for n in nodes]
        valid_yrs = [y for y in yrs if y > 0]
        if valid_yrs:
            node_colors = yrs
            colorbar_cfg = dict(
                title="Ano médio",
                tickfont=dict(color=TEXT_COLOR),
                titlefont=dict(color=TEXT_COLOR),
            )
            use_colorscale = True
        else:
            node_colors = [CLUSTER_PALETTE[0]] * len(nodes)
            colorbar_cfg = None
            use_colorscale = False
    else:
        node_colors = ["#5b6af0"] * len(nodes)
        colorbar_cfg = None
        use_colorscale = False

    clusters = sorted(set(partition.values())) if partition else [0]
    legend_added: set = set()
    traces: list[go.BaseTraceType] = []

    # ── Edge traces ───────────────────────────────────────────────────
    weights = [G[u][v].get("weight", 1) for u, v in G.edges()]
    max_w = max(weights) if weights else 1

    for (u, v), w in zip(G.edges(), weights):
        xu, yu = positions[u]
        xv, yv = positions[v]
        alpha = 0.15 + 0.35 * (w / max_w)
        width = 0.4 + 2.2 * (w / max_w)
        traces.append(go.Scatter(
            x=[xu, xv, None], y=[yu, yv, None],
            mode="lines",
            line=dict(width=width, color=f"rgba(148,163,184,{alpha:.2f})"),
            hoverinfo="none",
            showlegend=False,
        ))

    # ── Node traces ───────────────────────────────────────────────────
    if use_colorscale:
        hover = [
            f"<b>{nodes[i]}</b><br>"
            f"Cluster: {partition.get(nodes[i], 0)}<br>"
            f"Grau: {G.degree(nodes[i], weight='weight'):.1f}<br>"
            f"Ano médio: {year_means.get(nodes[i], '—')}"
            for i in range(len(nodes))
        ]
        traces.append(go.Scatter(
            x=xs, y=ys,
            mode="markers+text",
            name="Nós",
            showlegend=False,
            text=[nodes[i] if node_px[i] > 16 else "" for i in range(len(nodes))],
            textposition="top center",
            textfont=dict(size=9, color=TEXT_COLOR, family="Inter, sans-serif"),
            hovertext=hover,
            hoverinfo="text",
            marker=dict(
                size=node_px,
                color=node_colors,
                colorscale="Viridis",
                colorbar=colorbar_cfg,
                line=dict(width=1.5, color="rgba(255,255,255,1.0)"),
                opacity=0.95,
            ),
        ))
    else:
        for clust in clusters:
            mask = [i for i, n in enumerate(nodes) if partition.get(n, 0) == clust]
            if not mask:
                continue
            color = CLUSTER_PALETTE[clust % len(CLUSTER_PALETTE)]
            hover = [
                f"<b>{nodes[i]}</b><br>"
                f"Cluster: {clust}<br>"
                f"Grau: {G.degree(nodes[i], weight='weight'):.1f}<br>"
                f"Ocorrências: {G.nodes[nodes[i]].get('occurrence', '—')}<br>"
                f"Ano médio: {year_means.get(nodes[i], '—')}"
                for i in mask
            ]
            show = clust not in legend_added
            legend_added.add(clust)
            traces.append(go.Scatter(
                x=[xs[i] for i in mask],
                y=[ys[i] for i in mask],
                mode="markers+text",
                name=f"Cluster {clust}",
                legendgroup=f"cluster_{clust}",
                showlegend=show,
                text=[nodes[i] if node_px[i] > 16 else "" for i in mask],
                textposition="top center",
                textfont=dict(size=9, color=TEXT_COLOR, family="Inter, sans-serif"),
                hovertext=hover,
                hoverinfo="text",
                marker=dict(
                    size=[node_px[i] for i in mask],
                    color=color,
                    line=dict(width=1.5, color="rgba(255,255,255,1.0)"),
                    opacity=0.95,
                ),
            ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=16, color=ACCENT, family="Inter, sans-serif"),
            x=0.5,
        ),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=TEXT_COLOR, family="Inter, sans-serif"),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x"),
        legend=dict(
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="rgba(148,163,184,0.3)",
            borderwidth=1,
            font=dict(size=11, color=TEXT_COLOR),
            itemsizing="constant",
        ),
        hovermode="closest",
        dragmode="pan",
        margin=dict(l=20, r=20, t=50, b=20),
        height=750,
        modebar=dict(
            bgcolor="rgba(0,0,0,0)",
            color=TEXT_COLOR,
            activecolor=ACCENT,
        ),
    )

    return fig


def export_plotly_html(fig: go.Figure, path: str):
    fig.write_html(
        path,
        include_plotlyjs="cdn",
        config={
            "scrollZoom": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )


def build_plotly_density(
    G: nx.Graph,
    positions: dict,
    title: str = "Blicsa — Mapa de Densidade",
) -> go.Figure:
    """Plotly contour density view weighted by node occurrence."""
    if not positions:
        return go.Figure()

    nodes = list(G.nodes())
    raw_sizes = nx.get_node_attributes(G, "size")
    xs = [positions[n][0] for n in nodes]
    ys = [positions[n][1] for n in nodes]
    weights = [raw_sizes.get(n, 10) for n in nodes]

    fig = go.Figure()
    fig.add_trace(go.Histogram2dContour(
        x=xs, y=ys, z=weights,
        colorscale="PuBu",
        reversescale=False,
        showscale=True,
        line=dict(width=0),
        opacity=0.85,
        name="Densidade",
        colorbar=dict(
            title="Intensidade",
            titlefont=dict(color=TEXT_COLOR),
            tickfont=dict(color=TEXT_COLOR),
        ),
    ))
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        text=[n if raw_sizes.get(n, 10) > 20 else "" for n in nodes],
        textposition="top center",
        textfont=dict(size=8, color=TEXT_COLOR),
        hovertext=[f"<b>{n}</b>" for n in nodes],
        hoverinfo="text",
        marker=dict(size=5, color="#1e293b", opacity=0.8),
        showlegend=False,
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color=ACCENT), x=0.5),
        paper_bgcolor=PAPER_BG, plot_bgcolor=DARK_BG,
        font=dict(color=TEXT_COLOR),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x"),
        height=750,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def export_figure_image(fig, path: str, dpi: int = 300):
    """Save a matplotlib Figure to PNG, SVG, or PDF based on extension."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"[Export] Imagem → {path} (dpi={dpi})\n")


def build_sankey_diagram(df, field1="authors", field2="keywords", field3="source", top_n=10) -> go.Figure:
    """
    Builds a Plotly Sankey diagram mapping flow from field1 -> field2 -> field3.
    """
    import plotly.graph_objects as go
    from collections import Counter
    
    def get_relations(data, f1, f2):
        relations = []
        for _, row in data.iterrows():
            v1_list = [x.strip() for x in str(row.get(f1, "")).split(";") if x.strip()]
            v2_list = [x.strip() for x in str(row.get(f2, "")).split(";") if x.strip()]
            for v1 in v1_list:
                for v2 in v2_list:
                    relations.append((v1, v2))
        return relations

    rel1 = get_relations(df, field1, field2)
    rel2 = get_relations(df, field2, field3)
    
    if not rel1 and not rel2:
        fig = go.Figure()
        fig.update_layout(title="Sem dados de fluxo para gerar Sankey")
        return fig
        
    def get_top_items(relations, idx, top_n):
        items = [r[idx] for r in relations]
        return [item for item, _ in Counter(items).most_common(top_n)]

    top_f1 = get_top_items(rel1, 0, top_n)
    top_f2 = list(set(get_top_items(rel1, 1, top_n) + get_top_items(rel2, 0, top_n)))
    top_f3 = get_top_items(rel2, 1, top_n)
    
    rel1_filtered = [r for r in rel1 if r[0] in top_f1 and r[1] in top_f2]
    rel2_filtered = [r for r in rel2 if r[0] in top_f2 and r[1] in top_f3]
    
    counts1 = Counter(rel1_filtered)
    counts2 = Counter(rel2_filtered)
    
    nodes = top_f1 + top_f2 + top_f3
    node_to_idx = {n: i for i, n in enumerate(nodes)}
    
    colors = []
    palette = [
        "rgba(31, 119, 180, 0.8)", "rgba(255, 127, 14, 0.8)", "rgba(44, 160, 44, 0.8)",
        "rgba(214, 39, 40, 0.8)", "rgba(148, 103, 189, 0.8)", "rgba(140, 86, 75, 0.8)",
        "rgba(227, 119, 194, 0.8)", "rgba(127, 127, 127, 0.8)", "rgba(188, 189, 34, 0.8)",
        "rgba(23, 190, 207, 0.8)"
    ]
    for i, n in enumerate(nodes):
        colors.append(palette[i % len(palette)])
        
    sources = []
    targets = []
    values = []
    
    for (src, tgt), val in counts1.items():
        sources.append(node_to_idx[src])
        targets.append(node_to_idx[tgt])
        values.append(val)
        
    for (src, tgt), val in counts2.items():
        sources.append(node_to_idx[src])
        targets.append(node_to_idx[tgt])
        values.append(val)
        
    fig = go.Figure(data=[go.Sankey(
        node = dict(
          pad = 15,
          thickness = 20,
          line = dict(color = "black", width = 0.5),
          label = [n.upper() for n in nodes],
          color = colors
        ),
        link = dict(
          source = sources,
          target = targets,
          value = values,
          color = "rgba(200, 200, 200, 0.4)"
        )
    )])
    
    label_map = {
        "authors": "Autores",
        "keywords": "Palavras-chave",
        "source": "Fontes (Journals)",
        "year": "Ano"
    }
    
    fig.update_layout(
        title_text=f"Três Campos: {label_map.get(field1, field1)} → {label_map.get(field2, field2)} → {label_map.get(field3, field3)}",
        font_size=11,
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=DARK_BG,
        font_color=TEXT_COLOR,
        height=700,
        margin=dict(l=30, r=30, t=60, b=30),
    )
    return fig


def build_timeline_view(G: nx.Graph, pos: dict, title: str = "Blicsa — Visualização em Linha do Tempo") -> go.Figure:
    """
    Creates a timeline layout of the network where:
      - X-axis = Average publication year of the term
      - Y-axis = Louvain cluster ID
    Draws horizontal cluster guides and connecting lines for top edges.
    """
    import plotly.graph_objects as go
    
    nodes = list(G.nodes())
    if not nodes:
        return go.Figure()
        
    partition = nx.get_node_attributes(G, "group")
    raw_sizes = nx.get_node_attributes(G, "size")
    year_means = nx.get_node_attributes(G, "year_mean")
    
    nodes_with_year = [n for n in G.nodes() if year_means.get(n, 0) > 0]
    if not nodes_with_year:
        fig = go.Figure()
        fig.update_layout(title="Sem dados de ano médio para gerar Linha do Tempo")
        return fig
        
    xs = [year_means[n] for n in nodes_with_year]
    ys = [partition.get(n, 0) for n in nodes_with_year]
    sizes = [raw_sizes.get(n, 10) for n in nodes_with_year]
    
    min_sz, max_sz = min(sizes) if sizes else 1, max(sizes) if sizes else 1
    span = max_sz - min_sz if max_sz != min_sz else 1
    plotly_sizes = [8 + 32 * (s - min_sz) / span for s in sizes]
    
    clusters = sorted(list(set(ys)))
    
    fig = go.Figure()
    
    min_x, max_x = min(xs) if xs else 2000, max(xs) if xs else 2024
    padding = (max_x - min_x) * 0.05 if max_x != min_x else 1
    x_range = [min_x - padding, max_x + padding]
    
    for c in clusters:
        fig.add_trace(go.Scatter(
            x=x_range,
            y=[c, c],
            mode="lines",
            line=dict(color="rgba(148, 163, 184, 0.3)", width=1, dash="dash"),
            hoverinfo="none",
            showlegend=False
        ))
        
    weights = [G[u][v].get("weight", 1) for u, v in G.edges()]
    max_w = max(weights) if weights else 1
    thresh = 0.25 * max_w
    
    edge_x = []
    edge_y = []
    for u, v in G.edges():
        if G[u][v].get("weight", 0) < thresh:
            continue
        if u not in nodes_with_year or v not in nodes_with_year:
            continue
        xu, yu = year_means[u], partition.get(u, 0)
        xv, yv = year_means[v], partition.get(v, 0)
        
        edge_x.extend([xu, xv, None])
        edge_y.extend([yu, yv, None])
        
    if edge_x:
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(color="rgba(148, 163, 184, 0.25)", width=0.8),
            hoverinfo="none",
            showlegend=False
        ))
        
    legend_added = set()
    for c in clusters:
        cluster_nodes = [n for n in nodes_with_year if partition.get(n, 0) == c]
        c_xs = [year_means[n] for n in cluster_nodes]
        c_ys = [partition.get(n, 0) for n in cluster_nodes]
        c_sizes = [plotly_sizes[nodes_with_year.index(n)] for n in cluster_nodes]
        
        color = CLUSTER_PALETTE[c % len(CLUSTER_PALETTE)]
        hover_text = [
            f"<b>{n}</b><br>Ano Médio: {year_means[n]:.2f}<br>Ocorrências: {G.nodes[n].get('occurrence', '—')}"
            for n in cluster_nodes
        ]
        
        fig.add_trace(go.Scatter(
            x=c_xs, y=c_ys,
            mode="markers+text",
            name=f"Cluster {c}",
            text=[n if raw_sizes.get(n, 10) > max_sz * 0.4 else "" for n in cluster_nodes],
            textposition="top center",
            textfont=dict(size=9, color=TEXT_COLOR),
            hovertext=hover_text,
            hoverinfo="text",
            marker=dict(
                size=c_sizes,
                color=color,
                line=dict(color="rgba(255,255,255,1.0)", width=1.5),
                opacity=0.9
            ),
            legendgroup=f"group_{c}",
            showlegend=True
        ))
        
    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            font=dict(size=16, color=ACCENT, family="Inter, sans-serif")
        ),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=TEXT_COLOR, family="Inter, sans-serif"),
        xaxis=dict(
            title="Ano Médio de Publicação",
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.15)",
            tickmode="linear",
            dtick=1
        ),
        yaxis=dict(
            title="ID do Cluster (Grupo Louvain)",
            showgrid=False,
            tickvals=clusters,
            ticktext=[f"Cluster {c}" for c in clusters]
        ),
        hovermode="closest",
        height=750,
        margin=dict(l=80, r=40, t=60, b=60)
    )
    return fig


def build_thematic_map(G: nx.Graph, title: str = "Blicsa — Mapa Temático (Diagrama Estratégico)") -> go.Figure:
    """
    Computes Callon Centrality & Density for each Louvain cluster and plots them
    on a 2D scatter plot divided into 4 strategic quadrants.
    """
    import plotly.graph_objects as go
    import numpy as np
    
    partition = nx.get_node_attributes(G, "group")
    if not partition:
        fig = go.Figure()
        fig.update_layout(title="Sem dados de clusters para gerar o Mapa Temático")
        return fig
        
    clusters: dict[int, list[str]] = {}
    for node, grp in partition.items():
        clusters.setdefault(grp, []).append(node)
        
    data = []
    for c, nodes in clusters.items():
        # Centrality (Callon): sum of weights of edges connecting to external nodes
        cent = 0.0
        for u in nodes:
            for v in G.neighbors(u):
                if v not in nodes:
                    cent += G[u][v].get("weight", 1.0)
                    
        # Density (Callon): sum of weights of internal edges divided by node count
        dens = 0.0
        for u in nodes:
            for v in G.neighbors(u):
                if v in nodes:
                    dens += G[u][v].get("weight", 1.0)
        dens = (dens / 2.0) / len(nodes)
        
        top_t = sorted(nodes, key=lambda n: G.nodes[n].get("occurrence", 0), reverse=True)[:5]
        data.append({
            "cluster": c,
            "centrality": cent,
            "density": dens,
            "size": len(nodes),
            "top_nodes": top_t
        })
        
    if not data:
        return go.Figure()
        
    cents = [d["centrality"] for d in data]
    densities = [d["density"] for d in data]
    sizes = [d["size"] for d in data]
    
    med_cent = float(np.median(cents)) if cents else 0.0
    med_dens = float(np.median(densities)) if densities else 0.0
    
    fig = go.Figure()
    
    min_cent, max_cent = min(cents, default=0), max(cents, default=1)
    min_dens, max_dens = min(densities, default=0), max(densities, default=1)
    
    cent_pad = (max_cent - min_cent) * 0.15 or 0.5
    dens_pad = (max_dens - min_dens) * 0.15 or 0.5
    
    x_min, x_max = min_cent - cent_pad, max_cent + cent_pad
    y_min, y_max = min_dens - dens_pad, max_dens + dens_pad
    
    for d in data:
        c = d["cluster"]
        color = CLUSTER_PALETTE[c % len(CLUSTER_PALETTE)]
        hover = (
            f"<b>Cluster {c}</b><br>"
            f"Nós: {d['size']}<br>"
            f"Centralidade: {d['centrality']:.2f}<br>"
            f"Densidade: {d['density']:.4f}<br>"
            f"Termos: {', '.join(d['top_nodes'])}"
        )
        
        fig.add_trace(go.Scatter(
            x=[d["centrality"]],
            y=[d["density"]],
            mode="markers+text",
            name=f"Cluster {c}",
            text=[f"C{c}: {d['top_nodes'][0]}"],
            textposition="top center",
            hovertext=[hover],
            hoverinfo="text",
            marker=dict(
                size=[12 + 30 * (d["size"] / max(sizes, default=1))],
                color=color,
                opacity=0.85,
                line=dict(color="rgba(255,255,255,1.0)", width=1.5)
            ),
            showlegend=True
        ))
        
    fig.add_shape(type="line", x0=med_cent, y0=y_min, x1=med_cent, y1=y_max,
                  line=dict(color="rgba(148, 163, 184, 0.4)", width=1.5, dash="dash"))
    fig.add_shape(type="line", x0=x_min, y0=med_dens, x1=x_max, y1=med_dens,
                  line=dict(color="rgba(148, 163, 184, 0.4)", width=1.5, dash="dash"))
                  
    def add_quad_label(x, y, text):
        fig.add_annotation(
            x=x, y=y, text=text, showarrow=False,
            font=dict(size=11, color="rgba(71, 85, 105, 0.8)", weight="bold"),
            bgcolor="rgba(241, 245, 249, 0.75)", bordercolor="rgba(203, 213, 225, 0.5)",
            borderwidth=1, borderpad=4
        )
        
    add_quad_label(x_min + (med_cent - x_min)*0.5, y_max - (y_max - med_dens)*0.1, "<b>Temas Especializados</b> (Niche)")
    add_quad_label(max_cent - (max_cent - med_cent)*0.5, y_max - (y_max - med_dens)*0.1, "<b>Temas Motores</b> (Motor)")
    add_quad_label(x_min + (med_cent - x_min)*0.5, y_min + (med_dens - y_min)*0.1, "<b>Temas Emergentes/Declínio</b>")
    add_quad_label(max_cent - (max_cent - med_cent)*0.5, y_min + (med_dens - y_min)*0.1, "<b>Temas Básicos/Transversais</b>")
    
    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            font=dict(size=16, color=ACCENT, family="Inter, sans-serif")
        ),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=TEXT_COLOR, family="Inter, sans-serif"),
        xaxis=dict(
            title="Centralidade de Callon (Callon Centrality - relevância externa)",
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.15)",
            range=[x_min, x_max]
        ),
        yaxis=dict(
            title="Densidade de Callon (Callon Density - maturidade interna)",
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.15)",
            range=[y_min, y_max]
        ),
        hovermode="closest",
        height=700,
        margin=dict(l=80, r=40, t=60, b=60)
    )
    return fig


def build_historiograph(df, top_n: int = 25, title: str = "Blicsa — Historiografia de Citações Diretas") -> go.Figure:
    """
    Constructs a directed graph of direct citations among the top-cited papers,
    arranged chronologically from left to right.
    """
    import plotly.graph_objects as go
    import networkx as nx
    from collections import defaultdict
    import re
    
    if df is None or df.empty or "references" not in df.columns or "year" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="Sem dados de referências/ano para gerar a Historiografia")
        return fig
        
    top_papers = df.sort_values(by="citations", ascending=False).head(top_n).copy()
    
    nodes_data = []
    for idx, row in top_papers.iterrows():
        authors = str(row.get("authors", ""))
        sep = ";" if ";" in authors else ","
        lead_author = "Anon"
        if authors:
            first = authors.split(sep)[0].strip()
            surname = first.split()[-1] if first.split() else first
            surname = re.sub(r"[^A-Za-z\-]", "", surname)
            if surname:
                lead_author = surname
                
        year = int(row.get("year", 0) or 0)
        label = f"{lead_author} ({year})"
        
        nodes_data.append({
            "id": idx,
            "label": label,
            "author": lead_author,
            "year": year,
            "title": str(row.get("title", "")),
            "citations": int(row.get("citations", 0)),
            "doi": str(row.get("doi", "")).strip().lower(),
            "refs": str(row.get("references", "")).lower()
        })
        
    H = nx.DiGraph()
    for nd in nodes_data:
        H.add_node(nd["id"], **nd)
        
    for u in H.nodes():
        u_refs = H.nodes[u]["refs"]
        u_year = H.nodes[u]["year"]
        
        for v in H.nodes():
            if u == v:
                continue
            v_year = H.nodes[v]["year"]
            if u_year < v_year:
                continue
                
            v_doi = H.nodes[v]["doi"]
            v_author = H.nodes[v]["author"].lower()
            
            cited = False
            if v_doi and len(v_doi) > 4 and v_doi in u_refs:
                cited = True
            elif v_author and len(v_author) > 2 and str(v_year) in u_refs and v_author in u_refs:
                cited = True
                
            if cited:
                H.add_edge(u, v)
                
    years_map = defaultdict(list)
    for u in H.nodes():
        y = H.nodes[u]["year"]
        years_map[y].append(u)
        
    pos = {}
    for y, u_list in years_map.items():
        count = len(u_list)
        for idx, u in enumerate(u_list):
            pos[u] = (y, idx - (count - 1) / 2.0)
            
    fig = go.Figure()
    
    edge_x = []
    edge_y = []
    for u, v in H.edges():
        xu, yu = pos[u]
        xv, yv = pos[v]
        edge_x.extend([xu, xv, None])
        edge_y.extend([yu, yv, None])
        
    if edge_x:
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(color="rgba(99, 102, 241, 0.4)", width=1.5),
            hoverinfo="none",
            showlegend=False
        ))
        
    node_x = [pos[u][0] for u in H.nodes()]
    node_y = [pos[u][1] for u in H.nodes()]
    node_text = [H.nodes[u]["label"] for u in H.nodes()]
    node_hover = [
        f"<b>{H.nodes[u]['label']}</b><br>"
        f"Citações: {H.nodes[u]['citations']}<br>"
        f"Título: {H.nodes[u]['title']}"
        for u in H.nodes()
    ]
    
    years = [H.nodes[u]["year"] for u in H.nodes()]
    
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont=dict(size=9, color=TEXT_COLOR),
        hovertext=node_hover,
        hoverinfo="text",
        marker=dict(
            size=18,
            color=years,
            colorscale="Viridis",
            line=dict(color="rgba(255,255,255,1.0)", width=1.5),
            showscale=True,
            colorbar=dict(title="Ano", thickness=15, x=1.05)
        ),
        showlegend=False
    ))
    
    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            font=dict(size=16, color=ACCENT, family="Inter, sans-serif")
        ),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color=TEXT_COLOR, family="Inter, sans-serif"),
        xaxis=dict(
            title="Ano de Publicação",
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.15)",
            tickmode="linear",
            dtick=1
        ),
        yaxis=dict(
            title="Artigos no mesmo Ano",
            showgrid=False,
            zeroline=False,
            showticklabels=False
        ),
        hovermode="closest",
        height=680,
        margin=dict(l=40, r=60, t=60, b=60)
    )
    return fig
