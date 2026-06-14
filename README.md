# Blicsa — Inteligência Bibliométrica

Desktop application for bibliometric network analysis and visualization, built with Python.  
Maps scientific literature into interactive networks to reveal research fronts, clusters, and knowledge gaps.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)

---

## Features

### Data Import
- **Multi-source import**: Scopus CSV, Web of Science TXT, BibTeX, PubMed MEDLINE, OpenAlex JSON, Crossref JSON
- **Multi-file merging** with per-file format selection
- **Fuzzy deduplication** — 3-pass pipeline: DOI normalization → title similarity (≥ 93%) → (first author, year) matching
- **Drag-and-drop** file import
- **Thesaurus** for synonym normalization

### Network Types
| Map | Description |
|-----|-------------|
| Keyword Co-occurrence | Terms that appear together across papers |
| Co-authorship | Author collaboration network |
| Co-citation | References cited together |
| Bibliographic Coupling | Papers sharing references |
| Direct Citation | Paper-to-paper citation graph |
| IPC Co-classification | Patent subclass co-occurrence |

### Analysis
- **Louvain clustering** with automatic community detection
- **ForceAtlas2 layout** with optional LinLog mode
- **Association Strength normalization** and **TF-IDF relevance scoring**
- **Full / Fractional counting** methods
- **Temporal evolution** of the network across 5-year periods
- **Citation burst detection** — terms rising fastest in recent years
- **Network metrics**: diameter, average path length, clustering coefficient, density
- **Bradford's Law** — source dispersion by zone
- **Lotka's Law** — author productivity distribution
- **h-index** per author

### Visualization
- Dark-theme matplotlib canvas with:
  - Cluster-colored glow per node
  - Edge color blending between endpoint nodes
  - Label backgrounds tinted to cluster color
  - **Betweenness**, **PageRank**, **Degree**, **Year**, **KDE density** color modes
  - Click node → zoom + neighborhood highlight
  - Edge weight threshold slider
  - **Cluster filter** — show/hide individual clusters
- Interactive **Plotly HTML** map (CDN, no install needed)
- **Plotly density** contour map
- **Trend chart** — term frequency over time (multi-select, up to 14 terms)
- **Word cloud** from keywords or abstracts

### AI Integration
- **Groq API** (llama-3.3-70b-versatile) for:
  - Structured bibliometric insights (research fronts, gaps, recommendations)
  - Automatic semantic cluster labeling
- **Node info panel** — click any node to see: centrality metrics, co-occurring terms, related papers with citation counts

### Export
| Format | Content |
|--------|---------|
| PNG / SVG / PDF | High-res map image |
| Plotly HTML | Interactive standalone map |
| PyVis HTML | Force-directed interactive map |
| GML | Gephi / Cytoscape compatible |
| GEXF | Native Gephi format with attributes |
| Pajek .net | Pajek network format |
| JSON topology | Nodes + edges for D3.js / Cytoscape.js |
| CSV (nodes) | Rankings with betweenness, degree, relevance, year |
| CSV (edges) | Edge list with raw and normalized weights |
| Excel (.xlsx) | Rankings + edges + full dataframe in separate sheets |

### UX
- Save / load configuration as JSON
- Progress bar with status messages for all long operations
- Keyboard shortcuts: `Ctrl+G` generate · `Ctrl+I` AI insights · `Ctrl+E` export tab · `Ctrl+R`/`Esc` reset view
- Sortable ranking table (click any column header)
- Year filter, top-% relevance filter, extra stop words

---

## Installation

```bash
git clone https://github.com/LeoPani/PyBibliomics.git
cd PyBibliomics
pip install -r requirements.txt
python main.py
```

> **Python 3.11+** required.  
> On macOS, if `tkinterdnd2` fails to install, drag-and-drop will be disabled but all other features work normally.

---

## Quick Start

1. **Import** — add one or more files (Scopus, WoS, BibTeX…) in the Import tab. Click **Carregar e Combinar**.
2. **Deduplicate** — click **Deduplicar** to review and remove duplicate records.
3. **Configure** — choose network type, field, minimum occurrence, and ForceAtlas2 settings.
4. **Generate** — click **Gerar Mapa** (or `Ctrl+G`). The map opens automatically.
5. **Explore** — click nodes to inspect papers, adjust the cluster filter strip, toggle viz modes.
6. **AI** — add a Groq API key in the config tab and click **Insights com IA** or **Nomear Clusters**.
7. **Export** — use the Export tab to save the map, rankings, or full dataset.

---

## Project Structure

```
PyBibliomics/
├── main.py                  # UI and application logic (CustomTkinter)
├── core/
│   ├── parsers.py           # Data import: Scopus, WoS, BibTeX, PubMed, OpenAlex, Crossref
│   ├── matrix_builders.py   # Network construction, metrics, exports
│   ├── visualizer.py        # Plotly maps and ForceAtlas2 layout
│   └── nlp.py               # N-gram extraction, thesaurus, stop words
├── ai/
│   └── client.py            # Groq API: insights + cluster labeling
└── requirements.txt
```

---

## Groq API Key

Blicsa uses the [Groq API](https://console.groq.com/) for AI features (free tier available).  
Enter your key in the **Configurar Mapa** tab, or set the environment variable:

```bash
export GROQ_API_KEY=gsk_...
```

---

## License

MIT
