# Prompt — Mapas, camada 3 (rodar no Claude Code, no terminal do Mac)

Uso: `cd ~/PyBibliomics && claude` e cole tudo abaixo da linha.

---

Você vai trabalhar no Blicsa (`~/PyBibliomics`), app desktop de bibliometria em Python/CustomTkinter.
Trabalhe com autonomia do início ao fim e só me chame no relatório final. Não mude funcionalidades
que já existem, não remova tipos de mapa, não quebre projetos `.blicsa` antigos. Não faça push.

## Contexto (o que já foi feito — camadas 1 e 2, versão 2.1.0-beta.3)

Leia antes: `docs/AUDITORIA-2026-09.md` (Parte 5), `core/map_controls.py` (`viabilidade_tipo`),
`core/matrix_builders.py` (`_limitar_nos`, `_rotulo_ref`, `build_direct_citation_network`),
`main.py` (`_atualizar_tipo_de_mapa`, `_mapping_worker_impl`, função interna `construir`).

Já existe: aviso antes de clicar quando o tipo não serve para o corpus; rótulo do limiar
conforme o tipo; limite de nós valendo para todos os tipos; limiar alto demais é reduzido
automaticamente com aviso.

## O que falta (três problemas, nesta ordem)

### 1. Projetos antigos sem `openalex_id`
Nas bases do OpenAlex as referências são IDs (`https://openalex.org/W…`), não DOIs. A beta.3 já
casa a citação direta pelo `openalex_id` (`_id_openalex` em `core/matrix_builders.py`), e projetos
importados recentemente guardam a coluna. Projetos antigos (ex.: `seminario-qualificacao-grace-period`)
não a têm, e o app avisa `map.inviavel_citdir_openalex` em vez de gerar.
- Acrescente `openalex_id` a `SCHEMA_REGISTRO` em `core/project.py` (retrocompatível: projeto
  antigo abre com a coluna vazia; o aviso de inviabilidade tem que continuar funcionando).
- Garanta que o ID sobrevive busca → corpus → salvar → reabrir → exportar CSV → reimportar.
- Ofereça "Completar IDs do OpenAlex" quando o aviso aparecer (consulta por DOI em lote,
  `filter=doi:a|b|c`, 50 por chamada, respeitando `mailto`/polite pool e o cancelamento que o app
  já usa), rodando em thread, nunca na thread do Tk. Sem internet: mensagem clara, sem travar.
  Depois de completar, citação direta tem que gerar mapa no projeto antigo.

### 2. Referências aparecem como "W2741809807" no mapa
Cocitação e acoplamento com corpus do OpenAlex mostram IDs. Resolva para "Sobrenome (ano)" via
API do OpenAlex (`/works?filter=openalex:W1|W2…&select=id,publication_year,authorships,title`,
lotes de 50), com cache em disco na pasta do projeto (`refs_cache.json`) para não consultar de novo.
Sem internet ou falha: mantenha o rótulo curto atual (`_rotulo_ref`) — nunca falhe o mapa por isso.
Homônimos ("Silva (2020)" duas vezes): desambigue com sufixo a/b.

### 3. Categorias do seletor de tipo de mapa
Hoje é uma lista plana de 7 tipos técnicos. Agrupe por pergunta, **mantendo os mesmos 7 tipos e os
mesmos índices** (`MAP_TYPES`, o backlog e projetos salvos dependem deles):
- **Sobre o que se escreve?** — coocorrência de termos
- **Quem escreve com quem?** — coautoria
- **Em que o campo se apoia?** — cocitação, acoplamento bibliográfico, citação direta
- **Patentes / experimental** — IPC, agrupamento semântico
Cada tipo com uma frase curta do que o mapa mostra. Tipos inviáveis para o corpus aparecem
desabilitados/atenuados com o motivo (reaproveite `viabilidade_tipo`). Textos nos três idiomas
(`locales/pt_BR.json`, `en.json`, `fr.json`).

## Critérios de aceitação (verifique tudo pelo terminal antes do relatório)

1. `python scripts/check_i18n_parity.py` → sem chave faltando.
2. `python -m pytest tests -q` → nenhuma falha nova em relação ao início (anote a contagem inicial;
   existem ~5 testes de janela que só falham no Linux sem display — não conte esses).
3. Testes novos, offline (mockando a API com fixtures em `tests/fixtures/`), cobrindo:
   `openalex_id` sobrevive salvar/reabrir/exportar/reimportar; projeto antigo sem a coluna abre;
   "Completar IDs" com API mockada faz a citação direta gerar arestas; rótulo "Sobrenome (ano)" com cache;
   falha de rede mantém rótulo curto e o mapa sai; índices de `MAP_TYPES` inalterados.
4. Com internet, num projeto real do OpenAlex em `~/Blicsa/projects/`: gere cocitação e citação
   direta e mostre (no relatório) 5 rótulos de nós e a contagem de nós/arestas.
5. `python scripts/medir_travadas.py` (no Mac rode sem xvfb) → nenhuma ação nova acima de 500 ms
   congelado; a resolução de rótulos não pode rodar na thread da interface.
6. `python scripts/smoke_app.py` passa.

## Ao terminar

- Acrescente "Parte 6 — camada 3 dos mapas" ao fim de `docs/AUDITORIA-2026-09.md` (não sobrescreva
  o que existe) e uma entrada no `CHANGELOG.md`.
- Faça commit local (mensagem em português), sem push e sem tag.
- Relatório final curto: o que mudou, contagem de testes antes/depois, resultado de cada critério,
  e o que não deu para fazer e por quê.
