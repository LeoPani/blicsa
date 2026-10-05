**Blicsa** é um aplicativo de desktop para análise bibliométrica: buscar literatura, montar um
corpus, gerar mapas de conhecimento e extrair estatísticas — tudo na sua máquina.

Esta é a versão pública de testes **Blicsa Beta 2.1.0-beta.4**. Ela reúne as melhorias
desenvolvidas depois do snapshot estável 2.0.0. Comece pela
**[documentação](../../blob/main/docs/index.md)**.

## Instalação

Baixe o arquivo da sua plataforma aqui embaixo. Não precisa de Python instalado.

- **Windows** — `Blicsa.exe`. O SmartScreen vai avisar que o publicador é desconhecido: o
  executável não tem assinatura de código. **Mais informações → Executar assim mesmo**.
- **macOS** — `Blicsa-macos.zip`. Descompacte e, **na primeira vez**, clique com o **botão
  direito → Abrir** (não use duplo clique). O app não é assinado nem notarizado pela Apple, e
  com duplo clique o sistema recusa sem oferecer alternativa. Só é preciso fazer isso uma vez.
- **Linux** — `Blicsa-linux`. `chmod +x Blicsa-linux && ./Blicsa-linux`.

Prefere rodar do código? Precisa de **Python 3.11 ou superior** — veja a
[instalação](../../blob/main/docs/instalacao.md).

Confira o download com o `SHA256SUMS.txt` anexado:

```bash
sha256sum -c SHA256SUMS.txt
```

## Novo nesta versão (beta.4)

- **Explorar a partir de um artigo** (aba Coletar): cole o DOI de um ou mais artigos-chave e o
  Blicsa monta, pelo OpenAlex, o grafo dos artigos mais parecidos com eles (acoplamento
  bibliográfico + cocitação), com as **obras anteriores** em que o grupo se apoia e as
  **obras derivadas** que vieram depois. Marque o que interessar e adicione ao corpus.
- **Baixar PDFs de acesso aberto de verdade**: procura a versão aberta no Unpaywall, OpenAlex,
  arXiv e na página do editor, confere se o arquivo é PDF, deixa escolher a pasta, tem
  Cancelar e grava um relatório com o link de cada artigo que não foi possível baixar.
  Funciona também com corpus do Scopus e do Web of Science.
- **Importação mais confiável**: 14 correções nos leitores de RIS, Web of Science, BibTeX,
  PubMed, Scopus, OpenAlex e Crossref. Antes, um arquivo RIS inteiro podia virar um registro
  só, e o "tab-delimited" do WoS voltava vazio sem aviso. Guia novo:
  [como exportar de cada base](../../blob/main/docs/GUIA-IMPORTACAO.md).
- **Mapas**: tipos agrupados pela pergunta que respondem, com uma frase explicando cada um;
  na cocitação, referências do OpenAlex aparecem como "Silva et al. (2020)"; projetos antigos
  ganham "Completar códigos do OpenAlex" para a citação direta funcionar.
- **Busca do OpenAlex até 4 vezes mais rápida**: 3.000 resultados em 9 s (antes, 37 s), com os
  mesmos artigos.
- **Busca**: DOI errado no PubMed corrigido; filtros de ano e acesso aberto agora valem também
  na contagem do PubMed; autor institucional deixa de virar nome vazio no Crossref.

## Da versão anterior (beta.3)

Mapas mais fáceis de gerar. Nenhum tipo de mapa foi removido.

- **Cocitação e acoplamento não travam mais**: respeitam o limite de nós (antes, até 5 minutos).
- **Citação direta funciona com dados do OpenAlex.**
- **O Blicsa avisa antes de você clicar** quando o tipo de mapa não serve para o seu corpus, e diz por quê.
- **Limiar alto demais não deixa ninguém sem mapa**: o Blicsa reduz, avisa e mostra o valor usado.
- **O controle de limiar diz o que ele conta** em cada tipo de mapa (termos, autores, pares de referências…).

## Da beta.2

Correções de uma auditoria completa, com testes simulando o usuário que faz tudo errado.
Nenhuma funcionalidade foi removida ou mudou de comportamento.

- **O exemplo e o CSV exportado pelo próprio Blicsa voltam a importar** (antes vinham 0 registros, sem aviso).
- **CSV do Scopus aberto e salvo no Excel em português importa** (separador `;` e acentos).
- **Galeria, Exportação em Lote e exportar PNG/SVG/PDF/Plotly voltam a funcionar.**
- **Stopwords extras passam a valer para palavras-chave** — antes o termo excluído continuava no mapa.
- **Toda falha explica o que fazer, em português, inglês ou francês**: chave de IA recusada, limite
  da IA, sem internet, arquivo aberto no Excel, campo numérico com texto, período vazio.
- **Menos travadas**: abrir um projeto grande (6 mil registros) e "Revisar termos" não congelam
  mais a janela por vários segundos.
- **No executável, mapas e galeria ficam em `Blicsa/` na sua pasta pessoal** (antes podiam sumir ao fechar).

## ⚠️ Leia antes de atualizar

**Projetos salvos antes desta versão podem mostrar clusters diferentes ao serem reabertos.**
Até agora, a mesma entrada podia produzir agrupamentos distintos entre execuções; a partir
desta versão o resultado é reproduzível. **Seu corpus, suas métricas e as posições salvas não
mudam — só o agrupamento pode diferir.** Se você precisa preservar exatamente um agrupamento
já publicado, guarde a figura exportada antes de reabrir o projeto.

**Python 3.11 passa a ser o mínimo** para quem roda a partir do código.

**Registros antigos deixam de aparecer indevidamente como "Open Access".** Havia um defeito na
leitura desse campo em projetos salvos por versões anteriores.

## O que melhorou

- **Projetos antigos abrem.** Antes, um projeto de julho podia falhar ao gerar o mapa com uma
  mensagem de uma palavra só, que não dizia sequer que o problema era o arquivo.
- **O campo Qtd vazio agora traz tudo mesmo.** Havia um teto escondido de 1.000 registros:
  numa busca com 54 mil resultados, quem não digitava nada recebia 1.000 sem saber por quê.
- **As contagens dizem a verdade.** Quando uma colheita para, o app diz **por que** parou — se
  foi o limite que você pediu, se a base acabou, ou se foi um teto da API.
- **A paginação não promete página que não existe.** Uma busca com 366 mil resultados mostrava
  "Página 1 de 14.678" quando só 400 podiam ser abertas.
- **Documentação de usuário completa**, em português, com instalação, uso e métodos também em
  inglês.

## Limitação conhecida em destaque

**O PubMed entrega no máximo 9.999 registros por busca.** É um teto da API do NCBI, não do
Blicsa, e não há como contorná-lo por paginação. Quando acontece, o app diz. Para cobrir um
conjunto maior, divida a busca em consultas mais estreitas — o Blicsa deduplica ao juntar.

As demais estão em [limitações conhecidas](../../blob/main/docs/limitacoes.md).

---

Changelog completo: [CHANGELOG.md](../../blob/main/CHANGELOG.md)
