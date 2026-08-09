# Auditoria 1 · Fase 3 — arquitetura

**Data:** 2026-08-09 · **Escopo:** itens 15 a 22 de `audit-1-funcional-e-arquitetura.md`

> **Veredito:** a arquitetura está **saudável nas fronteiras e concentrada no meio**. Não há
> ciclo de importação, `core/` não importa de `ui/`, e o transporte HTTP é um só. O problema é
> um: `main.py` tem **6.256 linhas** e uma classe com **173 métodos**, e é onde vivem as duas
> funções mais complexas do projeto (CC 68 e 63).
>
> Esta fase é **diagnóstico**. O plano de decomposição da §3 está escrito para ser executado
> **depois** da publicação — refatoração grande antes do registro de software é risco sem
> contrapartida. O que foi executado agora está na §7, e é só o que não muda comportamento.

Medições: `scripts/audit_arquitetura.py` (AST puro, sem dependência nova — o Python do sistema
é gerenciado externamente, e instalar `radon` para uma auditoria seria trocar um número por uma
alteração no ambiente do usuário).

---

## 1. Métricas objetivas (item 15)

### Linhas por arquivo

| arquivo | linhas | |
|---|---:|---|
| `main.py` | **6.256** | 21% de todo o Python rastreado |
| `core/matrix_builders.py` | 1.254 | |
| `ui/components.py` | 1.028 | |
| `ui/search_feed.py` | 875 | |
| `core/visualizer.py` | 788 | |
| `core/term_extraction.py` | 671 | |
| `core/map_animation.py` | 543 | sem chamador (Fase 1, §2.6) |
| `core/parsers.py` | 514 | |

### Complexidade ciclomática

| função | arquivo:linha | CC | linhas | aninhamento |
|---|---|---:|---:|---:|
| `_search_worker` | `main.py:3099` | **68** | 304 | 6 |
| `_update_stats_tab` | `main.py:5462` | **63** | 220 | 5 |
| `export_svg` | `core/map_controls.py:173` | 51 | 123 | 3 |
| `search` | `core/sources/crossref.py:137` | 45 | 170 | 4 |
| `search` | `core/sources/pubmed.py:181` | 43 | 198 | 4 |
| `_mapping_worker` | `main.py:3625` | 40 | 165 | 6 |
| `extract_terms` | `core/term_extraction.py:483` | 39 | 135 | 3 |
| `timeline_frames` | `core/map_animation.py:77` | 36 | 97 | 4 |
| `build_historiograph` | `core/visualizer.py:629` | 35 | 160 | 4 |
| `build_keyword_cooccurrence` | `core/matrix_builders.py:256` | 34 | 118 | 3 |

`_search_worker` com **CC 68** significa, na prática, 68 caminhos independentes num método de
304 linhas — e é o método que atende ao botão mais usado do app. Foi também onde as duas
sondas da Fase 2 (rede caída, busca vazia) travaram sem que a causa fosse isolada. As duas
coisas são o mesmo fato visto de dois lados.

### Funções longas e aninhamento

- **91 funções com mais de 50 linhas** (79 fora de testes e scripts).
- **Aninhamento ≥ 5** em 10 funções de produção. As piores:

| função | arquivo:linha | aninhamento |
|---|---|---:|
| `load_ris` | `core/parsers.py:442` | **9** |
| `_create_seminal_library_worker` | `main.py:4564` | 8 |
| `chat_history_stream` | `ai/client.py:212` | 7 |
| `_trigger_map_ai_insights` | `main.py:4162` | 7 |
| `_trigger_corpus_ai_insights` | `main.py:4286` | 7 |
| `_trigger_import_ai_assistant` | `main.py:4398` | 7 |

Os três `_trigger_*` com aninhamento 7 e 326 linhas somadas são o mesmo desenho repetido três
vezes — candidato natural a extração (§3, passo 4).

---

## 2. Acoplamento e dependências (item 17)

| verificação | resultado |
|---|---|
| `core/` importando de `ui/` | **nenhuma** |
| `ai/` importando de `ui/` ou `main` | **nenhuma** |
| ciclos entre pacotes internos | **nenhum** |
| transporte HTTP | `urllib.request` em 14 pontos; **zero** `requests`, zero `http.client` |

As fronteiras estão certas. `core/` é importável sem Tk — foi decisão explícita da fase do
contexto de pesquisa (`core/research_context.py` diz isso no cabeçalho) e a auditoria confirma
que a regra se manteve em todo o pacote.

A dependência que existe é a inversa e é a esperada: `main.py` importa de `core/`, `ui/` e
`ai/`. O problema não é a direção — é o volume concentrado num arquivo só.

---

## 3. Plano de decomposição do `main.py` (item 16) — **não executado**

`BlicsaApp`: **173 métodos, 5.757 linhas** numa classe.

| grupo | métodos | linhas |
|---|---:|---:|
| outros (estado, callbacks, utilidades) | 108 | 2.162 |
| `_build_tab_*` (telas) | 12 | 932 |
| `*_worker` (threads) | 10 | 799 |
| `_refresh_*` / `_update_*` | 11 | 548 |
| `_build_*` (widgets) | 5 | 482 |
| `_show_*` (diálogos) | 8 | 364 |
| `export*` | 16 | 144 |
| `_trigger_*` (IA) | 3 | 326 |

### Ordem segura de extração

A ordem não é por tamanho: é por **quanto estado compartilhado cada peça arrasta**. Extrair
uma tela que lê seis atributos de `self` não reduz acoplamento — só o move de arquivo.

| # | o que sai | para onde | risco | por quê nesta posição |
|---|---|---|---|---|
| 1 | `_trigger_map_ai_insights`, `_trigger_corpus_ai_insights`, `_trigger_import_ai_assistant` | `ui/ai_triggers.py` | **baixo** | mesmo desenho três vezes; dependem só do analista e de um alvo de render, ambos já parametrizados desde a Fase 3 da IA |
| 2 | `export_*` (16 métodos, 144 linhas) | `core/exporters.py` | **baixo** | quase todos delegam a `NetworkGenerator`; são casca fina |
| 3 | `_show_*` (8 diálogos) | `ui/dialogs.py` | **baixo** | `Toplevel` autocontido; a única amarra é `self` como pai |
| 4 | `_build_tab_stats` + `_update_stats_tab` | `ui/views/stats.py` | **médio** | 220 linhas com CC 63; extrair **junto** com o `_update`, senão o par se separa e piora |
| 5 | `_build_tab_import` + `_auto_detect_format` | `ui/views/import.py` | **médio** | detecção de formato é lógica pura e deveria estar em `core/parsers.py`, não na tela |
| 6 | `_search_worker` | `core/search_flow.py` | **alto** | CC 68, 304 linhas, seis níveis de aninhamento, mexe em contagem, facetas, dedup, trilha e UI. **Precisa de teste de caracterização antes de encostar** |
| 7 | `_mapping_worker` | `core/map_flow.py` | **alto** | CC 40; mesma razão |

**Passos 1 a 3 são seguros hoje** e reduziriam ~800 linhas do `main.py` sem tocar em lógica.
**Passos 6 e 7 não devem ser feitos sem caracterização primeiro** — são os dois métodos que
sustentam os dois fluxos principais do app, e a suíte atual não cobre seus caminhos de erro
(Fase 2, §5).

### O que **não** fazer

- Não mover `main.py` inteiro de uma vez. As telas compartilham estado via `self._dataframe`,
  `self._graph`, `self._positions` — extrair sem resolver isso cria seis módulos que importam
  uns aos outros.
- Não introduzir camada de "controller" nesta rodada. O ganho é teórico e o risco, imediato.

---

## 4. Padrões inconsistentes (item 18)

| padrão | ocorrências | avaliação |
|---|---:|---|
| `urllib.request` | 14 | **consistente** — nenhum `requests` misturado |
| `except Exception` | 122 | genérico demais, mas deliberado em UI (evitar derrubar a janela) |
| **`except:` sem tipo** | **10** (todas em `main.py`) | **inconsistente e arriscado** |
| `messagebox.showerror` | 27 | consistente como canal; o conteúdo é que varia (Fase 2, §5) |
| exceções próprias do projeto | 5 (`AIClientError`) | só a camada de IA tem erro tipado |

**`except:` sem tipo captura `KeyboardInterrupt` e `SystemExit`.** Em `main.py:480`, `581`,
`765`, `914`, `1100`, `1153` e mais quatro. O sintoma é o app ignorar Ctrl-C e demorar a
fechar. São todos blocos de carregamento de ícone/imagem, onde a intenção era `except
Exception` — a correção é trocar a palavra, mas são dez pontos e nenhum tem teste, então fica
recomendado e não executado (§7).

**Acesso a coluna de dataframe** tem três dialetos convivendo: `df[col]` (87), `row.get(col)`
(47) e `if col in df.columns` (23). O terceiro é o correto para corpus heterogêneo — os dois
primeiros já produziram `KeyError` em projeto antigo (`e2c72ba`). Não há um ponto único de
acesso; `core/project.py::normalize_dataframe` existe e resolve na carga, mas nada impede um
código novo de ler direto.

---

## 5. Dívida catalogada (item 19)

| categoria | quantidade | observação |
|---|---:|---|
| `TODO` / `FIXME` / `HACK` / `XXX` | **0** | nenhum marcador no repositório |
| imports não usados | 20 → **4** | 16 removidos nesta fase (§7) |
| funções públicas sem nenhuma referência | 16 | lista abaixo |
| módulos sem chamador | 1 | `core/map_animation.py` (Fase 1, §2.6) |
| `except:` sem tipo | 10 | §4 |

### Funções sem referência

`clear_all_facets`, `count_passing_threshold`, `export_plotly_html`, `fraction`,
`highlight_node`, `invalidate_cache`, `reached_limit`, `refresh_style`, `reset_view`,
`schedule`, `set_cluster_labels`, `set_hidden_clusters`, `stagger_items`, `submit`,
`term_names`, `visible`.

**Não removidas.** A maioria é API de componente de UI (`ui/components.py`) escrita para ser
chamada de fora — remover exigiria confirmar que nenhuma tela futura a usa, o que é decisão de
produto, não limpeza. Ficam catalogadas.

> **Sobre esta lista específica.** A primeira versão do analisador apontou **33** funções
> mortas, entre elas `load_bibtex`, `load_ris`, `load_pubmed_medline` e `load_pdf` — que são
> chamadas por `getattr(parser, loaders_map[fmt])()` no `main.py`. Reportar aquilo teria
> mandado apagar o import de BibTeX e RIS do Blicsa. O analisador passou a contar **literal de
> string como referência**, e a lista caiu para 16. Uma auditoria que não audita a si mesma
> produz o defeito que veio procurar.

---

## 6. Cobertura por módulo (item 20)

`pytest-cov` não está disponível e instalá-lo alteraria o ambiente do usuário. O que segue é
uma **proxy declarada**: quantos arquivos de teste mencionam cada módulo de produção. Não é
cobertura de linha e não substitui uma.

**Módulos de produção com zero menções em teste:**

| módulo | linhas | está no caminho do usuário? |
|---|---:|---|
| `core/markdown_parser.py` | 130 | **sim** — renderiza a resposta do Blink no chat (`main.py:1090`, `1288`) |
| `core/sources/zotero.py` | — | sim — provedor registrado em `core/sources/__init__.py` |
| `core/webview_viewer.py` | 15 | sim — abre a janela do mapa |

`core/markdown_parser.py` é o mais sério dos três: é ele que transforma o Markdown do modelo
em tags do `CTkTextbox`, e um erro ali aparece como resposta de IA malformada na tela — a
mesma superfície que a Fase 3 da IA passou três commits protegendo.

---

## 7. Refatorações executadas (item 21)

Só o que **não muda comportamento**. Nada de arquitetura, nada de mover arquivo, nada de
renomear API pública.

**16 imports não usados removidos**, cada um confirmado com busca no repositório inteiro antes
de sair (o nome existe e é usado — em outro arquivo; a linha removida é que não o usava):

`core/browse.py` (`Any`, `Callable`, `Iterable`) · `core/harmonization.py` (`defaultdict`) ·
`core/i18n.py` (`Any`) · `core/import_job.py` (`math`, `field`) ·
`core/map_animation.py` (`Iterable`, `NO_DATA_COLOR`) · `core/map_controls.py` (`NO_DATA_COLOR`) ·
`core/matrix_builders.py` (`re as _re`) · `core/nlp.py` (`Path`) · `core/sources/base.py` (`json`) ·
`core/term_extraction.py` (`STOP_WORDS_EN`, `STOP_WORDS_PT`) · `core/visualizer.py` (`math`) ·
`main.py` (`build_plotly_density`, `extract_ngrams`) · `ui/animations.py` (`ctk`)

Suíte antes: **789 passed**. Depois: **789 passed**. Zero diferença — que é exatamente o
resultado esperado de uma limpeza que não muda comportamento.

`from __future__ import annotations` foi **excluído** da varredura: é diretiva de compilação,
não tem uso por nome, e removê-la mudaria a semântica das anotações do módulo inteiro. O
analisador o sinalizava até esta rodada.

### O que **não** foi executado, e por quê

| candidato | por que ficou |
|---|---|
| trocar os 10 `except:` por `except Exception:` | dez pontos sem teste; é mudança de comportamento em caso de erro, e o item 21 pede teste antes e depois |
| remover as 16 funções sem referência | maioria é API de componente de UI; remover é decisão de produto |
| extrair constantes mágicas | não foi encontrado caso claro o bastante para caber em "baixo risco, alto retorno" |
| unificar tratamento de erro | é o passo 1 do plano da §3, não uma limpeza |

---

## 8. Aceite

- `python3 -m pytest tests/ -q` → **789 passed, 1 xfailed** (idêntico ao antes da limpeza). ✅
- `python3 scripts/audit_arquitetura.py` → métricas reprodutíveis, sem dependência nova. ✅
- `python3 main.py --smoke-test` → OK. ✅

## 9. Recomendações, por prioridade

| # | o que | quando |
|---|---|---|
| 1 | Testes para `core/markdown_parser.py` — está no caminho da resposta de IA e tem zero | antes da publicação |
| 2 | Teste de caracterização de `_search_worker` (CC 68) antes de qualquer refatoração; é o mesmo método cujas sondas de erro travaram na Fase 2 | antes de tocar nele |
| 3 | `compute_overlay_scores` é O(nós × documentos) e domina o tempo acima de 2.000 nós (Fase 1, §7) | depois da publicação |
| 4 | Passos 1–3 do plano de decomposição (~800 linhas fora do `main.py`, risco baixo) | depois da publicação |
| 5 | Trocar os 10 `except:` por `except Exception:` | depois da publicação |
| 6 | Decidir o destino de `core/map_animation.py` | produto |
