import os
import json
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path

# Add project root to path for imports
import sys
sys.path.insert(0, os.path.abspath('.'))

from core.project import create_project, save_blicsa_project, project_dir, append_backlog, normalize_dataframe
from core.matrix_builders import NetworkGenerator
from core.visualizer import compute_fa2_layout

def export_network_png(G, path, title):
    if G.number_of_nodes() == 0:
        return
    pos = compute_fa2_layout(G)
    plt.figure(figsize=(16, 12))
    partition = nx.get_node_attributes(G, "group")
    if partition:
        colors = plt.get_cmap("tab20")
        node_colors = [colors(partition.get(n, 0) % 20) for n in G.nodes()]
    else:
        node_colors = ['#1E4DA0'] * len(G.nodes())
    sizes = [max(20, G.nodes[n].get("size", 10)) * 5 for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=sizes, alpha=0.8, edgecolors='white', linewidths=1.5)
    nx.draw_networkx_edges(G, pos, alpha=0.15)
    plt.title(title, fontsize=18, pad=20)
    plt.axis('off')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, bbox_inches='tight', dpi=200)
    plt.close()

def load_local_searches(base_path: Path) -> pd.DataFrame:
    """Read all JSON result files from the individual seminar projects.
    The Blicsa projects store raw OpenAlex JSON under `searches/`.
    This function merges all those records into a single DataFrame.
    """
    records = []
    for proj in base_path.glob('seminario-qualificacao-*'):
        if 'consolidado' in proj.name.casefold():
            continue
        searches_dir = proj / 'searches'
        if not searches_dir.is_dir():
            continue
        for json_file in searches_dir.glob('search_*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # o formato salvo pelo Blicsa costuma ser um dict com chave 'results'
                    if isinstance(data, dict) and 'results' in data:
                        records.extend(data['results'])
                    elif isinstance(data, list):
                        records.extend(data)
            except Exception as e:
                print(f"Erro ao ler {json_file}: {e}")
    return pd.DataFrame(records)

def extrair_insights(df, G_authors, G_terms):
    """Usa a mesma contagem verificável do fluxo de consolidação local."""
    from run_consolidated_from_blicsa import build_insights
    return build_insights(df, G_authors, G_terms)

def main():
    base_projects = Path(os.path.expanduser('~/Blicsa/projects'))
    print('Carregando resultados locais das pastas de projetos...')
    df_global = load_local_searches(base_projects)
    if df_global.empty:
        print('⚠️  Nenhum registro encontrado nos diretórios locais. Abortando.')
        return
    print(f'Total de registros consolidados: {len(df_global)}')
    # Normaliza colunas esperadas pelo core
    from run_consolidated_from_blicsa import deduplicate_works
    df_global = normalize_dataframe(deduplicate_works(df_global))
    gen = NetworkGenerator(df_global)
    # -------- Gerar redes --------
    G_authors = gen.build_coauthorship_network(min_publications=2)
    G_terms = gen.build_keyword_cooccurrence(min_occurrence=3, field='keywords')
    # -------- Salvar projeto --------
    project_name = 'Seminario Qualificacao - Consolidado (Local)'
    slug = create_project(project_name)
    p_dir = project_dir(slug)
    exports_dir = p_dir / 'exports'
    os.makedirs(exports_dir, exist_ok=True)
    export_network_png(G_authors, str(exports_dir / 'mapa_coautoria_global.png'), 'Coautoria Global - Autores')
    export_network_png(G_terms, str(exports_dir / 'mapa_termos_global.png'), 'Coocorrência de Termos Global')
    # Salvar insights
    insights_md = extrair_insights(df_global, G_authors, G_terms)
    with open(exports_dir / 'INSIGHTS_SEMINAIS.md', 'w', encoding='utf-8') as f:
        f.write('# Insights da Análise Conjunta (Local)\n\n')
        f.write(insights_md)
    # Salvar .blicsa usando a rede de termos como layout principal
    pos = compute_fa2_layout(G_terms)
    save_blicsa_project(
        path=str(p_dir / 'project.blicsa'),
        df=df_global,
        config={'name': project_name, 'research_context': 'Análise Conjunta a partir de dados locais'},
        positions=pos,
        G=G_terms,
        cluster_labels=None,
    )
    append_backlog(slug, 'import', {'msg': 'Projeto consolidado a partir de dados locais'})
    print(f'✅ Projeto consolidado pronto em {p_dir}')

if __name__ == '__main__':
    main()
