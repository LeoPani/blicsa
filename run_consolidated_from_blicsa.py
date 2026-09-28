import os
import json
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path
import sys
import re
import unicodedata

# Ensure repo root is in path for imports
sys.path.insert(0, os.path.abspath('.'))

from core.project import (
    create_project,
    save_blicsa_project,
    project_dir,
    append_backlog,
    normalize_dataframe,
)
from core.matrix_builders import NetworkGenerator
from core.seminal import ranked_corpus_authors, top_references
from core.visualizer import compute_fa2_layout


def export_network_png(G: nx.Graph, out_path: str, title: str) -> None:
    """Export a NetworkX graph as a PNG using FA2 layout.
    All files are written inside the project's ``exports/`` folder (writable).
    """
    if G.number_of_nodes() == 0:
        return
    pos = compute_fa2_layout(G)
    plt.figure(figsize=(16, 12))
    groups = nx.get_node_attributes(G, "group")
    if groups:
        cmap = plt.get_cmap("tab20")
        colors = [cmap(groups.get(n, 0) % 20) for n in G.nodes]
    else:
        colors = ["#1E4DA0"] * G.number_of_nodes()
    sizes = [max(20, G.nodes[n].get("size", 10)) * 5 for n in G.nodes]
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=sizes, alpha=0.8, edgecolors='white', linewidths=1.5)
    nx.draw_networkx_edges(G, pos, alpha=0.15)
    plt.title(title, fontsize=18, pad=20)
    plt.axis('off')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, bbox_inches='tight', dpi=200)
    plt.close()


def load_blicsa_dataframe(blicsa_path: Path) -> pd.DataFrame:
    """Open a .blicsa ZIP and return its DataFrame.
    Uses the helper ``load_blicsa_project`` which returns a dict containing ``df``.
    """
    from core.project import load_blicsa_project
    data = load_blicsa_project(str(blicsa_path))
    df = data.get('df')
    return df if df is not None else pd.DataFrame()


def gather_all_data(projects_root: Path) -> pd.DataFrame:
    """Junta apenas projetos de origem, sem reintroduzir consolidados antigos.

    O próprio script cria um projeto sob essa pasta; incluí-lo na execução seguinte
    multiplicava registros e infla as contagens do relatório.
    """
    frames = []
    for proj_dir in sorted(projects_root.iterdir()):
        if not proj_dir.is_dir() or "consolidado" in proj_dir.name.casefold():
            continue
        blicsa_file = proj_dir / 'project.blicsa'
        if blicsa_file.is_file():
            df = load_blicsa_dataframe(blicsa_file)
            if not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return deduplicate_works(pd.concat(frames, ignore_index=True))


def _work_keys(row: pd.Series) -> list[tuple]:
    keys = []
    doi = str(row.get("doi") or "").strip().lower()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi)
    if doi and doi not in {"nan", "none"}:
        keys.append(("doi", doi))
    title = str(row.get("title") or "").strip()
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    if title:
        try:
            year = int(float(row.get("year") or 0))
        except (TypeError, ValueError):
            year = 0
        keys.append(("title", title, year))
    return keys


def deduplicate_works(df: pd.DataFrame) -> pd.DataFrame:
    """Uma obra por DOI ou título+ano; prefere o registro com metadados mais completos."""
    if df.empty:
        return df.copy()
    output: list[pd.Series] = []
    positions: dict[tuple, int] = {}
    for _, row in df.iterrows():
        keys = _work_keys(row)
        existing = next((positions[key] for key in keys if key in positions), None)
        if existing is None:
            for key in keys:
                positions[key] = len(output)
            output.append(row.copy())
            continue
        for key in keys:
            positions[key] = existing
        current = output[existing]
        for field in ("authors", "title", "source", "keywords", "abstract", "doi",
                      "references", "origin", "language", "oa_url"):
            new_value = row.get(field)
            old_value = current.get(field)
            if (not str(old_value or "").strip() or str(old_value).lower() == "nan") \
                    and str(new_value or "").strip() not in {"", "nan"}:
                current[field] = new_value
        for field in ("citations",):
            try:
                current[field] = max(int(float(current.get(field) or 0)),
                                     int(float(row.get(field) or 0)))
            except (TypeError, ValueError):
                pass
    return pd.DataFrame(output).reset_index(drop=True)


def build_insights(df: pd.DataFrame, G_authors: nx.Graph, G_terms: nx.Graph) -> str:
    """Relatório baseado em campos verificáveis, sem atribuir uma obra ao autor errado."""
    insights = []
    authors = ranked_corpus_authors(df)
    insights.append('### Autores dos artigos do corpus por citações recebidas')
    insights.append('Este ranking soma as citações recebidas pelos artigos do corpus. '
                    'Ele não identifica, sozinho, os autores seminais citados por esses artigos.')
    if not authors:
        insights.append('Nenhum autor identificado nos registros.')
    for i, item in enumerate(authors, 1):
        insights.append(f'{i}. **{item["author"]}** — {item["citations"]} citações '
                        f'em {item["papers"]} artigo(s).')
        if item['top_title']:
            insights.append(f'   - Obra no corpus: {item["top_title"]} '
                            f'({item["top_year"]}; {item["top_citations"]} citações).')

    references = top_references(df, limit=15)
    insights.append('\n### Obras mais citadas nas referências do corpus')
    if references:
        insights.append('Contagem: número de artigos do corpus que citam cada referência. '
                        'Identificadores OpenAlex só recebem autor e título após consulta exata aos metadados.')
        for i, (reference, count) in enumerate(references, 1):
            insights.append(f'{i}. {reference} — citado por {count} artigo(s).')
    else:
        insights.append('Os registros não incluem referências citadas suficientes para esta análise.')
    # Principais termos
    weights = {n: G_terms.nodes[n].get('weight', G_terms.degree(n)) for n in G_terms.nodes()}
    top_terms = sorted(G_terms.nodes(), key=lambda n: weights[n], reverse=True)[:15]
    if top_terms:
        insights.append('\n### Principais conceitos e termos (rede de coocorrência)')
        for i, term in enumerate(top_terms, 1):
            occ = G_terms.nodes[term].get('occurrence', '?')
            insights.append(f'{i}. **{term.title()}** (aparece em {occ} documentos)')
    # Top artigos citados
    insights.append('\n### 📚 Top 10 Artigos Mais Citados da Base')
    top_papers = df.sort_values(by='citations', ascending=False).head(10)
    for i, (_, row) in enumerate(top_papers.iterrows(), 1):
        title = str(row.get('title', '')).replace('|', ' ').strip()
        year = row.get('year', '?')
        cits = int(float(row.get('citations', 0) or 0))
        insights.append(f'{i}. *{title}* ({year}) — **{cits} citações**')
    return '\n'.join(insights)


def main():
    projects_root = Path(os.path.expanduser('~/Blicsa/projects'))
    print('Carregando dados de todos os .blicsa …')
    df = gather_all_data(projects_root)
    if df.empty:
        print('⚠️  Nenhum registro encontrado em nenhum .blicsa. Abortando.')
        return
    print(f'Total de registros únicos dos projetos de origem: {len(df)}')
    df = normalize_dataframe(df)
    # Gerar redes
    gen = NetworkGenerator(df)
    G_authors = gen.build_coauthorship_network(min_publications=2)
    G_terms = gen.build_keyword_cooccurrence(min_occurrence=3, field='keywords')
    # Criar projeto consolidado
    project_name = 'Seminario Qualificacao – Consolidado (Local .blicsa)'
    slug = create_project(project_name)
    p_dir = project_dir(slug)
    exports_dir = p_dir / 'exports'
    os.makedirs(exports_dir, exist_ok=True)
    # Exportar PNGs (sem dependência de pyvis)
    export_network_png(G_authors, str(exports_dir / 'mapa_coautoria_global.png'), 'Coautoria Global – Autores')
    export_network_png(G_terms, str(exports_dir / 'mapa_termos_global.png'), 'Coocorrência de Termos Global')
    # Gerar insights markdown
    insights_md = build_insights(df, G_authors, G_terms)
    with open(exports_dir / 'INSIGHTS_SEMINAIS.md', 'w', encoding='utf-8') as f:
        f.write('# Insights da Análise Conjunta (Base Local)\n\n')
        f.write(insights_md)
    # Salvar .blicsa (usa layout de termos)
    pos = compute_fa2_layout(G_terms)
    save_blicsa_project(
        path=str(p_dir / 'project.blicsa'),
        df=df,
        config={
            'name': project_name,
            'research_context': 'Consolidação a partir dos .blicsa locais',
        },
        positions=pos,
        G=G_terms,
        cluster_labels=None,
    )
    append_backlog(slug, 'import', {'msg': 'Projeto consolidado a partir de .blicsa locais'})
    print(f'✅ Projeto consolidado criado em {p_dir}')

if __name__ == '__main__':
    main()
