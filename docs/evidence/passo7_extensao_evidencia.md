# Passo 7 — Evidências textuais da extensão

## D) /api/status — token Bearer (porta 8765, token persistente nas settings)

COM token:
    $ curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:8765/api/status
    {"status": "ok", "version": "1.0"}

SEM token:
    $ curl -s -o /dev/null -w "HTTP %{http_code}" http://127.0.0.1:8765/api/status
    HTTP 401

## C) Linha extension_add do backlog.jsonl REAL
Gerada por um POST /api/add real (como a extensão faz) com o DOI
10.1371/journal.pone.0173664, resolvido via OpenAlexProvider.get_by_doi:

    {"ts": "2026-07-21T08:06:40", "action": "extension_add", "detail": {"doi": "https://doi.org/10.1371/journal.pone.0173664", "titulo": "The miR-200 family is increased in dysplastic lesions in ulcerative colitis patients", "origem_url": "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0173664"}}

## Extração do content.js na PÁGINA REAL (PLOS One, via automação do Chrome)
Rodando a lógica exata de content.js em
https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0173664:

    title: "The miR-200 family is increased in dysplastic lesions in ulcerative colitis patients"
    doi:   "10.1371/journal.pone.0173664"
    source_url: "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0173664"
    authors: (populado; redigido pelo MCP como chave sensível)
