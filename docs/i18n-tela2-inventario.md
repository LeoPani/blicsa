# Inventário i18n — tela 2: Meus Projetos

Strings literais visíveis da aba "Meus Projetos". Fonte: `ui/projects_view.py`
(a tela inteira vive nesse arquivo; `main.py` só a instancia em `_build_tab_projects`,
sem literais próprios). Grep por `text=`, `title=`, `messagebox`, `CTkInputDialog`.

## `ui/projects_view.py`

### `ProjectCard`
| Linha | String literal | Chave |
|---|---|---|
| 65 | `"MAPA"` (fallback quando thumbnail falha ao carregar) | `projects.card_map` |
| 67 | `"SEM MAPA"` (placeholder sem thumbnail) | `projects.card_no_map` |
| 71 | `"Desconhecido"` (data ausente no manifest) | `projects.date_unknown` |
| 74 | `f"Atualizado em {date}"` | `projects.card_updated` `{date}` |
| 76 | `f"{df_count} documentos"` | `projects.card_documents` `{count}` |
| 79 | `f" \| Fontes: {sources}"` | `projects.card_sources` `{sources}` |
| 87 | `"Abrir"` | `projects.action_open` |
| 88 | `"Renomear"` | `projects.action_rename` |
| 89 | `"Duplicar"` | `projects.action_duplicate` |
| 90 | `"Excluir"` | `projects.action_delete` |

### `ProjectsView`
| Linha | String literal | Chave |
|---|---|---|
| 106 | `"Meus Projetos"` (título da aba) | `projects.title` |
| 107 | `"Atualizar"` (botão) | `projects.refresh` |
| 130 | `"Nenhum projeto encontrado. Realize uma busca..."` (estado vazio) | `projects.empty` |
| 139 | `"Novo nome do projeto:"` (prompt renomear) | `projects.rename_prompt` |
| 139 | `"Renomear Projeto"` (título do diálogo) | `projects.rename_title` |
| 144 | `"Erro"` (título do erro) | `projects.error_title` |
| 144 | `"Já existe um projeto com este nome."` | `projects.rename_exists` |
| 151 | `"(Cópia)"` (sufixo de duplicar) | `projects.copy_suffix` |
| 155 | `"(Cópia {counter})"` | `projects.copy_suffix_n` `{n}` |
| 163 | `"Confirmar Exclusão"` (título) | `projects.delete_title` |
| 163 | `"Tem certeza que deseja excluir o projeto '{name}'?"` | `projects.delete_confirm` `{name}` |

## Contagem
- **21 chaves novas** `projects.*`.

## Observação relevante (não é bug a corrigir aqui — registrado)
A aba `projects`/`ProjectsView` **não está registrada** em `self._tabs` (`main.py:174-183`)
nem existe botão de navegação para ela (loop de nav em `main.py:207-214` não a inclui),
e não há nenhum `_switch_tab("projects")` no código. Ou seja, `_build_tab_projects`
(`main.py:770`) está **órfão** — a tela não é alcançável na navegação atual do app.
Isso não impede a externalização das strings, mas **impede a captura de tela e a
validação humana "abrir a aba"** até que a tela seja ligada à navegação (fora do escopo
deste prompt de i18n). Ver relatório.
