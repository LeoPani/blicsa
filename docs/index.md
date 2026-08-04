# Blicsa — documentação

**Blicsa** é um aplicativo de desktop para **análise bibliométrica**: buscar literatura
científica, montar um corpus, gerar mapas de conhecimento e extrair estatísticas — tudo na sua
máquina, sem servidor e sem conta.

![Tela de navegação do Blicsa](evidence/v1_busca_navegacao.png)

*Navegação de resultados no modelo Web of Science: contagem real na hora, facetas com as
contagens do universo inteiro e paginação sob demanda.*

## Para quem é

Pesquisadores, estudantes de pós-graduação, bibliotecários e núcleos de inovação que precisam
mapear um campo de pesquisa e não querem depender de licença paga nem enviar seu corpus para
um serviço de terceiros.

## O que resolve

| problema | como o Blicsa trata |
|---|---|
| Ferramentas de mapeamento exigem licença ou Java | Aplicativo Python livre, com instalador para Windows, macOS e Linux |
| Buscar exige baixar tudo antes de ver qualquer coisa | **Navegar e importar são separados**: a contagem e a primeira página chegam em segundos; o download em massa é uma ação explícita |
| Não se sabe quantos resultados existem de verdade | O total real da base fica sempre visível, e a trilha de contagem diz **por que** a colheita parou |
| Corpus e dados vão para a nuvem | **Local-first**: o corpus, os projetos e os mapas nunca saem da sua máquina (veja o [FAQ](faq.md)) |

## Por onde começar

1. **[Instalação](instalacao.md)** — Windows, macOS e Linux · *[English](installation.md)*
2. **[Uso](uso.md)** — o fluxo completo, do primeiro termo buscado ao mapa exportado ·
   *[English](usage.md)*
3. **[Mapas](mapas.md)** — o que cada visualização significa e como ler
4. **[Métodos](metodos.md)** — as fórmulas e as referências por trás dos números ·
   *[English](methods.md)*
5. **[Limitações conhecidas](limitacoes.md)** — o que o Blicsa **não** faz, dito com todas as letras
6. **[Perguntas frequentes](faq.md)**

## Fontes de dados

| fonte | busca online | importação de arquivo |
|---|---|---|
| **OpenAlex** | sim (padrão) | — |
| **Crossref** | sim | — |
| **PubMed** | sim | — |
| **Scopus** | não | CSV / BibTeX |
| **Web of Science** | não | CSV / BibTeX / plain text |

As buscas online usam APIs públicas e gratuitas. Nenhuma exige cadastro; o OpenAlex aceita uma
chave gratuita opcional para quem esbarra no limite diário. Os limites de cada API estão em
[limitações conhecidas](limitacoes.md).

## Licença e citação

O Blicsa é software livre. Para citar, use o `CITATION.cff` na raiz do repositório — o GitHub
gera a citação formatada a partir dele no botão **Cite this repository**.
