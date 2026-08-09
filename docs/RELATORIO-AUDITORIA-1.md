# Relatório — Auditoria 1/3: mapas, fluxo e arquitetura

**Data:** 2026-08-09 · **Prompt:** `audit-1-funcional-e-arquitetura.md` · **Commits:**
`64d6685` · `77d9afc` · `afb29ca`

> **Veredito por área**
>
> | área | veredito | o que sustenta |
> |---|---|---|
> | **Mapas** | aprovado com correções | 11 corpus adversariais × 3 modos, nenhuma exceção, nenhum NaN, nenhuma tela branca — depois de 6 defeitos corrigidos |
> | **Fluxo** | aprovado com correções | percurso do usuário novo em 4,49 s, navegação íntegra — depois de 2 defeitos corrigidos |
> | **Arquitetura** | saudável nas fronteiras, concentrada no meio | zero ciclos, zero `core→ui`; `main.py` com 6.256 linhas e 173 métodos numa classe |
>
> **Nada encontrado bloqueia a publicação.** A lista do que corrigir antes está na §4.

---

## 1. Os oito defeitos

Todos corrigidos, todos com teste e reinjeção. Ordenados por quanto o usuário sentiria.

| # | defeito | como aparecia para o usuário | fase |
|---|---|---|---|
| 1 | **Mapa não era reprodutível** | regenerar o mapa do mesmo corpus dava outro desenho; figura publicada não podia ser refeita | 1 |
| 2 | **Import do WoS etiquetado dava zero registros** | exporta do WoS, importa, vê corpus vazio, sem erro nenhum | 2 |
| 3 | **Animação mostrava o ano errado** | termo usado desde 2010 estreava em 2013; anos com documento saíam vazios | 1 |
| 4 | **Zero citação lido como "sem dado"** | corpus recente saía com o overlay inteiro cinza sobre um dado que existia | 1 |
| 5 | **Trocar de idioma devolvia à tela inicial** | usuário no corpus troca o idioma e vê "novo projeto / abrir projeto", com o trabalho invisível atrás | 2 |
| 6 | **Exports corrompidos por quebra de linha** | `.net` ilegível no Gephi — e pelo próprio networkx que o escreveu | 1 |
| 7 | Correção nº 4 quebrou GML e GEXF | export levantava exceção | 1 |
| 8 | `except:` sem tipo (10×) | app ignora Ctrl-C | 3 (catalogado) |

**Sete dos oito eram silenciosos.** Nenhum levantava exceção visível; todos entregavam a coisa
errada sem avisar. É a assinatura que este projeto já conhece — o teto de 1.000 no campo Qtd,
o Crossref parando em 200, o `bool("false")`.

---

## 2. O que a auditoria diz sobre a suíte de testes

Antes desta rodada: **705 testes verdes**. Quatro dos oito defeitos estavam sob eles.

| defeito | por que a suíte não via |
|---|---|
| posições não reprodutíveis | determinismo só é verificável **entre processos**, com `PYTHONHASHSEED` distinto |
| ano de estreia da animação | os 30+ testes da animação **passam `first_year` na mão**; o app nunca tomava esse caminho |
| zero citação | havia um teste **afirmando o defeito** (`0.0` deveria virar `None`) |
| WoS etiquetado | nenhuma fixture usava o formato *plain text* |

E dois defeitos só apareceram porque a evidência era real: o ano da animação saiu de **olhar a
captura da janela**, e a corrupção dos exports saiu de **reler o arquivo com o leitor do
formato** em vez de conferir que ele existe.

### A reinjeção reprovou quatro testes meus

`scripts/reinject_ia_ux.py` (62 → 69 casos) achou, nas três fases, quatro guardas que eu tinha
acabado de escrever e que não guardavam nada:

1. guarda de determinismo procurando `"pos=None"` no código — casava com o **comentário** que
   explicava o defeito;
2. extração de chaves de catálogo por `ast.Call` de `_t(...)` — **não via** as `ai.sec_*`, que
   chegam como tuplas dentro de `_secoes(...)`; a paridade passava sobre um terço das chaves;
3. teste de cabeçalho do WoS conferindo colunas que **nunca chegam à tabela**;
4. dois casos de reinjeção que **não reinjetavam nada** (mutação em código que a leitura
   sobrescreve adiante; renomeação de método fora do caminho testado).

O padrão é um só, e vale mais que os defeitos: **teste escrito junto com a correção tende a
testar o caminho que a correção tomou, não o defeito que ela removeu.**

---

## 3. Números

| | antes | depois |
|---|---:|---:|
| testes verdes | 705 | **789** (+84) |
| defeitos reinjetados detectados | 56/56 | **69/69** |
| evidências auditadas | 71 | **80** |
| imports não usados | 20 | **4** |
| abas órfãs | 0 | 0 |
| ciclos de importação | 0 | 0 |

**Desempenho medido** (não estimado): 1,65 s / 10,65 s / 49,62 s para 500 / 2.000 / 5.000 nós.
O gargalo é `compute_overlay_scores`, O(nós × documentos) — 36 dos 50 segundos, quase o triplo
do ForceAtlas2, que é o passo que a intuição culparia.

**Percurso do usuário novo:** 15 passos, 4,49 s, zero atritos, sem chave de IA.

**Evidência visual:** 9 capturas (3 corpus × 3 modos) pela janela real, por `CGWindowID`,
todas distintas entre si — verificação que existe porque a primeira versão do script gerou
duas capturas idênticas e uma rotulada com o corpus errado.

---

## 4. O que corrigir antes de publicar

| # | o que | por quê agora |
|---|---|---|
| 1 | **Testes para `core/markdown_parser.py`** | zero testes, e é ele que renderiza a resposta do Blink no chat — a mesma superfície que três commits da fase de IA protegeram |
| 2 | **Mensagens de erro de projeto** | inglês fixo independentemente do idioma, nomeando arquivos internos (`manifest.json`). O usuário sabe que falhou e não sabe o que fazer |
| 3 | **Verificar rede caída e busca vazia** | as duas sondas travaram além de 5 min sem causa isolada. É o `_search_worker` (CC 68), o método do botão mais usado |
| 4 | **Decidir o destino de `core/map_animation.py`** | 543 linhas testadas, sem chamador. Ligar ou remover — não publicar indeciso |

## 5. O que pode esperar

| # | o que | onde está descrito |
|---|---|---|
| 5 | `compute_overlay_scores` O(nós × documentos) | `AUDITORIA-MAPAS.md` §7 |
| 6 | Passos 1–3 da decomposição do `main.py` (~800 linhas, risco baixo) | `AUDITORIA-ARQUITETURA.md` §3 |
| 7 | 10 `except:` sem tipo | `AUDITORIA-ARQUITETURA.md` §4 |
| 8 | Paleta de 8 cores pinta clusters distintos igual acima de 8 | `AUDITORIA-MAPAS.md` §11 |
| 9 | Três dialetos de acesso a coluna de dataframe | `AUDITORIA-ARQUITETURA.md` §4 |
| 10 | 16 funções públicas sem referência (API de componente) | `AUDITORIA-ARQUITETURA.md` §5 |

---

## 6. Limites desta auditoria

Registrados porque uma auditoria que só lista o que verificou é metade de um relatório.

- **Rede caída e busca vazia não foram verificadas.** As sondas travaram; as candidatas são o
  backoff das três tentativas do provedor e um modal bloqueando um teste sem interação. Estão
  como pendentes, não como aprovadas.
- **Disco cheio ao salvar** foi aproximado por caminho inválido. Simular disco cheio de verdade
  exige montar um volume — fora do escopo.
- **Cobertura de testes é uma proxy declarada**, não cobertura de linha: `pytest-cov` não está
  disponível e instalá-lo alteraria o ambiente do usuário.
- **A busca não entrou no percurso cronometrado**, de propósito: mediria a rede, não o app, e
  não seria refazível daqui a um ano com o mesmo resultado.
- **Compatibilidade sacrificada em um ponto:** projeto salvo antes da correção nº 4 tem
  `citations_mean: 0.0` para "zero" e para "não sei", e nada distingue os dois; passam a
  aparecer como zero. A troca é deliberada e está justificada em `AUDITORIA-MAPAS.md` §2.2.

## 7. Retomada

As três fases fecharam. Os prompts 2 (segurança e limpeza) e 3 (instaladores) podem começar da
árvore em `afb29ca`, limpa, com 789 testes verdes e 69/69 reinjeções detectadas.

| documento | fase |
|---|---|
| `docs/AUDITORIA-MAPAS.md` | 1 — mapas com corpus adversariais |
| `docs/AUDITORIA-FLUXO.md` | 2 — fluxo de ponta a ponta |
| `docs/AUDITORIA-ARQUITETURA.md` | 3 — arquitetura e dívida |
