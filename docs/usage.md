# Usage — from the first query to the exported map

*Versão em português: [uso.md](uso.md)*

This guide walks through the whole flow. To reproduce it without depending on the network, use
**`docs/sample_dataset.csv`** — 200 real records on *bibliometric analysis*, harvested from
OpenAlex, with the 13 columns of the Blicsa schema.

---

## 1. Create a project (recommended)

Blicsa works without a project, but nothing is recorded: searches, corpus and maps are lost
when you close it. With a project, everything becomes a `.blicsa` file you can keep, version
and reopen.

**My Projects → + Create project** → give it a name.

The blue bar at the top shows the open project. Without one it warns: *"No project — history
will not be saved to a project"*.

## 2. Search

**Collect → Term / Query**, pick the source (OpenAlex, Crossref or PubMed) and click
**🔍 Search**.

![Browsing results](evidence/v1_busca_navegacao.png)

What appears immediately:

- **Results: 54,581** — the **real** total in the source, not how many were downloaded;
- **the first page** (25 records) — only that page was fetched;
- **Refine results** — the facets, carrying counts for the entire universe of the search.

Nothing else was transferred. Moving between pages fetches one page at a time.

### The Qty field

Sets how many records the **import** will bring. **Empty means unlimited** — every matching
record. There is no hidden cap: the protection against downloading more than you intended is
the volume dialog, which shows the total and lets you choose.

## 3. Refine with facets

Tick values under **Type**, **Language**, **Year**, **Open access**, **Source** or **Author**.

- **Within the same category it is OR**: ticking `article` and `book-chapter` returns both.
- **Across categories it is AND**: `article` + `Portuguese` returns articles in Portuguese.

Each active filter becomes a *chip* above the list; the **✕** removes it. Counts in the other
categories update, but **the category you are filtering keeps showing all of its options** —
otherwise ticking `article` would make `book-chapter` vanish and you would be trapped by your
own filter.

## 4. Import into the corpus

Tick records individually and click **Import to corpus**, or import the whole result set.
That is where mass download happens, and the app warns about the volume beforehand.

**Offline alternative:** **Collect → Import file** and choose `docs/sample_dataset.csv` (or
your own Scopus / Web of Science export in CSV, BibTeX or plain text). This is the
reproducible path for following this guide without touching an API.

### Deduplication

When merging searches from different sources, the same article shows up more than once.
Blicsa flags duplicates by DOI and, when there is no DOI, by normalised title + year. You see
a preview before applying.

## 5. Generate the map

**Analyses → Map & AI**. Choose:

| control | what it does |
|---|---|
| **Map type** | network, overlay or density — see [mapas.md](mapas.md) |
| **Field** | where terms come from: keywords, titles, abstracts, or titles+abstracts |
| **Minimum occurrence** | drops terms appearing in too few documents |
| **Relevance** | keeps the terms most specific to the corpus |
| **Clustering resolution** | higher = more, smaller clusters |
| **Attraction / Repulsion** | layout spread |
| **Thesaurus** | unifies variants (`analyse` → `analysis`) |
| **Period** | restricts by year |

Click **Generate**.

![Network map](evidence/mapa_network.png)

## 6. Analyses

**Statistics** and **Analyses** give production per year, most frequent authors and sources,
Bradford's and Lotka's laws, and burst detection. What each number means is in
[metodos.md](methods.md).

## 7. Export

**Export** offers:

- **corpus** as CSV, Excel or BibTeX;
- **map** as PNG (including poster mode and a print theme) and interactive HTML;
- **temporal animation** of the map as GIF;
- **network** as GML, to open in Gephi or VOSviewer.

![Temporal animation](evidence/mapa_animacao.gif)

## 8. Save the project

**My Projects → Save**. The `.blicsa` file stores the corpus, the map, layout positions,
cluster labels, search history and every parameter. Reopening restores exactly the same state.

> **Projects saved before v2.0** may show **different clustering** from the original when
> reopened: until then, node insertion order was not deterministic and Louvain could reach a
> different partition from the same input. From v2.0 on, the result is reproducible. The
> corpus and the metrics do not change — only the grouping may differ.
