# Fixtures da suíte de busca

Respostas **reais** das APIs OpenAlex, Crossref e PubMed, gravadas em **2026-07-12**
e servidas offline por `tests/conftest.py::serve` (mock de `SearchProvider.fetch_url`).
Cada arquivo é `{"url": <URL exata usada>, "body": <corpo bruto retornado>}`.

Regravar: rode o coletor documentado em `tests/README-BUSCA.md`
(APIs evoluem; espere pequenas variações em contagens/rankings).

| Arquivo | Origem | Conteúdo |
|---|---|---|
| `openalex_vosviewer.json` | OpenAlex `filter=doi:10.1007/s11192-009-0146-3` | ground truth VOSviewer (1 work, com `abstract_inverted_index`) |
| `openalex_vosviewer_titlesearch.json` | OpenAlex `title.search:...` | top 3 por título (VOSviewer é #1) |
| `openalex_rel_{bibliometric,entrepreneurship,ml}.json` | OpenAlex `default.search` | 25 resultados p/ precision@10 |
| `openalex_isoa_true.json` | OpenAlex `is_oa:true,...` | 25 resultados open access |
| `openalex_year_2019_2021.json` | OpenAlex `publication_year:2019-2021,...` | 25 resultados no intervalo |
| `openalex_lang_pt.json` | OpenAlex `language:pt,...` | 25 resultados em português |
| `openalex_page{1,2,3}.json` | OpenAlex cursor | 3 páginas de 100 (teste de paginação/dedup) |
| `crossref_shane_doifilter.json` | Crossref `filter=doi:10.5465/amr.2000.2791611` | ground truth Shane (canônico) |
| `crossref_shane_titlesearch.json` | Crossref `query.bibliographic` | top 3 por título (canônico NÃO aparece — OBS-03) |
| `crossref_rel_{bibliometric,entrepreneurship,ml}.json` | Crossref `query.bibliographic` | 25 resultados p/ precision@10 |
| `crossref_year_2019_2021.json` | Crossref `from/until-pub-date` | 25 resultados no intervalo |
| `crossref_lang_pt_ignored.json` | Crossref `query.bibliographic:bibliometria` | evidência de BUG-02 (idiomas variados) |
| `pubmed_livak_{esearch,efetch}.json` | PubMed ESearch+EFetch | ground truth Livak 2001 (top 3) |
| `pubmed_rel_{bibliometric,ml}_{esearch,efetch}.json` | PubMed ESearch+EFetch | 25 resultados p/ precision@10 |
| `pubmed_lang_pt_BUG_esearch.json` | PubMed `bibliometria AND pt[LA]` | evidência de BUG-01 (`count=0`) |

Notas:
- O mock **ignora a URL** e devolve os corpos na ordem em que o provider os pede
  (`side_effect`); os testes que precisam validar a URL construída inspecionam
  `recorder.calls` (ver `serve`).
