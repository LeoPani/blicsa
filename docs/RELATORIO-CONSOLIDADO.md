# Blicsa — Relatório consolidado da sessão

**Período:** 2026-07-29 a 2026-08-01 · **Branch:** `fix/passo-7-extensao` · **Base:** `579c032`

Dois blocos de trabalho: a **re-auditoria dos três bugs da tela de revisão** e os **mapas
nível VOSviewer** (cinco fases). Tudo commitado, working tree limpo.

| | |
|---|---|
| Suíte de testes | **143 → 270 passed**, 1 xfailed |
| Testes novos | **127** |
| Commits | 14 |
| Linhas | +6.554 / −168 em 40 arquivos |
| Smoke test do app | OK |
| Paridade i18n | limpa (25 chaves novas × 3 catálogos) |

---

# PARTE I — Re-auditoria dos bugs da tela de revisão

O prompt pedia para corrigir três bugs que **já constavam como corrigidos** numa sessão
anterior. Auditei os três antes de tocar em qualquer código. **Dois ainda estavam quebrados**
— e nos dois casos o teste de regressão existente passava, porque cobria justamente o único
caminho que funcionava.

## BUG-A — a trilha mentia, num ponto diferente do relatado ❌→✅

O erro de rede já não era silencioso (fix anterior intacto). O que mentia era o
**"Encontrados"**: vinha só do `progress_cb`, e os providers passam ali o *alvo da barra de
progresso*, não o total da base:

```python
progress_cb(count_fetched, min(max_results, total_results))   # openalex / crossref
progress_cb(count_fetched, len(id_list))                      # pubmed (já cortada por retmax)
```

Com o limite padrão (1000), a trilha dizia `Encontrados 1000 · baixados 1000` numa busca com
319.300 na base. O ramo `"de N (limite)"` era **código morto**, porque a condição
`total_found_sum > baixados` nunca era verdadeira.

**Por que o screenshot mostrava 319300 certo:** veio do modo *Ilimitado*, onde
`min(9999999, 319300) = 319300`. Com limite finito — que é o **padrão** — sempre esteve errado.

**Correção:** providers expõem `total_available` (total real da API). Ao vivo, mesma busca 2x:

```
RUN 1: Encontrados 54051 · baixados 2000 de 2000 (limite) · atingiu limite
RUN 2: Encontrados 54051 · baixados 2000 de 2000 (limite) · atingiu limite   → idênticas
```

Durante os testes o PubMed levou rate limit e a saída foi
`Encontrados 0 · baixados 0 · erro de rede na ESearch: ... after retries` — demonstração ao
vivo de que a parada é sempre explicada.

## BUG-B — estava correto ✅ (faltava cobertura)

O drawer não precisou de correção: abre ao lado do feed, sem troca de aba, sem reconstruir
nada, e o RAG usa os records em revisão. O que faltava era cobertura — o teste chamava
`open_blink_drawer()` **direto**, sem passar pelo *callback*, que era onde o bug original
vivia (`_switch_tab("home")`). Dois testes novos, um deles verificado injetando a regressão de
volta no `main.py`.

## BUG-C — o vão branco continuava lá ❌→✅

O fix anterior pegou só o `left_bar`. Sobravam **dois outros `CTkFrame` sem `height`**, que
assumem os 200px default do CustomTkinter e não encolhem quando ficam sem filhos: a faixa de
badges (registro sem ano/citações/OA/idioma) e a faixa de ações (registro Open Access ou sem
DOI não ganha o botão). **Card mínimo: 454px.**

O teste passava porque usava um registro com `year`+`language`+`doi` — as duas faixas tinham
filhos e encolhiam. Media justamente o único caso que funcionava.

| | antes | depois |
|---|---:|---:|
| card mínimo | 454px | **61px** |
| folga topo/base | 0px / 4px | 12px / 12px em todas as variantes |
| razão card/conteúdo (dados reais) | — | **1,09** (teto do prompt: 1,5) |

## BUG-C.3 — o mesmo erro no eixo horizontal, achado pela captura de tela

Com a Gravação de Tela liberada, a primeira captura do feed mostrou um defeito que **nenhuma
medição de altura pegaria**: `grid_columnconfigure(1, weight=1)` dava o peso à coluna do
**checkbox**. A coluna do conteúdo encolhia e era empurrada para a direita por uma distância
que dependia da largura de cada card.

```
ANTES: x do título = 362, 194, 403, 726 …  → variação 532px
DEPOIS: 53, 53, 53, 53 …                   → variação 0px
```

É o mesmo erro do BUG-C — dimensão do grid atribuída ao widget errado — no outro eixo. Todos
os testes mediam altura.

## Teto do campo Qtd removido

A pedido do Leonardo (*"ilimitado tem que ser ilimitado; a proteção é o aviso de volume, não o
teto silencioso"*). O número digitado passa a valer (50000 → 50000) e o campo não é mais
reescrito. A proteção que ficou é a certa — o **aviso de volume**, que a partir de 2000
resultados mostra o total real e oferece "Top 2000 mais citados / Baixar todos / Cancelar".

---

# PARTE II — Mapas nível VOSviewer (5 fases)

Referência: [guia do VOSviewer](https://gorlaeus-library.github.io/VOSviewer/howto-topics.html),
seções 9–18.

## Decisões, com o motivo

**Extrator embutido em vez de spaCy.** spaCy + modelo + dependências passam de 100 MB, o Blicsa
é empacotado com PyInstaller, o modelo exige download separado (quebra o offline) e o
`requirements.txt` é pinado e verificado no CI. Mas **spaCy e NLTK são detectados em runtime** —
`method="auto"` usa spacy > nltk > embutido, então quem instalar ganha a qualidade melhor sem
inflar o bundle de todo mundo.

**Relevância por divergência KL** contra a distribuição marginal do corpus, normalizada para
média 1 (conceito do van Eck & Waltman):

```
p(j|i) = c_ij / Σ_j c_ij        ·  q(j) = Σ_i c_ij / Σ_ij c_ij
rel(i) = Σ_j p(j|i) · log( p(j|i) / q(j) )
```

Coocorrer com o termo *mais frequente* do corpus não é sinal de especificidade, e só a
comparação com a marginal captura isso.

**ΔE em vez de WCAG** para julgar a paleta de clusters. Meu primeiro teste usava WCAG e
**reprovava uma paleta perfeitamente legível**: vermelho `#DF3117` e roxo `#B65CA2` dão razão
1,1 porque WCAG mede luminância (é métrica para texto sobre fundo), mas se distinguem sem
esforço — ΔE > 40. Pior par real da paleta: **ΔE 25,6**, acima do limiar de ~20. WCAG segue em
uso onde é correta: nó contra o fundo papel.

## O que foi entregue

**Fase 1 — `core/term_extraction.py`.** Os dois caminhos (keywords e frases nominais de
título+abstract), contagem binária por documento como padrão, unificação singular/plural,
limiar com preview ao vivo (`threshold_preview`, `suggest_threshold`), thesaurus aplicado antes
de contar, detecção de idioma com aviso honesto. 5.000 docs em **0,77s** (meta: 30s).

**Fase 2 — três visualizações compartilhando as mesmas posições.** `core/map_render.py` (rampa,
escala, grade de densidade, ΔE, padrões de impressão) + `core/sigma_exporter.py` reescrito, com
duas regras que viraram contrato: nada de `NaN`/`Infinity` (era o bug do mapa em branco) e
métrica ausente é `null`, não `0` (0 pintaria o nó como "o mais antigo do mapa"). No `map.js`:
abas no canvas, barra de gradiente, resolução de sobreposição de rótulos, isolamento de cluster.

**Fase 3 — `core/map_controls.py` + painel na UI.** Reclusterização **sem refazer o layout**,
lista de termos revisável antes de gerar (passo 13 do guia), contagem binária como controle
próprio, atração/repulsão, `MapParams` persistido no `.blicsa`, export SVG vetorial com legenda
honesta, leitura tolerante da resposta da IA.

**Fase 4 — `core/map_animation.py` + linha do tempo.** Animação com **posições fixas** (por
construção o quadro nem carrega coordenada), play/pause/scrubber/velocidade, export GIF e PNGs
(MP4 degradando sem ffmpeg), cross-fade e stagger com interruptor "Reduzir movimento", modo
apresentação (tecla F), **modo pôster Mondrian** (treemap: área = peso do cluster) e três temas.

**Fase 5 — benchmarks e regressão E2E.** `scripts/benchmark_maps.py`, `scripts/benchmark_fps.py`,
`tests/test_map_regression_e2e.py`.

## Benchmarks

| docs | extração | matriz | layout | **total** | pico |
|---:|---:|---:|---:|---:|---:|
| 1.000 | 0,56s | 0,77s | 1,09s | **2,96s** | 15,1 MB |
| 5.000 | 2,76s | 4,15s | 1,23s | **8,83s** | 13,5 MB |
| 10.000 | 5,62s | 9,28s | 1,43s | **17,07s** | 26,9 MB |

O gargalo em corpus grande é a matriz de coocorrência, não a extração nem o layout.

| nós | rede | overlay | densidade |
|---:|---:|---:|---:|
| 500 | **432 fps** | **324 fps** | **63 fps** |
| 2.000 | **113 fps** | **101 fps** | **44 fps** |
| 5.000 | **42 fps** | **38 fps** | **26 fps** |

Metas batidas: 500 nós a 60fps nos três modos · 2.000 interativo · 5.000 utilizável.

**Gargalo achado e corrigido:** densidade a 11,6 fps com 5.000 nós. Perfilando, o custo era
(células tocadas por ponto) × (nº de pontos) = **14,6 milhões de contas por quadro**. Duas
correções — varrer só a caixa de 3σ do ponto, e célula adaptativa (8/12/16px, sem mudança
visual porque o campo é suave e interpolado). Resultado: **11,6 → 25,8 fps** (5.000 nós) e
**25,5 → 44,4 fps** (2.000 nós).

**Correção de método:** medir fps por `requestAnimationFrame` é inútil aqui — o macOS
suspende o rAF de janela em segundo plano, e a medição saía **vazia**, não baixa. A primeira
rodada "funcionou" por acidente. A métrica passou a ser tempo de render em laço fechado.

---

# Bugs encontrados

## Pré-existentes

**Clusterização não era reprodutível** (o mais grave). Os nós eram inseridos iterando um `set`,
cuja ordem varia com `PYTHONHASHSEED`, e o Louvain depende da ordem de inserção. **O mesmo
corpus com os mesmos parâmetros dava 4 clusters numa execução e 5 na seguinte.** Num programa
científico isso invalida a análise. O teste roda em subprocessos com sementes diferentes,
porque dentro de um processo a ordem do set é estável e o bug não apareceria.

**Tooltip da resolução mentia.** Prometia "valores > 1 geram mais clusters, < 1 geram menos".
Medido no karate club com python-louvain: `0.5 → 5 · 1.0 → 4 · 1.5 → 5 · 2.0 → 7`. Sobe, desce
e sobe — não é monotônico. (O exemplo do guia é da clusterização própria do VOSviewer, que é
outro algoritmo.) Texto corrigido e um teste trava a medição.

## Introduzidos e corrigidos durante o trabalho

| bug | como apareceu |
|---|---|
| `setSetting("nodeReducer")` não repintava — overlay saía com cor de cluster | render real na frente |
| `size` da aresta recebia o `weight` cru (centenas) → borrão cinza | render real na frente |
| costuras de grade na densidade (`globalAlpha` acumulando em bordas) | render real na frente |
| `singularize`: `"improves"` → **`"improfe"`**, `"sizes"` → `"siz"` | teste da própria fase |
| `int(row.get("year"))` quebrava com NaN de coluna ausente | fixture adversarial |
| `"bibliometrics"` → `"bibliometric"`, **`"big data"` → `"big datum"`** | teste E2E |
| `"public relations"` → `"public relation"` (termos plural-only) | teste E2E |

Os dois últimos são notáveis: **os testes de unidade das duas etapas passavam**. Só a costura —
comparar os termos extraídos com os nós que o gerador produziu — expôs a divergência.

---

# Sobre as regras de teste do prompt

## Regra 2 (reinjetar a regressão) — de longe a mais produtiva

39 defeitos reintroduzidos ao todo. Os que **não** derrubaram o teste valeram mais:

| fase | o que a reinjeção revelou |
|---|---|
| 1 | a guarda `grand_total == 0` na relevância era **código morto** (outra já cobria) |
| 1 | o ramo da contagem binária era **redundante** — o dedup a montante já garantia o resultado |
| 1 | minhas asserções de relevância **não distinguiam** a marginal de uma uniforme |
| 3 | o teste da resolução passava com a resolução **fixada em 1.0** (fixture separada demais) |
| 4 | o teste de quadro vazio cobria **só um dos dois ramos** de aviso |

## Regra 5 (provar que a evidência não é vazia) — estava certa e era insuficiente

A primeira captura das evidências do mapa pegou a **tela inteira** em vez da janela do app —
mostrava o terminal e um vídeo do YouTube — e **passou** no teste de histograma, com desvio de
brilho 41. Um desktop cheio é tudo menos uniforme.

Variância prova que a imagem não é chapada; **não prova que é a imagem certa**.
`scripts/verify_evidence.py` valida conteúdo: exige o fundo papel `#F6F4EE` do design system
dominando a imagem e cores de dado presentes. Verificado que reprova a captura de desktop que
antes passava (papel em 0,1% → falha). Para GIF, conta quadros **distintos**, não só quadros.

---

# Evidências visuais

Todas reais, do corpus da fixture gravada do OpenAlex (100 registros → 56 nós, 1.133 arestas,
4 clusters), com o mapa aberto no `pywebview` (WebGL) e a janela capturada por `CGWindowID`.

| arquivo | o que mostra |
|---|---|
| `mapa_network.png` | clusters em cor chapada, rótulos sem colisão |
| `mapa_overlay.png` | rampa azul→amarelo, barra `2014.8 · 2017.4 · 2020` |
| `mapa_density.png` | calor suave com rótulos, duas zonas quentes |
| `mapa_animacao.gif` | **20 quadros (2005–2024), todos distintos entre si** |
| `mapa_poster.png` | treemap Mondrian — erro de área **0,0000%**, cobertura **100%** |
| `mapa_tema_tinta.png` · `mapa_tema_impressao.png` | temas para projeção e para preto e branco |
| `bugc_cards_compactos_alinhados.png` | feed corrigido (BUG-A, BUG-C e BUG-C.3 de uma vez) |

---

# Critérios de aceitação — saída real

```
$ python3 -m pytest tests/ -q
270 passed, 18 deselected, 1 xfailed in 21.45s

$ python3 -m pytest tests/test_term_extraction.py tests/test_sigma_export.py -q
68 passed in 2.60s

$ python3 -c "from PIL import Image; im=Image.open('docs/evidence/mapa_animacao.gif'); print(im.n_frames)"
20

$ python3 scripts/verify_evidence.py docs/evidence/mapa_*.png docs/evidence/mapa_animacao.gif
[OK ] mapa_animacao.gif (1000, 700) · quadros=20 · distintos=20
[OK ] mapa_network.png  (2800, 1680) · papel=85.7% · dados=1.03%
[OK ] mapa_overlay.png  (2800, 1680) · papel=84.1% · dados=1.03%
[OK ] mapa_density.png  (2800, 1680) · papel=40.4% · dados=1.04%

$ python3 main.py --smoke-test
Smoke test passed: app subiu, locales/settings OK, UI fechada limpa.
```

`python -m pytest` não existe neste ambiente (só `python3`) — única alteração nos comandos de
aceitação.

---

# Limitações conhecidas e pendências

- **Extração de frases nominais em português** degrada (limitação reconhecida no próprio guia
  do VOSviewer). O app detecta o idioma e avisa na UI; nunca falha em silêncio.
- **Duas trilhas de extração convivem** — a nova (`core/term_extraction`) e a antiga do gerador
  de grafo (`core/matrix_builders._extract_term_lists`), que normalizam diferente. Foi o que o
  E2E flagrou. As divergências conhecidas estão corrigidas; **unificá-las numa só é a
  recomendação natural para a próxima rodada**.
- **Layout dinâmico da animação** não implementado (item marcado como opcional no prompt).
- **MP4 depende de `ffmpeg`**, ausente nesta máquina — degrada com mensagem clara e o GIF sai
  igual, comportamento previsto e coberto por teste.
- **`docs/sample_dataset.csv` tem 3 registros** — serve de exemplo de formato, mas não produz
  mapa com estrutura; evidências e benchmarks usam a fixture gravada do OpenAlex.
- **Playwright nunca foi usado neste projeto** (o prompt afirmava que sim; não há referência no
  repo). Como a Gravação de Tela está liberada, usei pywebview + `screencapture` por
  `CGWindowID` — render WebGL real, sem dependência nova.

---

# Commits

```
6b36898  docs: relatório dos mapas nível VOSviewer (5 fases)
896d885  perf: benchmarks, regressão ponta a ponta e otimização da densidade
1549709  feat: animação temporal, transições e camada artística do mapa
5518b15  feat: painel de controles de qualidade do mapa
5028471  feat: visualizações de rede, overlay e densidade no canvas Sigma
3f18d4e  feat: extração de termos (frases nominais + keywords) com relevância e limiar
7f44775  fix: BUG-C.3 cards alinhados — peso do grid estava na coluna do checkbox
01f2bbb  fix: tira o teto do campo Qtd — ilimitado é ilimitado
b7412e3  docs: relatório e bugreport da re-auditoria dos 3 bugs da revisão
1beb0f5  fix: BUG-A.3 — o teto de 10000 no campo Qtd deixa de cortar em silêncio
daa40aa  test: BUG-B — cobre o caminho real do botão Blink (drawer já estava correto)
6736c5f  fix: BUG-C card compacto de verdade — dois CTkFrame vazios reservavam 200px cada
ace716a  fix: BUG-A "Encontrados" mostra o total REAL da base (não o limite)
```

**Relatórios detalhados:** `docs/RELATORIO-FIX-REVISAO.md` (Parte I) ·
`docs/RELATORIO-MAPAS.md` (Parte II) · `docs/BUGREPORT.md` (causas-raiz).
