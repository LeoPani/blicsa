# Auditoria de setembro de 2026

Objetivo: versão funcional para apresentação acadêmica, **sem mudar nenhuma funcionalidade
existente**. Só correção de defeito, cada uma com teste. Diagnóstico escrito antes da correção.

Base auditada: a pasta local `~/PyBibliomics` (commit `dcb8a82` + trabalho ainda não
commitado), copiada sem alteração. Antes de qualquer mudança foi feito
`git stash push --include-untracked -m "antes da auditoria"` (seguido de `stash apply`): a
versão original inteira está guardada em `stash@{0}`.

## Como foi testado

1. **Suíte existente** (1.252 testes) antes e depois.
2. **`scripts/smoke_app.py`**: dirige o app real, sob Xvfb, de ponta a ponta — importa o
   dataset de exemplo, gera cada tipo de mapa, abre cada análise, clica cada exportação,
   salva e reabre projeto.
3. **`tests/test_usuario_desastrado.py`** (74 cenários): o usuário que faz tudo errado —
   arquivo vazio, binário, só cabeçalho, JSON/BibTeX/RIS quebrados, formato errado no seletor,
   arquivo apagado antes de carregar, CSV do Excel brasileiro (`;` e Windows-1252), mesmo
   arquivo duas vezes, acentos/aspas/emoji/barra invertida nos termos, anos bagunçados, texto
   em campo numérico, período invertido, ocorrência mínima absurda, stopwords que removem tudo,
   corpus de 1 registro ou sem palavra-chave, os 7 tipos de mapa com corpus pobre, clique
   duplo em Gerar Mapa, trocar de corpus e exportar o mapa velho, exportar sem mapa, para
   pasta inexistente, com nome acentuado, por cima de arquivo aberto no Excel, cancelar a
   janela de salvar, abrir `.blicsa` falso, salvar-reabrir e comparar o mapa, e **contagens
   conferidas à mão** (ocorrência, coocorrência, caixa de letra, filtro de período).

   Cada cenário exige: nada escapa em silêncio (exceção no Tk ou em thread), toda falha vira
   uma caixa em português **sem jargão de Python**, e onde há número o número está certo.

## Defeitos encontrados e corrigidos

| # | Gravidade | Sintoma para o usuário | Causa | Correção |
|---|---|---|---|---|
| B1 | **Crítica** | Importar `docs/sample_dataset.csv` (exemplo oficial) ou reimportar o CSV que o próprio Blicsa exporta carregava **0 registros**, sem erro | CSV no schema do Blicsa não era reconhecido; caía como Scopus, que não achava coluna nenhuma | Leitor `load_blicsa_csv` (usa a `normalize_dataframe` existente) e formato "Blicsa CSV" na detecção e no seletor |
| B2 | Alta | Com 0 registros: "0 registros carregados" e salto para o mapa, como se tivesse dado certo | Nenhuma verificação | Erro claro: "Nenhum registro foi lido… confira o formato" |
| B12 | Média | Arquivo importado com defeito dizia **"Não foi possível abrir o projeto"** — o usuário nem tinha aberto projeto | Erro de importação passava pelo tradutor de erros de projeto | Mensagens próprias de importação (pt/en/fr), com nome do arquivo e formato |
| B4 | **Crítica** | "Exportar Selecionados" (lote) falhava com `write() argument must be str, not list` e **nada era salvo** | Lista de dicionários gravada direto | Mesmo texto do export de clusters individual |
| B8 | **Crítica** | Exportar **PNG, SVG, PDF e Plotly HTML**: "Gere o mapa primeiro" com mapa gerado | PNG/SVG/PDF liam o canvas matplotlib que saiu da tela quando o Sigma.js entrou (sempre `None`); Plotly copiava um arquivo que nenhum código grava | Mesmo `MapCanvas` desenhado numa janela oculta; Plotly gerado na hora com `build_plotly_map` |
| B11 | **Crítica** | Aba Galeria quebrava ao listar mapas salvos | `return f` com `f` inexistente | Linha removida |
| B7 | Média | Mapa salvo na Galeria podia abrir em branco com aspas/barra invertida num termo | JSON usado como *template* de `re.sub` | `inline_graph_data` com substituição por função |
| **D3** | **Alta — resultado incorreto** | **Stopwords extras não removiam palavras-chave**: o usuário excluía "review, human" e elas continuavam no mapa, apesar de a dica da tela prometer exatamente isso | O ramo de palavras-chave ignorava `extra_stop_words` | Filtro aplicado antes e depois do tesauro |
| D2 | Média | Texto em "Máx. de nós" mostrava `invalid literal for int() with base 10: 'abc'`; "50%" em Top % e "dois mil" no ano eram **ignorados em silêncio** (o mapa saía sem o filtro pedido) | `int()`/`float()` crus | Aceita "10,5", "50%" e espaços; texto inválido gera aviso dizendo qual campo e qual valor |
| D4 | Média | Clique duplo em Gerar Mapa (ou Ctrl+G repetido) rodava dois cálculos simultâneos que gravavam grafo e layout um por cima do outro | Sem trava | Um mapa por vez; o segundo clique é ignorado |
| D5 | **Alta** | Qualquer falha ao gravar uma exportação — o caso típico no Windows é **o arquivo de destino aberto no Excel** — não mostrava nada: o usuário clicava e nada acontecia | Exceção dentro do botão só ia para o terminal | Todas as 17 exportações protegidas: mensagem em português (arquivo aberto em outro programa / pasta inexistente / disco) |
| D6 | Média | Reclusterizar (mudar a resolução com o mapa pronto) quebrava sempre, depois de recalcular | `time` usado sem importar | Import adicionado |
| — | Média | Erro inesperado ao gerar mapa mostrava a exceção crua | `str(exc)` na caixa | Mensagem para gente; detalhe no log |
| B5 | Baixa | PDF sem `pdfplumber`: `UnboundLocalError` em vez de "instale pdfplumber" | Variável `t` sombreava a função de tradução | Renomeada |
| B6 | Baixa | "Agrupamento Semântico (Embeddings)" gerava, sem aviso, um mapa de **patentes (IPC)** | Tipo sem construtor caía no `else` | Aviso de que o tipo ainda não está disponível |
| B9 | Baixa | Abrir projeto sem mapa mantinha o mapa do projeto anterior | Gerador não era zerado | Zerado |
| B10 | Alta (só no executável) | No `.exe`, mapas/gráficos/galeria gravados na pasta do programa (temporária no onefile, protegida quando instalado) | Caminho relativo ao programa | Executável grava em `~/Blicsa/`; rodando do código-fonte, nada muda |

### O que não era defeito (e ficou como está)

- **Juntar dois arquivos não remove quase-duplicatas** (mesmo DOI em caixa diferente). É
  decisão de projeto: a remoção é feita pelo botão **Deduplicar**, com prévia revisável. O
  teste confirma que o botão encontra e remove o par.
- Sem coluna de IPC, o mapa de patentes avisa que a coluna falta — correto.

## Resultado

| Checagem | Antes | Depois |
|---|---|---|
| Suíte existente | 1.252 passam · 6 falham | ver seção final |
| Cenários "usuário desastrado" (74) | 31 falham | **74 passam** |
| Regressões da auditoria (14) | todas falham | **14 passam** |
| Paridade dos catálogos pt/en/fr | ok | ok (17 chaves novas nos três) |

As 6 falhas da suíte original são do ambiente de teste Linux sem janela, não do app: duas
comparam `transient()` (objeto × texto na versão do Tk daqui), três medem uma janela ainda não
desenhada (1 px) e uma é o teste de servidor local, instável por *timeout* (já observado antes).

## Não testado aqui (faça antes de apresentar)

- **Busca online** (OpenAlex/Crossref/PubMed): a rede deste ambiente bloqueia essas APIs.
- **Abrir um mapa no navegador** (WebGL): sem navegador gráfico aqui. O HTML e o JSON
  embutido foram validados.
- IA (Groq), sem chave.

## Teste no app real, no Mac do Leonardo (28/09, madrugada)

Feito por controle de tela na versão aberta com `python main.py` (não no `dist/Blicsa.app`
de 25/09, que é anterior às correções):

| Passo | Resultado |
|---|---|
| Busca OpenAlex "bibliometric analysis entrepreneurship" | 62 encontrados · 62 baixados · fim dos resultados |
| Importar para o corpus | 62 registros importados |
| Gerar mapa (coocorrência) | 47 nós · 454 arestas · 5 clusters; abre no Chrome com Sigma.js |
| Insights de IA (Groq) | gerados automaticamente depois do mapa |
| Salvar na Galeria → aba Galeria → Abrir | salvo, listado e aberto (versão offline) |
| Exportação em Lote | adjacência, GML, relatório de clusters (5 clusters, texto) e Excel válidos |
| Stopwords "computer science, economics" | mapa com 45 termos (−2), nenhum dos dois presente |

Achado durante o teste e corrigido: a lista "Revisar termos" mostrava as stopwords extras
como "SIM" (manter), embora o mapa as removesse. Agora a lista já sai sem elas.

Observado e não mexido (visual): em janela de 1380 px, alguns rótulos de botão da aba
Análises aparecem cortados ("alvar na Galer", "iankey (3 Campos").
