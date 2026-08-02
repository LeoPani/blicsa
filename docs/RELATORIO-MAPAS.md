# Relatório — Mapas nível VOSviewer

**Data:** 2026-08-01 · Cinco fases, um commit por fase · Referência conceitual:
[guia do VOSviewer](https://gorlaeus-library.github.io/VOSviewer/howto-topics.html), seções 9–18.

| | |
|---|---|
| Suíte | **270 passed, 1 xfailed** (era 143 no início) |
| Testes novos | **127** somando as cinco fases (mínimo pedido: 40) |
| Commits | `3f18d4e` · `5028471` · `5518b15` · `1549709` · `896d885` |
| Smoke test | `python3 main.py --smoke-test` → OK |
| Paridade i18n | limpa (25 chaves novas nos três catálogos) |

---

## 1. Decisões

### 1.1 Extração de frases nominais: extrator embutido, não spaCy

O padrão-ouro seria POS tagging com spaCy (`en_core_web_sm`). **Não é o caminho padrão**, por
três razões deste projeto:

1. **Peso.** spaCy + modelo + dependências (thinc, blis, murmurhash…) passam de 100 MB. O
   Blicsa é empacotado com PyInstaller e distribuído como app desktop.
2. **Offline.** O modelo exige download em separado. Um app que precisa de rede na primeira
   execução para extrair termos quebra o uso offline, que é premissa aqui.
3. **`requirements.txt` pinado** e verificado no CI — somar uma árvore grande de dependências
   compiladas é risco de build desproporcional ao ganho.

O extrator embutido (`ngram`) aproxima "substantivo com dependentes": remove stopwords,
rejeita tokens com morfologia verbal/adverbial/adjetiva na cabeça da frase e não deixa a
frase atravessar um verbo. **spaCy e NLTK são detectados em tempo de execução** — quem os
instala ganha a qualidade melhor automaticamente (`method="auto"` → spacy > nltk > embutido),
quem não instala não paga o custo.

### 1.2 Fórmula da relevância

Segue o conceito do VOSviewer (van Eck & Waltman): comparar a distribuição de coocorrência de
cada termo com a distribuição **marginal** do corpus.

```
p(j|i) = c_ij / Σ_j c_ij          distribuição observada do termo i
q(j)   = Σ_i c_ij / Σ_ij c_ij     distribuição marginal do corpus
rel(i) = Σ_j p(j|i) · log( p(j|i) / q(j) )      ← divergência de Kullback-Leibler
```

Normalizada para **média 1**, como o VOSviewer faz. Termo genérico coocorre com todo mundo na
proporção em que cada um aparece (≈ marginal) → relevância baixa. Termo específico concentra
coocorrências → alta.

**Por que a marginal e não uma distribuição uniforme:** coocorrer com o termo *mais frequente*
do corpus não é sinal de especificidade, e só a comparação com a marginal captura isso. A
matriz de reinjeção mostrou que minhas asserções iniciais não distinguiam as duas — foi
preciso uma fixture onde a ordem inverte (`test_relevance_compares_against_the_corpus_marginal`).

### 1.3 Paleta e contraste

A paleta de clusters é a do design system, 8 cores. Verificação em
`test_cluster_palette_pairs_are_perceptually_distinguishable`:

| métrica | pior par | valor |
|---|---|---|
| **ΔE (CIE76)** — a que decide | `#7A9E7E` / `#5CB0B8` | **25,6** (limiar ~20) |
| WCAG (referência) | `#DF3117` / `#B65CA2` | 1,1:1 |

**A métrica certa para cores categóricas é ΔE, não a razão WCAG.** WCAG mede luminância, para
texto sobre fundo: vermelho e roxo dão razão 1,1 e se distinguem sem esforço, porque o matiz é
muito diferente (ΔE > 40). Meu primeiro teste usava WCAG e reprovava uma paleta perfeitamente
legível. WCAG segue em uso onde é correta — cor de nó contra o fundo papel.

Rampa do overlay: azul `#1E4DA0` → verde `#7A9E7E` → amarelo `#F5BE00`. É **a única escala
contínua da UI**, porque ali o gradiente é informação. As paradas vivem no Python e vão para o
JS no payload: fonte única da verdade, então a barra de gradiente e as cores dos nós não podem
discordar.

---

## 2. Benchmarks

### 2.1 Geração do mapa (`scripts/benchmark_maps.py`)

Corpus sintético com 5 temas plantados e vocabulário de cauda longa (Zipf) — ruído uniforme
geraria um grafo sem comunidades e mediria um caso que não existe.

| docs | termos | nós | arestas | extração | matriz+clusters | layout | payload | **total** | pico |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.000 | 163 | 104 | 1.441 | 0,56s | 0,77s | 1,09s | 0,55s | **2,96s** | 15,1 MB |
| 5.000 | 187 | 125 | 2.680 | 2,76s | 4,15s | 1,23s | 0,69s | **8,83s** | 13,5 MB |
| 10.000 | 205 | 143 | 3.682 | 5,62s | 9,28s | 1,43s | 0,75s | **17,07s** | 26,9 MB |

O gargalo em corpus grande é a **matriz de coocorrência** (9,3s dos 17s com 10k documentos),
não a extração nem o layout. Memória nunca passa de 27 MB.

### 2.2 Renderização (`scripts/benchmark_fps.py`)

Medido no pywebview real, WebGL, três modos, pan/zoom automatizado.

| nós | arestas | rede | overlay | densidade |
|---:|---:|---:|---:|---:|
| 500 | 2.886 | 2,3 ms → **432 fps** | 3,1 ms → **324 fps** | 16,0 ms → **63 fps** |
| 2.000 | 11.647 | 8,9 ms → **113 fps** | 9,9 ms → **101 fps** | 22,5 ms → **44 fps** |
| 5.000 | 29.530 | 23,7 ms → **42 fps** | 26,6 ms → **38 fps** | 38,7 ms → **26 fps** |

Metas do prompt: 500 nós a 60fps ✅ (os três modos) · 2.000 interativo ✅ · 5.000 utilizável ✅.

**Por que a métrica é tempo de render e não fps por `requestAnimationFrame`:** o macOS
estrangula — e às vezes suspende — o rAF de janela que não está em primeiro plano. A medição
saía **vazia**, não baixa, e só funcionava quando a janela tinha foco; a primeira rodada
"funcionou" por acidente. Além disso o rAF é limitado pelo vsync a 60, então só diria "≥60 ou
não", sem mostrar a folga. O tempo de render em laço fechado é reprodutível e revela a
margem real. O fps observado continua sendo reportado quando o sistema deixa medir.

### 2.3 Gargalo encontrado e corrigido

O benchmark mostrou **densidade a 11,6 fps com 5.000 nós**, enquanto rede e overlay ficavam
acima de 37. Perfilando, o custo é (células tocadas por ponto) × (nº de pontos):

```
 5000 nós · grade 150x100 = 15.000 células · 2.925 células/ponto · 14,6M contas/quadro
```

Duas correções:

1. O laço do kernel passou a varrer só as células dentro da **caixa de 3σ** do ponto. A versão
   anterior tinha o teste de corte, mas ainda percorria a grade inteira.
2. **Célula adaptativa** ao tamanho do grafo (8/12/16px). A densidade é um campo suave e o
   buffer é interpolado ao desenhar, então engrossar a célula não muda o resultado visual e
   corta o custo quadraticamente.

| | antes | depois |
|---|---:|---:|
| densidade, 2.000 nós | 25,5 fps | **44,4 fps** |
| densidade, 5.000 nós | 11,6 fps | **25,8 fps** |

### 2.4 Animação

500 nós → 12 quadros montados em 0,00s, renderizados a **7 ms/quadro**.

---

## 3. Testes por fase

| fase | arquivo | testes |
|---|---|---:|
| 1 — extração de termos | `tests/test_term_extraction.py` | 49 |
| 2 — três visualizações | `tests/test_sigma_export.py` | 19 |
| 3 — controles de qualidade | `tests/test_map_controls.py` | 28 |
| 4 — animação e camada artística | `tests/test_map_animation.py` | 22 |
| 5 — regressão ponta a ponta | `tests/test_map_regression_e2e.py` | 9 |

Todas as fases seguiram as cinco regras de teste do prompt. A **regra 2 (reinjetar a
regressão)** foi a mais produtiva: 39 defeitos reintroduzidos ao todo, e os que *não*
derrubaram o teste apontaram problemas que eu não veria.

### O que a reinjeção encontrou

| fase | o que estava errado |
|---|---|
| 1 | a guarda `grand_total == 0` na relevância era **código morto** (outra guarda já cobria) |
| 1 | o ramo da contagem binária era **redundante** — o dedup a montante já garantia o resultado |
| 1 | minhas asserções de relevância **não distinguiam** a marginal de uma distribuição uniforme |
| 3 | o teste da resolução passava com a resolução **fixada em 1.0** (fixture separada demais) |
| 4 | o teste de quadro vazio cobria **só um dos dois ramos** de aviso |

---

## 4. Bugs encontrados e corrigidos

### Pré-existentes

**Reprodutibilidade da clusterização** (o mais grave). Os nós eram inseridos iterando um
`set`, cuja ordem varia com `PYTHONHASHSEED`, e o Louvain depende da ordem de inserção. O
**mesmo corpus com os mesmos parâmetros dava 4 clusters numa execução e 5 na seguinte** — num
programa científico isso invalida a análise. O teste roda em subprocessos com sementes
diferentes, porque dentro de um mesmo processo a ordem do set é estável e o bug não apareceria.

**Tooltip da resolução mentia.** Prometia "valores > 1 geram mais clusters, < 1 geram menos".
Medido no karate club com python-louvain: `0.5 → 5 · 1.0 → 4 · 1.5 → 5 · 2.0 → 7`. Sobe, desce
e sobe — não é monotônico. (O exemplo do guia, 1.0 → 1.20 mudando 3 para 4 clusters, é da
clusterização própria do VOSviewer, que é outro algoritmo.) Texto corrigido e um teste trava a
medição.

### Introduzidos e corrigidos durante o trabalho

| bug | como apareceu |
|---|---|
| `setSetting("nodeReducer")` não repintava — o overlay saía com cor de cluster | render real na frente |
| `size` da aresta recebia o `weight` cru (centenas) → borrão cinza | render real na frente |
| costuras de grade na densidade (`globalAlpha` acumulando em bordas sobrepostas) | render real na frente |
| `singularize` com regra cega `ves→fe`: "improves" → "**improfe**" | teste da própria fase |
| `int(row.get("year"))` quebrava com NaN de coluna ausente | fixture adversarial |
| nomes de área destruídos: "bibliometrics" → "bibliometric", "**big data" → "big datum**" | teste E2E |
| termos plural-only: "public relations" → "public relation" | teste E2E |

Os dois últimos são notáveis: **os testes de unidade das duas etapas passavam**. Só a costura
— comparar os termos extraídos com os nós que o gerador produziu — expôs a divergência.

---

## 5. Evidências visuais

Todas reais, geradas do corpus da fixture gravada do OpenAlex (100 registros → 56 nós, 1.133
arestas, 4 clusters), com o mapa aberto no `pywebview` (WebGL) e a janela capturada por
`CGWindowID`.

| arquivo | o que mostra |
|---|---|
| `docs/evidence/mapa_network.png` | clusters em cor chapada, rótulos sem colisão |
| `docs/evidence/mapa_overlay.png` | rampa azul→amarelo, barra de gradiente `2014.8 · 2017.4 · 2020` |
| `docs/evidence/mapa_density.png` | calor suave com rótulos por cima, duas zonas quentes |
| `docs/evidence/mapa_animacao.gif` | **20 quadros (2005–2024), todos distintos entre si** |
| `docs/evidence/mapa_poster.png` | treemap Mondrian — erro de área **0,0000%**, cobertura **100%** |
| `docs/evidence/mapa_tema_tinta.png` | tema para projeção em sala escura |
| `docs/evidence/mapa_tema_impressao.png` | preto e branco, clusters por hachura |

### Sobre a regra 5 do prompt (provar que a evidência não é vazia)

A regra estava certa e era **insuficiente**. A primeira captura pegou a tela inteira em vez da
janela do app — mostrava o terminal e um vídeo do YouTube — e **passou** no teste de
histograma com desvio de brilho 41. Um desktop cheio é tudo menos uniforme.

Variância prova que a imagem não é chapada; não prova que é a imagem certa.
`scripts/verify_evidence.py` valida **conteúdo**: exige o fundo papel `#F6F4EE` dominando a
imagem e cores de dado presentes. Verificado que ele reprova a captura de desktop que antes
passava (papel em 0,1% → falha). Para GIF, conta quadros **distintos**, não só quadros.

---

## 6. Limitações conhecidas

**Extração de frases nominais em português.** É limitação reconhecida no próprio guia do
VOSviewer: o algoritmo depende da gramática inglesa. O Blicsa detecta o idioma predominante e
avisa na UI (`map.warn_non_english`), recomendando keywords ou thesaurus. Nunca falha em
silêncio.

**Qualidade do extrator embutido.** Sem POS tagging real, adjetivos ocasionalmente entram como
termo e frases que atravessam um verbo escapam do filtro morfológico. Instalar spaCy resolve —
o app passa a usá-lo sozinho.

**Termos plural-only são lista curada.** "public relations", "human resources", "operations
research"… O caminho geral para o resto é o thesaurus, que o usuário controla.

**Duas trilhas de extração convivem.** `core/term_extraction.extract_terms` (Fase 1, com
singularização e relevância KL) e `core/matrix_builders._extract_term_lists` (a antiga, que
alimenta o gerador de grafo) normalizam de formas diferentes. Foi o que o E2E flagrou. As
diferenças conhecidas estão corrigidas; **unificar as duas numa só é a recomendação natural
para a próxima rodada**, e reduziria a superfície de divergência a zero.

**Layout dinâmico da animação não foi implementado** (item 4.4, marcado como opcional no
prompt): recalcular o layout por período com interpolação. O modo de layout fixo é o
implementado — e é o que torna a animação legível, então a pendência é de "impressionar mais",
não de função.

**`docs/sample_dataset.csv` tem 3 registros.** Serve de exemplo de formato, mas não produz mapa
com estrutura. As evidências e os benchmarks usam a fixture gravada do OpenAlex (100
registros, offline, reprodutível). O CSV de exemplo segue coberto por um teste de carga.

**MP4 depende de `ffmpeg`**, que não existe nesta máquina. O export degrada com mensagem clara
e o GIF sai igual — comportamento previsto no prompt e coberto por teste.

---

## 7. Critérios de aceitação — saída real do terminal

```
$ python3 -m pytest tests/ -q
270 passed, 18 deselected, 1 xfailed, 3 warnings in 21.45s

$ python3 -m pytest tests/test_term_extraction.py tests/test_sigma_export.py -q
68 passed in 2.60s

$ ls -la docs/evidence/mapa_*.png docs/evidence/mapa_animacao.gif
-rw-r--r--  1445975  docs/evidence/mapa_animacao.gif
-rw-r--r--  2239011  docs/evidence/mapa_density.png
-rw-r--r--  1659551  docs/evidence/mapa_network.png
-rw-r--r--  1207320  docs/evidence/mapa_overlay.png
-rw-r--r--    48254  docs/evidence/mapa_poster.png
-rw-r--r--   218241  docs/evidence/mapa_tema_tinta.png
-rw-r--r--   214560  docs/evidence/mapa_tema_impressao.png

$ python3 -c "from PIL import Image; [print(f, Image.open(f).size) for f in [...]]"
docs/evidence/mapa_network.png (2800, 1680)
docs/evidence/mapa_overlay.png (2800, 1680)
docs/evidence/mapa_density.png (2800, 1680)
docs/evidence/mapa_poster.png (1400, 1000)

$ python3 -c "from PIL import Image; im=Image.open('docs/evidence/mapa_animacao.gif'); print('frames:', im.n_frames)"
frames: 20

$ python3 scripts/verify_evidence.py docs/evidence/mapa_*.png docs/evidence/mapa_animacao.gif
[OK ] mapa_animacao.gif (1000, 700) · quadros=20 · distintos=20
[OK ] mapa_network.png  (2800, 1680) · cores=3735  · papel=85.7% · dados=1.03%
[OK ] mapa_overlay.png  (2800, 1680) · cores=6576  · papel=84.1% · dados=1.03%
[OK ] mapa_density.png  (2800, 1680) · cores=17385 · papel=40.4% · dados=1.04%

$ python3 main.py --smoke-test
Smoke test passed: app subiu, locales/settings OK, UI fechada limpa.
```

**Nota sobre o comando do prompt:** `python -m pytest` não existe neste ambiente (só
`python3`). Foi a única alteração feita nos comandos de aceitação.

---

## 8. Roteiro de validação humana

Cinco minutos, com o app aberto:

1. **Importar** um corpus e ir em Análises → gerar o mapa.
2. **Revisar termos** (botão novo): conferir que a lista traz ocorrências e relevância, que
   ordenar por relevância põe os termos específicos no topo, e que desmarcar dois termos e
   regenerar os remove do mapa.
3. **Limiar**: mover o slider e conferir que o preview de contagem bate com o número de nós
   depois de gerar.
4. **Três abas** no topo do canvas: alternar rede → sobreposição → densidade. O mapa **não pode
   se mover** na troca; só a camada visual muda. Na sobreposição, conferir a barra de gradiente
   e que nó sem dado fica cinza com a contagem na legenda.
5. **Resolução**: mudar o slider e clicar "Aplicar resolução (sem refazer layout)". Os clusters
   mudam de cor, os nós ficam onde estavam.
6. **Linha do tempo**: play. Os nós devem aparecer ao longo dos anos **sem saltar de posição**.
7. **Tecla F**: modo apresentação. **Esc**: volta.
8. **Salvar `.blicsa`, fechar e reabrir**: os parâmetros e os termos excluídos voltam como
   estavam.
