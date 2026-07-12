# Inventário i18n — piloto (Ajustes + chat do Blink)

Strings literais visíveis das DUAS telas do piloto. Levantado por grep em
`main.py` (`text=`, `placeholder_text=`, `insert(`, `.title(`) + leitura do bloco.
Escopo rígido: nada fora de Ajustes/Settings e do chat do Blink Research.

## Tela de Ajustes/Settings (`_show_settings`, `main.py`)

| Linha | String literal | Estado | Chave |
|---|---|---|---|
| 336 | `dlg.title(t("menu_settings"))` | já externalizada | `menu_settings` (existente) |
| 348 | `text=t("menu_settings")` (título) | já externalizada | `menu_settings` (existente) |
| 368 | `text=t("reduce_animations")` | já externalizada | `reduce_animations` (existente) |
| 389 | `text="OK"` (botão fechar) | **literal → migrar** | `settings.ok` (nova) |

> As bandeiras (linhas 381-385) são imagens sem texto. O restante da tela já
> usava `t()` com chaves próprias — só o botão "OK" estava fixo.

## Chat do Blink Research (`_build_..._home` / research chat, `main.py`)

Situação encontrada: as strings já estavam embrulhadas em `t(...)`, porém usando
**o texto em português como chave** (anti-padrão) — como essas "chaves" não existem
em nenhum catálogo, `t()` caía no fallback e devolvia a própria string PT, ou seja o
Blink aparecia sempre em português. O piloto troca por chaves `blink.*` de verdade.

| Linha | String literal (PT) | Chave nova |
|---|---|---|
| 627 | `"O que vamos "` (título, parte 1) | `blink.titulo_1` |
| 628 | `"pesquisar"` (título, destaque em vermelho) | `blink.titulo_destaque` |
| 629 | `" hoje?"` (título, parte 2) | `blink.titulo_2` |
| 635 | `"⬅ Voltar"` (botão voltar) | `blink.voltar` |
| 641, 659 | `"Você é o 'Blink', um assistente de IA..."` (system prompt) | `blink.system_prompt` |
| 644 | `"**Blink:** fala mano, bora pesquisar?"` (saudação inicial) | `blink.saudacao` |
| 649 | `"Digite sua pergunta..."` (placeholder do input) | `blink.placeholder` |
| 683 | `"Contexto relevante do corpus:"` (rótulo do contexto RAG) | `blink.rag_contexto` |
| 737 | `"Erro:"` (mensagem de erro do chat) | `blink.erro` |
| 742 | `"Enviar"` (botão enviar) | `blink.enviar` |
| 749 | `"Quais as tendências mais recentes?"` (sugestão 1) | `blink.sugestao_1` |
| 750 | `"Como faço análise de rede de citações?"` (sugestão 2) | `blink.sugestao_2` |
| 751 | `"O que é um cluster bibliométrico?"` (sugestão 3) | `blink.sugestao_3` |

## Fora de escopo (NÃO tocar, registrado por clareza)

- `"⬅ Voltar"` aparece só no cabeçalho do Blink → **está** no escopo (acima).
- Linhas 1900, 2612, 2720, 2900 usam `"Erro:"`/`f"Erro: {e}"` em fluxos de IA de
  OUTRAS telas (revisão de busca, análise temática, mapa) — **fora do escopo**, ficam.
- Prompts fixos "em português" em `ai/client.py` (linhas 175, 197, 222, 237, 251, 265)
  pertencem a Análises/Mapa (outras telas) → **não migrados** neste piloto.
- Placeholders da tela de busca/config (linhas 788+, 816-820, 1210+) → outras telas.

## Contagem

- Chaves novas a criar: **14** (`settings.ok` + 13 `blink.*`).
- Chaves reaproveitadas (já existiam): `menu_settings`, `reduce_animations`.
