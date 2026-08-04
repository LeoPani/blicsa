# Limitações conhecidas

O que o Blicsa **não** faz, ou faz com ressalva. Esta página existe para você não descobrir
nada disso no meio de um trabalho.

---

## 1. PubMed: 9.999 registros por busca

**Teto duro da API do NCBI**, não do Blicsa. Uma busca com 300.000 resultados importa 9.999.

Isso vale mesmo usando o histórico do servidor (`usehistory=y` + `WebEnv`), que é a forma
documentada de paginar conjuntos grandes. Pedindo `retstart=10000`, o NCBI responde:

> `'retstart' cannot be larger than 9998. For PubMed, ESearch can only retrieve the first
> 9,999 records matching the query. To obtain more than 9,999 PubMed records, consider using
> EDirect...`

**Quando acontece, o Blicsa diz.** A trilha de contagem mostra *"teto do PubMed: 9.999
registros por busca (limite do NCBI)"* e o total real da base continua visível ao lado.

**Como contornar:** divida a busca em consultas mais estreitas (faixas de ano, revista,
descritores) e importe cada uma. O Blicsa deduplica ao juntar.

## 2. OpenAlex: 10.000 resultados na navegação

Ao **navegar** página a página, o OpenAlex entrega no máximo 10.000 registros — 400 páginas de
25. O pager anuncia **as páginas navegáveis**, não as teóricas: uma busca de 366.949
resultados mostra *"Página 1 de 400 navegáveis"*, e o total completo fica no cabeçalho.

**A importação não tem esse teto**: ela usa paginação por cursor e alcança o conjunto inteiro.
Se você precisa de tudo, importe em vez de navegar.

## 3. Extração de frases nominais: boa em inglês, ruim em português

A extração de termos a partir de **títulos e resumos** usa regras de sintagma nominal
calibradas para o inglês. Em português, resultados típicos:

- preposições e artigos sobrevivem onde deviam ser cortados (`análise de dados` vs `dados`);
- flexões de gênero e número não são unificadas (`inovadora` e `inovador` viram termos
  distintos);
- termos compostos se quebram em pontos errados.

**Como contornar:** para corpora em português, use o campo **palavras-chave** em vez de
títulos/resumos, e use o **thesaurus** para unificar as variantes que importam. É trabalho
manual, e é a limitação mais sentida por usuários brasileiros.

## 4. Scopus e Web of Science: só por importação de arquivo

Não há busca online para essas bases — as APIs exigem assinatura institucional e chave
autenticada. Exporte da própria plataforma (CSV, BibTeX ou texto) e importe pelo
**Coletar → Importar arquivo**.

## 5. macOS: aplicativo sem assinatura de código

O `.app` não é assinado nem notarizado pela Apple. Na primeira abertura é preciso clicar com o
botão direito → **Abrir** (veja [instalação](instalacao.md)). Assinar exige conta paga de
desenvolvedor Apple.

## 6. Relevância de termos não é comparável ao VOSviewer

A métrica de relevância usa divergência KL e é **inspirada** no conceito de especificidade de
termos de van Eck & Waltman, **não é a fórmula publicada por eles**. Os números não são
numericamente comparáveis aos do VOSviewer. Detalhes em [métodos](metodos.md).

## 7. Projetos anteriores à v1.0 podem reclusterizar

Até a v1.0, a ordem de inserção dos nós no grafo não era determinística, e o Louvain podia
chegar a partições diferentes com a mesma entrada. **Reabrir um projeto salvo antes da v1.0
pode produzir um agrupamento diferente do original.** O corpus, as métricas e as posições
salvas não mudam — só o agrupamento pode diferir. A partir da v1.0 o resultado é reproduzível
(semente fixa).

## 8. Sem análise de citações diretas

O Blicsa trabalha com **coocorrência** (de termos, autores, fontes). Não constrói redes de
citação direta nem de acoplamento bibliográfico, porque as fontes gratuitas não fornecem as
listas de referências de forma consistente — o OpenAlex fornece parcialmente, o PubMed não
fornece em MEDLINE, e o Crossref varia por editora.

## 9. Contagem de citações do PubMed é sempre zero

O formato MEDLINE não traz contagem de citações. Registros importados do PubMed vêm com
`citations = 0`. Se você precisa de citações, use OpenAlex ou Crossref como fonte, ou
enriqueça o corpus por DOI.

## 10. Interface em três idiomas, com lacunas

Português, inglês e francês. Algumas cadeias da barra inferior de seleção não passam pelo
sistema de tradução e permanecem em português nos outros idiomas.
