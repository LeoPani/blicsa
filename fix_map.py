import re
import sys

# 1. Fix core/visualizer.py (Plotly)
vis_file = 'core/visualizer.py'
with open(vis_file, 'r') as f:
    vis_code = f.read()

# We'll just replace the whole build_plotly_map function.
new_plotly = """def build_plotly_map(
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
    edge_weights = np.array([G[u][v].get("weight", 1) for u, v in G.edges()], float)
    if len(edge_weights) > 0:
        ew_mn, ew_mx = edge_weights.min(), edge_weights.max()
        ew_span = ew_mx - ew_mn if ew_mx != ew_mn else 1
        
        edge_x = []
        edge_y = []
        
        # Plotly doesn't support per-segment opacity in a single scatter with good performance, but we can group by width/opacity or just use a single line width and opacity if needed.
        # But for exact spec: opacity 8-22%, width 1-4px
        for (u, v), w in zip(G.edges(), edge_weights):
            w_norm = (w - ew_mn) / ew_span
            opacity = 0.08 + 0.14 * w_norm
            width = 1 + 3 * w_norm
            traces.append(go.Scatter(
                x=[positions[u][0], positions[v][0], None],
                y=[positions[u][1], positions[v][1], None],
                mode="lines",
                line=dict(width=width, color=f"rgba(20,20,20,{opacity})"),
                hoverinfo="none",
                showlegend=False,
            ))

    # Labels
    texts = [n if n in top_nodes else "" for n in nodes]
    text_sizes = [max(9, int(px/2)) for px in node_px]
    
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
        hovertext=[f"{n}<br>Cluster: {partition.get(n,0)}<br>Weight: {weights[n]:.1f}" for n in nodes],
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
"""

# replace between def build_plotly_map and def export_plotly_html
vis_code = re.sub(r'def build_plotly_map\(.*?return fig\n', new_plotly + "\n", vis_code, flags=re.DOTALL)
with open(vis_file, 'w') as f:
    f.write(vis_code)

# 2. Fix ui/components.py (Matplotlib MapCanvas)
comp_file = 'ui/components.py'
with open(comp_file, 'r') as f:
    comp_code = f.read()

new_redraw = """    def _redraw(
        self,
        G: nx.Graph,
        pos: dict,
        mode: str,
        node_scale: float,
        edge_opacity: float,
    ):
        import matplotlib.colors as mc
        import matplotlib.patheffects as path_effects
        from scipy.spatial import ConvexHull
        from matplotlib.patches import Polygon

        self._ax.clear()
        
        PAPER = "#F6F4EE"
        INK = "#141414"
        CLUSTER_PALETTE = ["#DF3117", "#1E4DA0", "#F5BE00", "#141414", "#7A9E7E", "#B65CA2", "#5CB0B8", "#C97B2D"]
        
        self._fig.patch.set_facecolor(PAPER)
        self._ax.set_facecolor(PAPER)
        
        # 3px border
        for spine in self._ax.spines.values():
            spine.set_visible(True)
            spine.set_color(INK)
            spine.set_linewidth(3)
            
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._ax.set_aspect("equal", adjustable="datalim")
        
        self._nodes = list(G.nodes())
        if G.number_of_nodes() == 0:
            self._ax.text(0.5, 0.5, "Nenhum nó.", ha="center", va="center", color=INK, transform=self._ax.transAxes)
            self._canvas.draw()
            return

        partition = nx.get_node_attributes(G, "group")
        weights = {n: G.nodes[n].get("weight", G.degree(n)) for n in self._nodes}
        
        xs = np.array([pos[n][0] for n in self._nodes])
        ys = np.array([pos[n][1] for n in self._nodes])

        node_w = np.array([weights[n] for n in self._nodes], float)
        mn, mx = node_w.min(), node_w.max()
        span = mx - mn if mx != mn else 1
        
        # sizes for scatter (points^2)
        sizes = (20 + 400 * (node_w - mn) / span) * node_scale
        
        colors = [CLUSTER_PALETTE[partition.get(n, 0) % len(CLUSTER_PALETTE)] for n in self._nodes]

        # Flat cluster panels
        cluster_points = {}
        for n, x, y in zip(self._nodes, xs, ys):
            c = partition.get(n, 0)
            cluster_points.setdefault(c, []).append((x, y))
            
        for c, pts in cluster_points.items():
            if len(pts) >= 3:
                try:
                    pts_arr = np.array(pts)
                    hull = ConvexHull(pts_arr)
                    poly = Polygon(pts_arr[hull.vertices], closed=True, 
                                 facecolor=CLUSTER_PALETTE[c % len(CLUSTER_PALETTE)], 
                                 alpha=0.08, zorder=0, edgecolor='none')
                    self._ax.add_patch(poly)
                except Exception:
                    pass

        # Edges
        edge_weights = np.array([G[u][v].get("weight", 1) for u, v in G.edges()], float)
        if len(edge_weights) > 0:
            ew_mn, ew_mx = edge_weights.min(), edge_weights.max()
            ew_span = ew_mx - ew_mn if ew_mx != ew_mn else 1
            
            from matplotlib.collections import LineCollection
            lines = []
            line_colors = []
            line_widths = []
            for (u, v), w in zip(G.edges(), edge_weights):
                w_norm = (w - ew_mn) / ew_span
                opacity = 0.08 + 0.14 * w_norm
                width = 1 + 3 * w_norm
                lines.append([pos[u], pos[v]])
                line_colors.append(mc.to_rgba(INK, alpha=opacity))
                line_widths.append(width)
                
            lc = LineCollection(lines, colors=line_colors, linewidths=line_widths, zorder=1)
            self._ax.add_collection(lc)

        # Nodes
        self._ax.scatter(xs, ys, s=sizes, c=colors, edgecolor=PAPER, linewidth=3, zorder=2)

        # Labels (Top 25)
        top_nodes = set(sorted(self._nodes, key=lambda n: weights[n], reverse=True)[:25])
        for n, x, y, s in zip(self._nodes, xs, ys, sizes):
            if n in top_nodes:
                font_size = max(8, int(np.sqrt(s) * 0.4))
                txt = self._ax.text(x, y, str(n), color=INK, fontsize=font_size, 
                                  ha='center', va='center', zorder=3, fontweight='bold')
                txt.set_path_effects([path_effects.withStroke(linewidth=3, foreground=PAPER)])

        self._canvas.draw()
"""

comp_code = re.sub(r'    def _redraw\(\s*self,\s*G: nx\.Graph,\s*pos: dict,\s*mode: str,\s*node_scale: float,\s*edge_opacity: float,\s*\):.*?self\._canvas\.draw\(\)\n', new_redraw, comp_code, flags=re.DOTALL)
with open(comp_file, 'w') as f:
    f.write(comp_code)
