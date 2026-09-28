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
    plt.figure(figsize=(12, 12))
    
    partition = nx.get_node_attributes(G, "group")
    if partition:
        colors = plt.get_cmap("tab20")
        node_colors = [colors(partition.get(n, 0) % 20) for n in G.nodes()]
    else:
        node_colors = ['blue'] * len(G.nodes())
        
    sizes = [max(10, G.nodes[n].get("size", 10)) * 5 for n in G.nodes()]
    
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=sizes, alpha=0.8)
    nx.draw_networkx_edges(G, pos, alpha=0.2)
    
    weights = {n: G.nodes[n].get("weight", G.degree(n)) for n in G.nodes()}
    top_nodes = set(sorted(G.nodes(), key=lambda n: weights[n], reverse=True)[:15])
    labels = {n: n if n in top_nodes else "" for n in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8)
    
    plt.title(title)
    plt.axis("off")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, bbox_inches="tight", dpi=150)
    plt.close()

def main():
    provider = OpenAlexProvider()
    
    for name, q in queries.items():
        project_name = f"Seminario Qualificacao - {name}"
        print(f"=== Processando: {project_name} ===")
        
        # 1. Busca
        records = []
        count = provider.count(q)
        print(f"Total na base: {count}")
        
        for i, rec in enumerate(provider.search(q, max_results=100000)):
            records.append(rec)
            
        df = pd.DataFrame(records)
        orig_len = len(df)
        
        # Deduplicação
        if not df.empty:
            df.loc[df["doi"] == "", "doi"] = None
            df = df.drop_duplicates(subset=["doi"], keep="first").fillna("")
            if "title" in df.columns:
                df = df.drop_duplicates(subset=["title"], keep="first")
        
        final_len = len(df)
        print(f"Baixados {orig_len} -> Após deduplicação: {final_len}")
        
        # 2. Cria Projeto
        project_slug = create_project(project_name)
        p_dir = project_dir(project_slug)
        exports_dir = p_dir / "exports"
        os.makedirs(exports_dir, exist_ok=True)
        
        # 3. Normaliza e Gera Redes
        df = normalize_dataframe(df)
        gen = NetworkGenerator(df)
        
        # Mapa principal (Cocitação)
        G_cocit = gen.build_cocitation_network(min_cocitations=2)
        pos_cocit = compute_fa2_layout(G_cocit)
        
        # Salva PNG de cocitação
        png_path = exports_dir / f"mapa_cocitacao_{project_slug}.png"
        export_network_png(G_cocit, str(png_path), f"Cocitação - {name}")
        print(f"Mapa salvo: {png_path}")
        
        # Se for PatentBERT ou DSR, gerar também de termos
        if name in ["PatentBERT", "DSR e PI"]:
            G_terms = gen.build_keyword_cooccurrence(min_occurrence=2, field="keywords")
            terms_path = exports_dir / f"mapa_termos_{project_slug}.png"
            export_network_png(G_terms, str(terms_path), f"Termos - {name}")
            print(f"Mapa salvo: {terms_path}")
            
        # 4. Salva .blicsa
        save_blicsa_project(
            path=str(p_dir / "project.blicsa"),
            df=df,
            config={"name": project_name, "research_context": "Busca automatizada OpenAlex"},
            positions=pos_cocit,
            G=G_cocit,
            cluster_labels=None,
            searches=[{"query": q, "count": count, "downloaded": orig_len, "deduped": final_len}]
        )
        append_backlog(project_slug, "import", {"msg": "Importado do script"})
        print(f"Projeto salvo em {p_dir}\n")

if __name__ == "__main__":
    main()
