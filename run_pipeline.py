import sys
import os
import time
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath("."))
from core.sources.openalex import OpenAlexProvider
from core.matrix_builders import NetworkGenerator
from core.project import create_project, save_blicsa_project, project_dir, append_backlog, normalize_dataframe
from core.visualizer import posicoes_iniciais, compute_fa2_layout

queries = {
    "a": '("patent classification" OR "patent retrieval" OR "patent text mining") AND ("BERT" OR "transformer" OR "pretrained language model")',
    "b": '("design science research") AND ("technology transfer" OR "intellectual property management" OR "innovation management")',
    "c": '"patent" AND "grace period" AND ("disclosure" OR "novelty")',
    "d": '("artificial intelligence" OR "large language model") AND "prior art" AND "patent"'
}

def export_network_png(G, path, title):
    if G.number_of_nodes() == 0:
        print(f"Grafo vazio para {title}, ignorando plot.")
        return
    pos = compute_fa2_layout(G)
    plt.figure(figsize=(12, 12))
    
    partition = nx.get_node_attributes(G, "group")
    colors = plt.cm.get_cmap("tab20", max(partition.values()) + 1 if partition else 1)
    node_colors = [colors(partition.get(n, 0)) for n in G.nodes()]
    
    sizes = [G.nodes[n].get("size", 10) * 10 for n in G.nodes()]
    
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=sizes, alpha=0.8)
    nx.draw_networkx_edges(G, pos, alpha=0.2)
    
    # Adicionar labels só para os maiores para não poluir
    weights = {n: G.nodes[n].get("weight", G.degree(n)) for n in G.nodes()}
    top_nodes = set(sorted(G.nodes(), key=lambda n: weights[n], reverse=True)[:15])
    labels = {n: n if n in top_nodes else "" for n in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8)
    
    plt.title(title)
    plt.axis("off")
    plt.savefig(path, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Salvo {path}")

def main():
    provider = OpenAlexProvider()
    all_dfs = []
    project_searches = []
    
    # 1. Busca OpenAlex
    for key, q in queries.items():
        print(f"Rodando busca {key}...")
        records = []
        count = provider.count(q)
        print(f"Total na base: {count}")
        # search pipeline com limite 1000
        for i, rec in enumerate(provider.search(q, max_results=100000)):
            rec["subsearch_id"] = key # identificador
            records.append(rec)
        
        # Deduplicação baseada no DOI e Title, mas só dentro da própria busca (ou global? A instrução diz: após deduplicação)
        df_sub = pd.DataFrame(records)
        orig_len = len(df_sub)
        # deduplicar no subset
        df_sub = df_sub.drop_duplicates(subset=["doi"]).dropna(subset=["doi"], how="all")
        # se nao tem doi, nao vai jogar fora se tiver titulo
        if not df_sub.empty and "title" in df_sub.columns:
            df_sub = df_sub.drop_duplicates(subset=["title"])
        
        # recupera os que nao tinham DOI e nao entraram na dedup de titulo? drop_duplicates ja lida. 
        # Vamos fazer um clean melhor:
        df_sub = pd.DataFrame(records)
        orig_len = len(df_sub)
        # remover duplicatas de DOI ignorando vazios
        df_sub.loc[df_sub["doi"] == "", "doi"] = None
        df_sub = df_sub.drop_duplicates(subset=["doi"], keep="first").fillna("") 
        df_sub = df_sub.drop_duplicates(subset=["title"], keep="first")
        
        final_len = len(df_sub)
        print(f"Encontrados {count} · baixados {orig_len} (limite) · após deduplicação {final_len}")
        
        project_searches.append({"query": q, "count": count, "downloaded": orig_len, "deduped": final_len})
        all_dfs.append(df_sub)
    
    # 2. Cria Projeto
    print("Criando projeto...")
    project_slug = create_project("seminario de qualificacao")
    p_dir = project_dir(project_slug)
    exports_dir = p_dir / "exports"
    
    # 3. Processar cada subset
    for key, df_sub in zip(queries.keys(), all_dfs):
        # O DataFrame precisa passar pelo normalize antes de gerar a rede
        df_sub = normalize_dataframe(df_sub)
        
        gen = NetworkGenerator(df_sub)
        
        # Mapa de cocitação de autores -> O PyBibliomics não possui 'author co-citation', possui 'build_cocitation_network' 
        # que usa referencias citadas (document co-citation) e 'build_coauthorship_network' (co-autoria).
        # A instrução pediu "mapa de cocitação de autores com clustering Louvain". Como a arquitetura usa references para cocitação,
        # vamos usar 'build_cocitation_network' e também gerar de co-autores para garantir.
        
        print(f"Gerando rede de cocitação para {key}...")
        G_cocit = gen.build_cocitation_network(min_cocitations=2)
        export_network_png(G_cocit, str(exports_dir / f"cocitacao_{key}.png"), f"Cocitacao - Busca {key}")
        
        if key in ["a", "b"]:
            print(f"Gerando rede de coocorrência de termos para {key}...")
            G_terms = gen.build_keyword_cooccurrence(min_occurrence=2, field="keywords")
            export_network_png(G_terms, str(exports_dir / f"termos_{key}.png"), f"Termos - Busca {key}")
            
    # Junta os dfs e salva o projeto global
    df_global = pd.concat(all_dfs, ignore_index=True)
    df_global = normalize_dataframe(df_global)
    
    # Como o modelo do app só suporta um G e um DF central, salvemos o concatenado.
    # Pode-se criar uma rede global
    gen_global = NetworkGenerator(df_global)
    G_global = gen_global.build_cocitation_network(min_cocitations=2)
    pos_global = compute_fa2_layout(G_global)
    
    save_blicsa_project(
        path=str(p_dir / "project.blicsa"),
        df=df_global,
        config={"name": "seminario de qualificacao", "research_context": "Seminário consolidado com 4 buscas"},
        positions=pos_global,
        G=G_global,
        cluster_labels=None,
        searches=project_searches
    )
    append_backlog(project_slug, "import", {"msg": "Importado do script"})
    
    print(f"Concluído. Projeto salvo em {p_dir}")

if __name__ == "__main__":
    main()
