# Relatório — IA & UX: chave, amarelo e contexto de pesquisa

Fecha o prompt de três fases sobre a camada de IA do Blicsa. As fases 1 (onboarding da chave)
e 2 (amarelo como marcador) foram entregues nos commits `9ed02bf`, `748bc91` e `ad5a858`.
Este relatório cobre a **Fase 3**, as três capturas que faltavam e o que apareceu no caminho.

O caminho, aliás, é a parte mais importante deste documento. Gerar as capturas com chamada
real ao modelo — em vez de aceitar a marcação como verificada por teste — desenterrou **seis
defeitos**, dois deles capazes de tornar a IA inutilizável para quem instalasse o app hoje.
A seção "O que a captura encontrou" existe por isso.

---

## Fase 3 — contexto de pesquisa por projeto

### O problema

O corpus diz **o que** foi publicado. Não diz que a pessoa estuda cooperativas de catadores no
Sul do Brasil, que "informalidade" no vocabulário dela é categoria da sociologia do trabalho e
não do direito tributário, nem que a revisão é para o capítulo 2 de uma tese. Sem isso, a IA
responde sobre o corpus certo com o enquadramento errado — e o pesquisador precisa corrigir o
enquadramento em toda pergunta, o que é pior do que não ter assistente.

### A ordem é a decisão

```
papel → idioma → contexto do usuário → dados do corpus → (pergunta, no turno do usuário)
```

O contexto do usuário vem **antes** dos dados, não depois. Posto depois, lê como observação
final sobre um material já apresentado; posto antes, é a lente pela qual o material é lido. É
a diferença entre "resuma estes abstracts — ah, e eu sou socióloga" e "você está ajudando uma
socióloga; aqui estão os abstracts".

A pergunta não entra no `system`: ela é a mensagem `user`. Misturá-la apagaria a distinção
entre instrução permanente e turno de conversa — e ela viraria instrução para todos os turnos
seguintes.

Tudo isso mora em `core/research_context.py`, **sem Tk**, para ser testável sem abrir janela.

### O corte de orçamento

Orçamento estourado corta **abstracts**. Nunca o contexto do usuário. O raciocínio é de custo
de erro:

- abstract cortado tira uma evidência de um conjunto que tem outras;
- contexto cortado faz a resposta inteira sair enquadrada errada, e o usuário não tem como
  saber por quê — ele digitou o contexto e está vendo o indicador aceso.

Ordem de sacrifício, afirmada em teste: **corpus inteiro → contexto → nada**. Papel e diretiva
de idioma não cedem nunca. Sem papel o assistente deixa de ser o Blink; sem a diretiva ele
responde no idioma do prompt em vez do idioma da interface — bug imediato para quem usa em
francês.

Dois refinamentos que só aparecem em fixture adversarial:

| situação | comportamento | por quê |
|---|---|---|
| corte cai no meio de um registro | recua até a fronteira anterior | meio abstract não é meia evidência: é uma frase solta que o modelo cita como se fosse o achado do artigo |
| sobra espaço só para o título | descarta o bloco inteiro (`MINIMO_CORPUS`) | título sem abstract entra na resposta como se fosse resultado apurado |

O `system_prompt[:4000]` que existia no `main.py` saiu. Ele cortava o **fim** do prompt, e o
fim era o lugar dos abstracts por acidente de montagem — não por decisão. O orçamento continua
4000 caracteres de propósito: a mudança desta fase é **como** se corta, não **quanto**.

### Persistência

`config["research_context"]` dentro do `.blicsa`. Vive no config, e não num arquivo próprio do
ZIP, porque é parâmetro do projeto como o campo de análise e a resolução do cluster — e porque
acrescentar chave a um dicionário livre não muda a versão do manifesto. A retrocompatibilidade
sai de graça **nos dois sentidos**: um `.blicsa` novo abre numa versão antiga do app (que
ignora a chave) e um `.blicsa` antigo abre aqui (chave ausente = sem contexto).

`research_context_do_config` tolera chave ausente, `None`, número e dicionário. Um campo de
texto opcional nunca pode impedir um projeto de abrir — seria perder dataset, mapa e
parâmetros pelo mesmo modo de falha que o `_id_cluster` já corrigiu para os rótulos.

### O campo e o indicador

**O exemplo é placeholder, não valor inicial.** Um exemplo pré-preenchido de verdade seria
enviado ao modelo por quem não reparasse nele, e o Blink passaria a responder sobre
cooperativas de catadores para alguém que estuda semicondutores. `valor()` devolve string
vazia enquanto o exemplo estiver na tela, e é o invariante que o teste guarda.

**O exemplo é concreto.** "Descreva sua pesquisa" não ensina nada; um exemplo que mostra um
termo sendo desambiguado ensina o que vale a pena escrever ali.

**O indicador é azul, nunca amarelo.** O amarelo significa "gerado por IA"
(`docs/inventario-ia.md`) e este campo é o oposto: é o que a **pessoa** escreveu. Marcá-lo de
amarelo diria a ela que uma máquina redigiu o enquadramento da própria pesquisa dela. É a
regra da Fase 2 aplicada no sentido menos óbvio — e o teste
`test_indicador_nao_e_amarelo` a guarda.

### As análises das outras telas

O contexto fica no **analista**, não em cada método:

```python
AIAnalyst(..., contexto_pesquisa=self._contexto_pesquisa())
```

A alternativa era um parâmetro novo em `generate_insights`, `generate_sankey_insights`,
`generate_thematic_insights`, `generate_historiograph_insights`, `generate_seminal_insights` e
`label_clusters` — seis lugares para esquecer um, e a próxima análise nasceria sem contexto.
Todas passam por `_chat`, e `test_nenhuma_analise_escapa_do_ponto_unico` falha se alguma
chamar `call_openai_chat` direto.

---

## Medição dos dois eixos

Widgets reais, `winfo_reqwidth`/`winfo_reqheight`, nos três idiomas, com o indicador aceso.

| idioma | rótulo | indicador | contador | soma | disponível | folga |
|---|---:|---:|---:|---:|---:|---:|
| pt_BR | 141 | 115 | 1 | 265 | 860 | **595** |
| en | 114 | 88 | 1 | 211 | 860 | **649** |
| fr | 148 | 111 | 1 | 268 | 860 | **592** |

Folga mínima **592px** (fr, o idioma mais largo do projeto). Zero estouros.

**Eixo vertical e origem:**

| | pt_BR | en | fr |
|---|---:|---:|---:|
| altura do campo | 66 | 66 | 66 |
| altura da ajuda | 28 | 28 | 28 |
| altura total da barra | 130 | 130 | 130 |
| x do campo · x do cabeçalho | 0 · 0 | 0 · 0 | 0 · 0 |
| **variação de origem** | **0px** | **0px** | **0px** |

A ajuda cabe em uma linha nos três idiomas (28px); o teto do teste é 60px (duas linhas).

## Paridade i18n com a fonte real do widget

`_chaves_i18n()` extrai por AST **toda** chave passada a `t(...)` em
`ui/research_context_bar.py` e confere as três nos catálogos. Lista fixa de chaves envelhece
em silêncio: quem acrescenta um `t("ai.novo")` não lembra de acrescentá-lo ao teste, e a chave
só falta na tela do usuário francês.

Há um guarda do guarda — `test_a_fonte_do_widget_realmente_usa_i18n` — porque se o widget
passar a usar literais, o extrator devolveria vazio e a paridade passaria a verde sem
verificar nada.

A diretiva de idioma saiu do `main.py` para `core.research_context.diretiva_idioma()`. Enquanto
era um trecho solto dentro de um método da janela, `tests/test_blink_i18n.py` **replicava a
lógica à mão** e passaria a verde mesmo se o `main.py` divergisse.

Cinco chaves novas nos três catálogos, com `test_textos_da_barra_sao_traduzidos_de_fato`
provando que não são cópia: `ai.contexto_titulo`, `ai.contexto_placeholder`,
`ai.contexto_ativo`, `ai.contexto_ajuda`, `ai.contexto_prompt`.

---

## O que a captura encontrou

Esta seção é o resultado de exigir chamada real ao modelo. Nenhum destes defeitos aparecia na
suíte, e quatro deles são visíveis para qualquer usuário.

### 1. `.env` do repositório sobrescrevia a chave do ambiente — **corrigido**

`main.py` carregava o `.env` com `os.environ[k] = v`. Uma chave revogada no arquivo vencia a
chave válida exportada no shell. A IA devolvia 401, o app dizia "falha na requisição de IA", e
nada na tela ligava o erro a um arquivo que o usuário não lembrava que existia.

Agora é `os.environ.setdefault(...)` — o ambiente real vence o arquivo, que é a semântica que
dotenv, docker compose e 12-factor usam. Foi o que travou a primeira tentativa de captura.

### 2. O teste de conexão reprovava chave válida — **corrigido**

`ai/onboarding.py::testar_chave` não mandava `User-Agent`. O Cloudflare do Groq responde `403`
(`error code: 1010`) a cliente sem User-Agent reconhecível, **antes de olhar a chave**, e o
diagnóstico classificava 403 como `invalida`.

O efeito era o pior possível para essa tela: quem colasse uma chave **correta** lia *"Chave
recusada pelo Groq. Confira se copiou a chave inteira, sem espaços, e se ela ainda está
ativa."* A IA funcionava normalmente depois, porque `ai/client.py` sempre mandou o cabeçalho —
só a tela que existe para configurar a chave a reprovava.

Verificado na chave real: `403 invalida` antes, `ok llama-3.3-70b-versatile` depois. O
`USER_AGENT` agora é constante única em `ai/client.py`, com teste que falha se os dois pontos
divergirem.

Isto é uma correção da **Fase 1**, encontrada na Fase 3. A fase 1 tinha dez casos de reinjeção
e todos passavam: eles testavam a classificação dos códigos HTTP, e nenhum testava se a
requisição chegava ao provedor.

### 3. O inventário declarava marcação que não existia — **corrigido**

`docs/inventario-ia.md` listava Sankey, mapa temático e historiografia como "faixa + selo".
Os três renderizam em `_show_insights`, um diálogo que **nunca** passa pelo funil
`_add_blink_message` — e não tinha marcação nenhuma. Descoberto porque não havia o que
fotografar para `ia_marcacao_insights`.

O erro sobreviveu à Fase 2 porque a existência do funil sugeria que tudo passava por ele. O
inventário ganhou a coluna "renderiza em" para que a próxima divergência seja visível na
tabela, e `test_todo_renderizador_de_ia_do_main_esta_marcado` varre os workers de IA e falha
se algum entregar resultado a renderizador não declarado.

Corrigido também `_show_seminal_insights` (marcação textual `[IA]`, porque o destino é um
textbox já montado no grid da aba).

### 4. `_switch_tab("viz")` deixava a tela em branco — **corrigido**

`"viz"` nunca foi chave de aba. `_switch_tab` esconde **todas** as abas e só então tenta
mostrar a pedida: chave inexistente = tela vazia, sem exceção e sem log. Havia duas chamadas
assim, depois de **carregar um arquivo** e depois de **abrir um projeto** — os dois momentos
em que o usuário acabou de fazer a coisa mais importante da sessão.

`tests/test_navegacao_abas.py` compara, por AST, as chaves pedidas com as registradas.

### 5. O bloco de corpus ia ao modelo com barra escapada — **corrigido**

`main.py` montava o contexto RAG com `"\\n\\n---\\n".join(...)` — barra invertida escapada
duas vezes. O modelo recebia a sequência literal de dois caracteres `\n` no meio do texto, em
vez de quebras de linha, e não havia fronteira nenhuma onde cortar. Invisível na tela;
aparecia só no que chegava ao modelo.

### 6. Análises reaproveitavam um system prompt congelado — **corrigido**

Três telas montavam o prompt a partir de `self._research_messages[0]["content"]`, valor
congelado quando a tela do Blink foi construída. Um contexto escrito depois disso nunca
chegaria ao modelo — com o indicador aceso afirmando o contrário.

---

## Defeitos encontrados e **não** corrigidos

### A bolha da pergunta do usuário renderiza vazia

No fluxo real do chat, a pergunta digitada aparece como um retângulo azul **sem texto**.
Reproduzível: duas capturas independentes, zero pixels de texto na região da bolha. Visível na
evidência `ia_marcacao_chat.png`.

O que se sabe: o widget tem o conteúdo correto (`tb.get()` devolve a pergunta), tamanho
correto (550×64, duas linhas de display), `yview` inteira visível, e cores corretas (`#FFFFFF`
sobre `#1E4DA0`). Chamado fora do fluxo de streaming, o mesmo `_add_blink_message("user", …)`
renderiza normalmente — confirmado por captura. Rolar o canvas também não reproduz.

Não corrigido porque é um problema de repintura do Tk no macOS cuja causa não foi isolada, e
sair mexendo em `_add_blink_message` — o funil de marcação de sete pontos de IA — sem entender
a causa arrisca a convenção inteira por um defeito cosmético. É o próximo item, com escopo
próprio.

### As análises respondem sempre em português

Os prompts de `generate_insights` e das quatro `generate_*_insights` pedem *"linguagem técnica
acadêmica em português"* em texto fixo. Um usuário com a interface em inglês ou francês recebe
o mapa temático e o Sankey em português. É anterior a esta fase e independente dela;
`_system_com_contexto` deliberadamente **não** injeta diretiva de idioma para não mascarar a
lacuna com uma correção pela metade.

### Dois pontos do inventário não estão ligados a tela nenhuma

`generate_insights` e `generate_seminal_insights` existem em `ai/client.py` e nenhum botão os
dispara. O renderizador do segundo já marca, para que a marcação não seja o que falta no dia
em que for ligado. Registrado na tabela do inventário em vez de silenciosamente removido:
função de IA sem chamador é decisão de produto pendente, não código morto a varrer.

---

## Reinjeção

`scripts/reinject_ia_ux.py` — **38 defeitos, todos detectados**. Os 16 das fases 1–2 continuam
lá; 22 são novos.

**Quatro furos reais** apareceram e obrigaram a reescrever os *testes*, não a matriz. Cada um
era um teste verde que não protegia nada:

1. **`corte parte um registro ao meio`** — o teste conferia que cada pedaço "começa com
   `Title:` e contém `Abstract:`", e um registro cortado no meio da última frase satisfaz as
   duas condições. Reescrito para afirmar **igualdade com o prefixo da origem**: o que sobra
   tem de ser exatamente `bloco_corpus(registros[:k])`.

2. **`toco de abstract entra no lugar de descartar o bloco`** — a fixture tinha orçamento tão
   apertado que nem o título cabia, o bloco caía por outro caminho e a guarda `MINIMO_CORPUS`
   nunca era exercitada. Fixture nova, com orçamento calibrado para caber o título e **não** o
   abstract.

3. e 4. **`diálogo de insights … sem marcação`** e **`análise seminal perde a marcação`** — os
   dois testes procuravam o nome da função (`AIContentFrame`, `marcar_texto_export`) como
   string no corpo do método. A linha de `import` contém o nome, então remover a **chamada**
   deixava o teste verde. Reescritos para localizar o `ast.Call` de fato.

O padrão dos quatro é o mesmo e vale registrar: **asserção sobre a forma do texto passa; só
asserção sobre o efeito protege.** Três deles eram testes que eu tinha acabado de escrever
para esta fase.

---

## As três capturas

Por `CGWindowID`, validadas por `check_evidence_privacy`, com **chamada real ao modelo**
(`llama-3.3-70b-versatile` via Groq). Script: `scripts/capture_ia_marcacao.py`, que **recusa**
rodar sem chave configurada em vez de gerar uma imagem que parece boa.

| arquivo | o que mostra | dimensões | fundo papel | veredito |
|---|---|---|---:|---|
| `ia_marcacao_chat.png` | resposta real do Blink com faixa + selo, e o indicador `CONTEXTO ATIVO` | 2560×1682 | 69,5% | OK |
| `ia_marcacao_insights.png` | diálogo do Sankey com faixa + selo — o ponto que **não tinha** marcação | 1440×1184 | 63,6% | OK |
| `ia_marcacao_clusters.png` | 12 rótulos `[IA] …` do modelo; cluster sem rótulo mostra `—` sem marcação | 2560×1682 | 69,9% | OK |

O corpus vem do CSV de exemplo do repositório, não de uma busca online: a captura precisa ser
refazível daqui a um ano com o mesmo conteúdo. O que é real é a **chamada ao modelo**, que é o
que a evidência afirma.

Três tropeços do próprio script, corrigidos e comentados no código porque são armadilhas
reutilizáveis: `event_generate("<Return>")` num `CTkEntry` não alcança o binding (fica no
`tkinter.Entry` interno); a tela de boas-vindas é um frame por cima de tudo que `_switch_tab`
não remove; e o `CTkToplevel` sobe com fade-in no macOS, o que produzia uma evidência lavada
até `-alpha` ser fixado em 1.0.

Em duas tentativas a captura **recusou** em vez de fotografar o que estava na frente (uma
janela do navegador do autor). O mecanismo da correção de `1a33124` funcionou como projetado.

---

## Aceite

- `python3 -m pytest tests/ -q` → **610 passed, 1 xfailed** (OBS-03 do Crossref, fora do
  escopo). Eram 557 antes desta rodada: **+53 testes**. ✅
- `python3 scripts/reinject_ia_ux.py` → **38/38 defeitos detectados**. ✅
- `python3 scripts/check_i18n_parity.py` → catálogos em paridade. ✅
- `python3 scripts/check_evidence_privacy.py` → **71 imagens · 71 OK · 0 para inspeção
  humana**. ✅
- Três capturas com chamada real ao modelo, sem mock. ✅
- Medição dos dois eixos nos três idiomas, variação de origem zero. ✅

### Uma observação sobre a própria auditoria

`check_evidence_privacy` enumera as imagens com `git ls-files` — ou seja, **só vê arquivos
rastreados**. Uma captura recém-gerada e ainda não indexada passa despercebida pela auditoria
do repositório. As três desta rodada foram indexadas para entrar na contagem acima, e o
`capture_ia_marcacao.py` roda a mesma análise inline em cada captura justamente porque não dá
para depender de o arquivo já estar no git no momento em que ele é criado.
