# Auditoria 1 · Fase 2 — fluxo de ponta a ponta

**Data:** 2026-08-09 · **Escopo:** itens 10 a 14 de `audit-1-funcional-e-arquitetura.md`

> **Veredito:** o percurso do usuário novo fecha em **4,49 s** e não tem atrito bloqueante.
> A navegação está íntegra — nenhuma aba órfã, nenhum botão sem destino. Mas dois defeitos
> **silenciosos** apareceram, e os dois entregavam a coisa errada sem avisar:
>
> 1. **Trocar de idioma devolvia o usuário à tela de boas-vindas** (§3.1)
> 2. **Import do Web of Science etiquetado devolvia zero registros** (§3.2)
>
> Os dois foram corrigidos. O resto desta fase é diagnóstico, com os atritos ordenados por
> severidade na §6.

---

## 1. Percurso do usuário novo, cronometrado (item 10)

Executado de verdade contra `BlicsaApp`, offline, a partir de `docs/sample_dataset.csv`
(200 registros). Executor: `scripts/audit_fluxo.py`.

| passo | s | resultado |
|---|---:|---|
| abrir o app pela primeira vez | 0,99 | 10 abas montadas |
| tela de boas-vindas está na frente | 0,00 | sim |
| escolher "abrir projeto" | 0,01 | aba = `projects` |
| importar CSV de exemplo | 0,01 | 200 registros |
| corpus vai para o app | 0,05 | aba = `corpus` |
| gerar o grafo | 0,35 | 221 nós · 6.393 arestas |
| calcular o layout (500 iterações) | 0,45 | 221 posições |
| publicar o mapa para a tela | 0,08 | 221 nós no payload |
| rótulos de cluster **sem chave de IA** | 0,00 | recusa clara: *"API Key não configurada nos Ajustes."* |
| exportar GML, GEXF, Pajek, VOSviewer | 0,48 | 4 formatos, todos relidos com 221 nós |
| salvar o projeto | 0,06 | 301 KB |
| fechar o app | 0,09 | — |
| reabrir o app | 1,12 | — |
| carregar o projeto salvo | 0,73 | 221 nós · 200 registros |
| fechar | 0,07 | — |
| **total** | **4,49** | **15 passos, zero atritos** |

**O que este número não mede.** Os dois passos lentos do uso real ficaram de fora de
propósito: a **busca** depende de rede (mediria a rede, não o app, e não seria refazível daqui
a um ano) e o **mapa grande** já foi medido na Fase 1 — 49,6 s para 5.000 nós, com
`compute_overlay_scores` respondendo por 36 deles. Para um corpus de 200 registros, o app é
instantâneo.

**Sem chave de IA o percurso inteiro funciona.** É o cenário do usuário novo, e a única
recusa é explícita e no lugar certo.

---

## 2. Consistência de navegação (item 13)

Extraído por AST de `main.py`: abas registradas em `_tabs`, botões da barra lateral e toda
chave literal passada a `_switch_tab`.

| | |
|---|---|
| abas registradas | 10 — `home`, `projects`, `import`, `review`, `corpus`, `stats`, `analises`, `hist`, `galeria`, `export` |
| botões na barra lateral | 9 (todos com aba correspondente) |
| destinos de `_switch_tab` | 8 (todos registrados) |
| **abas órfãs** | **nenhuma** |
| **chaves fantasma** | **nenhuma** |
| **botão sem destino** | **nenhum** |

`review` é a única aba sem botão, e por desenho: é tela de fluxo, entra depois da busca. O que
o teste garante é que ela não perca *todo* caminho —
`test_review_e_alcancavel_por_codigo`.

O `_switch_tab("viz")` corrigido em 08/08 continua ausente. O guarda dele foi estendido nesta
fase para cobrir os dois sentidos: aba sem caminho e botão sem aba. É o modo de falha da
"Meus Projetos" inalcançável, que já custou um commit próprio (`75fdb33`).

**Caminho sem saída:** nenhum encontrado. A tela de boas-vindas cobre a janela inteira e tem
exatamente duas saídas, ambas funcionais.

---

## 3. Defeitos encontrados

### 3.1 Trocar de idioma devolvia o usuário ao início — **corrigido**

`_refresh_language` destrói todos os widgets e remonta o layout. A tela de boas-vindas é um
`place()` sobre a janela inteira, montado dentro de `_build_layout` — e `_switch_tab` não a
remove.

Medido:

| momento | tela de boas-vindas | aba ativa |
|---|---|---|
| app recém-aberto | **sobre tudo** | `home` |
| usuário escolheu um caminho | fora do caminho | `projects` |
| usuário navegou até o corpus | fora do caminho | `corpus` |
| **usuário trocou o idioma** | **sobre tudo** | `corpus` |

A aba embaixo continuava certa. O corpus continuava carregado. O usuário via
"novo projeto / abrir projeto" e o trabalho dele invisível atrás — e clicar em "novo projeto"
dali entra no fluxo de criação por cima do que estava aberto.

Corrigido com `_dispensa_boas_vindas()`, que marca a escolha num atributo que sobrevive ao
`_build_layout`. Quem **ainda não** escolheu continua vendo a tela depois de trocar o idioma —
`test_sem_dispensar_a_tela_ela_sobrevive_a_troca_de_idioma` guarda esse lado, para a correção
não virar "nunca mostrar".

### 3.2 Import do Web of Science etiquetado devolvia zero registros — **corrigido**

O `.txt` do WoS vem em dois sabores:

| formato | como é | lido antes? |
|---|---|---|
| *Tab delimited* | planilha, cabeçalho de siglas | sim |
| *Plain text* | etiquetado (`AU Silva, J`), `ER` fecha o registro | **não** |

`load_wos_txt` fazia `pd.read_csv(sep="\t")` direto. Sobre o etiquetado isso devolve **zero
registros e nenhum erro**: o usuário exporta do WoS, importa no Blicsa, e vê um corpus vazio
sem nada que explique por quê.

O *plain text* é a opção que a interface do WoS oferece primeiro e a que a maior parte das
ferramentas bibliométricas espera. Corrigido com detecção de formato e um leitor etiquetado
que trata:

- **continuação com três espaços** — autores e referências ocupam várias linhas; ignorá-las
  perderia o segundo autor de todo artigo em coautoria, silenciosamente;
- **`FN`/`VR`** — metadados do arquivo, não campos de registro;
- **último registro sem `ER`** — arquivo truncado no download é comum, e descartar o último
  registro seria a mesma classe de defeito que esta correção resolve.

Os dois formatos passam agora, com teste para cada um (`test_wos_tab_delimited_continua_funcionando`
existe para a correção não trocar um pelo outro).

---

## 4. Percursos alternativos (item 11)

| percurso | resultado |
|---|---|
| importar Scopus CSV | 1 registro, colunas mapeadas (título, autores, ano, keywords, citações) |
| importar Web of Science *tab* | OK |
| importar Web of Science *plain text* | **era 0 registros** → corrigido (§3.2) |
| importar RIS | OK |
| importar BibTeX | OK |
| abrir projeto de schema antigo (`version: 1.0`) | abre; grafo restaurado; dataset ausente tolerado |
| usar sem chave de IA | recusa clara, percurso completo funciona |
| trocar de idioma no meio do fluxo | **era regressão à tela inicial** → corrigido (§3.1) |
| usar sem internet | ver §5 — não concluído |

---

## 5. Estados de erro (item 12)

| situação | o que acontece | veredito |
|---|---|---|
| sem chave de IA | `AIClientError: API Key não configurada nos Ajustes.` | **claro** |
| `.blicsa` truncado | `messagebox` com *"File is not a zip file"* | capturado, **mensagem crua** |
| `.blicsa` sem manifesto | *"There is no item named 'manifest.json' in the archive"* | capturado, **nomeia arquivo interno** |
| `.blicsa` com JSON inválido | `JSONDecodeError: Expecting property name...` | capturado, **mensagem de biblioteca** |
| CSV renomeado para `.blicsa` | *"File is not a zip file"* | capturado, mensagem crua |
| salvar em caminho inválido | `FileNotFoundError: [Errno 2]` | capturado, **carrega `Errno`** |

**Nenhum traceback chega ao usuário** — `_open_project` captura tudo e mostra `messagebox`.
O problema é o conteúdo: `messagebox.showerror("Erro ao carregar", str(e))` repassa a mensagem
da biblioteca, **em inglês independentemente do idioma da interface**, às vezes nomeando um
arquivo interno do formato. O usuário sabe que falhou; não sabe o que fazer.

Não corrigido nesta fase — é qualidade de mensagem, não quebra funcional, e traduzir os modos
de falha exige chaves novas nos três catálogos. É o atrito nº 1 da §6.

### O que não foi concluído

Duas sondas de erro **não terminaram** e estão registradas como pendentes, não como aprovadas:

- **rede caindo no meio da busca** e **busca sem resultados**, exercitadas pelo
  `_search_worker` real, travaram a sonda além de 5 minutos. A causa não foi isolada — as
  candidatas são o backoff exponencial das três tentativas do provedor e um `messagebox`
  modal bloqueando um teste sem interação. Registrado aqui em vez de omitido: uma sonda que
  trava é informação sobre o app, e afirmar que esses dois estados "passaram" seria falso.
- **disco cheio ao salvar** foi aproximado por caminho inválido. `/dev/full` não existe no
  macOS e simular disco cheio de verdade exige montar um volume — fora do escopo desta fase.

---

## 6. Atritos, por severidade

| # | severidade | atrito | estado |
|---|---|---|---|
| 1 | **média** | Mensagens de erro de projeto são as da biblioteca: inglês fixo, nomeiam arquivos internos, não dizem o que fazer | aberto |
| 2 | **média** | `_search_worker` não pôde ser exercitado sem travar a sonda; comportamento com rede caída e busca vazia **não verificado** | aberto |
| 3 | baixa | Carregar projeto muda a aba por `self.after(0, ...)`; fora do loop de eventos a aba não troca. Não afeta o app real, mas torna o passo não testável de forma síncrona | aberto |
| 4 | baixa | `core/map_animation.py` sem chamador (herdado da Fase 1) | aberto |
| — | **alta** | Trocar de idioma devolvia o usuário à tela inicial | **corrigido** |
| — | **alta** | Import do WoS etiquetado devolvia corpus vazio em silêncio | **corrigido** |

---

## 7. Aceite

- `python3 -m pytest tests/ -q` → **789 passed, 1 xfailed**. Eram 775 no fim da Fase 1:
  **+14 testes**. ✅
- `python3 scripts/reinject_ia_ux.py` → **69/69 defeitos detectados** (7 novos nesta fase). ✅
- `python3 scripts/audit_fluxo.py` → 15 passos, 4,49 s, zero atritos. ✅
- `python3 main.py --smoke-test` → OK. ✅
- `python3 scripts/check_i18n_parity.py` → catálogos em paridade. ✅

### Dois furos nos próprios testes desta fase

`scripts/reinject_ia_ux.py` reprovou dois testes que eu tinha acabado de escrever:

1. **`test_cabecalho_do_arquivo_nao_vira_registro`** conferia que nenhum título saía vazio num
   arquivo *com* registros — e `FN`/`VR` não estão entre as colunas exportadas, então nunca
   chegariam à tabela de jeito nenhum. Reescrito sobre um arquivo **só com cabeçalho**, onde
   a ausência da guarda produz um registro fantasma de verdade. E chamando
   `_load_wos_etiquetado` direto, porque um arquivo sem linha `PT ` é mandado pela detecção
   para o caminho TSV e a guarda nunca seria exercitada.

2. Um caso de reinjeção que **não reinjetava nada**: renomeava `_dispensa_boas_vindas` e
   inseria um stub, mutação que não toca o caminho da primeira abertura. Trocado pela guarda
   invertida, que é o defeito real.

O padrão dos dois é o mesmo da Fase 1 e do relatório de IA: **teste escrito junto com a
correção tende a testar o caminho que a correção tomou, não o defeito que ela removeu.** A
reinjeção é o que separa um do outro.
