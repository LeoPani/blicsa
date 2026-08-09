# Blicsa — relatório da sessão de 08–09/08/2026

**7 commits** (`71da1b2` → `bf55607`) · **testes: 557 → 789** · **reinjeções: 38/38 → 69/69**

Três blocos de trabalho: fechamento da camada de IA (contexto de pesquisa e idioma das
análises) e a **Auditoria 1** completa — mapas, fluxo e arquitetura.

**Quinze defeitos corrigidos.** Treze deles silenciosos: não levantavam exceção, não apareciam
em log, e entregavam a coisa errada sem avisar.

---

## Parte 1 — Camada de IA

### 1.1 Contexto de pesquisa por projeto (`71da1b2`)

O corpus diz *o que* foi publicado. Não diz que a pessoa estuda cooperativas de catadores, nem
que "informalidade", no vocabulário dela, é categoria da sociologia do trabalho e não do
direito tributário. Sem isso, a IA responde sobre o corpus certo com o enquadramento errado.

A ordem do prompt é a decisão: **papel → idioma → contexto do usuário → dados do corpus**. O
contexto vem *antes* dos dados — posto depois, lê como observação final sobre um material já
apresentado; posto antes, é a lente pela qual o material é lido. Quando o orçamento estoura, o
corte sacrifica **abstracts, nunca o contexto**: abstract cortado tira uma evidência entre
outras; contexto cortado enquadra a resposta inteira errado, sem o usuário ter como saber.

Exigir chamada real ao modelo para as capturas desenterrou **seis defeitos** que a suíte não
via, dois capazes de tornar a IA inutilizável na instalação:

- `.env` do repositório sobrescrevia a chave válida do ambiente (401 sem explicação);
- teste de conexão sem `User-Agent` levava 403 do Cloudflare e **reprovava chave válida** — só
  a tela que existe para configurar a chave a recusava;
- Sankey, mapa temático e historiografia renderizavam IA **sem marcação**, ao contrário do que
  o inventário declarava;
- `_switch_tab("viz")` — chave que nunca existiu — deixava a tela **em branco** depois de
  carregar arquivo e depois de abrir projeto;
- bloco de corpus ia ao modelo com `\n` literal em vez de quebra de linha;
- três telas reaproveitavam um system prompt congelado na construção da janela.

### 1.2 As análises respondiam sempre em português (`7da28ca`, `c931b8c`)

Cinco prompts pediam *"linguagem técnica acadêmica em português"* em texto fixo. Quem usava o
app em inglês ou francês recebia o mapa temático, o Sankey, a historiografia, as obras seminais
e os insights do corpus **em português**, com a interface inteira ao redor no idioma certo.

Troquei pela diretiva dinâmica `diretiva_idioma(get_lang())` — a mesma função do chat do Blink,
não um texto equivalente reescrito. Injetada no ponto único `_system_com_contexto`, porque
prompt a prompt seriam seis lugares para esquecer um, e foi exatamente assim que os cinco
ficaram presos ao português.

`label_clusters` entrou junto, embora não fosse uma das cinco: pedia *"Label conciso em
português"* no prompt do usuário. Corrigir só as cinco poria o `system` mandando responder em
francês contra o `user` mandando rotular em português — **contradição pior que o bug**.

**A verificação com chamada real reprovou essa correção.** Com 42 testes verdes e 44/44
reinjeções detectadas, **7 das 18 análises ainda saíam em português** — 4 das 6 em inglês. E
mesmo as que acertavam o corpo vinham encabeçadas por *"Frentes de Pesquisa Emergentes"*.

O que faltava não era diretiva, era o resto do prompt:

| causa | medição | correção |
|---|---|---|
| títulos de seção fixos em português | o modelo os copia literalmente e o cabeçalho puxa o corpo junto | 11 chaves `ai.sec_*` nos três catálogos |
| nome da análise no corpo do prompt | `Mapa Temático` em **3 de 3** respostas em inglês | 7 chaves `ai.obj_*` / `ai.rot_*` |
| diretiva só no `system` | perdia para um prompt longo em português vindo depois | repetida no fim do turno do usuário |

A distinção que faltava: **título de seção é conteúdo, não instrução.** O que o modelo *copia*
precisa estar traduzido; só o que ele *obedece* pode ficar em português.

**Resultado: 18/18** — seis análises × três idiomas, com chamada real ao `llama-3.3-70b` via
Groq. Zero vazamento de termo português em 18 chamadas adicionais.

---

## Parte 2 — Auditoria 1

### Veredito por área

| área | veredito | o que sustenta |
|---|---|---|
| **Mapas** | aprovado com correções | 11 corpus adversariais × 3 modos: nenhuma exceção, nenhum NaN, nenhuma tela branca — depois de 6 defeitos corrigidos |
| **Fluxo** | aprovado com correções | percurso do usuário novo em 4,49 s, navegação íntegra — depois de 2 defeitos corrigidos |
| **Arquitetura** | saudável nas fronteiras, concentrada no meio | zero ciclos, zero `core→ui`; `main.py` com 6.256 linhas e 173 métodos numa classe |

**Nada encontrado bloqueia a publicação.**

### 2.1 Fase 1 — mapas com corpus adversariais (`64d6685`)

Onze corpus, cada um por um modo de falha conhecido de pipeline de grafo: 1 documento; 2 e 10
componentes desconexas; todos do mesmo ano; nenhum com ano; frequências iguais; termo
dominante; 5.000 documentos; acento/emoji/aspas/600 caracteres; abstracts vazios; autor em
cinco grafias.

**A matriz passou toda verde na primeira execução, com seis defeitos presentes.** O que mudou
não foi rodar de novo — foi olhar *dentro* do payload em vez de perguntar se ele existia.

**O mapa não era reprodutível.** Medido em subprocessos com `PYTHONHASHSEED` distinto: ordem
dos nós, clusters e cores idênticos (a semente da v2.0.0 funciona), **posições diferentes a
cada execução** — inclusive entre dois runs com o mesmo seed, ou seja, RNG puro, não ordem de
hash. `fa2_modified` sorteia a posição inicial com o `random` **global do processo**, que
ninguém semeava. Uma figura publicada não podia ser refeita.

**A animação da tela mostrava o ano errado** — achado pela captura, não pelo código. O `map.js`
monta a linha do tempo com `first_year`, que **nunca esteve no payload** nem era escrito pelos
builders. Cada termo estreava no seu ano *médio*: corpus com documentos em 2010, 2011 e 2020
começava a barra em 2013, com os quadros de 2010–2012 vazios.

**Zero citação era lido como "sem dado".** `zero_is_missing` herdado do tratamento do ano, onde
a regra é certa porque ano zero não existe. Zero citação é o valor mais comum de artigo
recente: num corpus dos últimos dois anos o overlay saía inteiro cinza sobre um dado que estava
lá, com o payload se contradizendo — `citations_sum: 0` ao lado de `avg_citations: null`.

**Exports corrompidos por quebra de linha no termo.** `nx.read_pajek` levantava `ValueError`
sobre o arquivo que o próprio `export_pajek` acabara de escrever. Pajek e VOSviewer são
formatos de um registro por linha; um termo com `\n` partia o registro em cinco linhas físicas.
O usuário só descobriria ao abrir no Gephi.

**E a correção das citações quebrou GML e GEXF** — `.get(chave, padrao)` não cobre chave
presente valendo `None`. A própria bateria pegou, no mesmo dia.

**Medições:** densidade recalculada por viewport em 5 níveis de zoom; overlay em 5 extremos;
animação em 4 distribuições de ano; exports conferidos com o leitor de cada formato; ida e
volta do `.blicsa` campo a campo, incluindo a origem IA/humano de cada rótulo.

**Desempenho medido, não estimado:** 1,65 s / 10,65 s / 49,62 s para 500 / 2.000 / 5.000 nós.
O gargalo é `compute_overlay_scores`, O(nós × documentos) — 36 dos 50 segundos, quase o triplo
do ForceAtlas2, que é o passo que a intuição culparia.

**Documentado e não corrigido:** `core/map_animation.py` (543 linhas, GIF/MP4/pôster) é
importado **só por testes**. Ligar à interface é feature nova, não correção de defeito.

### 2.2 Fase 2 — fluxo de ponta a ponta (`77d9afc`)

Percurso do usuário novo, executado de verdade contra a aplicação e cronometrado: **15 passos,
4,49 s, zero atritos**, sem chave de IA — abrir, importar, gerar mapa, exportar nos 4 formatos,
salvar, fechar, reabrir, carregar.

Navegação íntegra: 10 abas, 9 botões, **nenhuma órfã**, nenhuma chave fantasma, nenhum botão
sem destino. O guarda foi estendido nos dois sentidos — é o modo de falha da "Meus Projetos"
inalcançável.

**Trocar de idioma devolvia o usuário à tela de boas-vindas.** `_refresh_language` destrói tudo
e remonta o layout; a tela de boas-vindas é um `place()` sobre a janela inteira que
`_switch_tab` não remove. Medido: aba continuava `corpus`, corpus continuava carregado, e o
usuário via "novo projeto / abrir projeto" com o trabalho invisível atrás — clicar em "novo
projeto" dali entra no fluxo de criação por cima do que estava aberto.

**Import do Web of Science etiquetado devolvia zero registros.** O `.txt` do WoS vem em dois
sabores e o parser fazia `read_csv(sep="\t")` direto. Sobre o *plain text* — a opção que a
interface do WoS oferece primeiro — isso dá zero registros e **nenhum erro**. Implementei o
leitor etiquetado, tratando continuação de três espaços (sem ela se perde o segundo autor de
todo artigo em coautoria), cabeçalho `FN`/`VR` e último registro sem `ER`.

**Estados de erro:** nenhum traceback chega ao usuário — tudo capturado em `messagebox`. Mas as
mensagens são as da biblioteca: inglês fixo independentemente do idioma da interface, às vezes
nomeando arquivo interno (`manifest.json`). O usuário sabe que falhou e não sabe o que fazer.

### 2.3 Fase 3 — arquitetura (`afb29ca`)

**Fronteiras certas:** zero ciclos de importação, `core/` não importa de `ui/`, `ai/` não
importa de `ui/` nem de `main`, transporte HTTP único (14 pontos de `urllib.request`, nenhum
`requests` misturado).

**Concentração no meio:** `main.py` com 6.256 linhas — 21% de todo o Python rastreado — e
`BlicsaApp` com 173 métodos e 5.757 linhas. As duas funções mais complexas do projeto vivem
ali: `_search_worker` (CC **68**, 304 linhas, 6 níveis de aninhamento) e `_update_stats_tab`
(CC **63**). `_search_worker` é o método do botão mais usado do app *e* aquele cujas sondas de
erro travaram na Fase 2 — as duas coisas são o mesmo fato visto de dois lados.

**Plano de decomposição escrito e não executado.** A ordem não é por tamanho, é por quanto
estado compartilhado cada peça arrasta — extrair uma tela que lê seis atributos de `self` só
move o acoplamento de arquivo. Passos 1–3 (triggers de IA, exporters, diálogos) tirariam ~800
linhas com risco baixo; passos 6–7 exigem teste de caracterização antes.

**Executado:** 16 imports não usados removidos, cada um confirmado com busca no repositório
inteiro. 789 antes, 789 depois — o resultado esperado de uma limpeza que não muda
comportamento.

**Catalogado e não executado:** 10 `except:` sem tipo em `main.py` (capturam
`KeyboardInterrupt` e `SystemExit`); 16 funções públicas sem referência, na maioria API de
componente de UI; três dialetos convivendo para acesso a coluna de dataframe. **Zero
TODO/FIXME/HACK** no repositório.

**Três módulos de produção sem nenhum teste**, e um é sério: `core/markdown_parser.py`
renderiza a resposta do Blink no chat.

**O analisador auditou a si mesmo, e precisou.** A primeira versão apontou 33 funções mortas —
entre elas `load_bibtex`, `load_ris` e `load_pdf`, chamadas por
`getattr(parser, loaders_map[fmt])()`. Reportar aquilo teria mandado apagar o suporte a BibTeX
e RIS. Passou a contar literal de string como referência e a lista caiu para 16. Idem para
`from __future__ import annotations`, sinalizado como import morto.

---

## Parte 3 — O que a sessão diz sobre o método

### Suíte verde não é evidência

Antes da auditoria: **705 testes verdes**. Quatro dos oito defeitos estavam sob eles.

| defeito | por que a suíte não via |
|---|---|
| posições não reprodutíveis | determinismo só é verificável **entre processos**, com `PYTHONHASHSEED` distinto |
| ano de estreia da animação | os 30+ testes da animação **passam `first_year` na mão**; o app nunca tomava esse caminho |
| zero citação | havia um teste **afirmando o defeito** — `0.0` deveria virar `None` |
| WoS etiquetado | nenhuma fixture usava o formato *plain text* |

E o mesmo vale para a camada de IA: 42 testes verdes e 44/44 reinjeções não impediram que 7 de
18 análises saíssem no idioma errado.

### A reinjeção reprovou quatro guardas escritos nesta sessão

`scripts/reinject_ia_ux.py` (38 → 69 casos) achou quatro testes meus que não guardavam nada:

1. guarda de determinismo procurando `"pos=None"` no código — casava com o **comentário** que
   explicava o defeito;
2. extração de chaves de catálogo por `ast.Call` de `_t(...)` — **não via** as `ai.sec_*`, que
   chegam como tuplas dentro de `_secoes(...)`; a paridade passava sobre um terço das chaves;
3. teste de cabeçalho do WoS conferindo colunas que **nunca chegam à tabela**;
4. dois casos de reinjeção que **não reinjetavam nada**.

**Teste escrito junto com a correção tende a testar o caminho que a correção tomou, não o
defeito que ela removeu.** A reinjeção é o que separa um do outro.

### Evidência real encontra o que leitura de código não encontra

Três defeitos vieram de exigir que a evidência fosse real, não de revisar código: o ano da
animação saiu de **olhar a captura da janela**; a corrupção dos exports saiu de **reler o
arquivo com o leitor do formato** em vez de conferir que ele existe; e os 7 de 18 no idioma
errado saíram de **chamar o modelo de verdade**.

O script de captura também precisou ser auditado: a primeira versão gerou **duas capturas
idênticas** (a troca de aba por AppleScript não trocava a aba) e **uma rotulada com o corpus
errado** (a janela nascia com o `graph.json` da execução anterior). Hoje ele confere
`state.mode` e `graph.order` antes de fotografar, e recusa capturas idênticas entre si.

---

## Números

| | antes | depois |
|---|---:|---:|
| testes verdes | 557 | **789** (+232) |
| defeitos reinjetados detectados | 38/38 | **69/69** |
| evidências auditadas | 71 | **80** |
| imports não usados | 20 | **4** |
| análises no idioma certo | 11/18 | **18/18** |
| abas órfãs · ciclos de importação | 0 · 0 | 0 · 0 |

---

## O que corrigir antes de publicar

| # | o que | por quê agora |
|---|---|---|
| 1 | Testes para `core/markdown_parser.py` | zero testes, e é ele que renderiza a resposta do Blink no chat |
| 2 | Mensagens de erro de projeto | inglês fixo independentemente do idioma, nomeando arquivos internos |
| 3 | Verificar rede caída e busca vazia | sondas travaram além de 5 min sem causa isolada; é o `_search_worker` (CC 68) |
| 4 | Decidir o destino de `core/map_animation.py` | 543 linhas testadas, sem chamador — ligar ou remover, não publicar indeciso |

## O que pode esperar

`compute_overlay_scores` O(nós × documentos) · passos 1–3 da decomposição do `main.py` (~800
linhas, risco baixo) · 10 `except:` sem tipo · paleta de 8 cores pinta clusters distintos igual
acima de 8 · três dialetos de acesso a coluna de dataframe · 16 funções públicas sem referência.

---

## Limites desta sessão

Registrados porque um relatório que só lista o que verificou é metade de um relatório.

- **Rede caída e busca vazia não foram verificadas.** As sondas travaram; candidatas são o
  backoff das três tentativas do provedor e um modal bloqueando teste sem interação. Estão como
  pendentes, não como aprovadas.
- **Disco cheio ao salvar** foi aproximado por caminho inválido — simular de verdade exige
  montar um volume.
- **Cobertura de testes é proxy declarada**, não cobertura de linha: `pytest-cov` não está
  disponível e instalá-lo alteraria o ambiente.
- **A busca não entrou no percurso cronometrado**, de propósito: mediria a rede, não o app, e
  não seria refazível daqui a um ano.
- **Compatibilidade sacrificada em um ponto:** projeto salvo antes da correção de citações tem
  `citations_mean: 0.0` para "zero" e para "não sei", e nada distingue os dois; passam a
  aparecer como zero. Troca deliberada, justificada em `AUDITORIA-MAPAS.md` §2.2.
- **A bolha da pergunta do usuário renderiza vazia** no chat do Blink (repintura do Tk no
  macOS, causa não isolada) — anterior a esta sessão e ainda aberta.

---

## Documentos no repositório

| documento | conteúdo |
|---|---|
| `docs/RELATORIO-IA-UX.md` | camada de IA: chave, amarelo, contexto de pesquisa, idioma das análises |
| `docs/AUDITORIA-MAPAS.md` | Auditoria 1 · Fase 1 |
| `docs/AUDITORIA-FLUXO.md` | Auditoria 1 · Fase 2 |
| `docs/AUDITORIA-ARQUITETURA.md` | Auditoria 1 · Fase 3 |
| `docs/RELATORIO-AUDITORIA-1.md` | consolidado das três fases |

**Ferramentas reexecutáveis:** `scripts/audit_mapas.py` · `scripts/audit_fluxo.py` ·
`scripts/audit_arquitetura.py` · `scripts/verify_analises_i18n.py` ·
`scripts/capture_mapas_adversariais.py` · `scripts/reinject_ia_ux.py`

Árvore limpa em `bf55607`. Os prompts 2 (segurança e limpeza) e 3 (instaladores) podem começar
daí.
