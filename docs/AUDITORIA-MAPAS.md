# Auditoria 1 · Fase 1 — bateria dos mapas com corpus adversariais

**Data:** 2026-08-09 · **Escopo:** itens 1 a 9 de `audit-1-funcional-e-arquitetura.md`

> **Veredito:** os mapas aguentam o que foi jogado neles — nenhum corpus adversarial produziu
> exceção, NaN no payload ou tela em branco. Mas a bateria encontrou **seis defeitos**, e
> quatro deles eram invisíveis para a suíte de 705 testes que existia antes dela.
>
> Dois merecem leitura antes do resto: **o mapa não era reprodutível** (§2.1) e **a animação
> da tela mostrava o ano errado** (§2.3). Os dois estavam sob teste verde.

---

## 1. Matriz de corpus adversariais × três modos

Onze corpus, cada um por um modo de falha conhecido de pipeline de grafo. Cada linha passa
pelo caminho real — `NetworkGenerator` → Louvain → ForceAtlas2 → `build_sigma_payload` — e os
três modos leem o mesmo payload (nós, escalas de overlay, grade de densidade).

Executor: `scripts/audit_mapas.py`. Corpus: `tests/corpus_adversarial.py`, **compartilhados**
com a bateria de testes para que relatório e suíte nunca auditem coisas diferentes.

| caso | o que testa | nós | arestas | comp. | clusters | densidade Σ | s | veredito |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `um_documento` | layout e clusterização com grafo mínimo | 3 | 3 | 1 | 1 | 301,06 | 0,32 | OK |
| `dois_desconexos` | ForceAtlas2/Louvain/densidade, 2 componentes | 6 | 6 | 2 | 2 | 445,91 | 0,01 | OK |
| `dez_desconexos` | o mesmo com 10 componentes | 30 | 30 | 10 | 10 | 637,11 | 0,03 | OK |
| `mesmo_ano` | overlay com variância zero (`vmax == vmin`) | 3 | 3 | 1 | 1 | 301,06 | 0,00 | OK |
| `sem_ano` | overlay com a métrica inteiramente ausente | 3 | 3 | 1 | 1 | 301,06 | 0,00 | OK |
| `frequencias_iguais` | escala de tamanho sem amplitude | 5 | 10 | 1 | 1 | 691,74 | 0,01 | OK |
| `termo_dominante` | escala esmagada por um outlier | 31 | 30 | 1 | 1 | 396,20 | 0,03 | OK |
| `cinco_mil` | 5.000 documentos | 200 | 600 | 1 | 11 | 646,33 | 1,92 | OK |
| `caracteres_dificeis` | acento, emoji, aspas, 600 caracteres | 11 | 27 | 1 | 2 | 636,47 | 0,01 | OK |
| `abstracts_vazios` | grafo vazio | 0 | 0 | 0 | 0 | 0,00 | 0,00 | OK |
| `autores_grafias` | coautoria com a mesma pessoa em 5 grafias | 6 | 5 | 1 | 1 | 597,28 | 0,01 | OK |

**Esta tabela toda verde é o resultado depois das correções.** Na primeira execução ela também
estava toda verde — e havia seis defeitos. O que a mudou não foi rodar de novo, foi **olhar
dentro do payload** em vez de só perguntar se ele existia. A seção 2 é o que apareceu ali.

### Grafo desconexo (item 2)

Duas e dez componentes isoladas. ForceAtlas2 as separa sem coordenada infinita, Louvain
devolve exatamente uma partição por componente (2 e 10), e a densidade cobre todas.
`test_componentes_isoladas_sobrevivem_ao_layout` afirma os três.

---

## 2. Defeitos encontrados

### 2.1 O mapa não era reprodutível — **corrigido**

O item 3 pedia para verificar posições e cores "já que clusters foi corrigido". Medido em
subprocessos com `PYTHONHASHSEED` distinto:

| | seed 0 | seed 1 | seed 2 |
|---|---|---|---|
| ordem dos nós | `98e1aca6` | `98e1aca6` | `98e1aca6` |
| clusters | `ddeba59b` | `ddeba59b` | `ddeba59b` |
| cores | `ed5390bd` | `ed5390bd` | `ed5390bd` |
| **posições** | `415fcf5b` | `8a0e7ab9` | `950e1fc4` |

As coordenadas mudavam **a cada execução**, inclusive entre dois runs com o mesmo
`PYTHONHASHSEED` — ou seja, não era ordem de hash, era RNG puro. Causa em
`fa2_modified/forceatlas2.py:125-126`: com `pos=None`, a biblioteca sorteia a posição inicial
de cada nó com o `random` **global do processo**, que ninguém semeia.

O efeito prático: **uma figura publicada não podia ser refeita.** O usuário regenerava o mapa
do mesmo corpus e recebia outro desenho — os mesmos agrupamentos, em outro lugar.

Corrigido com `core.visualizer.posicoes_iniciais()`, um `random.Random(42)` **local** na mesma
distribuição uniforme que a biblioteca usaria. Semear o `random` global consertaria o layout e
quebraria qualquer outro sorteio do processo.

### 2.2 Zero citação era lido como "sem dado" — **corrigido**

`avg_citations` usava `zero_is_missing=True`, herdado do tratamento do ano. Para ano a regra é
certa — **ano zero não existe**. Para citações é falsa: zero citação é o valor mais comum de
artigo recente.

Num corpus dos últimos dois anos, o overlay inteiro saía cinza com a legenda anunciando "sem
dado" sobre um dado que estava lá. O payload chegava a se contradizer:

```json
{ "citations_sum": 0.0, "avg_citations": null }   // o mesmo nó, o mesmo fato
```

Corrigido nos dois lados: o escritor grava `None` quando não sabe, e o leitor perde o
`zero_is_missing` só para citações.

> **A suíte tinha um teste afirmando o defeito.** `test_missing_metrics_are_null_never_zero`
> exigia que `citations_mean=0.0` virasse `None`. Reescrito com a assimetria explícita, mais
> `test_zero_citacoes_e_zero_e_nao_ausencia_de_dado`.

**Compatibilidade:** projeto salvo antes desta correção tem `citations_mean: 0.0` tanto para
"zero" quanto para "não sei", e nada distingue os dois. Passam a aparecer como zero. É a troca
deliberada — a alternativa mantinha o caso comum quebrado para preservar a leitura de um caso
que o arquivo antigo já não sabia representar.

### 2.3 A animação da tela mostrava o ano errado — **corrigido**

Encontrado **pela captura**, não pelo código. A janela real tem uma linha do tempo no rodapé e
o ano em marca-d'água; o `map.js` a monta assim (linhas 423 e 502):

```js
const y = a.first_year || (a.avg_year ? Math.round(a.avg_year) : null);
```

`first_year` **nunca esteve no payload do Sigma**, e nenhum builder do `NetworkGenerator` o
escrevia nos nós. A animação caía sempre no fallback: cada termo estreava no seu ano **médio**.

Medido: corpus com documentos em 2010, 2011 e 2020 produzia termos com `year_mean = 2013,7`.
A barra do tempo começava em 2013, e os quadros de 2010 a 2012 saíam **vazios** com o corpus
tendo documentos ali. A animação promete mostrar o campo se formando; mostrava outra coisa.

Corrigido em dois pontos: `build_keyword_cooccurrence` grava `first_year = min(anos)`, e
`build_sigma_payload` o carrega até o JS. Verificado: a linha do tempo agora começa em 2010.

> Os 30+ testes de `tests/test_map_animation.py` **passam `first_year` na mão** ao montar o
> grafo. A suíte inteira da animação exercitava um caminho que a aplicação nunca tomava.

### 2.4 Exports corrompidos por quebra de linha no termo — **corrigido**

`nx.read_pajek` levantava `ValueError: No closing quotation` sobre o arquivo que o próprio
`export_pajek` acabara de escrever. Causa: `k.strip().lower()` limpa só as pontas, e uma
quebra de linha **dentro** do termo ia inteira para o nome do nó.

Pajek e VOSviewer são formatos de **um registro por linha**. Um termo com `\n` partia o
registro em cinco linhas físicas:

```
7 quebra
linha 0.0 0.0 ellipse title "<b>quebra
linha</b><br>Ocorrências: 4...
```

O usuário só descobriria ao abrir no Gephi. Corrigido na origem, com
`core.nlp.normalizar_termo`: quebra e tabulação dentro de um termo são artefato de CSV/RIS
malformado, não conceito de duas linhas.

**Aspas não eram o problema** — `aspas "duplas"` sobrevive ao Pajek e volta íntegro. Anotado
porque a correção não pode virar desculpa para apagar caractere legítimo do vocabulário
(`test_aspas_no_termo_sobrevivem_ao_pajek`).

### 2.5 A correção 2.2 quebrou os exports — **corrigido**

Consequência que a própria bateria pegou, no mesmo dia: com `None` valendo "não sei",
`export_gml` levantava `NetworkXError: None is not a string` e `export_gexf` levantava
`TypeError: float() argument must be... not 'NoneType'` — porque `.get(chave, padrao)` **não**
cobre chave presente valendo `None`; o padrão só vale para chave ausente.

O conserto preguiçoso seria `.get(chave, 0.0)`, que reintroduziria no arquivo do Gephi a mesma
mentira que a correção tirou da tela. Ausência passou a ser **omitida** (GML/GEXF, formatos
sem nulo) ou **campo vazio** (TSV do VOSviewer, que escrevia a string literal `None`).

### 2.6 `core/map_animation.py` não tem chamador — **documentado, não corrigido**

543 linhas — quadros, GIF, sequência PNG, MP4, pôster em treemap — importadas **só por
testes**. A única menção fora de `tests/` é um comentário em `core/project.py`.

Não é o mesmo caso do 2.3: a animação que o **usuário** vê é a do `map.js`, e ela funciona.
O que está órfão é o exportador Python (GIF/MP4/pôster), entregue em `a9b2471` e relatado em
`docs/RELATORIO-MAPAS.md` como pronto.

Não corrigido porque ligar isso à interface é **feature nova**, não correção de defeito — e o
prompt desta auditoria autoriza correção de quebra funcional, não ampliação de escopo às
vésperas da publicação. Registrado aqui e não removido em silêncio: módulo testado sem chamador
é decisão de produto pendente, como `generate_insights` em `docs/inventario-ia.md`.

---

## 3. Overlay com extremos (item 4)

| situação | comportamento | veredito |
|---|---|---|
| todos os valores iguais | `uniform: true`, um tick só no meio, `min == max` | OK |
| métrica inteiramente ausente | `min`/`max` nulos, zero ticks, `no_data` = total de nós | OK |
| outlier único (1×20 + 1000) | faixa real preservada, ticks `1 · 500,5 · 1000` | OK |
| valores negativos | faixa `-50 · 0 · 50`, todo `t` dentro de [0,1] | OK |
| nenhum valor | sem ticks, rampa preservada para a legenda não sumir | OK |

A rampa (`stops`) sai sempre, mesmo sem dado — sem ela a legenda ficaria sem barra nenhuma.
Nós sem dado são contados em `no_data` para o JS pintá-los de cinza.

---

## 4. Densidade em zoom (item 5)

Recalculada em relação ao recorte, como no VOSviewer. Corpus `cinco_mil`, grade 32×32:

| zoom | largura do recorte | pontos dentro | Σ da grade | pico | picos locais |
|---|---:|---:|---:|---:|---:|
| 1× (tudo) | 595,30 | 200 | 646,33 | 6.160,57 | 2 |
| 2× | 297,65 | 38 | 514,42 | 2.515,30 | 2 |
| 4× | 148,83 | 4 | 214,96 | 624,42 | 3 |
| 20× | 29,77 | 0 | 0,00 | 0,00 | 0 |
| 0,12× (afastado) | 4.762,44 | 200 | 288,14 | 19.392,25 | 1 |

Grade sempre normalizada em [0,1], determinística para o mesmo recorte, e diferente entre
recortes. Em 20× sobre região vazia a grade zera — correto: σ acompanha a diagonal do recorte,
então nada dentro de 3σ significa nenhuma concentração *nesta vista*.

---

## 5. Animação temporal (item 6)

| corpus | quadros | anos | nós visíveis | posições fixas |
|---|---:|---|---|---|
| um ano só | 1 | `[2020]` | `[3]` | sim |
| buraco no meio (2010, 2011, 2020) | 11 | `2010…2020` | `[3, 3, 3, …]` | sim |
| ano ausente em metade dos registros | 3 | `[2015, 2016, 2017]` | `[0, 3, 3]` | sim |
| nenhum documento com ano | 0 | `[]` | — | — |

Anos sem documento viram quadro **válido e vazio**, não buraco. Corpus sem data nenhuma
devolve lista vazia em vez de inventar um ano. GIF do caso com buraco: **11 quadros, 11
distintos**.

A coluna "nós visíveis" da linha do buraco é o resultado **depois** da correção 2.3 — antes
era `[0, 0, 0, 3, 3, …]`.

---

## 6. Exports (item 7)

Número de nós e arestas conferidos programaticamente contra o mapa em tela, relendo cada
arquivo com o leitor do formato.

| corpus | GML | GEXF | Pajek | JSON topol. | Sigma JSON | VOSviewer |
|---|---|---|---|---|---|---|
| `caracteres_dificeis` (11/27) | OK | OK | OK¹ | OK | OK | OK¹ |
| `dez_desconexos` (30/30) | OK | OK | OK | OK | OK | OK |
| `cinco_mil` (200/600) | OK | OK | OK | OK | OK | OK |

¹ Passaram a funcionar com a correção 2.4. Antes: Pajek ilegível, VOSviewer com uma linha a
mais que o número de nós.

**Injeção verificada e limpa:** o termo `<script>alert(1)</script>` chega ao HTML exportado
pelo pyvis como `<script>` — sem escapar do bloco `<script>`. No mapa Sigma, os
rótulos vão por `textContent` e canvas; o único `innerHTML` com conteúdo recebe string do
catálogo de tradução, nunca dado do corpus.

**Perda de atributo no Pajek:** o formato descarta atributos não-string, e o `networkx` avisa.
Nós e arestas ficam íntegros; `group` (cluster), `size`, `occurrence` e as métricas não vão.
Cosmético para o uso declarado (topologia), anotado porque não é óbvio.

---

## 7. Desempenho medido (item 8)

Medido, não estimado. macOS, Python 3.14.5, ForceAtlas2 com 500 iterações.

| nós | arestas | grafo + overlay | cluster | layout | payload | **total** |
|---:|---:|---:|---:|---:|---:|---:|
| 500 | 2.000 | 0,90 s | 0,01 s | 0,69 s | 0,05 s | **1,65 s** |
| 2.000 | 8.000 | 6,42 s | 0,06 s | 3,95 s | 0,23 s | **10,65 s** |
| 5.000 | 20.000 | 36,26 s | 0,15 s | 12,64 s | 0,56 s | **49,62 s** |

**O gargalo é `compute_overlay_scores`, e ele cresce como nós × documentos.** Para cada nó ele
varre o dataframe inteiro com `.apply()`, três vezes (keywords, autores, título). A 5.000 nós
são 36 dos 50 segundos — quase o triplo do ForceAtlas2, que é o passo que a intuição culparia.

Não otimizado aqui: é refatoração, e o item 21 da Fase 3 é onde ela cabe. Registrado como a
primeira recomendação de desempenho da auditoria.

---

## 8. Ida e volta do `.blicsa` (item 9)

Mapa gerado com parâmetros customizados (`min_occurrence: 7`, `resolution: 1.7`,
`max_nodes: 123`, `counting_method: fractional`, contexto de pesquisa preenchido), salvo,
reaberto e conferido campo a campo.

| corpus | nós/arestas | clusters | cores | posições | `first_year` | parâmetros | rótulos | origem do rótulo | corpus |
|---|---|---|---|---|---|---|---|---|---|
| `caracteres_dificeis` | OK | OK | OK | OK (< 1e-6) | OK | OK | OK | OK | OK |
| `dez_desconexos` | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `termo_dominante` | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `cinco_mil` | OK | OK | OK | OK | OK | OK | OK | OK | OK |

Rótulos com acento e emoji voltam íntegros, e a **origem** de cada rótulo (IA ou humano)
sobrevive — é o que sustenta a convenção do amarelo de `docs/inventario-ia.md` depois de
fechar e reabrir o projeto.

---

## 9. Prova visual

Nove capturas, três corpus × três modos, pela janela real (`pywebview` + WebGL) por
`CGWindowID`, validadas por `check_evidence_privacy`.

| corpus | rede | superposição | densidade |
|---|---|---|---|
| `dez_desconexos` (30 nós, 10 clusters) | `auditoria_mapa_dez_desconexos_network.png` | `…_overlay.png` | `…_density.png` |
| `termo_dominante` (31 nós, 1 cluster) | `auditoria_mapa_termo_dominante_network.png` | `…_overlay.png` | `…_density.png` |
| `caracteres_dificeis` (11 nós, 2 clusters) | `auditoria_mapa_caracteres_dificeis_network.png` | `…_overlay.png` | `…_density.png` |

`80 imagens analisadas · 80 OK · 0 para inspeção humana`.

### O que a captura custou, e por que vale registrar

Três armadilhas, todas reutilizáveis:

1. **Trocar de aba por AppleScript não trocou de aba.** Duas das três capturas saíam com
   assinatura de pixels **idêntica** — `overlay` e `density` eram a mesma imagem. Um veredito
   visual em cima daquilo teria auditado a mesma foto duas vezes. Hoje a troca é
   `document.getElementById("tab-overlay").click()` e o script **confere** `state.mode` antes
   de fotografar.

2. **A janela nascia com o `graph.json` da execução anterior.** `dez_desconexos_density.png`
   saiu mostrando o corpus de caracteres difíceis — captura rotulada errado é pior do que
   captura nenhuma, porque vira linha de tabela num relatório. Hoje a janela nasce em
   `about:blank` e o script espera `graph.order` bater com o número de nós esperado antes de
   fotografar.

3. **O script agora recusa capturas idênticas entre si.** Foi essa verificação que expôs a
   armadilha 1 — e ela existe porque conferir "o arquivo existe" não conferia nada.

Em duas tentativas a captura **recusou** em vez de fotografar a janela do navegador do autor
que estava na frente. O mecanismo de `1a33124` funcionou como projetado.

---

## 10. Aceite

- `python3 -m pytest tests/ -q` → **775 passed, 1 xfailed** (OBS-03 do Crossref, fora do
  escopo). Eram 705 no início da fase: **+70 testes**. ✅
- `python3 scripts/reinject_ia_ux.py` → **62/62 defeitos detectados** (12 novos nesta fase). ✅
- `python3 scripts/audit_mapas.py` → 11 corpus, nenhuma anomalia. ✅
- `python3 scripts/check_evidence_privacy.py` → **80 imagens · 80 OK**. ✅
- Nove capturas reais dos três modos, todas distintas entre si. ✅

### Um furo no próprio arquivo de teste

`scripts/reinject_ia_ux.py` reprovou um teste desta fase antes de eu reprová-lo: o guarda do
determinismo procurava a string `"pos=None"` no código-fonte e ficava vermelho por causa do
**comentário** que explica o defeito. Reescrito para inspecionar o argumento real da chamada
por AST.

E um caso de reinjeção que não reinjetava nada: renomear `"cluster_label_origins"` atingia a
inicialização do dicionário de resultado, que a leitura sobrescreve adiante. Mutação inócua,
teste verde — o furo era do caso, não do teste. Hoje o defeito reinjetado é o que de fato
acontece: o arquivo de origens não chega a ser gravado.

## 11. Recomendações, por prioridade

| # | o que | onde cabe |
|---|---|---|
| 1 | `compute_overlay_scores` é O(nós × documentos) e domina o tempo a partir de 2.000 nós | Fase 3, item 21 |
| 2 | Decidir o destino de `core/map_animation.py`: ligar à interface ou remover | produto |
| 3 | Paleta de clusters tem 8 cores e o corpus de 10 componentes produziu 10 clusters — dois pares de clusters distintos saem pintados igual | cosmético, mas confunde leitura de mapa |
| 4 | `_extract_term_lists` separa keywords por `;` ou `,`; `compute_overlay_scores` separa por `[;\n,]` — dois parsers para o mesmo campo | Fase 3, item 18 |
