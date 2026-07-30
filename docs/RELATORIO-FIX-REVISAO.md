# Relatório — Fixes da tela de revisão (BUG-A / B / C)

**Data:** 2026-07-12 · Um commit por bug. Diagnóstico ANTES da correção (ver também
`docs/BUGREPORT.md`).

> **Re-auditoria em 2026-07-29** — o prompt dos três bugs foi rodado de novo sobre o
> estado já corrigido. **BUG-A e BUG-C ainda tinham defeito vivo**; BUG-B estava correto.
> Ver [Re-auditoria 2026-07-29](#re-auditoria-2026-07-29) no fim do documento. As seções
> abaixo são o registro original da sessão de 12/07 e ficam como estão.

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
- Limite: **sem teto** (a pedido do Leonardo — o teto de 10000 foi revertido). "Ilimitado"
  (ligado por padrão) baixa tudo o que a API entregar; o campo "Qtd" (padrão 1000) vale
  quando "Ilimitado" está desligado.
- Trilha honesta: quando há um limite FINITO definido e `encontrados > baixados`, mostra
  `"baixados M de {limite} (limite)"`; no modo ilimitado, mostra a contagem simples (o aviso
  de erro de rede, quando houver, explica qualquer parada parcial).
- **Nota:** a parte central do BUG-A (erro de rede visível na trilha, nunca silencioso) foi
  **mantida** — só o teto numérico saiu.

### BUG-A.2 — Crossref parava em 200 (cursor de scroll + cache) — descoberto depois
Relato: "200 baixados de 80598 encontrados". Diagnóstico com paginação manual:
- O cursor de deep paging do Crossref é um **token de scroll que se REPETE** entre páginas
  (mesma string, mas o servidor avança). Dois defeitos somados:
  1. O guard `next_cursor == cursor` interpretava a repetição como "fim" → parava na página 2 (200).
  2. Sem o guard, a URL idêntica batia no **cache do `fetch_url`** → devolvia a mesma página
     (500 baixados, só 200 únicos).
- **Correção:** no Crossref, parar só quando `items` vem vazio (não quando o cursor repete);
  e `fetch_url(no_cache=True)` para a paginação por scroll. Resultado live: "innovation",
  limite 500 → **500 registros, 500 únicos, 5 páginas**. Teste offline
  `test_crossref_repeating_cursor_does_not_stop_early` (cursor repetido + itens distintos → 300 únicos).

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

### Diagnóstico (medição programática de altura)
Medindo `ArticleCard.winfo_reqheight()`, o card mínimo (só título) dava **236px** — constante,
independente do conteúdo. Inspecionando os filhos: `CTkFrame ... reqh=200 children=0` — o
**`left_bar`** (barra decorativa de 6px na borda esquerda) foi criado **sem `height`**, então
o CTkFrame assumiu a **altura default 200px**; com `rowspan=4 sticky="ns"` isso forçava o card
a ≥200px de altura → o vão branco gigante abaixo do conteúdo.

### Correção
- `left_bar` criado com `height=1` (com `sticky="ns"` a barra estica ao conteúdo real);
  `rowspan` estendido a 5 para cobrir o card todo. Fim do piso de 200px.
- Label de meta (autores — fonte) só é criado quando há texto (não reserva linha vazia).
- **Sidebar — nomes de fonte truncados:** `f"{j[:20]} ({c})"` cortava no meio e depois colava
  a contagem ("LA Referencia (Red F (305)"). Agora trunca com **reticências** antes da
  contagem: `"LA Referencia (Red Fe… (305)"` — o parêntese da contagem nunca é cortado.

### Evidência (medição após o fix)
| card | antes | depois |
|---|---|---|
| mínimo (só título) | 236px | **106px** |
| + autor/fonte | 236px | 140px |
| + abstract curto | 236px | 172px |
| + abstract longo + badges | 412px | 365px |

Altura agora **segue o conteúdo** (sem vão fixo); card mínimo bem abaixo de 1.5× o conteúdo.
Teste `tests/test_search_feed_ui.py::test_article_card_no_fixed_whitespace` guarda a regressão
(card mínimo < 160px e altura cresce com abstract).

**Captura de tela:** `screencapture` segue bloqueado (permissão de Gravação de Tela) — evidência
visual pendente; validação feita por **medição programática** (aceita pelo prompt).

Suíte final: **77 passed, 1 xfailed** (OBS-03).



---

# Re-auditoria 2026-07-29

O mesmo prompt foi rodado sobre o estado já corrigido em 12/07. Auditei os três antes de
mexer em qualquer coisa. Resultado: **dois dos três ainda tinham defeito vivo**, e nos dois
casos o teste de regressão existente passava — ele não cobria o caminho que quebrava.

Suíte no início: 134 passed, 1 xfailed. Suíte ao final: **139 passed, 1 xfailed**.
Commits: `ace716a` (BUG-A), `1beb0f5` (BUG-A.3), `6736c5f` (BUG-C), `daa40aa` (BUG-B, testes).

---

## BUG-A — "Encontrados" mostrava o LIMITE, não o total da base ❌→✅

### Diagnóstico
O erro de rede já não era silencioso (fix de 12/07 intacto). Mas a trilha ainda mentia num
ponto diferente: **`Encontrados`**. `total_found_sum` (main.py) era alimentado só pelo
`progress_cb`, e os providers chamam:

```python
progress_cb(count_fetched, min(max_results, total_results))   # openalex.py / crossref.py
progress_cb(count_fetched, len(id_list))                      # pubmed.py (id_list já cortada por retmax)
```

O 2º argumento é o **alvo da barra de progresso**, não o total da base. Com limite finito
ele vale o próprio limite. Reprodução offline (`meta.count = 319300`, limite 1000):

```
Total REAL na base (meta.count) : 319300
baixados                        : 1000
total_found_sum (=Encontrados)  : 1000        <-- deveria ser 319300
TRILHA => Encontrados 1000 · baixados 1000
```

Duas consequências: o usuário não fica sabendo que existem mais 318300 resultados, e o ramo
`trail_limited` ("de N (limite)") era **código morto** — a condição `total_found_sum > baixados`
nunca dava verdadeira quando o limite era quem cortava.

**Por que o screenshot mostrava 319300 certo:** o relato veio do modo *Ilimitado*, onde
`max_results = 9999999` e `min(9999999, 319300) = 319300`. O número só ficava errado com
limite finito — que é o **padrão** (1000). PubMed calculava `total_results` e jogava fora.

### Correção
- Providers expõem `total_available` = total REAL da API (`meta.count` /
  `message.total-results` / `esearchresult.count`).
- O worker usa `total_available` para "Encontrados"; o `progress_cb` continua recebendo o
  alvo limitado (é barra de progresso — a distinção é o ponto). O total também é lido
  **depois** do provider rodar, para o caso de o `progress_cb` nem disparar.
- O motivo de rede embutia a URL inteira no label; na trilha entra truncado, log e backlog
  seguem completos.

### Evidências
**Reprodutibilidade ao vivo — mesma busca 2x, OpenAlex "empreendedorismo", limite 2000
(provider novo a cada run, sem cache compartilhado):**

```
RUN 1: Encontrados 54051 · baixados 2000 de 2000 (limite) · atingiu limite
       paginas=10 · erro=False · 23.5s
RUN 2: Encontrados 54051 · baixados 2000 de 2000 (limite) · atingiu limite
       paginas=10 · erro=False · 21.7s
trilhas identicas: SIM · baixados identicos: SIM
```

Antes do fix essa mesma busca diria `Encontrados 2000 · baixados 2000`.

**Crossref ao vivo:** `Encontrados 5849 · baixados 300 de 300 (limite) · atingiu limite`.

**Erro de rede nunca silencioso — demonstração acidental ao vivo:** encadeando Crossref e
PubMed, o PubMed levou rate limit e a saída foi:

```
PubMedProvider  Encontrados 0 · baixados 0 de 100 (limite) ·
                erro de rede na ESearch: Failed to fetch ...esearch.fcgi... after retries
```

Parada **explicada**, com `stop_error=True` (é o que aciona o `⚠ interrompido` na trilha).
Refeita sem o encadeamento, roda limpa e reprodutível: 12/12 registros nas duas vezes,
`stop_reason='exauriu (todos os PMIDs)'`, `stop_error=False`.

**Testes offline novos** (`tests/test_search_pagination.py`, ambos vermelhos sem o fix):
`test_total_available_is_the_real_base_total_not_the_limit` (OpenAlex: `total_available`
é 319300 enquanto o alvo do `progress_cb` é 1000) e
`test_crossref_and_pubmed_also_expose_total_available`.

### BUG-A.3 — teto do campo Qtd (`1beb0f5`)
`_current_limit()` reescrevia o campo para 10000 **sem dizer nada**: quem digitava 50000
recebia 10000 sem entender por quê — a mesma classe de problema do BUG-A. Agora a trilha
mostra `t("search.limit_capped")` apontando o "Ilimitado".

> **Divergência consciente com o prompt.** O item A.3 pedia "padrão 1000, máximo 10000".
> Isso foi implementado em 12/07 e **revertido a pedido do Leonardo** ("já ficou horrível
> pois limita a 10000, não queria esse limite") em `6bfe474`. Não reimpus teto nenhum.

#### Atualização (2026-07-30) — teto do campo Qtd removido de vez
Commit: `fix: tira o teto do campo Qtd — ilimitado e ilimitado`.
Decisão do Leonardo: *"ilimitado tem que ser ilimitado; a proteção é o aviso de volume, não
o teto silencioso."* O teto de 10000 saiu do `_current_limit()` — **o número digitado vale**
(50000 → 50000), e o campo não é mais reescrito. A mensagem `search.limit_capped`, criada em
`1beb0f5` para explicar o corte, virou órfã e foi removida dos três catálogos.

A proteção contra colher demais sem querer continua inteira, e é a certa: o **aviso de
volume** (`_search_after_count` → `_show_count_dialog`), que a partir de 2000 resultados na
base mostra o total real e oferece "Top 2000 mais citados" / "Baixar todos (N)" / "Cancelar".
Ele informa e deixa escolher, em vez de cortar por trás:

| base | limite pedido | comportamento |
|---|---|---|
| 319300 | 50000 | **aviso de volume** (antes: cortado para 10000 em silêncio) |
| 319300 | Ilimitado | **aviso de volume** |
| 319300 | 1000 | direto (limite baixo, não precisa avisar) |
| 500 | 50000 | direto (base pequena) |

Testes em `tests/test_sort_count.py`: `test_qtd_field_has_no_ceiling` (verificado
reintroduzindo o teto — fica vermelho), `test_qtd_field_defaults_and_unlimited` (entradas
inválidas → padrão 1000; Ilimitado → sentinela) e
`test_count_dialog_threshold_is_the_real_protection` (o aviso segue disparando nos cenários
que o teto cobria).

---

## BUG-B — Blink destruía a revisão ✅ (já estava correto; faltava cobertura)

### Diagnóstico
O drawer de `b99d4ab` está correto: abre na coluna 2 ao lado do feed, sem troca de aba,
sem reconstruir o `SearchFeedView`, e o RAG usa os records **em revisão** (estatísticas +
amostra de abstracts), não o corpus antigo. **Nenhuma correção de produção foi necessária.**

O que faltava era cobertura: o teste existente chamava `open_blink_drawer()` **direto**,
então não exercitava o defeito original, que estava no *callback* — `on_ai_assistant` fazia
`_switch_tab("home")` e a revisão sumia da tela. Uma regressão ali passaria batida.

### Correção (só testes, `daa40aa`)
- `test_blink_button_path_does_not_rebuild_the_feed`: dispara via `_trigger_ai` (o comando
  real do botão) com o callback ligado como em main.py, e compara os **objetos** de card
  (não só a contagem), a seleção, a trilha e a **posição de scroll**, ao abrir e ao fechar.
- `test_main_blink_callback_uses_the_drawer_and_never_switches_tab`: lê o corpo do
  `on_ai_assistant` real em main.py e exige `open_blink_drawer` sem `_switch_tab`.
  Verificado injetando a regressão original em main.py — o teste fica vermelho.

---

## BUG-C — o vão branco gigante continuava lá ❌→✅

### Diagnóstico (medição programática)
O fix de 12/07 pegou só o `left_bar`. Sobraram **outros dois `CTkFrame` criados sem
`height`** — que por isso assumem a altura default de **200px** do CustomTkinter e, quando
ficam **sem filhos**, não encolhem:

| frame | fica vazio quando |
|---|---|
| faixa de badges (row 0) | registro sem ano, citações, OA, idioma nem marca de duplicado |
| faixa de ações (row 4) | registro **Open Access** ou sem DOI (não ganha o botão "Abrir DOI") |

Medindo `winfo_reqheight()` no estado de 12/07:

```
caso                          card   filhos do card minimo
minimo (so titulo)            454    CTkFrame reqh=  1  (left_bar, corrigido em 12/07)
+ autor/fonte                 488    CTkCheckBox reqh= 24
+ abstract curto              520    CTkFrame reqh=200  <-- faixa de badges VAZIA
+ abstract longo + badges     356    CTkLabel reqh= 28  (titulo)
com DOI (botao)               278    CTkFrame reqh=200  <-- faixa de acoes VAZIA
```

**454px para um card de uma linha** — 200 + 200 + 28 de título. É exatamente o vão branco do
screenshot, e explica por que ele aparecia em *alguns* cards e não em todos: dependia de o
registro ter badge e botão. Um registro Open Access com abstract dava 356px.

**Por que o teste passava:** `test_article_card_no_fixed_whitespace` usava um registro com
`year`+`language` (badges) **e** `doi` (botão) — as duas faixas tinham filhos e encolhiam.
O teste media justamente o único caso que funcionava.

### Correção (`6736c5f`)
Ambas as faixas com `height=1`, **seguem gridadas** para preservar o respiro do card. Testei
a alternativa de só gridar quando têm conteúdo e ela quebra o design: a folga inferior caía
de 12px para 4px e o título encostava na borda (folga superior 0px).

```
caso                  altura  folga topo  folga base        card  conteudo  ratio
so titulo                 61          12          12          61        54   1.13
titulo+abstract          105          12          12          90        82   1.10
OA sem botao DOI         132          12          12         122       110   1.11
com botao DOI            155          12          12         157       145   1.08
```

Card mínimo **454px → 61px**; folga de 12px em cima e embaixo em **todas** as variantes;
razão card/conteúdo ~1.1 em todas (o prompt exige no máximo 1.5×).

**Sidebar:** `truncate_source_name()` extraída e testada. Além de proteger o parêntese da
contagem (já feito em 12/07), agora não deixa parêntese **aberto do nome** pendurado:
`"LA Referencia (Red Federal de Repositorios Institucionales)" (305)` →
`"LA Referencia… (305)"` em vez de `"LA Referencia (Red Fe… (305)"`.

### Testes
`test_article_card_no_fixed_whitespace` reescrito: cobre o registro **pelado** (sem badge e
sem botão), o **Open Access** e o com badges, e compara as três variantes entre si (não
podem divergir em centenas de px). Verificado revertendo o fix — falha com `assert 454 < 160`.
`test_truncate_source_name_never_leaves_a_dangling_paren` para a sidebar.

---

### Validação com dados REAIS (não sintéticos)
Busca ao vivo OpenAlex "empreendedorismo" (60 registros de 54067 na base), renderizada num
`SearchFeedView` de verdade — 25 cards na primeira página:

```
 altura  conteudo  ratio  titulo
    151       139   1.09  Empreendedorismo no Brasil
    151       139   1.09  Empreendedorismo social e comercial: igu…
    256       244   1.05  Empreendedorismo no Brasil
    117       109   1.07  Empreendedorismo : transformando idéias …

maior razao card/conteudo: 1.09 (teto do prompt: 1.5)
altura minima: 117px · maxima: 256px
PRIMEIRO CARD: 151px -> sem vao branco
```

As alturas **variam com o conteúdo** (117–256px) em vez de travar num piso — que é o
comportamento que o vão branco escondia. O primeiro card do feed, que era justamente o do
screenshot, fica em 151px com razão 1.09.

**Smoke test do app:** `python3 main.py --smoke-test` → `app subiu, locales/settings OK,
UI fechada limpa` (exit 0).

## Pendência honesta

**Captura de tela continua bloqueada:** `screencapture -x` retorna
`could not create image from display` (permissão de Gravação de Tela não concedida ao
terminal). Não há evidência visual desta sessão. Toda a validação do BUG-C é por **medição
programática** de altura e folga — que é o fallback previsto no próprio prompt, e nesta
sessão foi ela que achou o defeito que o olho no screenshot já tinha visto mas o teste não.
