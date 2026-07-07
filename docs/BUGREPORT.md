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
- **Solução Implementada:** Todos os e-mails `pybibliomics@example.com` modificados para `leopaniago2@gmail.com`. Método solto `chat_history` no `ai/client.py` deletado. `fix_treeview.py` solto na raiz deletado. `Access-Control-Allow-Origin` em `bridge.py` restringido a web extensions nativas.

## Fase 2: Idiomas nos Dados
- **Sintoma:** Os registros carregados via APIs perdem as referências de idioma e metadados Open Access.
- **Causa Raiz:** O processamento original em OpenAlex/Crossref/PubMed ignorava a chave "language", "is_oa" e "oa_url". Não havia fallback inteligente.
- **Solução Implementada:** Normalização estendida para preencher esses campos via API originais. Implementada camada de fallback baseada em `langdetect` na recepção dos registros, marcando a origem como `api` ou `detected`. Adicionado badge "OPEN ACCESS" e "IDIOMA" no card de artigo, filtro dinâmico de idiomas no painel esquerdo, e totalização dos top idiomas extraídos na string de resumo final.
## Fase 4: Blink Research
- **Sintoma:** O assistente de IA mostrava respostas sem formatação (Markdown cru em caixa de texto padrão) e não tinha contexto profundo do corpus.
- **Causa Raiz:** O componente `CTkTextbox` nativo do `customtkinter` não suporta Markdown. O prompt do chat original não injetava dados dos resumos, enviando apenas o prompt base.
- **Solução Implementada:** Desenvolvido parser `core/markdown_parser.py` para converter Markdown básico (bold, italic, código, headers) em tags ricas de Tkinter (`font_bold`, etc) no `CTkTextbox`. Adicionada lógica de RAG simples que extrai e injeta os resumos (abstracts) dos 100 artigos mais citados no system prompt, fornecendo contexto bibliográfico direto à LLM.
