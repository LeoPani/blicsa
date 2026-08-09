# Inventário: onde a IA aparece na interface

**Princípio:** o usuário precisa distinguir **sempre** o que é dado do que é máquina. O amarelo
do design system (`YELLOW = #F5BE00`) passa a significar **exatamente uma coisa** — "isto foi
gerado por IA" — e não é usado para mais nada.

**A cor nunca vem sozinha.** Todo ponto marcado carrega também o rótulo textual `t("ai.badge")`
("IA" / "AI" / "IA"). Regra inegociável: usuários com daltonismo e qualquer impressão em preto
e branco perdem a cor, e a informação não pode se perder junto. Um export em PDF monocromático
sem o rótulo textual seria indistinguível de dado apurado.

---

## Convenção visual adotada

**Faixa vertical amarela de 6 px na borda esquerda do bloco + selo textual "IA" no topo.**

Escolhida a borda esquerda, e não o plano de fundo, por três razões:

1. o fundo amarelo sob texto longo prejudica a leitura (o contraste de `#141414` sobre
   `#F5BE00` é bom para selo curto, cansativo para parágrafo);
2. a faixa lateral sobrevive a export monocromático como uma barra cinza visível, mantendo a
   distinção visual mesmo sem cor;
3. mantém o vocabulário neoplasticista do app — plano chapado, canto zero, sem gradiente.

O selo é `#F5BE00` chapado com texto `#141414`, canto zero, sem borda.

### Contraste medido

| combinação | razão | uso |
|---|---|---|
| `#141414` sobre `#F5BE00` | **10,7:1** | selo "IA" — passa WCAG AAA (mínimo 7:1) |
| `#141414` sobre `#FFFFFF` | 17,4:1 | corpo do texto de IA, sobre o card branco |

O texto do conteúdo gerado **não** fica sobre o amarelo: só o selo fica.

---

## Pontos marcados

| # | onde | função que gera | renderiza em | marcação |
|---|---|---|---|---|
| 1 | Respostas do Blink no chat | `AIAnalyst.chat_history_stream` | `_add_blink_message` | faixa + selo |
| 2 | Análise do corpus | `_trigger_corpus_ai_insights` (streaming) | `_add_blink_message` | faixa + selo |
| 3 | Rótulos de cluster | `label_clusters` | Treeview de clusters | selo textual `[IA]` na célula |
| 4 | Análise de obras seminais | `generate_seminal_insights` | `_show_seminal_insights`, pelo botão `_trigger_seminal_insights` | prefixo `[IA]` |
| 5 | Análise temática (quadrantes) | `generate_thematic_insights` | `_show_insights` | faixa + selo |
| 6 | Análise do Sankey | `generate_sankey_insights` | `_show_insights` | faixa + selo |
| 7 | Historiografia | `generate_historiograph_insights` | `_show_insights` | faixa + selo |
| 8 | Assistente de importação | `_trigger_import_ai_assistant` | `_add_blink_message` | faixa + selo |

### A coluna "renderiza em" existe por causa de um erro que esta tabela escondeu

Na primeira redação, a tabela dizia "faixa + selo" para os pontos 5, 6 e 7 — e **não havia
marcação nenhuma** na tela. Os três renderizam em `_show_insights`, um diálogo próprio que
nunca passa pelo funil `_add_blink_message`. O erro sobreviveu porque a existência do funil
sugeria que tudo passava por ele.

Foi encontrado ao preparar a captura `ia_marcacao_insights`: não havia o que fotografar.
`tests/test_ai_marking.py::test_todo_renderizador_de_ia_do_main_esta_marcado` agora varre os
workers de IA e falha se algum entregar o resultado a um renderizador não declarado aqui.

### Os dois pontos sem chamador foram resolvidos em 09/08/2026

A tabela declarava dois pontos que **nenhum botão disparava**. Código de IA testado e
inalcançável em repositório público é pergunta de revisor, e o levantamento está em
`docs/CODIGO-SEM-CHAMADOR.md`:

- **Obras seminais** (ponto 4) foi **ligada**: a aba, o destino e o renderizador com
  marcação já existiam — faltava o fio. O botão que dispara é amarelo, como os outros
  disparadores de IA, e está declarado em `BOTOES_IA`.
- **`generate_insights`** foi **removida**: era superada por `_trigger_corpus_ai_insights`
  (ponto 2), que faz o mesmo trabalho, responde em streaming e **tem** botão. Duas rotas para
  a mesma análise, uma delas morta, é o que se queria evitar.

## Rótulos de cluster: IA vs. humano

Rótulo gerado por `label_clusters` é marcado. **Rótulo editado à mão pelo usuário deixa de ser
amarelo** — passa a ser dado do usuário, não saída de máquina. O estado é guardado por cluster
no projeto, e a marcação segue esse estado, não a origem histórica.

---

## Onde o amarelo **deixou** de ser usado

Estes pontos usavam `YELLOW` para outra finalidade e foram trocados. Manter qualquer um deles
diluiria o sinal: se o amarelo às vezes quer dizer "IA" e às vezes "atenção" ou "citações", ele
não quer dizer nada.

| onde | significava | trocado por | por quê |
|---|---|---|---|
| Badge de citações no card de resultado | contagem de citações | `INK` sobre `PAPER` | é **dado** da base, o oposto de conteúdo gerado |
| Badge "baixa confiança" da deduplicação | qualidade da heurística | `RED` | é aviso sobre **dado**, e o vermelho já é o token de atenção do app |
| Barra de progresso da barra lateral | progresso de tarefa | `BLUE` | estado da aplicação, não conteúdo |
| `CLUSTER_PALETTE[2]` (cor de nós do mapa) | cluster nº 3 | `#C97B2D` (âmbar) | nós do mapa são **dado**; um cluster amarelo seria lido como "cluster gerado por IA" |
| Botão “☁ Word Cloud” | ação de visualização | `BLUE` | a nuvem sai dos termos do corpus — é **dado**, não texto gerado |

### O que continua amarelo, e por quê

Os **botões que disparam a IA** (`✨ Blink`, `Análise IA do Corpus`) continuam amarelos. Eles
não são conteúdo gerado — são a porta de entrada da IA, e o amarelo ali reforça a mesma
associação: amarelo = máquina. É a única exceção, e é coerente com a regra em vez de furá-la.

---

## Exports carregam a marcação em **texto**

Cor se perde: em PDF monocromático, em impressão, em quem copia e cola para o Word. Por isso o
export não depende dela.

- **Markdown / PDF**: cada seção gerada por IA recebe o prefixo `[IA]` no título, e o arquivo
  termina com uma nota de rodapé explicando o que o marcador significa.
- **Imagem do mapa**: quando os rótulos de cluster vêm da IA, a legenda traz a indicação.

Isso é honestidade científica, não decoração: quem lê um relatório exportado precisa saber
quais frases foram escritas por um modelo de linguagem antes de citá-las.

---

## Teste de conformidade

`tests/test_ai_marking.py::test_amarelo_nao_e_usado_fora_do_inventario` varre o código e falha
se `YELLOW` aparecer fora dos pontos declarados aqui. O inventário e o código não podem
divergir sem alguém perceber.
