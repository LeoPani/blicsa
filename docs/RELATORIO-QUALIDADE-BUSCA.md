# Relatório de qualidade das buscas — Blicsa

**Data da medição:** 2026-07-12 · **Providers:** OpenAlex, Crossref, PubMed
**Suíte:** `tests/test_search_{correctness,relevance,speed}.py` (37 testes novos)
**Ambiente:** Python 3.14.5, pytest 9.1.1, rede residencial (medições live variam).

> As APIs mudam contagens, rankings e disponibilidade de campos ao longo do tempo.
> Reexecute os testes live antes de tomar decisões com base nestes números.

---

## 1. Pertinência — precision@10 (heurística de termos/sinônimos em título+abstract+keywords)

Offline (fixtures gravadas), aceite ≥ 0.70:

| Query | OpenAlex | Crossref | PubMed |
|---|---|---|---|
| bibliometric analysis | **1.00** | **1.00** | **1.00** |
| entrepreneurship education | **1.00** | **1.00** | — |
| machine learning | **1.00** | **0.80** | **1.00** |

Todos os providers passam o limiar. O menor valor (Crossref/ML, 0.80) vem de itens
sem abstract e de matches parciais; ainda acima de 0.70. Variante live
(`test_precision_at_10_live`) confirmou ≥ 0.70 para "bibliometric analysis" nos 3.

## 2. Correção no ground truth (campos corretos / campos checados)

Artigos-âncora, um por área. "Campos" = título(fuzzy≥0.9), ano, DOI normalizado,
1º autor, fonte, citações(>limiar), idioma.

| Âncora (DOI) | Provider | Top-3? | Campos OK |
|---|---|---|---|
| VOSviewer `10.1007/s11192-009-0146-3` | OpenAlex | ✅ (#1) | **7/7** (ano 2009, 20.071 cites, en, van Eck) |
| Shane 2000 `10.5465/amr.2000.2791611` | Crossref | ❌ (ver OBS-03) | **7/7** via fixture por DOI (2000, 2.730 cites, en, Shane) |
| Livak 2001 `10.1006/meth.2001.1262` | PubMed | ✅ (#2) | **6/6** (2001, eng, Livak, *Methods*) — citações N/A (OBS-04) |

- **Abstract (inverted index) do OpenAlex:** reconstrução idêntica à referência
  independente, não-vazia, inicia em "We present VOSviewer…" — sem palavras trocadas/dup.
- **Schema entre providers:** os 3 emitem **exatamente** as mesmas 13 chaves; campos de
  texto nunca `None`; tipos corretos (`year:int`, `citations:int`, `is_oa:bool`).
- **Fallback de idioma:** abstract em PT sem `language` → `pt`/`detected`; com `language`
  presente → mantém/`api`. (Lógica espelhada de `main.py:1745-1767`; ver OBS-05.)

## 3. Filtros

| Filtro | OpenAlex | Crossref | PubMed |
|---|---|---|---|
| ano (intervalo) | ✅ 100% no range | ✅ 100% no range | (via `[DP]`, não medido isolado) |
| open access | ✅ 100% `is_oa` | (pós-filtro CC) | ❌ sempre `is_oa=False` (OBS-04) |
| idioma | ✅ ≥90% no idioma | ❌ **ignorado (BUG-02)** | ❌ **0 resultados (BUG-01)** |
| sintaxe query builder | ✅ `TITLE`/`YEAR` → filtro certo | — | — |

## 4. Deduplicação (`core.harmonization.fuzzy_deduplicate_papers`)

- ✅ remove duplicata exata e títulos ~95–99% similares;
- ✅ preserva artigos distintos de títulos parecidos (sem falso positivo);
- ✅ trilha de contagem consistente (`baixados − removidos == importados`);
- ✅ mesmo DOI com/sem prefixo `https` + título idêntico → deduplicado;
- ❌ **caixa/pontuação diferentes não são normalizadas (BUG-03).**

Paginação (OpenAlex): pedir 250 → exatamente 250, 3 páginas via cursor, **DOIs únicos**;
pedir 50 → 50 em 1 requisição.

## 5. Velocidade (live, mediana de 3 repetições · 100 records · "bibliometric analysis")

| Provider | Mediana 100 rec | Throughput | Latência 1º record | Cancelamento |
|---|---|---|---|---|
| OpenAlex | ~2.0 s | ~49 rec/s | ~1.9 s | **0.00 s** após pedido |
| Crossref | ~4.0 s | ~25 rec/s | ~3.6 s | **0.00 s** após pedido |
| PubMed   | ~1.8 s | ~57 rec/s | ~2.3 s | **0.00 s** após pedido |

- Nenhum estouro do timeout duro de 120 s.
- **Crossref é o mais lento e o mais variável** (repetições de 3.6 s a 7.9 s); a latência
  da 1ª página domina a percepção. OpenAlex e PubMed são consistentes.
- **Cancelamento é imediato** nos 3 (para em ~0 s após o pedido; a busca de 500 parou
  após a 1ª página com 100 records íntegros, sem corrupção de estado).

---

## Bugs encontrados (não corrigidos — ver `docs/BUGS-ENCONTRADOS-BUSCA.md`)

| ID | Severidade | Resumo |
|---|---|---|
| **BUG-01** | Alta | PubMed: filtro de idioma usa ISO-639-1 (`pt`/`en`) mas a API exige `por`/`eng` → **0 resultados silenciosos**. |
| **BUG-02** | Alta | Crossref: filtro de idioma **ignorado** por completo. |
| **BUG-03** | Média | Dedup fuzzy é sensível a caixa/pontuação → duplicatas do mesmo artigo sobrevivem. |
| OBS-03 | Média | Crossref rankeia reimpressões acima do artigo seminal na busca por título. |
| OBS-04 | Média | PubMed nunca preenche `citations`/`is_oa`. |
| OBS-05 | Baixa | `language_source`/detecção de idioma presa na thread de UI, não testável isoladamente. |

## Recomendação priorizada (o que corrigir depois)

1. **BUG-01 (PubMed idioma)** — maior impacto/menor esforço: mapear `pt→por`, `en→eng`,
   `es→spa`, `fr→fre` em `core/sources/pubmed.py:37`. Hoje o filtro zera a busca.
2. **BUG-02 (Crossref idioma)** — pós-filtrar por `language` em Python (como já é feito
   com `is_oa`) ou desabilitar o controle de idioma na UI quando a fonte é Crossref.
3. **BUG-03 (dedup)** — normalizar título (lowercase + strip de pontuação) antes do
   `difflib` em `core/harmonization.py`, unificando com o `norm_title` de `main.py`
   (hoje há duas lógicas de dedup divergentes).
4. **OBS-04 (PubMed cites/OA)** — enriquecer com ELink/iCite se citações forem relevantes;
   ao menos avisar na UI que ordenar por citação exclui o PubMed.
5. **OBS-05 (refatorar idioma)** — extrair a detecção de `main.py:1745-1767` para uma
   função pura em `core/` e testá-la de verdade (hoje só a espelhamos).
6. **OBS-03 (ranking Crossref)** — para busca por título exato, priorizar
   `query.title` ou reordenar por similaridade de título no cliente.

## Como reproduzir

```bash
python -m pytest tests/ -q            # offline (62 passed, xfails documentados)
python -m pytest -m live -q           # live nas APIs reais
python -m pytest -m live tests/test_search_speed.py -s   # baseline de velocidade
```
