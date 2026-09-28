# Prompt para agente de código — saneamento do menu de geração de mapas (Blicsa)

> Cole o bloco inteiro abaixo no Claude Code (ou Antigravity), com o repositório
> `PyBibliomics` aberto na raiz. O prompt é autocontido.

---

Você vai sanear o menu de geração de mapas do Blicsa (PyBibliomics). O diagnóstico
já foi feito e as decisões de correção já estão tomadas — está tudo abaixo. **Não
me faça perguntas durante a tarefa.** Onde houver ambiguidade, escolha a opção que
respeita as regras do projeto listadas na seção "Invariantes" e registre a escolha
no relatório final.

Trabalhe com autonomia total: leia o código, corrija, escreva os testes, rode a
suíte, gere as provas visuais e só então me responda.

## Contexto mínimo

- Tela afetada: aba de visualização, construída em `main.py::_build_tab_viz`
  (a partir da linha ~2000) e `main.py::_build_config_widgets`.
- Fluxo afetado: `_run_mapping` → `_mapping_worker` → `_publish_sigma_map` →
  `assets/map.js`.
- As linhas citadas são do commit `dcb8a82`. **Confirme cada alvo por `grep`
  antes de editar**, nunca confie no número da linha.

## Invariantes do projeto (não negociáveis)

1. **Prova visual obrigatória.** Trabalho visual falha em silêncio. Toda mudança
   que toca tela ou mapa precisa de PNG renderizado de verdade em
   `docs/evidence/`, conferido contra o critério do item. Auto-relato de "está
   pronto" não conta.
2. **Sem regressões.** A suíte existente continua verde. Lógica nova ganha teste
   pytest.
3. **Design system neoplasticista.** Raio de canto zero em tudo, zero sombras,
   zero gradientes. Paleta em `ui/styles.py` — não invente cor.
4. **i18n.** Toda string visível ao usuário passa por `t()`, com chave nos três
   catálogos (`pt_BR`, `en`, `fr`). O teste de paridade de catálogo quebra o CI se
   faltar chave.
5. **Sigma é a saída principal** do mapa. Plotly e matplotlib não voltam a
   disputar esse papel.
6. **Local-first.** Nada de backend, conta ou nuvem.

## Entregável de teste

Crie `tests/test_menu_mapas.py`. Cada item abaixo tem um nome de teste indicado —
use exatamente esse nome, porque meu critério de aceitação é rodar a suíte e ver
esses nomes passando. O `conftest.py` já esconde janelas Tk durante os testes
(fixture `janelas_fora_da_frente`), então instanciar o app no teste é permitido e
já é feito em `tests/test_layout_blink.py` e `tests/test_navegacao_abas.py` — siga
o padrão de lá.

---

# Bloco A — erros que chegam ao usuário

## A1. Gerar o segundo mapa mostra o primeiro

**Defeito.** `main.py:4661` abre
`http://127.0.0.1:{porta}/assets/map_template.html` sem parâmetro de revisão. O
navegador apenas foca a aba já aberta, sem recarregar: o usuário vê o mapa
anterior e conclui que os parâmetros não surtiram efeito.

**Decisão.** `_recluster_only` (`main.py:4336`) já resolveu isso com
`?revision={int(time.time() * 1000)}`. Extraia um helper único —
`_url_do_mapa(self) -> str` — que monta a URL com a revisão, e use-o nos **dois**
chamadores. Nada de duplicar a f-string.

**Teste.** `test_gerar_mapa_duas_vezes_usa_urls_diferentes` — monkeypatche
`webbrowser.open`, rode o worker duas vezes sobre o mesmo corpus e afirme que as
duas URLs capturadas diferem e que ambas casam com `?revision=\d+`.

## A2. Duplo clique dispara duas gerações

**Defeito.** `_run_mapping` (`main.py:4461`) não tem guarda de reentrância, e o
botão "Gerar Mapa" não é guardado em atributo nenhum (`self._btn(...)` na linha
~2037 descarta o retorno), então nem dá para desabilitá-lo. Dois cliques = duas
threads calculando ForceAtlas2 e escrevendo no mesmo `graph.json`; as estatísticas
exibidas podem vir de outra corrida.

**Decisão.** Duas camadas:
- Guarde o botão em `self._btn_gerar_mapa` e desabilite-o na entrada de
  `_run_mapping`, reabilitando em `_set_idle` via `self.after(0, ...)` —
  inclusive no caminho de erro e no de rede vazia.
- Guarda de reentrância independente da UI: `self._mapeamento_em_curso` (bool),
  checada no topo de `_run_mapping`, liberada no `finally` de `_mapping_worker`.
  A guarda é o que protege; o botão desabilitado é só o sinal visível.

**Teste.** `test_segundo_clique_nao_inicia_segunda_thread` — monkeypatche
`threading.Thread` para contar instanciações, chame `_run_mapping` duas vezes sem
deixar a primeira terminar, afirme uma única thread de mapeamento.

## A3. Chamada Tk fora da main thread

**Defeito.** `main.py:4667`, dentro de `_mapping_worker`:

```python
if getattr(self, '_tv_analises', None):
    self._tv_analises.set("Mapa")
```

Todas as linhas vizinhas usam `self.after(0, ...)`; essa não. Tkinter não é
thread-safe — é fonte de travamento intermitente, especialmente no macOS.

**Decisão.** Envolver em `self.after(0, ...)`. Depois, **varra o corpo inteiro de
`_mapping_worker` e de `_map_animation_worker`** procurando outras chamadas
diretas a widget ou a variável Tk fora de `after`; corrija todas as que achar e
liste-as no relatório.

**Teste.** `test_worker_nao_toca_tk_fora_da_main_thread` — instrumente o app com
um duplo que registre a thread de cada chamada a `_tv_analises.set`,
`_set_idle`, `_set_busy` e `_update_stats`; rode `_mapping_worker` numa thread
secundária e afirme que toda chamada chegou pela main thread.

## A4. Exceção crua virando caixa de diálogo

**Defeito.** `main.py:4679`: `messagebox.showerror("Erro", str(exc))`. O usuário lê
`invalid literal for int() with base 10: 'abc'` quando digita texto em "Máx. nós"
(`main.py:4553`, `int(self._max_nodes_var.get() or 0)` sem tratamento). E escolher
Cocitação num corpus OpenAlex sem coluna de referências só falha **depois** do
clique e da espera, lá em `_find_ref_col` (`core/matrix_builders.py:555`).

**Decisão.** Três correções, nesta ordem:

1. **Validação de entrada antes de começar.** "Máx. nós" e "Top %" validados no
   início de `_run_mapping`; entrada inválida vira aviso com `t()` que nomeia o
   campo e o valor aceito, e **não** inicia thread nenhuma.
2. **Preflight do tipo de mapa.** Crie `core/map_controls.py::tipos_suportados(df)
   -> dict[str, str | None]`, que devolve, para cada entrada de `MAP_TYPES`, `None`
   se o corpus suporta ou a chave i18n do motivo se não suporta (coluna de
   referências ausente, coluna de autores ausente, etc. — reaproveite a lógica de
   `_find_ref_col`, não a duplique). Quando o corpus é carregado ou trocado, o
   combo "Tipo de Mapa" passa a listar só os suportados, e um rótulo abaixo dele
   diz, com `t()`, quais ficaram de fora e por quê. O usuário nunca mais escolhe
   um tipo que o corpus não aguenta.
3. **Mensagem de erro honesta no `except`.** Mantenha o `str(exc)` no log
   (`log.exception`, para o traceback ir ao terminal), mas o diálogo passa a
   mostrar um texto com `t()` que diz o que falhou e o que fazer. A exceção crua
   fica no log, não na cara do pesquisador.

**Testes.** `test_max_nos_invalido_nao_inicia_thread`,
`test_tipos_suportados_exclui_cocitacao_sem_referencias`,
`test_erro_no_worker_nao_mostra_excecao_crua` (afirme que o texto passado ao
`showerror` não contém `Traceback` nem `invalid literal`).

---

# Bloco B — falhas silenciosas

## B1. `_candidate_worker` engole todas as exceções

**Defeito.** `main.py:4300`: `except Exception: pass`. Quando falha,
`self._candidate_counts` fica vazio; aí `_run_mapping:4465` pula silenciosamente o
diálogo de verificação de termos e o rótulo "→ N de M termos passam" nunca
preenche. Há ainda corrida: clicar em "Gerar Mapa" antes do worker terminar
também pula o diálogo. O passo aparece e some sem motivo visível.

**Decisão.**
- Troque o `pass` por `log.exception(...)` mais um estado visível: o rótulo
  `self._thresh_lbl` passa a dizer, com `t()`, que a contagem de candidatos
  falhou. Silêncio não é opção.
- Elimine a corrida: guarde o `threading.Event` do worker de candidatos e, em
  `_run_mapping`, espere por ele com timeout curto (2 s) antes de decidir sobre o
  diálogo. Se estourar o timeout, siga sem o diálogo **e diga isso no log**.

**Teste.** `test_falha_em_candidatos_aparece_no_rotulo`.

## B2. "Salvar na Galeria" monta o HTML por regex, sem rede de proteção

**Defeito.** `save_plot` (`main.py:2045-2101`) não tem `try/except` nenhum e monta
o HTML autocontido substituindo, por regex (`main.py:2079`), o bloco de `fetch` do
`map.js`. Hoje casa com `assets/map.js:522-524`. Qualquer renomeação de variável
naquele trecho faz a substituição falhar **em silêncio**: o HTML sai com um
`fetch("graph.json")` que morre no `file://`, o `map.js` cai no `showEmpty()`
(linha 94) e o usuário abre um mapa branco sem explicação. Além disso o tempfile
vaza se o export falhar, e `reports/` (`main.py:2096`) é relativo ao CWD — no app
instalado vai parar em lugar imprevisível.

**Decisão.**
- **Pare de usar regex.** O `map.js` já tem o caminho limpo:
  `assets/map.js:519` testa `window.BLICSA_GRAPH` antes de tentar o `fetch`.
  Injete `window.BLICSA_GRAPH = {...};` junto do `window.BLICSA_I18N` que você já
  injeta, e remova a substituição por regex por completo.
- Envolva `save_plot` em `try/except`, com `finally` removendo o tempfile.
  Falha vira diálogo com `t()` e `log.exception`.
- O destino passa a ser um diretório estável do usuário (o mesmo lugar onde a
  galeria já procura os mapas), nunca `reports/` relativo ao CWD. Resolva pelo
  caminho que `_refresh_gallery` já usa e reaproveite-o.

**Testes.** `test_html_da_galeria_embute_o_grafo` (gere o HTML num `tmp_path` e
afirme que contém `window.BLICSA_GRAPH` e **não** contém `fetch("graph.json")`),
`test_falha_ao_salvar_galeria_nao_vaza_tempfile`.

## B3. `_populate_cluster_filter` nunca é chamado

**Defeito.** Definido em `main.py:4761`, sem um único chamador — a faixa de
checkboxes de cluster jamais é reconstruída depois de gerar um mapa.

**Decisão.** Decida entre as duas, registre a escolha no relatório e execute:
- **(a)** ligar: chamar via `self.after(0, self._populate_cluster_filter)` logo
  após `_update_stats` em `_mapping_worker`, e conferir que
  `_apply_cluster_filter` realmente filtra o mapa Sigma publicado; ou
- **(b)** remover: se o filtro de clusters do `map.js` (`buildClustersUi`, linha
  ~581) já cobre a mesma necessidade dentro do mapa, apague `_populate_cluster_filter`,
  `_apply_cluster_filter`, `_cluster_filter_frame` e `_cluster_filter_vars`, e
  registre a remoção em `docs/CODIGO-SEM-CHAMADOR.md`, que já existe para isso.

Prefira **(b)** se a paridade de função se confirmar — código morto que parece
vivo é pior que ausência de recurso.

**Teste.** Conforme a escolha: `test_filtro_de_clusters_preenche_apos_gerar` ou
`test_filtro_de_clusters_foi_removido_por_inteiro`.

## B4. `_build_node_info` sem `try/except`

**Defeito.** `main.py:4695`. `df[col]` com coluna ausente levanta `KeyError` dentro
da thread; o painel fica com o texto anterior e o usuário conclui que o clique não
funcionou. Mesmo risco em `sort_values("citations")`.

**Decisão.** `try/except` no corpo inteiro, com `log.exception` e um texto de
fallback com `t()` no painel dizendo que os detalhes daquele nó não puderam ser
montados. Use `.get`/checagem de coluna em vez de indexação direta.

**Teste.** `test_clique_em_no_com_coluna_ausente_mostra_fallback`.

---

# Bloco C — desempenho

## C1. Centralidades recalculadas a cada clique

**Defeito.** `main.py:4709` e `4711` chamam `nx.betweenness_centrality(G, weight=...)`
e `nx.pagerank(G, weight=...)` sobre o grafo **inteiro**, a **cada** clique de nó.
Betweenness é O(nm): com 500 nós são segundos de congelamento por clique.

**Decisão.** Calcule as duas uma única vez, no `_mapping_worker`, logo após o
layout, e guarde em `self._centralidades = {"betweenness": {...}, "pagerank": {...}}`.
`_build_node_info` passa a só consultar o dicionário. Invalide (`= None`) em
`_recluster_only` **apenas se** a reclusterização alterar arestas — como ela não
altera (só cores e grupos), documente isso num comentário em vez de recalcular.

**Teste.** `test_centralidade_calculada_uma_vez_por_mapa` — conte chamadas a
`nx.betweenness_centrality` via monkeypatch durante geração + três cliques de nó;
afirme exatamente 1.

## C2. Teto de arestas implementado e nunca usado

**Defeito.** `_publish_sigma_map` (`main.py:4345`) chama `export_sigma_json` sem
`max_edges`, então o default `0` (sem teto) vale sempre. O `core/sigma_exporter.py`
tem o corte implementado e testado, e o `assets/map.js:573` tem UI pronta para
avisar via `meta.edges_capped` — nada disso chega a disparar. Uma rede de
coocorrência densa exporta todas as arestas e afoga o WebGL, contra a meta de 500
nós a 60 fps.

**Decisão.** Passe um teto padrão em `_publish_sigma_map` e exponha-o como
controle no painel de parâmetros (campo numérico, com `t()` e `HoverTooltip`,
`corner_radius=0`). Escolha o padrão medindo: gere o mapa do corpus de exemplo
(`docs/sample_dataset.csv`) com tetos de 5.000 / 10.000 / 20.000, meça o fps e
fixe o maior teto que sustenta 60 fps com 500 nós. **Relate os números medidos**,
não estime.

**Teste.** `test_publicacao_aplica_teto_de_arestas` — afirme que o payload
publicado traz `meta.edges_capped is True` e `len(edges) == teto` num grafo
sintético acima do teto.

## C3. Dois congelamentos da main thread

**Defeito.** `_open_term_review` (`main.py:4372`) roda `extract_terms`
sincronamente no callback do botão, e o cálculo de `doc_freq` antes do diálogo de
verificação roda `_extract_term_lists` também na main thread (`main.py:4477`). O
`_set_busy` nem chega a repintar, porque o mainloop está bloqueado.

**Decisão.** Ambos vão para thread, com `_set_busy` antes e o diálogo aberto por
`self.after(0, ...)` quando o resultado chega. Aproveite e some o que falta abaixo
(C4) na mesma passagem, porque é a mesma tela.

**Teste.** `test_revisar_termos_nao_bloqueia_main_thread`.

## C4. Falta a trilha de contagem

**Defeito.** Quando a rede sai vazia, o aviso
(`map.warn_empty_network`/`map.warn_empty_coauth`) informa só o limiar. O usuário
não sabe se o problema foi o limiar, a poda ou o corpus. É a mesma regra da
trilha de contagem que o pipeline de busca já cumpre, e que aqui não existe.

**Decisão.** Uma linha única, logada **e** exibida (no rótulo de estatísticas e no
aviso de rede vazia), com `t()` e placeholders nomeados:

> `N candidatos · M passaram o limiar ≥k · K nós após poda · E arestas (R renderizadas)`

Os números já existem todos no `_mapping_worker` e no `meta` do payload Sigma —
é agregação, não cálculo novo.

**Teste.** `test_trilha_de_contagem_aparece_em_rede_vazia`.

---

# Bloco D — consistência com as regras do projeto

Um commit separado, sem mudança de comportamento.

## D1. Emojis residuais

`main.py:2126` e `main.py:2137` ainda trazem `⏳` nos botões "Linha do Tempo" e
"Historiografia de Citações". O commit `dcb8a82` removeu emojis do resto da
interface. Remova esses dois e rode `grep -rn "⏳" main.py ui/` para garantir que
não sobrou nenhum.

## D2. Resíduo de Plotly/matplotlib no painel principal

"Abrir Plotly Interativo" está na segunda posição da primeira fileira de botões
(`main.py:2040`), imediatamente ao lado de "Gerar Mapa", e o layout ainda carrega
`# matplotlib canvas gets all vertical height` (`main.py:2031`). Sigma é a saída
principal.

**Decisão.** Mova o botão de Plotly para a fileira das análises auxiliares
(junto de Sankey, Bursts, Mapa Temático), corrija o comentário mentiroso do
layout, e confira se `viz_panel.grid_rowconfigure(3, weight=1)` ainda faz sentido
sem canvas matplotlib — se não fizer, ajuste o peso para a linha certa. **Isto
muda a tela: exige prova visual.**

## D3. Strings fora do `t()`

O painel está quase todo em português cravado no código: `"Gerar Mapa"`,
`"Parâmetros do Mapa"`, `"Sem mapa"`, `"Gere o mapa primeiro"`, `"Tipo de Mapa:"`,
`"Campo:"`, `"Contagem:"`, `"IA & Análise"`, `"Nós"`, `"Arestas"`, `"Clusters"`, e
todos os textos de `HoverTooltip`.

**Decisão.** Inventarie todas as strings visíveis de `_build_tab_viz` e
`_build_config_widgets`, mova para os três catálogos sob o prefixo `map.`, e
troque por `t()`. Siga o padrão de `docs/i18n-tela2-inventario.md` e grave o
inventário desta tela em `docs/i18n-menu-mapas-inventario.md`.

## D4. Raio de canto

Os widgets do painel — `CTkComboBox`, `CTkSlider`, `CTkEntry`, `CTkCheckBox` e os
`CTkFrame` de `viz_panel`, `br`, `ctrl` e `sc` — são criados sem `corner_radius=0`.
A regra é raio zero em tudo.

**Decisão.** Acrescente `corner_radius=0` a todos. Se o tema
`assets/theme/blicsa.json` puder impor isso globalmente, prefira o tema e diga no
relatório por que a alteração local ficou ou não ficou necessária. **Isto muda a
tela: exige prova visual.**

---

# Prova visual (obrigatória)

Para os itens que tocam a tela (A4 item 2, C2, C4, D1, D2, D4), gere PNGs reais e
salve em `docs/evidence/menu-mapas/`:

1. `01-painel-antes.png` e `02-painel-depois.png` — o painel de parâmetros
   inteiro, antes e depois. Confira lado a lado: nenhum canto arredondado, nenhuma
   sombra, nenhum emoji.
2. `03-tipos-nao-suportados.png` — corpus sem coluna de referências, mostrando o
   combo sem Cocitação e o rótulo explicando a ausência.
3. `04-trilha-de-contagem.png` — o aviso de rede vazia com os quatro números.
4. `05-mapa-com-teto.png` — mapa do corpus de exemplo com o teto de arestas ativo
   e o aviso `edges_capped` visível no mapa.

Abra cada PNG e confira contra o critério antes de declarar o item pronto. Um
item sem PNG conferido não está pronto.

---

# Critérios de aceitação (verificáveis no terminal)

```bash
# 1. Suíte inteira verde, sem regressão
pytest -q

# 2. Todos os testes novos existem e passam
pytest tests/test_menu_mapas.py -v

# 3. Nenhum emoji na interface
grep -rn "⏳" main.py ui/ ; test $? -eq 1

# 4. A regex frágil de montagem do HTML da galeria não existe mais
grep -n 'await fetch\\\\("graph' main.py ; test $? -eq 1

# 5. A URL do mapa sempre carrega revisão — um helper, dois chamadores
grep -c "_url_do_mapa" main.py   # deve ser >= 3

# 6. Paridade dos catálogos i18n continua garantida
pytest tests/test_i18n.py -q

# 7. As provas visuais existem
ls docs/evidence/menu-mapas/*.png | wc -l   # deve ser >= 5
```

# Relatório final

Ao terminar, responda com:

1. **Uma linha por item** (A1…D4): corrigido, removido ou não aplicável — e, se
   não aplicável, por quê.
2. **Decisões que você tomou** onde o prompt deixou escolha: B3 (ligar ou
   remover), C2 (o teto escolhido, com os fps medidos nos três cenários), D4
   (tema global ou `corner_radius` local).
3. **Arquivos tocados**, com o que mudou em cada um.
4. **Chamadas Tk fora da main thread** que você encontrou além da de A3.
5. **Saída literal** dos sete comandos de aceitação.
6. **O que você não corrigiu** e por quê — inclusive o que descobriu de quebrado
   fora do escopo deste prompt.

Não abra pull request e não faça push. Deixe os commits locais, um por bloco
(A, B, C, D), com mensagens no padrão do repositório (`fix(mapa): ...`,
`perf(mapa): ...`, `refactor(mapa): ...`).
