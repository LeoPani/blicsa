# Map Overhaul Evidence Checklist

- [x] Background is paper `#F6F4EE` inside a 3px ink `#141414` border
- [x] No Plotly colorbar, no modebar, no grid, no axis ticks
- [x] Cluster palette in exact order: `#DF3117`, `#1E4DA0`, `#F5BE00`, `#141414`, `#7A9E7E`, `#B65CA2`, `#5CB0B8`, `#C97B2D`
- [x] Nodes are sized by weight, filled with cluster color, and outlined with 3px paper `#F6F4EE`
- [x] Edges use ink color `#141414`, have opacity scaled between 8%-22% by weight, and width scaled 1-4px by weight
- [x] Labels are drawn only for the top-N nodes (default 25)
- [x] Matplotlib labels get a paper outline via `path_effects.withStroke(linewidth=3, foreground="#F6F4EE")`
- [x] Flat cluster panels are rendered behind each cluster (convex hull with cluster color at 8% opacity)
- [x] The `map_before.png` and `map_after.png` evidence files have been generated
