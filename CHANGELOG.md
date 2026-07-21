# Changelog

All notable changes to this project will be documented in this file.

## [0.9.0] - 2026-07-20

Primeira release pública instalável do Blicsa (macOS `.app` + Windows `.exe`),
consolidando os passos 1–5 de amadurecimento.

### Added
- **Mapa temático 100% offline (passo 5)**: graphology + sigma (3.0.3 estável)
  vendorizados num bundle local (`assets/vendor/`) — o mapa Sigma renderiza sem
  internet, sem depender de CDN em runtime. Exports Plotly com o `plotly.js`
  embutido (`include_plotlyjs=True`). Strings dos gráficos vindas do catálogo i18n.
- **Ajustes persistentes + keyring (passo 4)**: configurações no diretório de
  usuário (`platformdirs`) e a API key guardada no keyring do sistema, com
  migrações automáticas e erros de IA honestos na UI.
- **Projetos + histórico (passo 3)**: cada pesquisa é uma pasta de projeto com
  corpus, configuração e backlog de eventos (busca/análise), recarregável offline.
- **Busca consolidada (passo 2)**: fonte única por busca (OpenAlex/Crossref/
  PubMed), feed de revisão com deduplicação, tradução e paginação.
- **Empacotamento**: `Blicsa.spec` inclui `assets/` (com `assets/vendor/`),
  `locales/` e `docs/sample_dataset.csv`; flag `--smoke-test` para validação
  pós-build no binário. Release Windows via GitHub Actions.

### Changed
- **Higiene (passo 1)**: importações e índices únicos, deduplicação exata,
  remoção de dependências de rede em caminhos que deviam ser locais.

### Notas de instalação
- **macOS**: na primeira abertura, clique com o botão direito no `Blicsa.app` →
  **Abrir** (o app ainda não é assinado; o Gatekeeper bloqueia o duplo-clique).

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
