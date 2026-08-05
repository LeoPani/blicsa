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

| # | onde | função que gera | marcação |
|---|---|---|---|
| 1 | Respostas do Blink no chat | `AIAnalyst.chat_history_stream` | faixa + selo |
| 2 | Insights bibliométricos do corpus | `generate_insights` | faixa + selo |
| 3 | Rótulos de cluster | `label_clusters` | selo na legenda e no painel de clusters |
| 4 | Análise de obras seminais | `generate_seminal_insights` | faixa + selo |
| 5 | Análise temática (quadrantes) | `generate_thematic_insights` | faixa + selo |
| 6 | Análise do Sankey | `generate_sankey_insights` | faixa + selo |
| 7 | Historiografia | `generate_historiograph_insights` | faixa + selo |
| 8 | Assistente de importação | `_trigger_import_ai_assistant` | faixa + selo |

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
