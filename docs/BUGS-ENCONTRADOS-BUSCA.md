# Bugs e limitações encontrados nas buscas (Blicsa)

> Levantados pela suíte de testes `tests/test_search_{correctness,relevance,speed}.py`.
> **Nada foi corrigido** — este documento apenas registra. Cada item tem um teste
> marcado `xfail` (`strict=True`) que passará a falhar (XPASS) quando o bug for corrigido,
> sinalizando que o `xfail` pode ser removido.
> Medição: 2026-07-12.

---

## BUG-01 — PubMed: filtro de idioma usa o sistema de códigos errado (retorna ZERO)

- **Sintoma:** filtrar por idioma no PubMed (`filters={"language": "pt"}` ou `"en"`)
  retorna **nenhum** resultado, silenciosamente.
- **Causa provável:** `core/sources/pubmed.py:37` monta o termo como
  `f"{filters['language']}[LA]"`. O app usa códigos **ISO-639-1** (`pt`, `en`),
  mas o PubMed espera **ISO-639-2/nome** (`por`, `eng`, `portuguese`…).
  Verificado ao vivo: `bibliometria AND pt[LA]` → `count=0`,
  `errorlist.phrasesnotfound=['pt']`; já `por[LA]` → resultados normais.
- **Impacto:** buscas com filtro de idioma no PubMed viram buscas vazias — o usuário
  pensa que "não há artigos" quando na verdade o código foi rejeitado.
- **Arquivo/linha:** `core/sources/pubmed.py:37`.
- **Teste:** `test_search_relevance.py::test_pubmed_language_filter_offline_xfail`
  (fixture `pubmed_lang_pt_BUG_esearch.json`, gravada com `count=0`).
- **Correção sugerida:** mapear `pt→por`, `en→eng`, `es→spa`, `fr→fre`… antes de
  montar `[LA]`, ou aceitar o nome completo do idioma.

## BUG-02 — Crossref: filtro de idioma é ignorado por completo

- **Sintoma:** `filters={"language": "pt"}` no Crossref não restringe nada; voltam
  artigos em qualquer idioma (e a maioria vem com `language` ausente).
- **Causa provável:** `core/sources/crossref.py` monta `filter_parts` apenas para
  `year_start/year_end/type`. O ramo de `language` **não existe** — o filtro é
  descartado sem aviso. (Crossref suporta pós-filtragem só para `is_oa`.)
- **Impacto:** promessa de filtro não cumprida; corpus "em português" fica contaminado.
  Agrava-se porque o metadado `language` do Crossref é majoritariamente `null`
  (medido: 19/25 `None` para "bibliometria").
- **Arquivo/linha:** `core/sources/crossref.py:23-37` (bloco de filtros).
- **Teste:** `test_search_relevance.py::test_crossref_language_filter_offline_xfail`
  (fixture `crossref_lang_pt_ignored.json`).
- **Correção sugerida:** ou pós-filtrar em Python por `language` (como já se faz com
  `is_oa`), ou documentar explicitamente na UI que o Crossref não filtra idioma.

## BUG-03 — Deduplicação fuzzy é sensível a caixa e pontuação

- **Sintoma:** o mesmo artigo, com o título em caixa/pontuação diferentes
  ("Bibliometric Analysis of Innovation" vs "bibliometric analysis of innovation."),
  **sobrevive como duplicata** ao passar por `fuzzy_deduplicate_papers`.
- **Causa provável:** `core/harmonization.py:26-47` compara títulos crus com
  `difflib.get_close_matches(cutoff=0.93)`, sem normalizar (lowercase / remover
  pontuação). Diferenças de caixa/pontuação derrubam a similaridade abaixo de 0.93.
- **Impacto:** duplicatas óbvias passam quando a origem escreve o título de forma
  diferente (comum entre Crossref e PubMed). Curiosamente o dedup **inline** de
  `main.py:1786-1792` (`norm_title` remove não-alfanuméricos + lowercase) trata isso —
  ou seja, há **duas** implementações de dedup com comportamentos divergentes.
- **Arquivo/linha:** `core/harmonization.py:26-47`.
- **Teste:** `test_search_relevance.py::test_dedup_case_and_punctuation_insensitive_xfail`.
- **Correção sugerida:** normalizar o título (lowercase + strip de pontuação) antes do
  `get_close_matches`, unificando com a lógica de `norm_title` do `main.py`.

---

## Observações (não são bugs de código, mas afetam qualidade)

### OBS-03 — Crossref rankeia reimpressões acima do artigo seminal
`query.bibliographic` para "The Promise of Entrepreneurship as a Field of Research"
devolve, no top 3, capítulos de livro (reimpressões, 2007) e uma "discussion" (2017);
o DOI canônico `10.5465/amr.2000.2791611` (2000) fica **fora do top 3**.
Não é bug do Blicsa (é ranking do Crossref), mas prejudica a busca por título exato.
Teste: `test_search_correctness.py::test_crossref_shane_in_top3_offline_xfail`.

### OBS-04 — PubMed nunca preenche `citations` nem `is_oa`
`core/sources/pubmed.py:141,146` fixa `citations=0` e `is_oa=False` (o formato MEDLINE
não traz esses campos). Consequência: ordenar/filtrar por citações ou por open access
degrada silenciosamente para o subconjunto PubMed, e `filters={"is_oa": True}` não pode
ser validado nesse provider.

### OBS-05 — `language_source` não é emitido pelos providers
O contrato de saída dos providers tem **13 chaves** (sem `language_source`). O campo
`language_source` é adicionado depois, na thread de enriquecimento em
`main.py:1745-1767`. Não é defeito, mas a lógica de detecção de idioma vive dentro de
uma thread de UI e **não é testável isoladamente** — recomenda-se extraí-la para uma
função pura em `core/` (ver relatório).
