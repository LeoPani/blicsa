# Código sem chamador — levantamento e decisão

**Data:** 2026-08-09 · **Motivo:** código testado e sem chamador em repositório público gera
pergunta de revisor. As três peças abaixo não podem ficar como estão.

**Regra aplicada:** funcionalidade **completa e testada → ligar à interface**; funcionalidade
**parcial → remover e registrar como trabalho futuro**.

| peça | estado | decisão |
|---|---|---|
| `core/map_animation.py` | completa, 22 testes, 543 linhas | **ligar** |
| `generate_seminal_insights` | completa, testada em 3 idiomas, com renderizador pronto e slot na tela | **ligar** |
| `generate_insights` | completa, mas **superada** por outro caminho já ligado | **remover** |

---

## 1. `core/map_animation.py`

### O que faz

Exportação de artefatos visuais do mapa, em duas famílias:

| função | entrega |
|---|---|
| `timeline_frames` | quadros ano a ano a partir do grafo (cumulativo ou por recorte) |
| `render_frame` | desenha um quadro (rede / overlay / densidade, três temas) |
| `export_gif` | GIF multi-quadro, via PIL — sem `imageio`, sem `ffmpeg` |
| `export_png_sequence` | sequência de PNGs numerados |
| `export_mp4` / `ffmpeg_available` | MP4 via `ffmpeg`, degradando com elegância quando ausente |
| `render_poster` / `squarified_treemap` / `poster_area_report` | pôster neoplasticista: treemap com área proporcional ao peso do cluster |

### Estado: completa

- **22 testes** em `tests/test_map_animation.py` (385 linhas), mais uso em
  `tests/test_map_regression_e2e.py`.
- `frames_share_positions` é invariante do desenho: os quadros nunca movem os nós.
- `poster_area_report` mediu **erro de área 0,0000% e cobertura 100%**
  (`docs/RELATORIO-MAPAS.md`).
- `export_mp4` devolve `(False, motivo)` sem `ffmpeg`, em vez de levantar.

**Um defeito real existia e foi corrigido antes desta decisão:** os 30+ testes passavam
`first_year` na mão, e nenhum builder escrevia esse atributo — a animação estreava cada termo
no seu ano *médio*. Corrigido na Auditoria 1 Fase 1 (`64d6685`). **Sem essa correção, ligar o
módulo teria exposto o defeito ao usuário.**

### O que se perde ao remover

A **exportação**. A linha do tempo interativa existe no `map.js` e continuaria funcionando —
o que sumiria é levar o resultado para fora do app: GIF para apresentação, PNG para artigo,
pôster para impressão. Para um aplicativo cujo produto final é figura publicável, é perda
direta.

### Esforço para ligar

**Baixo.** O grafo (`self._graph`), as posições (`self._positions`) e o dataframe
(`self._dataframe`) já estão no app; os rótulos e cores de cluster também. Falta um botão, um
diálogo de arquivo e um worker — o mesmo desenho dos exports que já existem.

### → Decisão: **ligar**

---

## 2. `generate_seminal_insights`

### O que faz

Identifica autores e obras seminais a partir das referências mais citadas do corpus e produz
um relatório em Markdown estruturado por autor.

### Estado: completa, e **a interface já a promete**

Este é o caso mais claro dos três. Já existem, prontos:

- a **aba** (`seminal_tab`) e o **destino** (`self._seminal_box`, `main.py:1752`);
- o **renderizador** `_show_seminal_insights` (`main.py:4492`), **com marcação de IA** — feita
  na Fase 2 do trabalho de IA justamente para não ser esquecida no dia em que fosse ligada;
- os **testes de idioma** nos três catálogos (`tests/test_analises_i18n.py`);
- o **teste de marcação** (`tests/test_ai_marking.py`).

E o texto que o usuário lê hoje naquela aba é:

> *"A análise de autores e obras seminais aparecerá aqui após gerar o mapa."*

**O aplicativo promete a análise e nunca a entrega.** Falta exclusivamente o fio entre o
cliente e o renderizador: reunir as referências mais citadas, chamar a função, entregar o
texto ao `_show_seminal_insights`.

### O que se perde ao remover

A promessa teria de ser removida junto — e sobraria uma aba com um botão de baixar PDFs e
nenhuma análise. Remover é mais trabalho visível do que ligar.

### → Decisão: **ligar**

---

## 3. `generate_insights`

### O que faz

Análise do corpus a partir de estatísticas gerais, top-20 palavras-chave, relatório de
clusters e distribuição por ano, produzindo três seções (frentes emergentes, lacunas,
recomendações).

### Estado: completa, mas **superada**

Existe um caminho **já ligado** que faz o mesmo trabalho: `_trigger_corpus_ai_insights`
(`main.py:4286`), disparado pelo botão *"Análise IA do Corpus"* (`main.py:5978`). Ele monta o
próprio contexto e usa `chat_history_stream` — ou seja, **responde em streaming**, enquanto
`generate_insights` devolve o texto de uma vez.

As duas fazem "analise este corpus". A diferença é que uma está ligada, é mais nova, e
entrega melhor experiência.

### O que se perde ao remover

Nada de funcionalidade. Perde-se um segundo caminho para o mesmo resultado — que é o problema,
não o valor. Manter duas rotas de análise de corpus, uma delas morta, é exatamente a pergunta
que um revisor faria.

### Ressalva honesta

`generate_insights` recebe `cluster_report` e `year_distribution` estruturados, enquanto
`_trigger_corpus_ai_insights` monta o contexto a partir do dataframe. Não são idênticas em
entrada. Mas nenhuma tela produz aquela entrada estruturada hoje, e construí-la seria escrever
funcionalidade nova sob o pretexto de preservar código morto.

### → Decisão: **remover**, e registrar como trabalho futuro no roadmap: *"análise de corpus
com relatório de clusters e distribuição temporal estruturados, se houver demanda por saída
não-streaming"*.

---

## Como as decisões foram verificadas

O item 7 do prompt pede testes no **caminho real do aplicativo**, não na função isolada — e a
razão está nesta mesma base: existiam trinta testes de animação passando `first_year` por um
caminho que o app nunca tomava, e por isso a suíte inteira ficava verde sobre um defeito
visível.

Os testes escritos para esta etapa, portanto:

- disparam o **método do botão**, não a função do cliente;
- afirmam que o resultado chega ao **widget de destino**, não que a função devolveu algo;
- verificam a **marcação de IA** no texto entregue, porque é ela que o usuário vê;
- exercitam **sem chave de IA**, que é o estado do usuário novo.
