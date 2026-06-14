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


def apply_thesaurus(term: str, thesaurus: dict[str, str]) -> str:
    return thesaurus.get(term, term)
