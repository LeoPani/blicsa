# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0-beta.3] - 2026-09-28

Fluxo de mapas mais permissivo — só correções, nenhum tipo de mapa removido.
Matriz de 200 combinações em projetos reais: de 114 para 150 mapas gerados; nenhum tipo inviável
descoberto só depois de clicar. Detalhes em [`docs/AUDITORIA-2026-09.md`](docs/AUDITORIA-2026-09.md) (Parte 5).

### Corrigido
- Cocitação e acoplamento ignoravam o limite de nós e travavam por minutos (até 300 s) em corpus reais.
- Citação direta nunca gerava mapa com corpus do OpenAlex (referências são IDs, não DOIs).
- Limiar alto demais deixava o usuário sem mapa; agora é reduzido com aviso.
- Tipo de mapa que o corpus não sustenta (IPC sem patentes, semântico, citação direta sem ID) só era descoberto depois de clicar.
- Mensagem de mapa vazio mandava "reduzir a frequência mínima" mesmo quando ela já era 1.
- Rótulo do limiar era o mesmo para os sete tipos; referências do OpenAlex apareciam como URL inteira.
- Rodar os testes gravava o idioma francês nas preferências reais do usuário.

## [2.1.0-beta.2] - 2026-09-28

Auditoria de setembro de 2026 — só correções, nenhuma funcionalidade nova ou alterada.
Detalhes, medições e evidências em [`docs/AUDITORIA-2026-09.md`](docs/AUDITORIA-2026-09.md).

### Corrigido
- CSV no formato do Blicsa (incluindo `docs/sample_dataset.csv`) importava 0 registros; importação vazia fingia sucesso.
- CSV do Scopus salvo pelo Excel em português (`;`, Windows-1252) não importava.
- Erro de importação dizia "Não foi possível abrir o projeto".
- Salvar na Galeria, aba Galeria, Exportação em Lote e exportar PNG/SVG/PDF/Plotly HTML quebrados.
- Stopwords extras ignoradas no campo de palavras-chave (resultado incorreto); lista de revisão mostrava como "manter" termos que o mapa removia.
- Texto em campos numéricos mostrava erro cru; "50%" e anos por extenso eram ignorados em silêncio.
- Clique duplo em Gerar Mapa rodava dois cálculos simultâneos; reclusterizar quebrava sempre.
- Exportações que falhavam (ex.: arquivo aberto no Excel) não avisavam nada.
- Falhas de IA chegavam em inglês técnico; chave errada era tentada 3 vezes.
- Congelamentos: abrir projeto (até 4,9 s), Revisar termos (até 5,4 s), projeto de 6 mil registros (2,9 s).
- Executável gravava saídas na pasta do programa; "Agrupamento Semântico" gerava mapa de IPC sem aviso.

### Adicionado (desenvolvimento)
- `tests/test_usuario_desastrado.py` (93 cenários), `tests/test_auditoria_2026_09.py`,
  `scripts/smoke_app.py` e `scripts/medir_travadas.py`.

## [2.1.0-beta.1]

Versão de testes unificada como **Blicsa Beta 2.1.0-beta.1**. A release estável 2.0.0 e
seu DOI permanecem como registro histórico reproduzível.

### ⚠️ Resultados podem diferir de versões anteriores

Três correções mudam o que aparece na tela para um projeto criado antes delas. Nenhuma
altera o seu **corpus**: os registros, os autores, os anos e as citações continuam exatamente
como foram coletados. O que muda é o que o Blicsa **calcula** a partir deles.

**1. O mapa agora sai igual toda vez.** Antes, gerar o mapa duas vezes a partir do mesmo
corpus produzia desenhos diferentes — os mesmos agrupamentos, em posições diferentes. A
biblioteca de layout sorteava o ponto de partida de cada nó sem semente fixa. Se você publicou
uma figura, não conseguiria refazê-la. Agora consegue.

*O que fazer:* nada. Projetos salvos guardam as posições e continuam abrindo com o mapa que
você viu. A diferença aparece só se você mandar **recalcular** o mapa — e aí o novo desenho é
o que se repetirá dali em diante.

**2. Zero citação deixou de ser lido como "sem informação".** Um termo que aparece só em
artigos ainda não citados — o caso mais comum de corpus recente — era pintado de cinza no mapa
de superposição, com a legenda dizendo "sem dado". O dado existia: era zero.

*O que fazer:* nada, na maioria dos casos. Ao abrir um projeto antigo, o Blicsa **recalcula
essa métrica a partir do corpus guardado dentro do próprio arquivo** e desfaz a confusão
sozinho — um termo com citações volta a mostrar suas citações, e um termo genuinamente sem
citação mostra zero. A única exceção é projeto salvo **sem o corpus junto**: nesse caso não há
de onde recalcular, e os termos afetados passam a aparecer como zero em vez de cinza.

**3. Os agrupamentos ficaram reprodutíveis** (já valia desde a v2.0.0). A ordem de inserção
dos nós não era determinística e o algoritmo de comunidades podia chegar a divisões diferentes
com a mesma entrada. Hoje há semente fixa.

*O que fazer:* se um agrupamento publicado precisa ser preservado exatamente, guarde a figura
exportada antes de reabrir o projeto.

### Corrigido

- **Import do Web of Science no formato "plain text" trazia zero registros.** O arquivo é
  aceito, a importação termina sem erro, e o corpus fica vazio. Era o formato que a interface
  do Web of Science oferece primeiro. Os dois formatos (`plain text` e `tab delimited`) agora
  funcionam.
- **Trocar o idioma no meio do trabalho devolvia à tela inicial.** O corpus continuava
  carregado, mas coberto pela tela de "novo projeto / abrir projeto".
- **As análises de IA saíam sempre em português**, mesmo com a interface em inglês ou francês —
  mapa temático, Sankey, historiografia, obras seminais, insights e rótulos de cluster.
- **Exportação para Gephi e VOSviewer podia gerar arquivo ilegível** quando um termo do corpus
  continha quebra de linha (acontece com CSV e RIS malformados).
- **A linha do tempo do mapa mostrava o ano errado.** Um termo usado desde 2010 só aparecia na
  animação alguns anos depois, e os primeiros anos saíam vazios mesmo havendo publicações.

## [2.0.0] - 2026-08-04

Primeira versão estável, e a base congelada para o registro de software e a submissão
acadêmica. O salto de 0.9 para 2.0 respeita as tags `1.1.x-beta` já publicadas — número
público não regride.

### ⚠️ Mudanças que afetam quem já usava

- **Python 3.11 ou superior passa a ser obrigatório.** As bibliotecas científicas fixadas
  (`numpy`, `pandas`, `scipy`, `networkx`) declaram `requires-python >=3.11`. Em 3.10 a
  instalação falha ao resolver as dependências. O CI testava 3.10 e ficou **vermelho de 21/07
  a 04/08** por causa disso, sem que ninguém notasse.

- **Projetos salvos antes da v2.0 podem apresentar clusterização diferente da original ao
  serem reabertos.** Até aqui, a ordem de inserção dos nós no grafo não era determinística e o
  Louvain podia chegar a partições distintas com a mesma entrada. Agora há semente fixa
  (`seed=42`) e o resultado é reproduzível. **O corpus, as métricas e as posições salvas não
  mudam — só o agrupamento pode diferir.** Se um agrupamento publicado precisa ser preservado,
  guarde a figura exportada antes de reabrir o projeto.

- **`is_oa` lido como texto**: projetos antigos gravavam o campo como a string `"false"`, e
  `bool("false")` é verdadeiro — **todo registro antigo aparecia como Open Access**. Agora a
  conversão é feita na carga.

### Corrigido

- **Projetos antigos não abrem mais com erro.** Abrir um `.blicsa` de julho e mandar calcular
  a rede imprimia `[ERRO] 'keywords'` — uma mensagem de uma palavra, que não dizia sequer que
  o problema era o arquivo. O gancho de migração existia desde o começo, vazio, com o
  comentário "Insert migrations here if schema ever changes". O schema mudou. Agora há
  normalização do schema na carga, para qualquer versão de arquivo.
- **Rótulo de cluster não numérico derrubava o projeto inteiro.** `int(k)` sem guarda levantava
  `ValueError` e o `.blicsa` deixava de abrir — dataset, mapa e parâmetros perdidos por causa
  do rótulo de um cluster.
- **Campo Qtd vazio agora é ilimitado de verdade.** Havia um teto silencioso de 1.000: quem não
  digitava nada recebia 1.000 registros de uma busca com 54.440 resultados, e a trilha dizia
  "atingiu limite", indistinguível de um limite pedido pelo usuário.
- **Trilha de contagem honesta em todas as fontes.** No PubMed, o fim do conjunto se
  disfarçava de "atingiu limite"; e a truncagem pelo teto da API era silenciosa.
- **Paginação da navegação anuncia só páginas que existem.** Uma busca de 366.949 resultados
  mostrava "Página 1 de 14.678" quando só 400 podiam ser abertas. Agora diz "de 400
  navegáveis", com o total completo no cabeçalho.
- **Versão do app unificada.** Havia cinco declarações independentes e três delas diziam
  `v3.0`, número que nunca existiu e que aparecia nas capturas de tela.
- **`LICENSE` ausente.** O README anunciava MIT em badge e seção, mas sem o arquivo o GitHub
  não detectava licença nenhuma.

### Adicionado

- **Documentação de usuário** em `docs/`: visão geral, instalação, uso, mapas, métodos,
  limitações conhecidas e FAQ — em português, com instalação, uso e métodos também em inglês.
- **Declaração de honestidade acadêmica** sobre a métrica de relevância: usa divergência KL,
  é *inspirada* no conceito de especificidade de termos de van Eck & Waltman e **não** é a
  fórmula publicada por eles; os valores não são comparáveis aos do VOSviewer.
- **`CODE_OF_CONDUCT.md`** e `docs/JOSS-CHECKLIST.md`.
- **`docs/sample_dataset.csv`** com 200 registros reais do OpenAlex, para o exemplo de ponta a
  ponta (os 3 anteriores não geravam mapa).
- **Importação do PubMed por histórico do servidor** (`usehistory=y` + EFetch paginado):
  uma requisição de busca em vez de trafegar a lista de PMIDs.
- **Chave opcional do OpenAlex** nos Ajustes, com mensagem clara ao atingir o limite diário.

### Limitações conhecidas nesta versão

Documentadas em `docs/limitacoes.md`. Em destaque: **PubMed entrega no máximo 9.999 registros
por busca** — teto do NCBI, que `usehistory=y` não remove; e a extração de frases nominais
funciona bem em inglês e mal em português.

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
