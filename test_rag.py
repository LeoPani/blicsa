import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

df = pd.read_csv("docs/sample_dataset.csv").dropna(subset=['abstract'])
docs = df['abstract'].astype(str).tolist()

vectorizer = TfidfVectorizer(stop_words='english')
tfidf_matrix = vectorizer.fit_transform(docs)

msg = "Quais as principais descobertas sobre mineração de dados?"
query_vec = vectorizer.transform([msg])
sims = cosine_similarity(query_vec, tfidf_matrix).flatten()
top_indices = sims.argsort()[-5:][::-1]

abstracts = []
for idx in top_indices:
    if sims[idx] > 0.01:
        row = df.iloc[idx]
        title = row.get("title", "")
        abs_txt = str(row.get("abstract", ""))[:300]
        abstracts.append(f"Title: {title}\nAbstract: {abs_txt}...")

ctx = "\n\n---\n".join(abstracts)
system_prompt = "Você é o 'Blink Research', um assistente de IA focado em pesquisa dentro do software Blicsa. Ajude o usuário com sua pesquisa bibliométrica. Use markdown para formatar a resposta."
system_prompt += f"\n\nContexto relevante do corpus:\n{ctx}"

system_prompt = system_prompt[:4000]
print(f"[Blink RAG] contexto: {len(system_prompt)} chars")
print(system_prompt)
