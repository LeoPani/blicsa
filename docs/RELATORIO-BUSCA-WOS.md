# Relatório — Busca instantânea no modelo Web of Science

**Data:** 2026-08-02 · Quatro fases, um commit por fase.

| | |
|---|---|
| Suíte | **394 passed, 1 xfailed** (era 287 no início) |
| Testes novos | **107** somando as fases (mínimo pedido: 40) |
| Commits | `12f0adc` · `589127a` · `1b130cb` · `4040b11` (+ este) |
| Smoke test | `python3 main.py --smoke-test` → OK |
| Paridade i18n | limpa (29 chaves novas × 3 catálogos) |

---

## 1. Arquitetura dos dois modos

A premissa: **navegar e baixar são operações separadas**. O app colhia os 319.300 registros
antes de desenhar o primeiro card; o WoS mostra "Results: 849" e "1 of 85" na hora porque não
baixa nada além da página visível.

### Modo Navegação (`core/browse.py`)

```
buscar  →  1 requisição  →  meta.count + os 25 primeiros   (contagem E cards juntos)
página  →  1 requisição  →  os 25 daquela página            (LRU de 12 páginas)
faceta  →  1 requisição  →  contagens do universo inteiro   (group_by, sem baixar registro)
```

`BrowseSession` guarda query, filtros, facetas ativas, ordenação e página. Três decisões que
merecem registro:

- **Token incremental por requisição.** Resposta de token velho é descartada. Sem isso uma
  busca ampla disparada antes responde depois e sobrescreve a lista com o resultado da query
  anterior — e o usuário não tem como perceber que está vendo a resposta errada.
- **Ordenação sempre via API.** Em memória só ordenaria os 25 da página corrente, o que é
  pior que não ordenar: parece que funcionou.
- **Provider declara suas facetas.** Crossref e PubMed têm `FACETS = {}`, então a sidebar de
  refinamento não aparece para eles. Oferecer um filtro que não filtra foi a origem do BUG-02.

### Modo Importação (`core/import_job.py`)

Limite **vazio = ilimitado** (padrão). Acima de 10.000 registros aparece o aviso com o número
real e a estimativa, com três saídas: baixar tudo, limitar, cancelar. O aviso olha **o que
será baixado**, não o total do universo — quem já limitou não é incomodado.

Cancelar preserva o parcial. A trilha final é completa: `Encontrados N · baixados M · após
deduplicação K · filtrados por idioma X`, com aviso explícito de interrupção por rede.

---

## 2. Medições live

**Método:** query `empreendedorismo`, sem filtros, base OpenAlex; 3 repetições, **mediana**
(a média seria puxada por um outlier de rede); cada repetição com `BrowseSession` e provider
**novos**, sem cache herdado; relógio `time.perf_counter()`.
Reproduzível por `python3 scripts/benchmark_search.py`.

| medida | mediana | meta | status |
|---|---:|---:|---|
| contagem visível | **1,04s** | 1,5s | OK |
| primeiros 25 cards | **1,04s** | 2,5s | OK |
| troca de página | **1,30s** | 1,5s | OK |
| aplicar faceta | **1,07s** | 1,5s | OK |
| remover faceta | **0,01s** | 1,5s | OK¹ |
| 6 facetas em sequência | 2,58s | — | 6/6 ok |
| importar 1.000 registros | 10,4s (96 reg/s) | — | — |

¹ Remover um chip volta a um estado já visitado, e a URL é servida pelo cache HTTP do
provider. É o tempo real que o usuário sente, mas **não é uma ida à rede** — registrado assim
para o número não ser lido como "a API responde em 10ms".

A contagem e os primeiros 25 saem da **mesma requisição**, então o tempo é o mesmo: a
contagem não custa uma chamada extra.

### Reprodutibilidade

Mesma busca, duas execuções, sessões e providers novos:

```
execução 1: total=54356 · página 1 com 25 registros · 1,83s
            type=[('article', 29730)]  language=[('pt', 44333)]
execução 2: total=54356 · página 1 com 25 registros · 1,08s
            type=[('article', 29730)]  language=[('pt', 44333)]
```

Contagem e contagens de faceta **idênticas**. A diferença de tempo é conexão fria na primeira.

---

## 3. Teste de stress

**Método:** widgets por contagem recursiva de descendentes do `SearchFeedView`; threads por
`threading.enumerate()`; memória por `tracemalloc`. Reproduzível por
`pytest tests/test_search_stress.py -q -s`.

| cenário | widgets | threads | memória |
|---|---|---|---|
| 20 trocas de página | 781 → 784 (+3) | 1 → 1 | +7,3 MB |
| 20 alternâncias de faceta | 830 → 830 (**0**) | 1 → 1 | — |

Sem vazamento, sem thread pendurada. O cache tem teto: navegar 100 páginas guarda 12
(`CACHE_PAGINAS`), e 12 navegações por 3 páginas custam 3 requisições.

Determinismo verificado em **subprocessos com `PYTHONHASHSEED` diferente** — dentro de um
mesmo processo a ordem de iteração é estável e o problema não apareceria. Foi assim que o bug
de clusters não-determinísticos escapou no trabalho dos mapas.

---

## 4. Nota de risco — orçamento da API do OpenAlex

**Medido ao vivo em 2026-08-02**, lendo os headers de resposta:

| requisição | créditos | custo US$ |
|---|---:|---:|
| página (qualquer `per_page`) | **10** | 0,001 |
| faceta (`group_by`) | **1** | 0,0001 |

Teto sem chave: `X-RateLimit-Limit: 1000` créditos/dia (US$ 0,10/dia), com
`X-RateLimit-Reset` em segundos. O `mailto` **continua funcionando** (HTTP 200, 12/12 numa
rajada), sem degradação observada.

**O que isso significa na prática:**

- ~100 visualizações de página por dia, ou
- ~62 buscas completas com a sidebar inteira (1 página + 6 facetas = 16 créditos).

**Isto valida a arquitetura de facetas:** carregar as seis facetas custa 6 créditos, menos que
uma única página extra. Trocar faceta é barato; folhear muitas páginas é o que consome.

**Recomendação (não implementada — o prompt pede reportar, não bloquear):** campo opcional
"Chave OpenAlex" nos Ajustes, funcionando sem chave por padrão. Já deixei o dado disponível:
`SearchProvider.rate_limit` captura `remaining`/`limit`/`used_by_last`/`reset_seconds` a cada
resposta, então uma UI futura pode avisar quando estiver acabando — em vez de o usuário
descobrir o teto com um 429 no meio de uma busca. Nada bloqueia nem cobra.

---

## 5. Bugs encontrados

### Dois que só a medição ao vivo revelou

**`per_page=1` truncava as facetas para UM grupo.** A chamada de `group_by` levava
`per_page=1` para "não baixar registros" — mas uma resposta de `group_by` **não traz
`results`** de qualquer jeito (medido: `results=0`, custo idêntico), e o parâmetro limitava a
lista de grupos. A sidebar mostraria "article (29.730)" e mais nada, em vez dos 26 tipos.
A captura de tela não pegou porque usava facetas **sintéticas** — foi preciso capturar com
facetas reais para o defeito aparecer.

**A faceta aplicava o próprio filtro.** Marcar "Artigo" fazia "Capítulo de livro" sumir da
lista de tipos, prendendo o usuário na escolha que ele acabou de fazer: para trocar, teria de
remover o chip primeiro. Corrigido com `filters_excluding(campo)` — a faceta X ignora o
filtro de X e respeita os das outras categorias, que é como o "Refine Results" do WoS
funciona.

### Um pré-existente

**`self.feed` misturava gerenciadores de geometria** — cards em `grid`, botão "Carregar mais"
em `pack`. Convivia por acaso, porque os dois nunca eram removidos no mesmo ciclo. Ao somar os
frames de estado (vazio/erro), o Tk passou a recusar com
`cannot use geometry manager "pack" ... grid is already managing`. Corrigido no `_clear_feed`.

### Um de arquitetura, corrigido

**A seleção era por índice.** Funcionava enquanto tudo estava carregado de uma vez; com
paginação, "índice 3" é um registro na página 1 e outro na página 2 — a marcação migraria
para registros que o usuário nunca escolheu. Agora há `record_key()` (DOI normalizado; sem
DOI, título normalizado + ano) e `selected_keys`, que atravessa páginas.

---

## 6. O que a reinjeção encontrou nos meus próprios testes

39 defeitos reintroduzidos ao todo. Os que **não** derrubaram o teste apontaram problemas na
minha cobertura:

| fase | o que estava errado no teste |
|---|---|
| 1 | o teste do cache LRU media `urlopen`, mas o `fetch_url` tem o **próprio** cache por URL — dava verde com o cache da sessão desligado. Passou a espionar `provider.browse` |
| 1 | a injeção que "esvaziava" as facetas trocava **uma chave só**; as outras cinco seguiam valendo |
| 2 | "limite deixa de cortar" passava por **sorte aritmética**: 10.000 é múltiplo exato do lote de 25. Teste novo com limite 10.007, que cai no meio de um lote |
| 2 | "progresso pode regredir" não caía porque há **duas guardas independentes**, cada uma suficiente sozinha. Verificado que remover as duas deixa vermelho; a redundância ficou anotada no código |

O padrão que se repete: **guarda redundante faz a reinjeção individual passar**. Já apareceu
três vezes nesta base (a guarda KL nos mapas, o `max(1,…)` do slider, e agora o progresso).
Vale como regra: ao injetar um defeito e ver verde, procurar a segunda guarda antes de
concluir que o teste é fraco.

---

## 7. Evidências visuais

Capturadas pela **janela do app** (`screencapture -l <CGWindowID>`), nunca a tela inteira, e
validadas com `scripts/verify_evidence.py`:

| arquivo | verificação |
|---|---|
| `docs/evidence/busca_wos_estilo.png` | OK · 2940×1680 · papel 54,3% · dados 12,7% |
| `docs/evidence/busca_blink_drawer.png` | OK · 2940×1680 · papel 52,7% · dados 13,1% |

`busca_wos_estilo.png` mostra: "Resultados: 319.300", chips removíveis, sidebar "Refinar
resultados" com **10 valores reais por faceta** vindos da API (article 2.769, book-chapter
359, dissertation 228…), 25 cards com badges/título/autores/abstract, e
"◀ Página 1 de 12.772 ▶" com campo para pular.

`busca_blink_drawer.png` mostra o Blink aberto **ao lado**, com o feed inteiro visível atrás.

---

## 8. Limitações e pendências de validação humana

- **O modo navegação não está ligado ao fluxo de busca do `main.py`.** `core/browse.py` e a
  UI (`load_browse_page`, `render_facets`, `render_chips`, paginação) estão prontos e
  testados, e a evidência visual foi gerada com o `SearchFeedView` real — mas o botão Buscar
  ainda dispara o caminho antigo (colheita completa). **Ligar o botão é o passo seguinte**, e
  vale fazer com o app aberto na frente.
- **Facetas de `source` e `author`** devolvem a URI do OpenAlex como chave e o nome legível
  como rótulo. A API aceita as duas formas no filtro (verificado), e o chip mostra o nome —
  mas quem construir filtro por fora precisa saber disso.
- **Crossref e PubMed não têm facetas.** É limitação das APIs, declarada em `FACETS = {}` e
  refletida na UI.
- **O `remover faceta` de 0,01s** é cache HTTP, não rede (ver nota ¹ na tabela).
- **Chave do OpenAlex**: recomendação registrada, não implementada.

---

## 9. Critérios de aceitação — saída real

```
$ python3 -m pytest tests/ -q
394 passed, 18 deselected, 1 xfailed, 3 warnings in 92.82s

$ grep -c "def test_" tests/test_search_browse.py tests/test_search_stress.py
tests/test_search_browse.py:42
tests/test_search_stress.py:8

$ python3 scripts/verify_evidence.py docs/evidence/busca_*.png --expect any
[OK ] busca_wos_estilo.png   (2940, 1680) · papel=54.3% · dados=12.71%
[OK ] busca_blink_drawer.png (2940, 1680) · papel=52.7% · dados=13.07%

$ python3 main.py --smoke-test
Smoke test passed: app subiu, locales/settings OK, UI fechada limpa.
```

`python -m pytest` não existe neste ambiente (só `python3`), e não há marcador `-m live`: as
medições ao vivo estão em `scripts/benchmark_search.py`, fora da suíte, para o pytest não
depender de rede.

---

# Religamento do fluxo (2026-08-02, mesma sessão)

A pendência principal do relatório acima está resolvida: **o botão Buscar usa o modo
navegação**. Verificado com o app aberto na frente e busca real na API.

## O que mudou

`_on_gui_search` deixou de contar e disparar a colheita completa; agora chama `_open_browse`,
que monta a `BrowseSession`, busca a página 1 numa thread e desenha a lista. As facetas vêm
logo depois, também em thread. O caminho antigo (`search_to_dataset`) **continua vivo** — é
usado pela re-consulta da sidebar, pela prévia e pela recarga offline do backlog.

O download em massa migrou para o botão "Importar para o corpus": sem nada marcado, ele
importa o conjunto inteiro da busca corrente, passando pelo aviso de volume. Com registros
marcados, importa só eles.

**Medido no app real** (`empreendedorismo`, base OpenAlex):

```
lista pronta em 1,5s · total=54.409 · páginas=2.177 · cards=25
facetas: type=10 · language=10 · publication_year=10 · is_oa=2 · source=10 · author=10
```

## Facetas em paralelo — lacuna que o religamento expôs

O prompt da Fase 1 pedia as facetas "em paralelo" e eu havia implementado em série. Só
apareceu ao rodar o app: a sidebar ficava um retângulo branco vazio por vários segundos ao
lado de uma lista já pronta.

| | tempo |
|---|---:|
| 6 facetas em série | **8,11s** |
| 6 facetas em paralelo | **1,49s** |

Mesmo custo em créditos (1 por faceta); o que muda é a espera. A ordem de exibição continua
estável — quem responde primeiro não reordena a sidebar. Somado um estado "Carregando
filtros…" enquanto elas não chegam.

## Chave OpenAlex (opcional) e erro 429

**Ajustes → Chave OpenAlex**, vazio por padrão. Quando preenchida, entra em todas as
requisições do provider — um único ponto (`OpenAlexProvider.fetch_url`), em vez de repetir o
parâmetro nos cinco lugares que montam URL. O app funciona sem ela, que é o caminho normal.

**429 esgotado virou um tipo próprio** (`RateLimitError`, subclasse de `IOError` para quem já
tratava erro de rede continuar funcionando). A UI mostra:

> Limite gratuito diário do OpenAlex atingido. Uma chave gratuita, colada em Ajustes → Chave
> OpenAlex, aumenta esse limite. O app continua funcionando sem ela — o limite volta a zerar
> em algumas horas.

Em vez de `Failed to fetch https://api.openalex.org/works?per_page=25&mailto=…`, que não diz
ao usuário o que fazer. Erro 500 esgotado **continua** genérico — o teste cobre os dois lados.

**Nenhum contador de créditos nem aviso preventivo na UI**, conforme pedido. O
`SearchProvider.rate_limit` segue capturando os headers, mas nada é exibido: o usuário só
ouve falar do limite se de fato bater nele.

## Evidências

| arquivo | como foi feito |
|---|---|
| `docs/evidence/busca_religada.png` | app real, clique programático no Buscar, **dado vivo da API** (54.409 resultados, facetas com contagens reais) |
| `docs/evidence/busca_erro_429.png` | app real, com o **HTTP 429 injetado no transporte** |

Sobre o 429: o gatilho é simulado, a mensagem e a tela são reais. Provocar um 429 de verdade
exigiria queimar a cota diária inteira do Leonardo por uma captura — troca ruim. Está dito
aqui para o número não ser lido como "aconteceu na prática".

## Duas coisas que deram errado no caminho

**Uma captura pegou a janela do navegador do Leonardo.** O script tinha um fallback: se não
achasse o `CGWindowID`, capturava o **retângulo de tela** nas coordenadas da janela — e
capturou o que estava ali, que era outro app. O arquivo foi apagado na hora e o fallback,
removido: agora falha em voz alta em vez de gravar a janela errada e chamar de evidência.

**Quebrei meu próprio roteiro** ao trocar `time.sleep` global para acelerar o teste do 429 —
as esperas do roteiro usavam a mesma função, e o laço rodou instantaneamente. Só o `urlopen`
é trocado agora.

## Pendência

**A captura do diálogo de Ajustes não saiu.** Ele usa `overrideredirect(True)` e é uma janela
separada; a captura por `CGWindowID` da janela principal não o inclui, e a listagem do Quartz
para janelas Tk se mostrou intermitente (funcionou em algumas execuções, não em outras). O
campo está coberto por testes (chave ausente por padrão, anexada quando configurada, lida dos
Ajustes, não duplicada) e a instrução aparece na captura do 429. Fica como validação humana:
abrir Ajustes e conferir o campo "Chave OpenAlex (opcional)".

Suíte: **407 passed, 1 xfailed**. Smoke test OK.
