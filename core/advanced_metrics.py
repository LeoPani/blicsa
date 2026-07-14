import networkx as nx
import pandas as pd

from core.i18n import t

def compute_eigenvector(G: nx.Graph) -> dict:
    """Calcula a centralidade de autovetor."""
    if len(G) == 0: return {}
    try:
        return nx.eigenvector_centrality(G, max_iter=1000, weight="weight")
    except nx.PowerIterationFailedConvergence:
        return {n: 0 for n in G.nodes()}

def compute_closeness(G: nx.Graph) -> dict:
    """Calcula a centralidade de proximidade."""
    if len(G) == 0: return {}
    return nx.closeness_centrality(G, distance="weight")

def build_bipartite_network(df: pd.DataFrame, col1="authors", col2="keywords") -> nx.Graph:
    """
    Constrói uma rede 2-mode (bipartida).
    """
    B = nx.Graph()
    if df.empty or col1 not in df.columns or col2 not in df.columns:
        return B
        
    for _, row in df.iterrows():
        list1 = [x.strip() for x in str(row[col1]).split(';') if x.strip()]
        list2 = [x.strip() for x in str(row[col2]).split(';') if x.strip()]
        
        for n1 in list1:
            if n1 not in B:
                B.add_node(n1, bipartite=0)
            for n2 in list2:
                if n2 not in B:
                    B.add_node(n2, bipartite=1)
                if B.has_edge(n1, n2):
                    B[n1][n2]['weight'] += 1
                else:
                    B.add_edge(n1, n2, weight=1)
    return B

def extract_topics_lda(texts: list[str], n_topics: int = 5) -> dict:
    """
    Extrai tópicos latentes usando LDA (Topic Modeling).
    Retorna os top termos por tópico.
    """
    if not texts:
        return {}

    try:
        from sklearn.decomposition import LatentDirichletAllocation
        from sklearn.feature_extraction.text import CountVectorizer
    except ImportError:
        raise RuntimeError(t("deps.missing_ai", pkg="scikit-learn"))

    vectorizer = CountVectorizer(stop_words='english', max_df=0.9, min_df=2)
    try:
        X = vectorizer.fit_transform(texts)
    except ValueError:
        # Se o vocabulário for vazio
        return {}
        
    lda = LatentDirichletAllocation(n_components=n_topics, random_state=42)
    lda.fit(X)
    
    feature_names = vectorizer.get_feature_names_out()
    topics = {}
    
    for topic_idx, topic in enumerate(lda.components_):
        top_features_ind = topic.argsort()[:-6:-1]
        top_features = [feature_names[i] for i in top_features_ind]
        topics[f"Topic_{topic_idx}"] = top_features
        
    return topics
