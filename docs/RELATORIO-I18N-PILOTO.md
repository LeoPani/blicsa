# Relatório — i18n piloto: Ajustes + chat do Blink

**Data:** 2026-07-12 · **Escopo:** SOMENTE tela de Ajustes/Settings e chat do Blink Research.
Nenhuma outra tela foi tocada. **PONTO DE PARADA atingido** (fim do passo 5) —
aguardando validação humana antes de qualquer próxima tela.

## Inventário migrado

Inventário completo em `docs/i18n-piloto-inventario.md`.

- **14 chaves novas** criadas nos 3 catálogos (`pt_BR`, `en`, `fr`):
  - `settings.ok` (1)
  - `blink.titulo_1`, `blink.titulo_destaque`, `blink.titulo_2`, `blink.voltar`,
    `blink.system_prompt`, `blink.saudacao`, `blink.placeholder`, `blink.rag_contexto`,
    `blink.erro`, `blink.enviar`, `blink.sugestao_1`, `blink.sugestao_2`, `blink.sugestao_3` (13)
- Catálogos: 62 → **76 chaves** em `en`/`pt_BR`; `fr` 76 + `_note`.
- Achado: as strings do Blink já estavam em `t(...)`, mas usando **o texto PT como chave**
  (não existia em catálogo nenhum → caía no fallback e sempre aparecia em PT). Trocadas
  por chaves `blink.*` reais, agora traduzidas de fato para en e fr.

## Arquivos tocados

| Arquivo | Mudança |
|---|---|
| `main.py` | Ajustes: botão `OK`→`t("settings.ok")`. Blink: 13 strings→`blink.*`; novo método `_blink_system_prompt()` (system prompt + diretiva de idioma via `get_lang()`). |
| `core/i18n.py` | Adicionado `get_lang()` público. |
| `locales/pt_BR.json`, `en.json`, `fr.json` | +14 chaves cada (fr traduzido com cuidado, sem placeholder). |
| `locales/de.json` | **Removido** pelo próprio `check_i18n_parity.py` (catálogo incompleto que quebrava paridade — comportamento existente da ferramenta, não escolha do piloto). |
| `docs/i18n-piloto-inventario.md`, `docs/RELATORIO-I18N-PILOTO.md` | novos. |

Diff de produção mínimo e cirúrgico (só linhas de string + o helper). Zero mudança de
layout, cor, `corner_radius` ou qualquer token de design.

## Decisões de escopo

- **Idioma dinâmico do Blink sem tocar outras telas:** o passo 4 sugeria alterar os
  prompts de `ai/client.py`. Porém `chat_history_stream` é compartilhado por **5** chamadas
  (o Blink + 4 fluxos de IA de outras telas: revisão de busca, tema, mapa…), e os prompts
  `generate_*`/`label_clusters` com "em português" fixo servem **Análises/Mapa** — telas
  fora do piloto. Alterá-los violaria "PROIBIDO tocar outras telas". Solução: a diretiva de
  idioma é montada **no system prompt do Blink em `main.py`** (`_blink_system_prompt()`),
  usando `get_lang()` → `"Always respond … in {Brazilian Portuguese|English|French}"`.
  `ai/client.py` ficou **intocado**. Blink responde no idioma da UI; as outras telas seguem
  exatamente como antes.
- **Troca ao vivo (passo 5):** `_refresh_language()` já reconstrói o layout inteiro. As duas
  telas do piloto passam a refletir o novo idioma (chaves novas); as demais reconstroem mas
  **mostram o mesmo texto** porque suas strings continuam literais (não migradas). Ou seja,
  o resultado visível exigido — só as duas telas mudam de idioma — já é obtido sem alterar a
  mecânica de refresh (mudança de menor risco). Nenhum aviso novo foi adicionado.

## Saída dos gates

```
$ python scripts/check_i18n_parity.py
Removed de.json as it was incomplete and breaking parity.
All catalogs are in parity.
exit=0

$ python -m pytest tests/ -q
62 passed, 18 deselected, 4 xfailed in 4.73s
```
(os 4 xfailed são os BUG-01/02/03 + OBS já documentados na suíte de busca, sem relação
com o piloto; 18 deselected são os testes `live`.)

Resolução das chaves confirmada nos 3 idiomas (`blink.saudacao`, `blink.enviar`,
`settings.ok`) e `get_lang()` retornando `pt_BR`/`en`/`fr` corretamente.

---

## PONTO DE PARADA — Roteiro de validação humana (Leonardo executa)

Rodar `python3 main.py` e verificar:

1. **Abrir em pt_BR:** tela de Ajustes e chat do Blink íntegros — nada truncado, nada em
   inglês sobrando. Saudação "**Blink:** fala mano, bora pesquisar?", botão "Enviar",
   placeholder "Digite sua pergunta...", 3 sugestões em PT, título "O que vamos **pesquisar** hoje?".
2. **Trocar para `en`** (bandeira nos Ajustes ou no topo do Blink): as duas telas atualizam
   ao vivo, layout íntegro. Saudação/placeholder/botão/sugestões/título em inglês.
   Botão OK dos Ajustes = "OK".
3. **Trocar para `fr`:** idem. **Atenção especial** (francês ~20% mais longo):
   - botão "Envoyer" (vs "Enviar"/"Send") no botão de largura fixa 100px — conferir que não corta;
   - título "Qu'allons-nous **rechercher** aujourd'hui ?" — conferir quebra/entrelinha;
   - sugestões longas ("Comment réaliser une analyse de réseau de citations ?") nos botões — conferir truncamento.
4. **Perguntar algo ao Blink em cada idioma:** a resposta deve vir **no idioma da UI**
   (diretiva dinâmica via `get_lang()`), não fixo em português. Requer API key configurada
   nos Ajustes.

**Pendências de validação humana (não verificáveis neste ambiente headless):**
- Integridade visual/layout das duas telas em pt_BR/en/fr (não há como renderizar a UI
  CustomTkinter aqui) — **especialmente o francês mais longo** nos botões de largura fixa.
- Resposta do Blink efetivamente no idioma da UI depende de API key + chamada real ao LLM.

**Só o humano decide se o piloto passou.** Se passar, próximas telas em prompts separados,
um por tela, na ordem: Meus Projetos → revisão de busca → Exportar → Análises → Home/navegação.

## Commit

`i18n-piloto: ajustes + blink` (único).
