# Relatório — Liga aba Meus Projetos + micro-fixes de layout

**Data:** 2026-07-12 · Commit único: `fix: liga aba Meus Projetos à navegação + ajustes de layout medidos`.
Suíte: **73 passed, 1 xfailed** (o xfail é o OBS-03 do Crossref, fora deste escopo).

## 1. Aba Meus Projetos ligada à navegação

- Registrada em `self._tabs` como `"projects"` logo após `"home"` (`main.py`).
- Botão na sidebar **logo após a Home**, com rótulo `t("projects.title")` (traduz ao vivo).
  Ícone: `icon_name="house"` — par livre (`stack` já é usado por corpus/galeria).
- **Bug crítico corrigido (bloqueava tudo):** `_build_tab_projects` referenciava
  `self._main_content`, atributo **inexistente** (só existe `self._content`, `main.py:169`).
  Registrar a aba dispararia `AttributeError` no startup. Trocado para `self._content`.
- Deslocado o bloco inferior da sidebar +1 row (agora 8 botões de nav ocupam rows 1-8;
  corpus badge 9, spacer 10, settings 11, status 12, progress 13, about 14).

**Validação (headless, app real instanciado):**
- app constrói sem erro; `"projects"` em `_tabs` e `_nav_btns`; rótulo do botão = "Mes projets"/"Meus Projetos" conforme idioma.
- `_switch_tab("projects")` funciona; `ProjectsView` criada; `_refresh_language()` reconstrói a aba.
- **Fluxo 1.4 completo:** projeto `.blicsa` salvo → card aparece na aba (`refresh` lista) →
  clicar "Abrir" dispara `on_open` → `_load_project_file` (dataset/mapa carregam de volta).

## 2. Micro-fixes de layout (medidos com `font.measure`, fonte real SF Display)

### Tabela final — tudo OK, zero ESTOURA

**Botões de ação do card** (largura fixa 60 → **100px**, folga de texto ~88px):

| chave | pt_BR | en | fr |
|---|---|---|---|
| action_open | Abrir 37 ✅ | Open 42 ✅ | Ouvrir 47 ✅ |
| action_rename | Renomear 78 ✅ | Rename 63 ✅ | Renommer 84 ✅ |
| action_duplicate | Duplicar 64 ✅ | Duplicate 73 ✅ | Dupliquer 74 ✅ |
| action_delete | Excluir 51 ✅ | Delete 50 ✅ | Supprimer 80 ✅ |

**Botão Voltar do Blink** (80 → **100px**): pt "⬅ Voltar" 66 ✅ · en "⬅ Back" 58 ✅ · fr "⬅ Retour" 71 ✅.

**Sugestões do Blink** (antes 1 linha ~1114px em fr): agora **grid de 2 colunas** → 3 botões
em **2 linhas**; largura de cada botão = maior texto do idioma + 24px (**sem truncar**):

| idioma | largura botão | 2 colunas | linhas |
|---|---|---|---|
| pt_BR | 313px | 636px | 2 |
| en | 320px | 650px | 2 |
| fr | 419px | 848px | 2 (≤ ~1000px) |

### Slider de anos (ZeroDivisionError com ano único)

`SearchFeedView._build_sidebar`: `CTkSlider(number_of_steps=max_y-min_y)` quebrava quando
todos os resultados tinham o mesmo ano. Corrigido: slider só é criado quando `max_y > min_y`
(com `number_of_steps=max(1, …)`); em ano único mostra um rótulo estático "Ano único: N".
Também descarta um `year_slider` de busca anterior (evita referência a widget destruído).
**Teste novo** `tests/test_search_feed_ui.py`: ano único não quebra e oculta o slider;
anos variados criam o slider. (Pula automaticamente em ambiente sem display.)

## 3. Capturas de tela — RESOLVIDAS em 2026-08-01

> A pendência abaixo era real na primeira execução. A permissão de Gravação de Tela foi
> concedida depois, e as quatro capturas foram feitas. Registro original mantido:
>
> ~~`screencapture -x` continua falhando (`could not create image from display`, exit 1) —
> permissão de **Gravação de Tela** do macOS ainda não concedida.~~

Capturadas pela **janela do app** (`screencapture -l <CGWindowID>`), nunca a tela inteira, e
validadas com `scripts/verify_evidence.py`:

| arquivo | verificação |
|---|---|
| `docs/evidence/projetos_ligada_pt_BR.png` | OK · 2800×1680 · papel 69,6% · dados 2,67% |
| `docs/evidence/projetos_ligada_en.png` | OK · 2800×1680 · papel 69,7% · dados 2,69% |
| `docs/evidence/projetos_ligada_fr.png` | OK · 2800×1680 · papel 69,3% · dados 2,57% |
| `docs/evidence/blink_layout_fr.png` | OK · 2800×1680 · papel 82,1% · dados 2,16% |

O que as capturas confirmam visualmente:

- **Aba alcançável:** "Mes projets" / "My Projects" / "Meus Projetos" na navegação logo após
  a Home, com a borda vermelha de estado ativo, e a lista de cards renderizada.
- **Botões do card cabem em francês:** `Ouvrir · Renommer · Dupliquer · Supprimer` lado a
  lado, sem truncar — era o item 2.1.
- **Sugestões do Blink quebram em duas linhas em francês**, com o texto inteiro visível —
  era o item 2.3.

### Duas dificuldades técnicas da captura (resolvidas)

1. **A janela Tk não aparecia na lista do Quartz.** Um script Python puro não é ativado como
   app, e `CGWindowListCopyWindowInfo` não a listava — nem por título, nem por PID. Resolvido
   elevando a janela (`-topmost` + `lift` + `focus_force`) e ativando o processo por
   `osascript` antes de procurar, com fallback para capturar o **retângulo da janela** (`-R`)
   caso o ID ainda não apareça. Em nenhum caminho se captura a tela inteira.
2. **A tela de boas-vindas cobria as abas.** `_welcome_frame` usa `place(relwidth=1,
   relheight=1)` e fica por cima de tudo; a primeira leva de capturas registrou a tela de
   boas-vindas em vez da aba. Resolvido dispensando o frame antes de navegar.

## Observações

- **Ícones da navegação são text-only** (pré-existente): o loop abre `assets/icons/{name}.png`,
  mas os arquivos têm sufixo `_normal`/`_active` (ex.: `house_normal.png`), então o `try`
  falha e os botões ficam sem ícone — vale para **todas** as abas, não só Projetos. Segui a
  convenção existente (par livre `house`); corrigir o carregamento de ícones afeta todas as
  abas e está fora deste escopo. **Confirmado nas capturas:** nenhum botão da navegação tem
  ícone, nos três idiomas.
- Idioma do app restaurado para `pt_BR` ao fim dos testes (as verificações passaram por fr).

---

# Re-auditoria de 2026-08-01

O prompt foi reexecutado sobre o estado já corrigido. **Os cinco itens estavam implementados**
(este mesmo commit os entregou). O trabalho desta rodada foi: **medir em vez de ler o código**,
executar as capturas que tinham ficado pendentes, e reinjetar os defeitos para provar que a
cobertura é real. Três achados.

## Achado 1 — o `max(1, …)` do slider era código morto com comentário enganoso

A reinjeção mostrou que trocar `number_of_steps=max(1, max_y - min_y)` por
`number_of_steps=max_y - min_y` **não derrubava o teste**. Motivo: a expressão está dentro de
`if max_y > min_y:`, onde a diferença já é ≥ 1 — o `max(1, …)` nunca fez nada.

A proteção real contra o `ZeroDivisionError` é o próprio `if`, e removê-lo deixa o teste
vermelho na hora (`ZeroDivisionError: division by zero`). O comentário, porém, apontava para o
`max(1, …)` como sendo a proteção — um leitor concluiria a coisa errada. Código morto removido
e comentário corrigido para o guarda que de fato protege.

## Achado 2 — a navegação só traduz 2 de 9 rótulos

Visível na captura em francês: a barra lateral mistura idiomas. Auditoria do fonte:

| rótulo | estado |
|---|---|
| `projects`, `hist` | `t(...)` — traduzem |
| `home` ("Blink"), `corpus` ("Corpus") | hardcoded, mas são iguais nos três idiomas |
| `import` ("Coletar"), `stats` ("Estatísticas"), `analises` ("Análises"), `galeria` ("Galeria"), `export` ("Exportar") | **hardcoded em português** |

São **5 rótulos** que precisariam de chave. Também hardcoded: os textos da **tela de
boas-vindas** ("Bem-vindo! Inicie uma nova jornada…", "Começar Nova Pesquisa", "Carregar
Pesquisa"), que é a primeira tela que o usuário vê.

**Não corrigido** — está fora da lista deste prompt, que pede mudanças mínimas. Documentado
porque as capturas em `en`/`fr` mostram o problema, e a correção é barata (5 + 3 chaves).

## Achado 3 — bandeira alemã sem catálogo

Há botão de bandeira `de` em dois pontos da UI (`main.py`, seletor de idioma), mas `de.json`
não existe — foi removido por quebrar a paridade. Clicar **não quebra**: cai no fallback
inglês. Mas grava `lang="de"` nos settings, então o app fica em inglês dizendo que está em
alemão. Documentado, não corrigido (fora do escopo).

## Correção de um teste frágil (encontrada por acidente)

O script de captura persistiu o idioma como francês, e
`tests/test_backlog.py::test_reload_results_is_offline` quebrou: ele buscava a palavra
`"offline"` na trilha, que em francês é `"hors ligne"`. **O teste dependia do estado global da
máquina** — passava só com o app em pt_BR ou en.

Reescrito para comparar com a mensagem traduzida (`t("history.reloaded")`). Verificado
passando nos três idiomas. O idioma foi restaurado para `pt_BR` ao final.

## Medições finais (widgets reais, `winfo_reqwidth`, 4 fixtures adversariais)

Fixtures: projeto completo · **sem thumbnail** · **sem searches.json** · **`.blicsa` antigo
(sem `version` no manifest)**. Os quatro renderizam sem exceção.

| idioma | botão | texto (px) | largura | folga | status |
|---|---|---:|---:|---:|---|
| pt_BR | Abrir / Renomear / Duplicar / Excluir | 30 / 62 / 51 / 41 | 100 | 70 / 38 / 49 / 59 | OK |
| en | Open / Rename / Duplicate / Delete | 33 / 49 / 58 / 40 | 100 | 67 / 51 / 42 / 60 | OK |
| fr | Ouvrir / Renommer / Dupliquer / Supprimer | 38 / 66 / 59 / 63 | 100 | 62 / **34** / 41 / 37 | OK |

Folga mínima: **34px** (fr, "Renommer"). **Zero estouros.**

**Dois eixos + origem**, como manda a regra de teste:

| | pt_BR | en | fr |
|---|---|---|---|
| altura dos 4 cards | 156 · 156 · 156 · 156 | idem | idem |
| x do 1º botão | 0 · 0 · 0 · 0 | idem | idem |
| **variação de x** | **0px** | **0px** | **0px** |

**Sugestões do Blink** (grid de 2 colunas):

| idioma | maior botão | 1 linha (antes) | 2 linhas (agora) |
|---|---:|---:|---:|
| pt_BR | 313px | 959px OK | 636px OK |
| en | 320px | 980px OK | 650px OK |
| fr | 419px | **1277px ESTOURA** | **848px OK** |

**Botão Voltar do Blink** (width=100): `⬅ Voltar` 66px · `⬅ Back` 58px · `⬅ Retour` 71px — OK.

## Aceite da re-auditoria

- `python3 -m pytest tests/ -q` → **270 passed, 1 xfailed**. ✅
  *(O prompt esperava "4 xfail dos bugs de busca"; hoje resta **1** — o OBS-03 do Crossref.
  Os outros três foram corrigidos em rodadas anteriores.)*
- Aba alcançável por clique, confirmado por captura nos 3 idiomas. ✅
- Tabela de medição sem estouros, nos dois eixos, com variação de origem zero. ✅
- Smoke funcional: 100 registros normalizados → mapa com 56 nós e 1.133 arestas → 4 abas
  alternam → Blink e ProjectsView instanciados. ✅
- `python3 main.py --smoke-test` → OK. ✅

## Aceite

- `pytest tests/ -q` → **73 passed, 1 xfailed** (OBS-03, fora do escopo). ✅
- Aba alcançável por clique na navegação (validado com app real). ✅
- Tabela de medição final sem estouros. ✅
- Smoke: app constrói, abas home/projects/import/corpus alternam, mapa/Blink/busca já
  validados em rodadas anteriores. ✅
