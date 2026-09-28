import sys
import os
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath("."))
from core.sources.openalex import OpenAlexProvider
from core.matrix_builders import NetworkGenerator
from core.project import create_project, save_blicsa_project, project_dir, append_backlog, normalize_dataframe
from core.visualizer import compute_fa2_layout

queries = {
    "PatentBERT": '("patent classification" OR "patent retrieval" OR "patent text mining") AND ("BERT" OR "transformer" OR "pretrained language model")',
    "DSR e PI": '("design science research") AND ("technology transfer" OR "intellectual property management" OR "innovation management")',
    "Grace Period": '"patent" AND "grace period" AND ("disclosure" OR "novelty")',
    "IA Prior Art": '("artificial intelligence" OR "large language model") AND "prior art" AND "patent"'
}

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
    
    # Top 30 nodes get labels for better insights
    weights = {n: G.nodes[n].get("weight", G.degree(n)) for n in G.nodes()}
    top_nodes = set(sorted(G.nodes(), key=lambda n: weights[n], reverse=True)[:30])
    labels = {n: (n[:30] + '..' if len(n)>30 else n) if n in top_nodes else "" for n in G.nodes()}
    
    nx.draw_networkx_labels(G, pos, labels, font_size=10, font_weight="bold", font_family="sans-serif")
    
    plt.title(title, fontsize=18, pad=20)
    plt.axis("off")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, bbox_inches="tight", dpi=200)
    plt.close()

def extrair_insights(df, G_authors, G_terms):
    """Usa a mesma contagem verificável do fluxo de consolidação local."""
    from run_consolidated_from_blicsa import build_insights
    return build_insights(df, G_authors, G_terms)

def main():
    provider = OpenAlexProvider()
    all_dfs = []
    
    print("=== Baixando todos os dados para Análise Conjunta ===")
    
    for name, q in queries.items():
        records = []
        # Limite mais conservador para evitar 429
        limit = 200
        attempts = 0
        max_attempts = 3
        while attempts < max_attempts:
            try:
                for rec in provider.search(q, max_results=limit):
                    rec["subsearch"] = name
                    records.append(rec)
                break
            except Exception as e:
                attempts += 1
                print(f"Erro ao buscar {name} (tentativa {attempts}/{max_attempts}): {e}")
                if attempts < max_attempts:
                    import time
                    time.sleep(10)
                else:
                    print(f"Falha permanente na busca {name}; continuando com dados parciais.")
        # Pequena pausa entre sub‑buscas para respeitar a API
        import time
        time.sleep(5)
            
        df = pd.DataFrame(records)
        all_dfs.append(df)
        
    df_global = pd.concat(all_dfs, ignore_index=True)
    from run_consolidated_from_blicsa import deduplicate_works
    df_global = deduplicate_works(df_global)
    print(f"Total de registros consolidados: {len(df_global)}")
    
    project_name = "Seminario Qualificacao - Consolidado"
    project_slug = create_project(project_name)
    p_dir = project_dir(project_slug)
    exports_dir = p_dir / "exports"
    
    df_global = normalize_dataframe(df_global)
    gen = NetworkGenerator(df_global)
    
    print("Gerando mapas globais...")
    # Coautoria global (Autores colaborando)
    G_authors = gen.build_coauthorship_network(min_publications=2)
    export_network_png(G_authors, str(exports_dir / f"mapa_coautoria_global.png"), "Coautoria Global - Autores")
    
    # Termos globais
    G_terms = gen.build_keyword_cooccurrence(min_occurrence=3, field="keywords")
    export_network_png(G_terms, str(exports_dir / f"mapa_termos_global.png"), "Coocorrência de Termos Global")
    
    pos = compute_fa2_layout(G_terms) # Usaremos a rede de termos como rede principal no arquivo blicsa
    
    print("Extraindo insights formatados...")
    texto_insights = extrair_insights(df_global, G_authors, G_terms)
    
    with open(exports_dir / "INSIGHTS_SEMINAIS.md", "w", encoding="utf-8") as f:
        f.write("# Insights da Análise Conjunta\n\n")
        f.write(texto_insights)
    
    save_blicsa_project(
        path=str(p_dir / "project.blicsa"),
        df=df_global,
        config={"name": project_name, "research_context": "Análise Conjunta Consolidada"},
        positions=pos,
        G=G_terms,
        cluster_labels=None
    )
    append_backlog(project_slug, "import", {"msg": "Projeto consolidado gerado"})
    print(f"Pronto! Projeto Consolidado em {p_dir}")

if __name__ == "__main__":
    main()
