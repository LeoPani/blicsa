# Relatório — i18n tela 2: Meus Projetos

**Data:** 2026-07-12 · **Escopo:** SOMENTE a aba "Meus Projetos" (`ui/projects_view.py`).
Nenhuma outra tela tocada. **PONTO DE PARADA atingido** — aguardando validação humana.

## Inventário migrado

Inventário completo em `docs/i18n-tela2-inventario.md`.

- **21 chaves novas** `projects.*` nos 3 catálogos. Catálogos: 76 → **97 chaves**
  (`en`/`pt_BR`); `fr` 97 + `_note`. Francês traduzido com cuidado (sem placeholder).
- Cobertura: título da aba, botão Atualizar, estado vazio, placeholders de thumbnail
  (MAPA/SEM MAPA), rótulos de data/documentos/fontes dos cards, 4 ações
  (Abrir/Renomear/Duplicar/Excluir), diálogo de renomear (prompt+título+erro), sufixo de
  duplicar, diálogo de exclusão (título+confirmação). Placeholders `{date}/{count}/{sources}/{name}/{n}`
  validados nos 3 idiomas.

## Arquivos tocados

| Arquivo | Mudança |
|---|---|
| `ui/projects_view.py` | +`from core.i18n import t`; 21 strings → `projects.*` (via `t()` com placeholders). |
| `locales/pt_BR.json`, `en.json`, `fr.json` | +21 chaves cada. |
| `docs/i18n-tela2-inventario.md`, `docs/RELATORIO-I18N-TELA2.md` | novos. |

Diff cirúrgico: só strings. Zero mudança de layout, cor, largura de widget ou token de design.
`main.py` **não foi tocado** (a aba não tem literais próprios lá).

## Troca ao vivo (passo 4)

`_refresh_language()` já reconstrói o layout inteiro; a `ProjectsView` lê `t()` na
construção, então ao trocar de idioma e reabrir a aba ela reflete o novo idioma sem
qualquer mudança na mecânica de refresh (mesmo padrão do piloto). **Ressalva importante
abaixo** (aba órfã).

## Gates

```
$ python scripts/check_i18n_parity.py   → All catalogs are in parity. (exit 0)
$ python -m pytest tests/ -q            → 68 passed, 18 deselected, 4 xfailed
```
(os 4 xfailed são os BUG-01/02/03 + OBS da suíte de busca, sem relação com esta tela.)
Resolução de chaves e placeholders confirmada em pt_BR/en/fr.

## Tabela de medição de fonte (passo 2) — botões de ação do card (largura fixa 60px)

Fonte real medida: `SF Display` size 13 (default CTk). Orçamento estimado ~46px
(60 − borda − folga interna). `!` = excede o orçamento estimado.

| chave | pt_BR | en | fr |
|---|---|---|---|
| action_open | Abrir = 37px | Open = 42px | **Ouvrir = 47px !** |
| action_rename | **Renomear = 78px !** | **Rename = 63px !** | **Renommer = 84px !** |
| action_duplicate | **Duplicar = 64px !** | **Duplicate = 73px !** | **Dupliquer = 74px !** |
| action_delete | **Excluir = 51px !** | **Delete = 50px !** | **Supprimer = 80px !** |

**Achado (para olho humano / fila de layout, NÃO corrigido aqui):** os botões de ação
`width=60` são **estreitos demais para os rótulos em todos os idiomas — inclusive no
pt_BR original** ("Renomear"=78px, "Duplicar"=64px, "Excluir"=51px já estouravam antes do
i18n). Portanto **não é regressão** desta tela; é aperto pré-existente do design dos cards.
O francês agrava ("Supprimer"=80px, "Renommer"=84px). Recomenda-se, num prompt futuro de
layout (fora do escopo i18n), largura automática ou ≥90px nesses botões. Título
("Mes projets"=148px @20bold) é label auto-width, sem risco.

## Capturas de tela (passo 5) — PENDENTES, por DOIS motivos

> **NENHUM mock gerado.** As capturas `i18n_projetos_{pt_BR,en,fr}.png` não foram
> produzidas porque:
>
> 1. **Permissão de Gravação de Tela ainda ausente:** `screencapture -x` falha com
>    `could not create image from display` (exit 1). Conceder: Ajustes do Sistema →
>    Privacidade e Segurança → **Gravação de Tela** → habilitar **Terminal** → reabrir.
> 2. **A aba está órfã na navegação:** `ProjectsView`/`_build_tab_projects` (`main.py:770`)
>    **não** está registrada em `self._tabs` (`main.py:174-183`) nem tem botão de nav
>    (`main.py:207-214`), e não há `_switch_tab("projects")` em lugar nenhum. Ou seja, a
>    tela **não é alcançável no app atual** — mesmo com permissão, não há como abri-la para
>    capturar. Ligar a aba à navegação é uma mudança de `main.py` **fora do escopo** deste
>    prompt de i18n; fica registrado para um prompt futuro.

## PONTO DE PARADA — Roteiro de validação humana

Pré-requisito para executar: (a) conceder Gravação de Tela; (b) tornar a aba "Meus
Projetos" alcançável (wire em `main.py`) — hoje ela está órfã.

Com isso feito, e com ao menos 1 projeto salvo:
1. **pt_BR:** abrir a aba — título "Meus Projetos", card com "Atualizado em…", "N documentos",
   ações Abrir/Renomear/Duplicar/Excluir, estado vazio quando não há projetos.
2. **Trocar para `en`:** aba reconstrói em inglês; conferir cards e botões.
3. **Trocar para `fr`:** idem — **conferir os botões de ação estreitos** (ver tabela:
   "Supprimer"/"Renommer"/"Dupliquer" podem cortar em 60px) e o título.
4. **Abrir cada diálogo nos 3 idiomas:** Renomear (prompt + título + erro "nome já existe"),
   Duplicar (sufixo "(Cópia)"/"(Copy)"/"(Copie)"), Excluir (confirmação com nome do projeto).

**Pendências de validação humana:** integridade visual dos cards/diálogos nos 3 idiomas
(headless + sem permissão de captura) e confirmação do truncamento dos botões de ação.

## Commit

`i18n: tela Meus Projetos` (único).
