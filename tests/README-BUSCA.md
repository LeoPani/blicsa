# Suíte de testes de busca (correção · pertinência · velocidade)

Dois níveis:

- **Nível 1 — Offline** (`test_search_correctness.py`, `test_search_relevance.py`):
  usam fixtures JSON com respostas reais gravadas (`tests/fixtures/`), servidas por
  mock de `SearchProvider.fetch_url`. Determinísticos, sem rede. Rodam sempre / no CI.
- **Nível 2 — Live** (marcados `@pytest.mark.live`, todo o `test_search_speed.py` +
  variantes `_live` dos outros): batem nas APIs reais. **Excluídos por padrão** via
  `addopts = -m "not live"` em `pytest.ini`. **Não** entram no CI (rate limits/flakiness).

## Como rodar

```bash
# Suíte offline completa (inclui as 32 pré-existentes). xfails documentados são esperados.
python -m pytest tests/ -q

# Só os testes live (APIs reais). -s mostra os números de velocidade.
python -m pytest -m live -q
python -m pytest -m live tests/test_search_speed.py -s   # baseline de velocidade

# Tudo (offline + live)
python -m pytest -m "live or not live" -q
```

## Dependências

- `langdetect` — usado pelo fallback de idioma (já em `requirements.txt`).
- `pytest-benchmark` — instalado como plugin; a suíte usa medição própria (`time.perf_counter`),
  então o plugin é opcional. Instale com:
  `python -m pip install --user langdetect pytest-benchmark`.

## Regravar as fixtures

As fixtures foram geradas batendo nas APIs reais (OpenAlex/Crossref/PubMed) para os
artigos-âncora e queries de pertinência, salvando `{"url","body"}` por resposta.
Para regravar (APIs mudam contagens/rankings ao longo do tempo), rode um coletor que
repita as chamadas listadas em `tests/fixtures/README.md` e sobrescreva os arquivos.
Depois, reveja os asserts de ground truth (ano/citações podem variar) e a data no
topo de `docs/RELATORIO-QUALIDADE-BUSCA.md`.

## Bugs conhecidos

Testes `xfail` apontam para `docs/BUGS-ENCONTRADOS-BUSCA.md` (BUG-01 idioma PubMed,
BUG-02 idioma Crossref, BUG-03 dedup caixa/pontuação). Quando um bug for corrigido, o
respectivo `xfail (strict)` vira **XPASS** e falha o build — sinal para remover o marcador.
