# Perguntas frequentes

## Preciso pagar alguma coisa?

Não. O Blicsa é software livre e as bases que ele consulta online (OpenAlex, Crossref, PubMed)
são gratuitas e públicas.

## Preciso de chave de API?

Não. O app funciona sem nenhuma chave.

Há **um** campo opcional, em **Configurações → Chave OpenAlex**. O OpenAlex oferece uma cota
diária gratuita para uso anônimo; quem faz muitas buscas grandes num mesmo dia pode esbarrar
nela e receber um aviso dizendo exatamente isso. Uma chave gratuita do OpenAlex aumenta a cota.
Deixar o campo vazio é o padrão e não limita nenhuma funcionalidade.

Para a IA (aba Blink) é preciso uma chave de provedor de modelos, configurada por você. É a
única parte do app que depende de serviço externo pago — e é opcional.

## Meus dados saem do meu computador?

**Não.** O Blicsa é *local-first*:

- o **corpus**, os **projetos** (`.blicsa`), os **mapas** e as **exportações** ficam só na sua
  máquina;
- nenhum dado é enviado para servidor do projeto — não existe servidor do projeto;
- não há cadastro, login nem telemetria.

O que **sai** da sua máquina são apenas as **consultas às APIs públicas**: o termo que você
buscou e os filtros, enviados a OpenAlex, Crossref ou PubMed, que respondem com os metadados.
Essas APIs recebem também um e-mail de contato do projeto (`blicsa.app@gmail.com`), exigido
pelos termos de uso delas para identificar o cliente — **não o seu e-mail**.

Se você usar a aba Blink (IA), aí sim o texto que você enviar vai para o provedor de modelos
que você configurou. Essa é a única exceção, é opcional, e está sob seu controle.

## Por que meus resultados vieram em línguas misturadas?

Porque as bases são multilíngues e, por padrão, nenhum filtro de idioma é aplicado. Use a
faceta **Idioma** na lateral para restringir. Repare que a faceta mostra a contagem real de
cada idioma no universo da busca antes de você filtrar.

## Como o Blicsa se compara ao VOSviewer?

| | Blicsa | VOSviewer |
|---|---|---|
| Licença | livre | gratuito, código fechado |
| Plataforma | Python, executável nativo | Java |
| Busca online integrada | OpenAlex, Crossref, PubMed | via APIs configuradas |
| Mapas | rede, overlay, densidade | rede, overlay, densidade |
| Clustering | Louvain (semente fixa) | algoritmo próprio (VOS) |
| Relevância de termos | divergência KL — **não comparável** | fórmula própria publicada |

**Os mapas não são numericamente equivalentes.** As métricas de relevância diferem (veja
[métodos](metodos.md)) e os algoritmos de clustering são diferentes. Para reproduzir um
resultado publicado com o VOSviewer, use o VOSviewer. O Blicsa exporta a rede em **GML**, que
o VOSviewer e o Gephi leem — dá para montar o corpus aqui e analisar lá.

## Posso usar meus dados do Scopus ou da Web of Science?

Sim, por importação de arquivo (CSV, BibTeX ou texto exportado da plataforma). Não há busca
online para essas bases porque as APIs delas exigem assinatura institucional.

## Por que a importação do PubMed parou em 9.999?

É um teto da API do NCBI, não do Blicsa. Veja
[limitações conhecidas](limitacoes.md#1-pubmed-9999-registros-por-busca).

## Deixei o campo Qtd vazio. Ele vai baixar tudo mesmo?

Sim — vazio significa ilimitado, sem teto escondido. Antes de uma colheita grande o app mostra
o total e pede confirmação; essa é a proteção, no lugar de um corte silencioso.

## Reabri um projeto antigo e os clusters mudaram. É bug?

É a mudança de determinismo da v2.0. Até então a partição podia variar entre execuções com a
mesma entrada; agora não varia mais. O corpus e as métricas continuam idênticos. Veja
[limitações](limitacoes.md#7-projetos-anteriores-à-v20-podem-reclusterizar).

## Onde ficam meus projetos?

Em `~/Blicsa/projects/<slug>/project.blicsa`. É um arquivo ZIP — dá para inspecionar o
conteúdo com qualquer descompactador.

## Encontrei um bug. Onde reporto?

Abra uma issue em <https://github.com/LeoPani/blicsa/issues>. O que ajuda: o que você fez, o
que esperava, o que aconteceu, e o texto do terminal se houver. Detalhes em
[CONTRIBUTING.md](../CONTRIBUTING.md).
