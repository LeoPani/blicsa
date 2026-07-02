# Changelog

All notable changes to this project will be documented in this file.

## [2.0-upgrade] - 2026-07-01

### Added
- **Integrated Search**: Direct search interface for OpenAlex, Crossref, and PubMed in the Data Import tab and via CLI (`python -m core.search`).
- **Leiden Clustering**: Added Leiden community detection as an alternative to Louvain with custom resolution controls.
- **VOSviewer Export & Overlay Scores**: Added per-node overlay scores (mean publication year, mean citations) in GEXF and VOSviewer Map/Network file exports.
- **Project Save/Load**: Native `.blicsa` project archives that zip dataset, config, layout, and cluster labels with migration hooks.
- **Generic AI Provider**: Abstracted Groq client to support any OpenAI-compatible API endpoint (Groq, OpenAI, OpenRouter, Ollama) with retries, timeout, and key redaction from logs.
- **i18n Support**: Catalog-based internationalization (English default and Portuguese PT-BR support).
- **Thematic Map (Callon)**: Callon Strategic Diagram analysis with strategic density and centrality quadrants.
- **Sankey Flow Chart**: Three-field flow mapping (Sources -> Authors -> Keywords) with Matplotlib fallback.
- **Release Automation**: PyInstaller build spec for standalone packaging and self-check headlessly validation.
