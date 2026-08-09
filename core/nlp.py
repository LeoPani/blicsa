import re
import csv

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
    "estudo", "estudos", "método", "métodos", "resultado", "resultados", 
    "análise", "análises", "abordagem", "abordagens", "artigo", "artigos", 
    "pesquisa", "pesquisas", "proposto", "proposta", "baseado", "baseada",
    "utilizando", "utilizado", "novo", "nova", "dois", "três", "primeiro", 
    "segundo", "alto", "baixo", "grande", "pequeno", "diferente", "diferentes", 
    "trabalho", "trabalhos", "sistema", "sistemas", "modelo", "modelos",
    "tipo", "tipos", "número", "números", "parte", "partes", "caso", "casos", 
    "nível", "níveis", "geral", "específico", "importante", "significativo", 
    "principal", "principais", "efeito", "efeitos", "fator", "fatores", 
    "valor", "valores", "objetivo", "objetivos", "desenvolvido", "aplicado", 
    "existente", "melhorado", "mostrar", "demonstrar", "avaliar", "comparar",
    "apresentar", "descrever", "discutir", "revisar", "investigar",
    "identificar", "obter", "encontrar", "observar", "indicar", "sugerir",
    "concluir", "relatar", "considerar", "partir", "vez", "cada", "podem",
    "sendo", "sido", "fazer", "forma", "frente", "meio", "ainda", "apenas",
    "durante", "todos", "todas", "qualquer", "outros", "outras", "alguns",
    "algumas", "mesmo", "mesma", "mesmos", "mesmas", "então", "pois", "porque",
    "cujo", "cuja", "cujos", "cujas", "deste", "desta", "destes", "destas",
    "neste", "nesta", "nestes", "nestas", "nesse", "nessa", "nesses", "nessas",
    "desse", "dessa", "desses", "dessas", "naquele", "naquela", "daquele",
    "daquela", "à", "àquele", "àquela", "têm", "quem", "tão",
    "contexto", "papel", "relação", "processo", "impacto", "desenvolvimento",
    "literatura", "dados", "teórico", "empírico", "prática", "teoria",
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


#: Qualquer sequência de espaço em branco, inclusive quebra de linha e tabulação.
_ESPACO_BRANCO = re.compile(r"\s+")


def normalizar_termo(termo: str) -> str:
    """Termo do vocabulário sem espaço em branco de controle no meio.

    `strip()` sozinho limpa só as pontas, e quebra de linha **dentro** de um termo passava
    inteira para o nome do nó. Isso não é um conceito de duas linhas: é artefato de CSV ou
    RIS malformado, que o Blicsa importa.

    O custo era real e invisível na tela. Pajek e VOSviewer são formatos de **um registro por
    linha**: um termo com `\\n` partia o registro em vários, e o arquivo exportado deixava de
    ser legível — inclusive pelo próprio networkx que o havia escrito. Medido na Auditoria 1:
    `nx.read_pajek` levantava `ValueError` sobre o arquivo gerado pelo `export_pajek`.
    """
    return _ESPACO_BRANCO.sub(" ", termo or "").strip()


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


#: Caracteres que fazem uma célula de CSV virar fórmula ao ser aberta em planilha.
#:
#: `=`, `+`, `-` e `@` são reconhecidos por Excel e LibreOffice; tabulação e retorno de carro
#: entram porque a planilha os ignora antes de olhar o primeiro caractere real.
GATILHOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")

#: Prefixo neutralizador. A aspa simples é a convenção do próprio Excel para "isto é texto":
#: ela não aparece na célula e impede a avaliação.
PREFIXO_SEGURO = "'"


def neutralizar_formula(valor):
    """Impede que um texto do corpus vire fórmula ao abrir o CSV exportado numa planilha.

    O vetor é real e não exige nada de especial do atacante: basta um registro cujo campo de
    palavra-chave contenha `=HYPERLINK("http://…")` ou `=cmd|'/C calc'!A0`. O Blicsa exporta
    o termo tal como veio, o pesquisador abre no Excel para conferir os rankings, e a planilha
    **avalia** a célula. Medido na Auditoria 2: 5 células no ranking e 14 nas arestas.

    Não altera o dado — prefixa. O termo continua legível na célula e volta inteiro se o
    arquivo for lido por um programa (que ignora a convenção da aspa).
    """
    if not isinstance(valor, str) or not valor:
        return valor
    return PREFIXO_SEGURO + valor if valor.startswith(GATILHOS_DE_FORMULA) else valor


def neutralizar_formulas_no_df(df):
    """Aplica `neutralizar_formula` a toda coluna de texto de um DataFrame."""
    seguro = df.copy()
    for coluna in seguro.columns:
        # Sem filtrar por `dtype`: o pandas desta versão infere `str` (e não `object`) para
        # coluna de texto, e a checagem `dtype == object` deixava passar TODAS as células —
        # a neutralização existia e não neutralizava nada. `neutralizar_formula` já devolve
        # o valor intacto quando não é texto, então aplicar em tudo é correto e barato.
        seguro[coluna] = seguro[coluna].map(neutralizar_formula)
    return seguro
