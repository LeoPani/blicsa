import math
import numpy as np
import networkx as nx
import plotly.graph_objects as go
from fa2_modified import ForceAtlas2

from .matrix_builders import CLUSTER_PALETTE

DARK_BG    = "#0d0d1f"
PAPER_BG   = "#13131f"
ACCENT     = "#D4A017"
TEXT_COLOR = "#e0e0e0"


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
    color_mode: str = "cluster",   # "cluster" | "degree" | "year"
    df=None,
) -> go.Figure:
    if not positions:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=PAPER_BG, plot_bgcolor=DARK_BG,
            font_color=TEXT_COLOR,
            annotations=[dict(
                text="Nenhum nó encontrado.",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16, color=TEXT_COLOR),
            )],
        )
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
        alpha = 0.12 + 0.30 * (w / max_w)
        width = 0.3 + 1.8 * (w / max_w)
        traces.append(go.Scatter(
            x=[xu, xv, None], y=[yu, yv, None],
            mode="lines",
            line=dict(width=width, color=f"rgba(160,160,220,{alpha:.2f})"),
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
            textfont=dict(size=8, color="white"),
            hovertext=hover,
            hoverinfo="text",
            marker=dict(
                size=node_px,
                color=node_colors,
                colorscale="Viridis",
                colorbar=colorbar_cfg,
                line=dict(width=1.0, color="rgba(255,255,255,0.3)"),
                opacity=0.92,
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
                textfont=dict(size=8, color="white"),
                hovertext=hover,
                hoverinfo="text",
                marker=dict(
                    size=[node_px[i] for i in mask],
                    color=color,
                    line=dict(width=1.0, color="rgba(255,255,255,0.3)"),
                    opacity=0.92,
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
            bgcolor="rgba(13,13,31,0.8)",
            bordercolor=ACCENT,
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
        colorscale="Inferno",
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
        textfont=dict(size=7, color="white"),
        hovertext=[f"<b>{n}</b>" for n in nodes],
        hoverinfo="text",
        marker=dict(size=4, color="white", opacity=0.6),
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
