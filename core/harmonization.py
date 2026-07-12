import difflib
import re
from collections import defaultdict


def _dedup_key(title) -> str:
    """Chave normalizada para comparação de títulos (casefold, sem pontuação,
    espaços colapsados). NÃO altera os dados exibidos — só a comparação."""
    t = str(title).casefold()
    t = re.sub(r"[^\w\s]", " ", t)     # remove pontuação
    t = re.sub(r"\s+", " ", t).strip()  # colapsa espaços
    return t

def harmonize_authors(authors: list[str], cutoff=0.85) -> list[str]:
    """
    Funde nomes de autores sinônimos usando fuzzy matching básico.
    Ex: 'Silva, J.' e 'Silva, João' -> 'Silva, João'
    """
    if not authors:
        return []
    
    # Sort by length descending so we keep the longest form (e.g. Silva, João over Silva, J.)
    authors_sorted = sorted(authors, key=len, reverse=True)
    canonical = {}
    
    for author in authors_sorted:
        match = difflib.get_close_matches(author, canonical.keys(), n=1, cutoff=cutoff)
        if match:
            # We found a longer representation previously
            canonical[author] = match[0]
        else:
            canonical[author] = author
            
    return [canonical[a] for a in authors]

def fuzzy_deduplicate_papers(df, title_col="title", threshold=0.93):
    """
    Simula uma deduplicação fuzzy baseada em similaridade de títulos.
    """
    if df.empty or title_col not in df.columns:
        return df
        
    keep_indices = []
    seen = set()  # chaves normalizadas já vistas

    for i, row in df.iterrows():
        key = _dedup_key(row[title_col])
        if key in seen:
            continue

        match = difflib.get_close_matches(key, seen, n=1, cutoff=threshold)
        if not match:
            seen.add(key)
            keep_indices.append(i)

    return df.loc[keep_indices].copy()
