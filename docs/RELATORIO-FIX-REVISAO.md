# Relatório — Fixes da tela de revisão (BUG-A / B / C)

**Data:** 2026-07-12 · Um commit por bug. Diagnóstico ANTES da correção (ver também
`docs/BUGREPORT.md`).

---

## BUG-A — Paginação morria em silêncio

### Diagnóstico (instrumentação + reprodução)
Instrumentei o loop de cada provider com `stop_reason`/`stop_error`/`pages_fetched`.
Busca ampla "empreendedorismo" (limite 600), 2x:
```
RUN 1: baixados=0 · páginas=1 · stop='erro de rede na página 1: ... after retries' · erro=True
RUN 2: baixados=0 · páginas=1 · stop='erro de rede na página 1: ... after retries' · erro=True
```
**Causa raiz (duas somadas):** (1) erro de fetch no meio da paginação fazia
`logger.error + break` **silencioso** → parcial sem sinal; `baixados` variava conforme a
página em que o rate-limit/timeout caía. (2) "Ilimitado" ligado por padrão → `max_results=9999999`,
saturando a API (HTTP 429).

### Correção
- `fetch_url` já faz 3 tentativas com backoff 1s/2s/4s (confirmado nos logs). Mantido.
- Providers expõem `stop_reason`/`stop_error`/`pages_fetched`. O worker lê e a trilha mostra
  `"⚠ interrompido (Provider, página N) por erro de rede — resultados parciais"` — **nunca silencioso**.
- Limite honesto: padrão **1000**, teto **10000**; "Ilimitado" virou "Máx (10000)" e é
  desligado por padrão; valores acima de 10000 são rejeitados na UI (`t("search.limit_exceeded")`).
- Trilha honesta: quando `encontrados > baixados`, mostra `"baixados M de {limite} (limite)"`.

### Evidências
- **Reprodutibilidade (mesma busca 2x):**
  - Crossref "social innovation", limite 1000 → **200 / 200** (idêntico), `stop='cursor encerrado (fim dos resultados)'`, `erro=False`.
  - OpenAlex (janela com rate-limit saturado pela sessão de testes) → **0 / 0** (idêntico),
    `erro=True` com motivo explícito — a diferença/parada agora é **sempre explicada**.
- **Testes offline** (`tests/test_search_pagination.py`, mock no nível do `urlopen`):
  - `test_transient_error_recovered_by_retry`: 429 numa página é recuperado pelo retry → 500 completos, `stop_error=False`.
  - `test_persistent_error_is_not_silent`: 429 além dos retries → **200 parciais + `stop_error=True`** com motivo "erro de rede na página 3".

Suíte: **75 passed, 1 xfailed** (OBS-03).

---

## BUG-B — Blink destruía a tela de revisão

### Diagnóstico
`on_ai_assistant` (callback do botão "✨ Blink" do feed) fazia `self._switch_tab("home")` —
navegava para a aba Home (chat do Blink), tirando a revisão da vista; o usuário percebia a
"tela de importação sumindo". O `SearchFeedView` não era destruído, mas o contexto de
revisão (posição, foco) era perdido.

### Correção
- Novo **drawer do Blink AO LADO do feed** no `SearchFeedView` (`open_blink_drawer` /
  `close_blink_drawer`), coluna 3 do grid — o feed (coluna 1) e seu estado
  (cards, seleções, filtros, scroll, trilha) **não são tocados**. O ✕ fecha o drawer e
  devolve a revisão intacta. Sem troca de aba, sem reconstrução.
- `on_ai_assistant` reescrito: abre o drawer e **transmite a resposta nele**, com **RAG dos
  resultados EM REVISÃO** (estatísticas + amostra de abstracts dos records em revisão),
  não do corpus antigo. Reusa `AIAnalyst.chat_history_stream` + `insert_markdown` (caminho já provado).

### Evidência
- Teste `tests/test_search_feed_ui.py::test_blink_drawer_preserves_feed_state`: feed com 50
  records → abre drawer (cards/seleções/trilha/records idênticos) → fecha drawer (idem). ✅

---

## BUG-C — Card com área em branco gigante
<!-- preenchido no commit do BUG-C -->

