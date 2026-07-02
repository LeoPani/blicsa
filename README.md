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

## Releases & Standalone Binaries

Standalone pre-compiled binaries are generated automatically via GitHub Actions release workflows:

*   **Windows**: [Blicsa-windows.zip](https://github.com/leopani/PyBibliomics/releases/latest/download/Blicsa-windows.zip) (Extract and run `Blicsa-onefile.exe` or use `Blicsa-dir`)
*   **macOS**: [Blicsa-macos.dmg](https://github.com/leopani/PyBibliomics/releases/latest/download/Blicsa-macos.dmg) (Open and drag Blicsa to Applications)
*   **Linux**: [Blicsa-linux.AppImage](https://github.com/leopani/PyBibliomics/releases/latest/download/Blicsa-linux.AppImage) (Make executable: `chmod +x Blicsa-linux.AppImage` and run)

> [!NOTE]
> **macOS Gatekeeper Workaround**: Because these standalone builds are unsigned, macOS will block the initial double-click launch. To bypass this, **right-click** `Blicsa.app` (or click while holding Control), choose **Open**, and then click **Open** on the confirmation dialog.

---

## Installation

To run directly from source code:

```bash
git clone https://github.com/LeoPani/PyBibliomics.git
cd PyBibliomics
pip install -r requirements.txt
python main.py
```

> **Python 3.10+** is required.

---

## Quick Start

1.  **Import & Online Search**: Add bibliometric files using **➕ Adicionar** in the **Data Import** tab, or query **OpenAlex / Crossref / PubMed** directly inside the **Busca Online** panel.
2.  **Deduplicate**: Click **🔍 Deduplicar** to review and filter duplicate documents.
3.  **Clustering & Layout**: Select your mapping configurations, including **Louvain** or **Leiden** community clustering and **Resolução Cluster** slider.
4.  **Redraw / Explore**: Click **Gerar Mapa** (`Ctrl+G`). Hovering over a node highlights all connected nodes in their cluster color, fading other elements to 15% opacity.
5.  **AI Insights**: Configure your AI provider settings (Preset models for Groq, OpenAI, OpenRouter, or local Ollama) in the sidebar, input your **Chave API**, and click **Nomear Clusters** or **Insights com IA**.
6.  **Save & Export**: Use the **Exportar** tab to save your complete project in `.blicsa` zip format or export graph networks in Gephi (GEXF) and VOSviewer (Map/Net txt) formats.

---

## Project Structure

```
PyBibliomics/
├── main.py                  # CustomTkinter GUI wrapper
├── Blicsa.spec              # PyInstaller spec file for multi-target packaging
├── core/
│   ├── parsers.py           # Multi-source parsers & merging
│   ├── matrix_builders.py   # Co-occurrence matrices, Leiden/Louvain, & VOSviewer
│   ├── visualizer.py        # Plotly graph and map visualizations
│   ├── nlp.py               # Stopwords, n-grams, and burst detection
│   ├── sources/             # OpenAlex, Crossref, and PubMed API search providers
│   ├── project.py           # .blicsa project save/load manager
│   └── i18n.py              # System language detector (PT-BR / EN default)
├── ai/
│   └── client.py            # Generic OpenAI-compatible AI API client
├── locales/
│   ├── en.json              # English catalog (default)
│   └── pt_BR.json           # Portuguese (Brazil) catalog
├── paper/
│   ├── paper.md             # JOSS publication skeleton
│   └── paper.bib            # Bibliography file
└── requirements.txt
```

---

## License

MIT License.
