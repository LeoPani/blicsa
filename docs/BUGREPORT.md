# BUGREPORT

1. **Filters do not appear after a search completes:**
   - **Root cause:** The filter sidebar was never implemented for the search results screen; the search flow previously just dumped results directly into the corpus without a review screen or post-search filtering mechanism.
   
2. **Not all results appear:**
   - **Root cause:** In `core/sources/openalex.py`, the pagination logic checks `count_fetched >= max_results` but breaks early if `cancel_event` is set, or if the API cursor pagination silently drops records due to cursor expiration, or if deduplication silently removes records during `fuzzy_deduplicate_papers` without notifying the user of the dropped count before import.
   
3. **Search jumps straight to the map:**
   - **Root cause:** At the end of `_search_worker` in `main.py`, there is an explicit call to `self.after(0, lambda: self._switch_tab("viz"))` which unconditionally jumps to the map visualization tab immediately after fetching and merging results.

## Fase 0: Mapas Abrindo Vazios
- **Sintoma:** Ao gerar um mapa de coocorrência e visualizá-lo via janela interativa do pywebview, a janela abre, porém o canvas permanece completamente branco/vazio.
- **Causa Raiz:** O JSON gerado por `core/sigma_exporter.py` contém `NaN` (caso coordenadas do FA2 não convirjam ou nós não tenham `size`), o que faz com que o `JSON.parse` falhe silenciosamente no `map.js`. Além disso, chamadas locais `fetch("graph.json")` sofrem bloqueio de CORS em determinados ambientes do pywebview se o servidor local não for iniciado, além de falta de tratamento no Sigma se o grafo estiver vazio.
- **Solução (em andamento):** Remover a serialização assíncrona/NaN de posições, embutir o JSON no HTML para evitar CORS, e adicionar um bloco `try/catch` no `map.js` que exibe a mensagem `"Nenhum dado para exibir"` caso não haja nós.

## Fase 1: Higiene de Código
- **Sintoma:** O código contém strings de e-mail de teste fixadas e métodos não utilizados ou redundantes que criam ruído.
- **Causa Raiz:** Dívida técnica ao longo do desenvolvimento inicial.
- **Solução Implementada:** Todos os e-mails `pybibliomics@example.com` modificados para `blicsa.app@gmail.com`. Método solto `chat_history` no `ai/client.py` deletado. `fix_treeview.py` solto na raiz deletado. `Access-Control-Allow-Origin` em `bridge.py` restringido a web extensions nativas.

## Fase 2: Idiomas nos Dados
- **Sintoma:** Os registros carregados via APIs perdem as referências de idioma e metadados Open Access.
- **Causa Raiz:** O processamento original em OpenAlex/Crossref/PubMed ignorava a chave "language", "is_oa" e "oa_url". Não havia fallback inteligente.
- **Solução Implementada:** Normalização estendida para preencher esses campos via API originais. Implementada camada de fallback baseada em `langdetect` na recepção dos registros, marcando a origem como `api` ou `detected`. Adicionado badge "OPEN ACCESS" e "IDIOMA" no card de artigo, filtro dinâmico de idiomas no painel esquerdo, e totalização dos top idiomas extraídos na string de resumo final.
## Fase 4: Blink Research
- **Sintoma:** O assistente de IA mostrava respostas sem formatação (Markdown cru em caixa de texto padrão) e não tinha contexto profundo do corpus.
- **Causa Raiz:** O componente `CTkTextbox` nativo do `customtkinter` não suporta Markdown. O prompt do chat original não injetava dados dos resumos, enviando apenas o prompt base.
- **Solução Implementada:** Desenvolvido parser `core/markdown_parser.py` para converter Markdown básico (bold, italic, código, headers) em tags ricas de Tkinter (`font_bold`, etc) no `CTkTextbox`. Adicionada lógica de RAG simples que extrai e injeta os resumos (abstracts) dos 100 artigos mais citados no system prompt, fornecendo contexto bibliográfico direto à LLM.

## BUG-A: Paginação morre em silêncio (revisão de busca) — 2026-07-12
- **Sintoma (relato + screenshot):** "Encontrados 319300 · baixados 2904 (limite 9999999)"; buscas idênticas dão `baixados` diferentes; parte dos resultados some sem explicação.
- **Diagnóstico (instrumentação `stop_reason`/`stop_error` + reprodução 2x):** com a busca ampla "empreendedorismo" (limite 600), ambas as runs pararam em `stop_reason='erro de rede na página N'`, `stop_error=True`. Log:
  `HTTP 429 received. Retrying in 1.0s/2.0s/4.0s...` → `Failed to fetch ... after retries`.
- **Causa Raiz (duas somadas):**
  1. Em `core/sources/openalex.py` (e crossref/pubmed), um erro de fetch no meio da paginação fazia `logger.error` + `break` **silencioso** → a busca terminava parcial sem nenhum sinal ao usuário. `baixados` varia porque depende de EM QUE página o rate-limit/timeout ocorre (não-determinístico).
  2. A UI usa "Ilimitado" **ligado por padrão** → `max_results = 9999999` (`main.py:1662`), que dispara buscas enormes e satura a API (HTTP 429), aumentando muito a chance da parada por erro.
- **Correção:**
  1. `fetch_url` já faz 3 tentativas com backoff 1s/2s/4s (confirmado no log). Mantido.
  2. Providers passam a expor `stop_reason`/`stop_error`/`pages_fetched`; o worker lê e a trilha mostra `"⚠ interrompido na página N por erro de rede — resultados parciais"` quando `stop_error` — nunca mais silencioso.
  3. Limite honesto: padrão 1000, máximo 10000; "Ilimitado" passa a significar 10000; entradas acima são rejeitadas na UI. Trilha: `"Encontrados N · baixados M de LIMITE (limite)"` quando `N > M`.
- **Reprodutibilidade:** ver `docs/RELATORIO-FIX-REVISAO.md` (mesma busca 2x, limite 2000, trilhas comparadas).

## Re-auditoria 2026-07-29 — o que ainda estava quebrado depois do fix de 12/07

### BUG-A.3: "Encontrados" mostrava o LIMITE, não o total da base
- **Sintoma:** com o limite padrão (1000), a trilha dizia `Encontrados 1000 · baixados 1000`
  numa busca cuja base tem 319300. O usuário não ficava sabendo que havia mais.
- **Causa Raiz:** `total_found_sum` (main.py) era alimentado **só** pelo `progress_cb`, e os
  providers passam nele o **alvo da barra de progresso**, não o total da base:
  `progress_cb(count_fetched, min(max_results, total_results))` em openalex/crossref, e
  `len(id_list)` (já cortada por `retmax`) em pubmed. Com limite finito, o "encontrados"
  virava o próprio limite. Efeito colateral: o ramo `trail_limited` ("de N (limite)") era
  **código morto**, porque `total_found_sum > baixados` nunca era verdadeiro.
  O screenshot mostrava 319300 correto só porque veio do modo *Ilimitado*
  (`min(9999999, 319300) = 319300`). PubMed calculava `total_results` e descartava.
- **Correção:** providers expõem `total_available` (total REAL da API: `meta.count` /
  `message.total-results` / `esearchresult.count`); o worker usa esse valor para
  "Encontrados" e o `progress_cb` segue com o alvo limitado. Commit `ace716a`.
- **Correção 2:** `_current_limit()` cortava o campo Qtd para 10000 em silêncio — agora
  explica via `t("search.limit_capped")`. Nenhum teto novo: o "Ilimitado" segue como está
  desde `6bfe474`. Commit `1beb0f5`.

### BUG-C.2: o vão branco gigante continuava — eram outros DOIS frames
- **Sintoma:** o mesmo do relato original (card com ~4x a altura do conteúdo), em *alguns*
  cards e não em todos.
- **Causa Raiz:** o fix de 12/07 corrigiu só o `left_bar`. Outros dois `CTkFrame` do
  `ArticleCard` eram criados **sem `height`** e por isso assumiam a altura default de
  **200px** do CustomTkinter, que não encolhe quando o frame fica **sem filhos**:
  a faixa de badges (row 0), vazia quando o registro não tem ano/citações/OA/idioma; e a
  faixa de ações (row 4), vazia quando o registro é Open Access ou não tem DOI (não ganha o
  botão "Abrir DOI"). Card mínimo medido: **454px** (200 + 200 + 28 de título) — daí o vão
  aparecer só em certos registros. O teste de regressão passava porque usava um registro com
  `year`+`language`+`doi`, ou seja, as duas faixas tinham filhos.
- **Correção:** `height=1` nas duas faixas, mantidas gridadas para preservar o respiro de
  12px do card (só gridar quando têm conteúdo derrubava a folga inferior para 4px).
  454px → 61px. Commit `6736c5f`.

### BUG-B: nada quebrado, cobertura insuficiente
- O drawer de `b99d4ab` está correto (sem troca de aba, sem reconstruir o feed, RAG dos
  records em revisão). O teste chamava `open_blink_drawer()` direto e não cobria o
  *callback*, que era onde o defeito original vivia (`_switch_tab("home")`). Dois testes
  novos fecham o buraco, um deles verificado injetando a regressão. Commit `daa40aa`.
