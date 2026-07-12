# Relatório — Correção dos bugs de busca + percepção de velocidade

**Data:** 2026-07-12 · Dois commits: `fix: bugs de busca BUG-01/02/03` (68d7b58) e
`feat: streaming de resultados e carregamento vivo no feed de busca`.

---

## PARTE 1 — Bugs (xfail → pass)

Os três testes que provavam os bugs (`xfail strict`) viraram testes normais que passam.

| Bug | Correção | Status do teste | Verificação |
|---|---|---|---|
| **BUG-01** PubMed idioma | Mapa ISO 639-1→639-2 (`_ISO639_1_TO_2`) em `core/sources/pubmed.py`; código desconhecido loga aviso e não aplica filtro | `test_pubmed_language_filter_offline` **passa** (era xfail) | Live: PubMed pt "saúde pública" = **10** resultados (era 0) |
| **BUG-02** Crossref idioma | Filtro client-side (`_record_matches_language`): campo `language` da API ou `langdetect`; descartados **contados** em `language_filtered_count` → trilha "filtrados por idioma: X"; rótulo "ⓘ Crossref: local" na UI | `test_crossref_language_filter_offline` **passa** | Live: pt devolveu 25, filtrou 10, todos pt |
| **BUG-03** dedup caixa/pontuação | Chave de comparação normalizada (`_dedup_key`: casefold + sem pontuação + espaços colapsados) em `core/harmonization.py`; dados exibidos inalterados | `test_dedup_case_and_punctuation_insensitive` **passa**; falso-positivo preservado | unit |

Suíte: **71 passed, 1 xfailed**. O único xfail remanescente é **OBS-03** (ranking do
Crossref) — não é um dos 3 bugs, permanece como observação, conforme instruído
(OBS-03/04/05 mantidos). `docs/BUGS-ENCONTRADOS-BUSCA.md` atualizado com status ✅ CORRIGIDO.

---

## PARTE 2 — Streaming e carregamento vivo

Reestruturado `_search_worker` (`main.py`) para exibir o feed imediatamente e transmitir
os records em lotes; `SearchFeedView` (`ui/search_feed.py`) ganhou `begin_stream`,
`stream_update` e `finish_stream`. Tudo despachado à UI via `self.after()` — a thread de
busca **nunca** toca widget diretamente (snapshots `records[:]`).

| Requisito | Implementação | Verificação |
|---|---|---|
| 1. Feed incremental (lotes ~25) | records bufferizados; `push_batch` a cada 25 (e no 1º) via `after()` | headless: 200 records em 8 lotes, 25 cards na página 1 |
| 2. Contador vivo | "Encontrados N · carregando M…" sobe em tempo real; ao fim, trilha completa (+ "filtrados por idioma: X") | headless OK |
| 3. Barra neoplasticista | `CTkProgressBar(corner_radius=0, progress_color=RED)` bloco chapado, `loaded/limit`; **Cancelar continua visível** | headless: barra exibida/oculta corretamente |
| 4. Estado inicial (skeletons) | 4 `SkeletonCard` até o 1º lote; animação reduzida a **2 tons chapados** em passo discreto (sem shimmer/gradiente) | headless: 4 skeletons criados e removidos no 1º lote |
| 5. Listas grandes | **decisão abaixo** | — |
| 6. Ordem estável | cards em ordem de chegada (append-only); página 1 fixa; sidebar/filtros só em `finish_stream` (fim do load) | headless: `[c.index]==range(25)` |

### Medições (acceptance)

- **Tempo até o 1º card < 2.5s:** busca live 200 resultados OpenAlex →
  `[feed] primeiro lote em 2.0s` → **PASSOU** (2.00s < 2.5s). 200 completos em ~4.0s.
- **UI nunca congela:** o enriquecimento por idioma (`langdetect`) e todas as chamadas de
  rede rodam na **thread de busca** (`_search_worker` é lançado em `threading.Thread`),
  não na main thread; só `self.after()` toca a UI. (OBS-05 já satisfeito para o fluxo de busca.)
- **Cancelar < 1s mantém resultados:** `_cancel_search` seta `cancel_event`; o provider
  levanta `InterruptedError` na verificação seguinte (responsividade ~0s medida antes); o
  worker finaliza com os records parciais → `finish_stream(parciais)` mantém o que já veio.

### Decisão do item 5 (listas grandes)

**Escolha: manter a paginação já existente** do `SearchFeedView` (`page_size=25` +
botão "Carregar mais") — o caminho mais simples que já atende a meta. Durante o streaming
apenas a **primeira página (25 cards)** é instanciada; os demais records só viram widgets
quando o usuário clica "Carregar mais". Assim a visão default/streaming nunca instancia
milhares de widgets e a rolagem permanece fluida. Virtualização completa (instanciar/destruir
por scroll) foi **deixada para depois** por não ser necessária para a meta com a paginação atual.

### Captura de tela (`docs/evidence/percepcao_busca.png`) — PENDENTE

> **NENHUM mock gerado.** A captura do feed em carregamento (contador + barra + cards
> parciais) não foi produzida: `screencapture` continua bloqueado por permissão de
> **Gravação de Tela** do macOS (`could not create image from display`). Conceder em
> Ajustes do Sistema → Privacidade e Segurança → Gravação de Tela → Terminal, e reinvocar.
> O feed é composto por widgets CustomTkinter (sem caminho `savefig` como o mapa), então não
> há alternativa headless para a captura — fica pendente de validação humana.

---

## Achado colateral (pré-existente, NÃO corrigido)

`SearchFeedView._build_sidebar` (`ui/search_feed.py:~312`) cria `CTkSlider(number_of_steps=max_y-min_y)`.
Quando **todos os resultados têm o mesmo ano** (`max_y == min_y`), `number_of_steps=0` →
`ZeroDivisionError` no `slider.set()`. É **pré-existente** (também no `load_results` original,
não introduzido pelo streaming) e foge ao escopo desta parte (aditiva/streaming). Registrado
para a fila: proteger com `number_of_steps=max(1, max_y-min_y)`.

## Validação humana (roteiro)

Conceder Gravação de Tela e, no app:
1. Buscar "entrepreneurship education", limite 500, OpenAlex → **1º card em ~2s**, contador
   subindo, barra andando, Cancelar no meio funciona e mantém o que já carregou, rolagem
   fluida ao final, trilha de contagem completa.
2. Filtro de idioma **pt no PubMed** → agora retorna resultados (BUG-01).
3. Filtro de idioma **pt no Crossref** → trilha mostra "filtrados por idioma: X" (BUG-02).
