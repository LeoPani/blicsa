import re
import csv
from pathlib import Path

STOP_WORDS_EN: set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should", "may", "might",
    "must", "can", "could", "this", "that", "these", "those", "i", "we",
    "you", "he", "she", "it", "they", "them", "their", "our", "its", "my",
    "which", "who", "what", "when", "where", "how", "all", "both", "each",
    "more", "also", "than", "then", "so", "if", "as", "not", "no", "nor",
    "such", "while", "however", "therefore", "thus", "study", "method",
    "result", "results", "analysis", "approach", "paper", "research",
    "proposed", "based", "using", "used", "new", "show", "data", "first",
    "second", "high", "low", "large", "small", "different", "use", "present",
    "provide", "work", "system", "model", "two", "three", "one", "many",
    "several", "various", "number", "type", "types", "set", "sets",
    "including", "included", "include", "although", "addition", "due",
    "well", "known", "found", "given", "made", "make", "between", "among",
    "without", "within", "across", "toward", "towards", "upon", "since",
    "before", "after", "while", "because", "other", "same", "good",
    "better", "best", "way", "ways", "part", "parts", "case", "cases",
    "order", "point", "points", "level", "levels", "general", "specific",
    "important", "significant", "major", "key", "main", "effect", "effects",
    "factor", "factors", "value", "values", "aim", "objective", "propose",
    "developed", "applied", "used", "existing", "novel", "improved",
    "show", "shown", "demonstrate", "demonstrated", "evaluate", "evaluated",
    "compare", "compared", "present", "presented", "describe", "described",
    "discuss", "discussed", "review", "reviewed", "investigate", "investigated",
    "assess", "assessed", "analyze", "analyzed", "identify", "identified",
    "achieve", "achieved", "obtain", "obtained", "find", "found", "observe",
    "observed", "indicate", "indicated", "suggest", "suggested", "conclude",
    "concluded", "report", "reported", "consider", "considered",
}

STOP_WORDS_PT: set[str] = {
    "a", "o", "e", "é", "de", "do", "da", "dos", "das", "em", "no", "na",
    "nos", "nas", "para", "por", "com", "um", "uma", "uns", "umas", "se",
    "ao", "aos", "às", "que", "ou", "este", "esta", "esse", "essa", "seu",
    "sua", "seus", "suas", "mais", "como", "mas", "foi", "pela", "pelo",
    "sobre", "entre", "após", "também", "até", "já", "não", "isso", "isto",
    "aqui", "assim", "ser", "ter", "há", "está", "são", "tem", "pode",
    "quando", "onde", "qual", "quais", "muito", "bem", "através", "uso",
    "estudo", "método", "resultado", "resultados", "análise", "abordagem",
    "artigo", "pesquisa", "proposto", "baseado", "utilizando", "utilizado",
    "novo", "dois", "três", "primeiro", "segundo", "alto", "baixo",
    "grande", "pequeno", "diferente", "trabalho", "sistema", "modelo",
    "tipo", "tipos", "número", "parte", "caso", "casos", "nível",
    "geral", "específico", "importante", "significativo", "principal",
    "efeito", "efeitos", "fator", "fatores", "valor", "valores",
    "objetivo", "proposto", "desenvolvido", "aplicado", "existente",
    "melhorado", "mostrar", "demonstrar", "avaliar", "comparar",
    "apresentar", "descrever", "discutir", "revisar", "investigar",
    "identificar", "obter", "encontrar", "observar", "indicar", "sugerir",
    "concluir", "relatar", "considerar",
}

STOP_WORDS: set[str] = STOP_WORDS_EN | STOP_WORDS_PT


def extract_ngrams(
    text: str,
    min_n: int = 1,
    max_n: int = 3,
    extra_stop_words: set[str] | None = None,
) -> list[str]:
    sw = STOP_WORDS | (extra_stop_words or set())
    raw_tokens = re.findall(r"[a-záéíóúàâêôãõüç\-]+", text.lower())
    tokens = [t for t in raw_tokens if t not in sw and len(t) > 2 and not t.isdigit()]
    ngrams: list[str] = []
    for n in range(min_n, max_n + 1):
        for i in range(len(tokens) - n + 1):
            gram = " ".join(tokens[i : i + n])
            ngrams.append(gram)
    return ngrams


def load_thesaurus(csv_path: str) -> dict[str, str]:
    """CSV com colunas 'term' e 'canonical'. Retorna mapa lowercase."""
    mapping: dict[str, str] = {}
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = row.get("term", "").strip().lower()
            canon = row.get("canonical", "").strip().lower()
            if term and canon:
                mapping[term] = canon
    return mapping


def apply_thesaurus(term: str, thesaurus: dict[str, str] | None) -> str:
    if not thesaurus:
        return term
    return thesaurus.get(term, term)


def detect_bursts(
    df,
    field: str = "keywords",
    thesaurus: dict | None = None,
    extra_stop_words: set[str] | None = None,
) -> list[dict]:
    """
    Detect sudden spikes in term occurrences over time (years) normalized by publication volume.
    Returns sorted list of dicts: [{'term': term, 'start': y1, 'end': y2, 'strength': s, 'total_occ': o}]
    """
    import numpy as np
    from collections import Counter
    from core.matrix_builders import _extract_term_lists
    
    thesaurus_dict = thesaurus or {}
    term_lists = _extract_term_lists(df, field, thesaurus_dict, extra_stop_words)
    years = df["year"].fillna(0).astype(int).values
    
    term_years = {}
    for lst, yr in zip(term_lists, years):
        if yr <= 0:
            continue
        for t in lst:
            term_years.setdefault(t, []).append(yr)
            
    if not term_years:
        return []
        
    valid_yrs = df[df["year"] > 0]["year"].dropna().astype(int)
    if valid_yrs.empty:
        return []
    min_yr = int(valid_yrs.min())
    max_yr = int(valid_yrs.max())
    
    if max_yr <= min_yr:
        return []
        
    all_years = list(range(min_yr, max_yr + 1))
    
    pub_counts = Counter(df[df["year"] > 0]["year"].astype(int))
    total_pubs = np.array([pub_counts.get(y, 1) for y in all_years], float)
    total_pubs[total_pubs == 0] = 1.0
    
    bursts = []
    
    for term, yrs in term_years.items():
        counts = Counter(yrs)
        raw_freqs = np.array([counts.get(y, 0) for y in all_years], float)
        freqs = (raw_freqs / total_pubs) * 1000.0
        
        if sum(counts.values()) < 4:
            continue
            
        mean = freqs.mean()
        std = freqs.std()
        if std == 0:
            continue
            
        z_scores = (freqs - mean) / std
        
        in_burst = False
        start_idx = None
        period_z = []
        
        for idx, z in enumerate(z_scores):
            is_burst_yr = (z > 1.645) and (raw_freqs[idx] >= 1)
            if is_burst_yr:
                if not in_burst:
                    in_burst = True
                    start_idx = idx
                period_z.append(z)
            else:
                if in_burst:
                    end_idx = idx - 1
                    strength = sum(period_z)
                    bursts.append({
                        "term": term,
                        "start": all_years[start_idx],
                        "end": all_years[end_idx],
                        "strength": float(strength),
                        "total_occ": sum(counts.values())
                    })
                    in_burst = False
                    period_z = []
                    
        if in_burst:
            end_idx = len(all_years) - 1
            strength = sum(period_z)
            bursts.append({
                "term": term,
                "start": all_years[start_idx],
                "end": all_years[end_idx],
                "strength": float(strength),
                "total_occ": sum(counts.values())
            })
            
    bursts = sorted(bursts, key=lambda x: x["strength"], reverse=True)
    return bursts
