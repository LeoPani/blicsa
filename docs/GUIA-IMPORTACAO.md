# Guia de importação de arquivos

Este guia explica como tirar os seus registros de cada base de dados e colocar no Blicsa.
Para cada base você encontra: como exportar, o que o Blicsa lê do arquivo e o que fica de
fora. No fim há uma tabela que mostra quais mapas cada formato permite gerar.

Uma regra vale para quase tudo: **o mapa só mostra o que o arquivo traz**. Se você não
marcar "referências" na hora de exportar, nenhum mapa de cocitação vai funcionar depois,
por mais que o artigo tenha referências na página da base.

Os nomes de botões estão em inglês porque é assim que a maioria das bases aparece. As
interfaces mudam com o tempo; quando não temos certeza de um passo, dizemos isso.

## Como importar no Blicsa

1. Na tela de importação, clique em **Adicionar Arquivos** e escolha um ou mais arquivos.
   Você também pode arrastar os arquivos para a lista.
2. O Blicsa reconhece o formato sozinho e mostra o nome ao lado do arquivo. Se ele errar,
   troque na lista ao lado do nome.
3. Clique em **Carregar e Combinar**. Se você trouxe arquivos de bases diferentes, o Blicsa
   junta tudo e oferece a remoção de duplicatas (mesmo DOI, título muito parecido ou mesmo
   primeiro autor e ano).

Arquivos aceitos: `.csv`, `.txt`, `.bib`, `.ris`, `.nbib`, `.json` e `.pdf`. Para ver PDFs
na janela de escolha, selecione "All files" no tipo de arquivo (ou arraste o PDF).

Codificação não é problema: o Blicsa lê UTF-8 (com ou sem BOM), UTF-16 e Windows-1252.
Se você abriu o CSV do Scopus no Excel e salvou de novo, ele continua sendo lido.

## Scopus

**Formato recomendado: CSV.** BibTeX e RIS do Scopus também funcionam e trazem as mesmas
informações.

Como exportar:

1. Na lista de resultados, marque todos os documentos (caixa de seleção no topo da lista).
2. Clique em **Export** e escolha **CSV**.
3. Na janela de campos, marque:
   - em "Citation information": tudo (autores, título, ano, fonte, número de citações, DOI,
     tipo de documento);
   - em "Abstract & keywords": **Abstract**, **Author keywords** e **Index keywords**;
   - **Include references** (na versão atual fica no grupo "Other information"; se não
     achar, procure pelo nome na janela). Sem isso não há cocitação, acoplamento nem
     citação direta.
4. Confirme a exportação.

O Scopus limita a quantidade de documentos por exportação. Se aparecer o aviso de limite,
divida a busca (por exemplo, por faixa de anos), exporte cada parte e carregue todos os
arquivos juntos no Blicsa.

O que o Blicsa lê: autores, título, ano, fonte (periódico), palavras-chave do autor,
resumo, número de citações, DOI, referências e tipo de documento.

O que fica de fora:

- **Index Keywords** não entram no mapa de palavras-chave; o Blicsa usa só as
  palavras-chave do autor. Artigos sem palavras-chave do autor ficam sem termos nesse
  mapa (use o mapa de termos do título e resumo para cobri-los).
- Afiliações, financiamento, nomes completos dos autores ("Author full names") e país.
- Os marcadores "[No author name available]" e "[No abstract available]" são tratados
  como campo vazio.

## Web of Science

**Formato recomendado: Plain text file.** O "Tab delimited file" também funciona.

Como exportar:

1. Na lista de resultados, clique em **Export**.
2. Escolha **Plain text file** (ou **Tab delimited file**).
3. Em "Records", indique o intervalo (por exemplo, de 1 a 1000). O WoS exporta um número
   limitado de registros por vez com referências (hoje 1.000; em versões antigas eram 500).
   Para mais registros, repita a exportação com o intervalo seguinte e carregue todos os
   arquivos juntos.
4. Em "Record Content", escolha **Full Record and Cited References**. Esta opção é a que
   traz as referências citadas.
5. Clique em **Export**. O arquivo costuma se chamar `savedrecs.txt`.

O que o Blicsa lê: autores (AU), título (TI), ano (PY; nos artigos em "Early Access", o
ano de EY ou EA), fonte (SO), tipo de documento (DT), palavras-chave do autor (DE),
resumo (AB), citações (TC), DOI (DI) e referências citadas (CR).

O que fica de fora:

- **Keywords Plus** (ID) não entram no mapa de palavras-chave.
- Nomes completos (AF), endereços (C1), áreas (WC, SC), financiamento.
- "[Anonymous]" é tratado como autor vazio.

## PubMed

**Formato: PubMed (MEDLINE).**

Como exportar, por um destes caminhos:

- Clique em **Save**, em "Selection" escolha **All results** (ou as páginas que quiser),
  em "Format" escolha **PubMed** e clique em **Create file**. Sai um `.txt`.
- Ou clique em **Send to**, depois **Citation manager**, e salve o arquivo `.nbib`.

O PubMed também limita a quantidade por arquivo (hoje 10.000 registros pelo Save). Para
mais, divida a busca.

O que o Blicsa lê: autores, título, ano, periódico, tipo de publicação, palavras-chave,
resumo, DOI e idioma. Como palavras-chave, o Blicsa usa os descritores **MeSH**; só usa os
termos livres do autor (OT) quando o artigo não tem MeSH. O asterisco do MeSH (assunto
principal) é retirado.

O que fica de fora:

- **Referências e número de citações:** o PubMed não exporta essas informações neste
  formato. Por isso não há cocitação, acoplamento nem citação direta com arquivos do
  PubMed.
- Os qualificadores do MeSH continuam junto do descritor ("Neoplasms/drug therapy" e
  "Neoplasms/pathology" contam como termos diferentes). Se isso atrapalhar, use a
  harmonização de termos do Blicsa.

## OpenAlex

**Recomendado: a busca integrada do Blicsa**, que já traz tudo, inclusive as referências.

Se você baixou um arquivo JSON da API do OpenAlex (por exemplo, o resultado de um endereço
`https://api.openalex.org/works?...`), o Blicsa lê esse JSON. Não temos certeza de quais
formatos o botão de exportação do site do OpenAlex oferece hoje; se ele der um RIS, o
Blicsa lê, mas o RIS não costuma trazer referências.

O que o Blicsa lê do JSON: autores, título, ano, fonte, tipo, palavras-chave, resumo,
citações, DOI, referências (os códigos dos trabalhos citados), código OpenAlex de cada
artigo, idioma e acesso aberto.

O que fica de fora: afiliações e instituições, financiamento, tópicos.

## Crossref

**Recomendado: a busca integrada do Blicsa.**

Também é possível carregar um JSON baixado da API do Crossref, tanto uma lista
(`https://api.crossref.org/works?query=...`) quanto um único trabalho
(`https://api.crossref.org/works/10.xxxx/...`).

O que o Blicsa lê: autores, título, ano, periódico, tipo, assuntos (como palavras-chave),
resumo (quando a editora depositou), citações, DOI e referências que têm DOI.

O que fica de fora:

- Referências sem DOI (o Crossref só traz o texto delas, e o Blicsa não as usa).
- Muitas editoras não depositam resumo nem assuntos; nesses casos o campo fica vazio.
- Os autores aparecem como "Sobrenome Nome", sem vírgula. Ao juntar com arquivos de outras
  bases, a mesma pessoa pode aparecer escrita de dois jeitos; use a harmonização.

## Zotero

**Formato: BibTeX ou RIS.** Os dois funcionam do mesmo jeito.

Como exportar:

1. Clique com o botão direito na coleção (ou selecione os itens e clique com o botão
   direito).
2. Escolha **Export Collection...** (ou **Export Items...**).
3. Em "Format", escolha **BibTeX** ou **RIS**. Não precisa exportar notas nem arquivos.

O que o Blicsa lê: autores, título, ano, periódico ou livro, tipo, palavras-chave (as tags
do Zotero), resumo e DOI. Acentos escritos em LaTeX (como `{\'e}`) são convertidos.

O que fica de fora:

- **Referências e número de citações:** o Zotero não guarda o que cada artigo cita. Então
  não há cocitação, acoplamento nem citação direta com arquivos do Zotero.
- Editores de livro não entram como autores.

## Mendeley

**Formato: RIS ou BibTeX.**

Não temos certeza do caminho exato no Mendeley Reference Manager atual. Em geral: selecione
as referências, procure a opção **Export** (no menu do botão direito ou no menu de
arquivo) e escolha **RIS** ou **BibTeX**.

O que o Blicsa lê e o que perde: o mesmo que no Zotero. Não há referências nem citações.

## EndNote e outros gerenciadores

Exporte em **RIS**. O Blicsa reconhece RIS mesmo com extensão `.txt` e mesmo gravado em
Windows-1252. Lê e perde o mesmo que no Zotero.

## CSV do próprio Blicsa

É o CSV que o próprio Blicsa grava quando você exporta o corpus (os registros carregados),
e também o formato de `docs/sample_dataset.csv`. O cabeçalho tem os nomes em minúsculas: `authors`, `title`,
`year`, `source`, `keywords`, `abstract`, `citations`, `doi`, `references`.

Serve para guardar um corpus, editar à mão no Excel (o Blicsa aceita o arquivo salvo de
volta pelo Excel) e reabrir depois. Tudo o que estava no corpus volta.

Para o mapa de **IPC** (patentes), acrescente uma coluna `ipc` com os códigos separados
por ponto e vírgula, por exemplo `G06F 17/30; H04L 29/06`.

## PDF

Precisa do pacote opcional de PDF (`pip install -r requirements-pdf.txt`). Sem ele, o
Blicsa avisa o que falta.

Cada PDF vira um registro com: o texto completo no lugar do resumo, o título dos
metadados do PDF (ou o nome do arquivo) e o DOI, quando ele aparece impresso no texto.

O que fica de fora: autores, ano, periódico, palavras-chave, citações e referências. O
PDF serve só para o mapa de termos do título e resumo (que aqui usa o texto completo).

## Qual mapa funciona com qual formato

"Sim" quando o arquivo traz o que o mapa precisa. "Não" quando a base não exporta essa
informação nesse formato.

| Formato | Coocorrência de termos | Coautoria | Cocitação | Acoplamento | Citação direta | IPC |
|---|---|---|---|---|---|---|
| Scopus CSV, BibTeX ou RIS (com referências) | Sim | Sim | Sim | Sim | Sim (aproximada) | Não |
| Web of Science (Plain text ou Tab delimited, com Cited References) | Sim | Sim | Sim | Sim | Sim (aproximada) | Não |
| PubMed (MEDLINE / .nbib) | Sim | Sim | Não | Não | Não | Não |
| OpenAlex (JSON ou busca integrada) | Sim | Sim | Sim | Sim | Sim | Não |
| Crossref (JSON ou busca integrada) | Sim | Sim | Sim (só refs. com DOI) | Sim (só refs. com DOI) | Sim | Não |
| Zotero, Mendeley, EndNote (BibTeX ou RIS) | Sim | Sim | Não | Não | Não | Não |
| CSV do Blicsa | Sim | Sim | Se tiver referências | Se tiver referências | Se tiver referências | Só com coluna `ipc` |
| PDF | Só pelo texto | Não | Não | Não | Não | Não |

Notas sobre a tabela:

- **Coocorrência de termos** funciona com palavras-chave ou com título e resumo. Se o
  arquivo não tem palavras-chave (Zotero sem tags, por exemplo), escolha o campo título e
  resumo.
- **Citação direta aproximada:** no Scopus e no WoS, a referência é um texto
  ("Small H, 1973, ..."). O Blicsa liga a referência ao artigo do corpus pelo sobrenome do
  primeiro autor e pelo ano. Dois autores com o mesmo sobrenome no mesmo ano podem se
  confundir. No OpenAlex e no Crossref a ligação é exata (pelo código ou pelo DOI).
- **Juntar bases:** cocitação compara o texto das referências. Uma referência escrita no
  estilo do Scopus e a mesma referência no estilo do WoS contam como referências
  diferentes. Para cocitação e acoplamento, prefira usar arquivos de uma base só.
- **IPC** é um mapa para patentes. Nenhuma base de artigos traz esses códigos.
