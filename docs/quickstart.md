# Quickstart Guide

This guide will help you get started with **Blicsa (PyBibliomics)**.

## 1. Import Data

Blicsa supports importing bibliographic data from Scopus, Web of Science, PubMed, OpenAlex, and Crossref.

To test the application:
1. Click **➕ Adicionar** in the **Data Import** tab.
2. Select the sample file: `docs/sample_dataset.csv`.
3. Set the default format option to **Scopus** (since our sample CSV matches standard Scopus schema columns).
4. Click **⚡ Carregar e Combinar**.

## 2. Search Online

You can search literature directly:
1. Under **Busca Online**, select **OpenAlex**, **Crossref**, or **PubMed**.
2. Type a query (e.g., `deep learning`).
3. Click **🔍 Buscar**. Results will be dynamically fetched, normalized, and merged.

Leaving the **Qtd** field empty means *unlimited* — every matching record is imported. The
protection against downloading more than you meant to is the volume dialog, which shows the
real total and lets you choose; there is no silent cap.

### Known limits of each source

These are limits of the APIs, not of Blicsa. Blicsa always reports the real total of the
search, so you can tell the difference between "that is all there is" and "that is all the
API will give".

| source | browsing (page by page) | importing (full download) |
|---|---|---|
| **OpenAlex** | first **10,000** results | **no limit** — uses cursor pagination |
| **PubMed** | first **10,000** results | **9,999 records per search** |
| **Crossref** | — | **no limit** — uses cursor pagination |

**The PubMed ceiling is hard.** The NCBI E-utilities refuse to return more than 9,999 records
for a single query, even using the server-side history (`usehistory=y` + `WebEnv`), which is
the documented way to page through large sets. Asking for `retstart=10000` returns:

> `'retstart' cannot be larger than 9998. For PubMed, ESearch can only retrieve the first
> 9,999 records matching the query.`

When a PubMed import hits it, the count trail says so explicitly — *"teto do PubMed: 9.999
registros por busca (limite do NCBI)"* — and the real total of the base stays visible next to
it. **To cover a larger PubMed set, split the search into narrower queries** (by year range,
journal, or subject terms) and import each one; Blicsa deduplicates on merge.

## 3. Generate Map

Once data is loaded:
1. Switch to the **Mapa & IA** tab.
2. Select your desired settings (e.g., Map Type, Field) and click **Gerar** in the left config panel.
3. Interact with the generated network map! Pass the mouse over nodes to highlight their connections in the cluster color.

## 4. Save and Export

- Save the complete project state (data, configuration, layout coordinates, cluster names) in `.blicsa` format.
- Export network files for **Gephi** (GEXF) or **VOSviewer** (Map/Net txt files).
