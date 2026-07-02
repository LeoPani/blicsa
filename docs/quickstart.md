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

## 3. Generate Map

Once data is loaded:
1. Switch to the **Mapa & IA** tab.
2. Select your desired settings (e.g., Map Type, Field) and click **Gerar** in the left config panel.
3. Interact with the generated network map! Pass the mouse over nodes to highlight their connections in the cluster color.

## 4. Save and Export

- Save the complete project state (data, configuration, layout coordinates, cluster names) in `.blicsa` format.
- Export network files for **Gephi** (GEXF) or **VOSviewer** (Map/Net txt files).
