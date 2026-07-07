import re
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

comp_code = re.sub(r'    def _redraw\(.*?    def highlight_node\(', new_redraw + "    def highlight_node(", comp_code, flags=re.DOTALL)
with open(comp_file, 'w') as f:
    f.write(comp_code)
