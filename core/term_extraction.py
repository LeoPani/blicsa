"""Extração de termos para os mapas — no padrão VOSviewer.

O VOSviewer não monta o mapa a partir das keywords do metadado: ele extrai **frases
nominais** de título+abstract, conta **uma vez por documento** (contagem binária) e ranqueia
os termos por **relevância** derivada do padrão de coocorrência. Este módulo oferece os dois
caminhos (keywords e frases nominais), selecionáveis pelo usuário.

## Escolha do extrator de frases nominais (e o motivo)

O padrão-ouro seria POS tagging com spaCy (`en_core_web_sm`). **Não é o caminho padrão aqui**,
por três razões concretas deste projeto:

1. **Peso.** spaCy + modelo + dependências (thinc, blis, murmurhash…) passam de 100 MB. O
   Blicsa é empacotado com PyInstaller (`Blicsa.spec`) e distribuído como app desktop; isso
   multiplicaria o tamanho do bundle.
2. **Offline.** O modelo exige download em separado (`spacy download`). Um app que precisa de
   rede na primeira execução para extrair termos quebra o uso offline, que é premissa aqui.
3. **`requirements.txt` pinado.** Todas as versões são fixas e verificadas no CI; somar uma
   árvore grande de dependências compiladas é risco de build desproporcional ao ganho.

Então o extrator **embutido** (`ngram`) é o padrão: aproxima frases nominais por n-gramas
filtrados — remove stopwords, rejeita tokens com morfologia verbal/adverbial e exige que a
cabeça da frase (último token) seja substantivo plausível. Fica abaixo de um POS tagger de
verdade em textos difíceis, mas roda offline, sem dependência nova, e é determinístico.

spaCy e NLTK são **detectados em tempo de execução**: se o usuário os tiver instalados,
`method="auto"` os usa preferencialmente (spaCy > NLTK > embutido). Quem quer a qualidade
máxima instala spaCy e ganha automaticamente; quem não quer, não paga o custo.

## Fórmula da relevância

Segue o conceito do VOSviewer (van Eck & Waltman): comparar, para cada termo, a distribuição
das suas coocorrências com a distribuição **marginal** do corpus. Termo genérico coocorre com
todo mundo na proporção em que cada um aparece — sua distribuição ≈ a marginal → relevância
baixa. Termo específico concentra coocorrências num punhado de vizinhos → relevância alta.

Para o termo `i`, com `c_ij` = nº de documentos onde `i` e `j` coocorrem:

    p(j|i) = c_ij / Σ_j c_ij          (distribuição observada de i)
    q(j)   = Σ_i c_ij / Σ_ij c_ij     (distribuição marginal do corpus)
    rel(i) = Σ_j p(j|i) · log( p(j|i) / q(j) )        ← divergência de Kullback-Leibler

`rel(i)` é 0 quando o termo se comporta como a média (genérico) e cresce com a concentração.
No fim os valores são normalizados para **média 1**, como o VOSviewer faz, para que o número
seja legível ("acima de 1 = mais específico que a média do corpus").
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field as _dc_field
from typing import Callable, Iterable, Sequence

from core.nlp import STOP_WORDS, STOP_WORDS_EN, STOP_WORDS_PT, apply_thesaurus

# Campos de origem dos termos.
FIELDS = ("keywords", "title_abstract", "both")
# Métodos de extração de frases nominais. "auto" = melhor disponível.
METHODS = ("auto", "spacy", "nltk", "ngram")

# Tamanho máximo da frase nominal (em tokens). 4 cobre "small and medium sized enterprises".
MAX_PHRASE_LEN = 4

# Sufixos que denunciam token não-nominal na CABEÇA da frase. Não é POS tagging; é um filtro
# de morfologia que derruba os casos mais comuns de verbo/advérbio/adjetivo virando "termo".
# A cabeça de uma frase nominal é um substantivo: "medical unit" é termo, "medical" sozinho não.
_NON_NOUN_HEAD_SUFFIXES = (
    "ly", "ing", "ed", "ize", "ise", "ify", "ate",           # verbo / advérbio
    "al", "ive", "ous", "ic", "ical", "ful", "less", "able", "ible", "ary", "ant", "ent",
)
# Exceções: substantivos legítimos que terminam com os sufixos acima.
_NOUN_EXCEPTIONS = {
    # -al / -ic / -ive / -ary … que são substantivos de verdade
    "material", "materials", "capital", "hospital", "journal", "signal", "metal",
    "goal", "coal", "trial", "potential", "proposal", "removal", "arrival", "animal",
    "individual", "professional", "official", "capital", "terminal", "channel",
    "objective", "perspective", "initiative", "alternative", "incentive", "narrative",
    "representative", "executive", "cooperative", "drive", "archive", "olive",
    "music", "logic", "traffic", "plastic", "fabric", "clinic", "topic", "ethic",
    "public", "republic", "electric", "graphic", "statistic", "characteristic",
    "library", "summary", "boundary", "salary", "dictionary", "vocabulary", "primary",
    "secondary", "beneficiary", "subsidiary", "territory", "category", "battery",
    "plant", "grant", "client", "patient", "student", "agent", "component",
    "environment", "government", "management", "development", "investment",
    "treatment", "equipment", "instrument", "document", "element", "segment",
    "experiment", "assessment", "commitment", "recruitment", "employment",
    "content", "event", "percent", "continent", "resident", "president", "accident",
    "variable", "vegetable", "table", "cable", "vehicle", "obstacle", "principle",
    "learning", "modeling", "modelling", "engineering", "manufacturing", "marketing",
    "training", "clustering", "mining", "planning", "funding", "branding", "housing",
    "networking", "sensing", "imaging", "monitoring", "reasoning", "programming",
    "accounting", "banking", "farming", "policy", "energy", "supply", "family",
    "certificate", "climate", "candidate", "graduate", "estate", "state", "rate",
    "corporate", "private", "innovate", "advocate", "aggregate", "template",
    "feed", "seed", "speed", "need", "breed", "method", "period", "record", "field",
    "child", "world", "trend", "brand", "demand", "fund", "ground", "sound", "bed",
}

# Palavras terminadas em "s" que são SINGULARES — não podem ser "des-pluralizadas".
_S_SINGULAR = {
    "analysis", "basis", "thesis", "hypothesis", "diagnosis", "synthesis", "crisis",
    "emphasis", "bias", "gas", "virus", "focus", "consensus", "campus", "status",
    "apparatus", "corpus", "genus", "nucleus", "radius", "stimulus", "surplus",
    "business", "access", "process", "success", "progress", "stress", "address",
    "class", "mass", "loss", "less", "cross", "press", "glass", "grass", "illness",
    "awareness", "effectiveness", "robustness", "usefulness", "wellness", "fitness",
    "news", "series", "species", "means", "physics", "economics", "ethics", "politics",
    "statistics", "mathematics", "genetics", "logistics", "dynamics", "athletics",
    "aerobics", "diabetes", "index", "always", "perhaps", "various", "previous",
    "obvious", "serious", "numerous", "continuous", "simultaneous", "homogeneous",
}

# Plurais em "-ves" cujo singular termina em f/fe. Lista explícita porque a regra genérica
# "ves → fe" destrói verbos na 3ª pessoa ("improves" → "improfe").
_VES_PLURALS = {
    "lives": "life", "wives": "wife", "knives": "knife", "leaves": "leaf",
    "halves": "half", "shelves": "shelf", "wolves": "wolf", "thieves": "thief",
    "calves": "calf", "selves": "self", "loaves": "loaf", "elves": "elf",
}

# Plurais irregulares → singular.
_IRREGULAR_PLURALS = {
    "children": "child", "men": "man", "women": "woman", "people": "person",
    "teeth": "tooth", "feet": "foot", "geese": "goose", "mice": "mouse",
    "criteria": "criterion", "phenomena": "phenomenon",
    # "data" NÃO entra aqui: em texto científico moderno é substantivo massivo, e o mapa
    # exibiria "big datum" — que não é termo de área nenhuma. O E2E pegou isso.
    "media": "medium", "bacteria": "bacterium", "curricula": "curriculum",
    "analyses": "analysis", "bases": "basis", "theses": "thesis",
    "hypotheses": "hypothesis", "diagnoses": "diagnosis", "syntheses": "synthesis",
    "crises": "crisis", "indices": "index", "matrices": "matrix",
    "vertices": "vertex", "appendices": "appendix", "series": "series",
    "species": "species",
}


# Termos de área que só existem no PLURAL — singularizar destrói o nome ("public relation",
# "operations research" → "operation research"). Lista curada; o caminho geral para o resto
# é o thesaurus, que o usuário controla.
_PLURAL_ONLY_HEADS = {
    "relations", "resources", "operations", "communications", "affairs", "humanities",
    "sciences", "arts", "studies", "systems", "networks", "commons", "analytics",
}


def is_plural_only(phrase: str) -> bool:
    """A frase termina numa cabeça que é plural-only? (usado por `normalize_phrase`)"""
    p = str(phrase or "").strip().lower()
    if not p:
        return False
    cabeca = p.split(" ")[-1]
    if cabeca not in _PLURAL_ONLY_HEADS:
        return False
    # "systems"/"studies"/"networks" só são plural-only quando FAZEM PARTE de um nome
    # composto ("information systems", "regional studies"); sozinhos são plural comum.
    return len(p.split(" ")) > 1 or cabeca in {
        "relations", "resources", "operations", "communications", "affairs",
        "humanities", "commons", "analytics"}


def singularize(word: str) -> str:
    """Reduz uma palavra ao singular por regras (sem dependência externa).

    Unifica "medical unit"/"medical units" — o VOSviewer funde essas variantes. Conservador
    de propósito: quando a palavra é um singular terminado em "s" (`analysis`, `business`),
    devolve intacta, porque cortar o "s" ali inventaria termo inexistente.
    """
    w = (word or "").strip().lower()
    if len(w) <= 2:
        return w
    if w in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[w]
    # Nomes de campo terminados em "-ics" são SINGULARES no uso: bibliometrics,
    # scientometrics, informatics, robotics… A lista de exceções cobria só um punhado deles
    # (physics, economics…) e o resto virava "bibliometric"/"informatic" — nomes de área que
    # ninguém escreve. Regra geral, achada pelo teste de ponta a ponta.
    if w.endswith("ics") and len(w) > 4:
        return w
    if w in _S_SINGULAR or not w.endswith("s"):
        return w
    if w.endswith("ss") or w.endswith("us") or w.endswith("is"):
        return w
    if w.endswith("ies") and len(w) > 4:          # studies → study
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "sses", "xes", "zzes")):  # boxes → box, matches → match
        return w[:-2]
    if w in _VES_PLURALS:                          # lives → life (lista explícita: a regra
        return _VES_PLURALS[w]                     # cega "ves"→"fe" fazia improves→improfe)
    if w.endswith("es") and len(w) > 3:
        # "sizes"/"genes"/"states" → tira só o "s" (o "e" faz parte da palavra).
        # "processes"/"boxes" já saíram acima, onde o "es" é sufixo de plural.
        return w[:-1]
    return w[:-1]                                  # units → unit


def normalize_phrase(phrase: str) -> str:
    """Forma canônica de um termo: minúsculas, espaços colapsados, cabeça no singular."""
    p = re.sub(r"\s+", " ", str(phrase or "").strip().lower())
    if not p:
        return ""
    if is_plural_only(p):
        return p                     # "public relations" não vira "public relation"
    parts = p.split(" ")
    parts[-1] = singularize(parts[-1])
    return " ".join(parts)


def _plausible_noun_head(token: str) -> bool:
    """A cabeça da frase (último token) parece substantivo?"""
    if token in _NOUN_EXCEPTIONS:
        return True
    return not token.endswith(_NON_NOUN_HEAD_SUFFIXES)


# Morfologia verbal no MEIO da frase: "the hospital showed rapid improvement" não deve gerar
# "hospital showed rapid" — uma frase nominal não atravessa o verbo da oração.
_VERBAL_SUFFIXES = ("ed", "ing")


def _plausible_noun_phrase(tokens: Sequence[str]) -> bool:
    """A sequência inteira é uma frase nominal plausível?"""
    if not tokens or not _plausible_noun_head(tokens[-1]):
        return False
    for tok in tokens[:-1]:
        if tok.endswith(_VERBAL_SUFFIXES) and tok not in _NOUN_EXCEPTIONS:
            return False
    return True


# ─────────────────────────── backends de frase nominal ───────────────────────────

def available_methods() -> tuple[str, ...]:
    """Backends de extração realmente disponíveis nesta instalação, do melhor ao mais simples."""
    found = []
    try:
        import spacy  # noqa: F401
        try:
            spacy.load("en_core_web_sm")
            found.append("spacy")
        except Exception:
            pass
    except ImportError:
        pass
    try:
        import nltk  # noqa: F401
        from nltk import pos_tag, word_tokenize  # noqa: F401
        pos_tag(word_tokenize("a test sentence"))
        found.append("nltk")
    except Exception:
        pass
    found.append("ngram")  # sempre disponível
    return tuple(found)


def resolve_method(method: str = "auto") -> str:
    """Traduz "auto" no melhor backend presente. Método pedido e ausente cai no embutido."""
    if method not in METHODS:
        raise ValueError(f"method inválido: {method!r} (use um de {METHODS})")
    avail = available_methods()
    if method == "auto":
        return avail[0]
    return method if method in avail else "ngram"


def _noun_phrases_ngram(text: str, extra_stop_words: set[str] | None = None) -> list[str]:
    """Extrator embutido: n-gramas de tokens não-stopword cuja cabeça parece substantivo.

    Aproxima "substantivo com dependentes" do VOSviewer: as stopwords cortam determinantes,
    preposições e verbos auxiliares, então uma sequência contígua sobrevivente é quase sempre
    um núcleo nominal com seus modificadores.
    """
    sw = STOP_WORDS | (extra_stop_words or set())
    phrases: list[str] = []
    # Segmenta por pontuação: uma frase nominal não atravessa vírgula nem ponto.
    segments = re.split(r"[.;:,()\[\]/!?\"]+", str(text or "").lower())
    for seg in segments:
        tokens = re.findall(r"[a-záéíóúàâêôãõüçñ][a-záéíóúàâêôãõüçñ\-']*", seg)
        # Quebra o segmento em runs contíguos de tokens úteis.
        run: list[str] = []
        for tok in tokens + [None]:  # sentinela para fechar o último run
            useful = tok is not None and tok not in sw and len(tok) > 2 and not tok.isdigit()
            if useful:
                run.append(tok)
                continue
            for n in range(1, MAX_PHRASE_LEN + 1):
                for i in range(len(run) - n + 1):
                    gram = run[i : i + n]
                    if _plausible_noun_phrase(gram):
                        phrases.append(" ".join(gram))
            run = []
    return phrases


def _noun_phrases_spacy(text: str, extra_stop_words: set[str] | None = None) -> list[str]:
    """POS tagging real via spaCy: usa os noun_chunks do parser."""
    import spacy
    global _SPACY_NLP
    try:
        nlp = _SPACY_NLP
    except NameError:
        nlp = None
    if nlp is None:
        nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        globals()["_SPACY_NLP"] = nlp
    sw = STOP_WORDS | (extra_stop_words or set())
    out: list[str] = []
    for chunk in nlp(str(text or "")[:100_000]).noun_chunks:
        toks = [t.text.lower() for t in chunk
                if t.is_alpha and t.text.lower() not in sw and len(t.text) > 2]
        if toks:
            out.append(" ".join(toks[-MAX_PHRASE_LEN:]))
    return out


def _noun_phrases_nltk(text: str, extra_stop_words: set[str] | None = None) -> list[str]:
    """POS tagging via NLTK: agrupa runs de adjetivo/substantivo terminando em substantivo."""
    from nltk import pos_tag, word_tokenize
    sw = STOP_WORDS | (extra_stop_words or set())
    out: list[str] = []
    run: list[str] = []
    tagged = pos_tag(word_tokenize(str(text or "")[:100_000]))
    for word, tag in tagged + [("", "")]:
        w = word.lower()
        keep = tag.startswith(("NN", "JJ")) and w.isalpha() and w not in sw and len(w) > 2
        if keep:
            run.append(w)
            continue
        if run:
            for n in range(1, MAX_PHRASE_LEN + 1):
                for i in range(len(run) - n + 1):
                    out.append(" ".join(run[i : i + n]))
        run = []
    return out


_BACKENDS: dict[str, Callable[..., list[str]]] = {
    "ngram": _noun_phrases_ngram,
    "spacy": _noun_phrases_spacy,
    "nltk": _noun_phrases_nltk,
}


def extract_noun_phrases(text: str, method: str = "auto",
                         extra_stop_words: set[str] | None = None) -> list[str]:
    """Frases nominais de um texto, já normalizadas (cabeça no singular)."""
    backend = resolve_method(method)
    raw = _BACKENDS[backend](text, extra_stop_words)
    return [p for p in (normalize_phrase(r) for r in raw) if p]


# ─────────────────────────────── keywords do metadado ───────────────────────────────

def split_keywords(raw: str) -> list[str]:
    """Divide o campo keywords (";" ou "," conforme a fonte) e normaliza cada termo."""
    s = str(raw or "").strip()
    if not s:
        return []
    sep = ";" if ";" in s else ","
    return [p for p in (normalize_phrase(k) for k in s.split(sep)) if p]


# ────────────────────────────────── relevância ──────────────────────────────────

def compute_relevance(doc_terms: Sequence[Iterable[str]]) -> dict[str, float]:
    """Relevância por padrão de coocorrência (ver a fórmula no docstring do módulo).

    Divergência KL entre a distribuição de coocorrência do termo e a marginal do corpus,
    normalizada para média 1. Termo genérico ≈ marginal → perto de 0; termo concentrado → alto.
    """
    cooc: dict[str, Counter] = {}
    for terms in doc_terms:
        uniq = sorted(set(terms))
        for a in uniq:
            row = cooc.setdefault(a, Counter())
            for b in uniq:
                if a != b:
                    row[b] += 1

    if not cooc:
        return {}

    marginal: Counter = Counter()
    grand_total = 0
    for row in cooc.values():
        for b, c in row.items():
            marginal[b] += c
            grand_total += c

    raw: dict[str, float] = {}
    for term, row in cooc.items():
        n_i = sum(row.values())
        if n_i == 0:
            raw[term] = 0.0
            continue
        kl = 0.0
        for j, c_ij in row.items():
            p = c_ij / n_i
            q = marginal[j] / grand_total
            if p > 0 and q > 0:
                kl += p * math.log(p / q)
        raw[term] = max(kl, 0.0)

    mean = sum(raw.values()) / len(raw) if raw else 0.0
    if mean <= 0:
        # Sem sinal de coocorrência (corpus de um único termo, ou um termo por documento):
        # não há como discriminar genérico de específico. Relevância uniforme 1.0 — honesto,
        # e é o que evita a divisão por zero na normalização abaixo.
        return {t: 1.0 for t in raw}
    return {t: v / mean for t, v in raw.items()}


# ──────────────────────────────────── resultado ────────────────────────────────────

@dataclass
class TermInfo:
    """Uma linha da lista de termos revisável (Fase 3)."""
    term: str
    occurrences: int          # respeita binary_count
    documents: int            # nº de documentos que contêm o termo (sempre binário)
    relevance: float
    avg_year: float | None    # None (não 0) quando não há ano — 0 mentiria no overlay
    avg_citations: float | None
    first_year: int | None

    def as_dict(self) -> dict:
        return {
            "term": self.term, "occurrences": self.occurrences,
            "documents": self.documents, "relevance": round(self.relevance, 4),
            "avg_year": self.avg_year, "avg_citations": self.avg_citations,
            "first_year": self.first_year,
        }


@dataclass
class ExtractionResult:
    """Saída de `extract_terms`."""
    terms: list[TermInfo] = _dc_field(default_factory=list)
    doc_terms: list[list[str]] = _dc_field(default_factory=list)
    warnings: list[str] = _dc_field(default_factory=list)   # chaves de i18n
    language: str = ""
    method_used: str = ""
    total_unique_before_threshold: int = 0

    def __len__(self) -> int:
        return len(self.terms)

    @property
    def term_names(self) -> list[str]:
        return [t.term for t in self.terms]

    def as_dicts(self) -> list[dict]:
        return [t.as_dict() for t in self.terms]


# ──────────────────────────────────── idioma ────────────────────────────────────

def detect_corpus_language(df) -> str:
    """Idioma predominante do corpus. Usa a coluna `language` (já preenchida na busca);
    sem ela, tenta detectar pelo texto. Devolve "" quando não há como saber."""
    if df is None or len(df) == 0:
        return ""
    if "language" in df.columns:
        vals = [str(v).strip().lower()[:2] for v in df["language"].fillna("") if str(v).strip()]
        if vals:
            return Counter(vals).most_common(1)[0][0]
    texto = " ".join(
        str(df.iloc[i].get("title", "") or "") for i in range(min(len(df), 30))
    ).strip()
    if not texto:
        return ""
    try:
        import langdetect
        langdetect.DetectorFactory.seed = 0      # determinismo
        return str(langdetect.detect(texto))[:2]
    except Exception:
        return ""


# ────────────────────────────────── função pública ──────────────────────────────────

def extract_terms(
    df,
    fields: str = "both",
    method: str = "auto",
    binary_count: bool = True,
    min_occurrences: int = 1,
    thesaurus: dict[str, str] | None = None,
    extra_stop_words: set[str] | None = None,
) -> ExtractionResult:
    """Extrai e ranqueia os termos do corpus.

    Args:
        df: DataFrame do corpus (colunas usadas: keywords, title, abstract, year, citations,
            language — todas opcionais).
        fields: "keywords" | "title_abstract" | "both".
        method: backend de frase nominal — "auto" | "spacy" | "nltk" | "ngram".
        binary_count: True (padrão, como no VOSviewer) conta o termo **uma vez por
            documento**; False conta todas as ocorrências.
        min_occurrences: limiar mínimo de ocorrências para o termo entrar na lista.
        thesaurus: mapa termo→canônico (`core.nlp.load_thesaurus`), aplicado ANTES de contar.
        extra_stop_words: stopwords adicionais do usuário.

    Returns:
        ExtractionResult com a lista de termos ordenada por (relevância, ocorrências) e os
        avisos a exibir na UI (chaves de i18n).
    """
    if fields not in FIELDS:
        raise ValueError(f"fields inválido: {fields!r} (use um de {FIELDS})")

    result = ExtractionResult()
    if df is None or len(df) == 0:
        return result

    th = thesaurus or {}
    result.method_used = resolve_method(method) if fields != "keywords" else "keywords"
    lang = detect_corpus_language(df)
    result.language = lang

    # Aviso honesto: a extração de frases nominais é dependente da gramática inglesa (é
    # limitação reconhecida no próprio guia do VOSviewer). Nunca falhar em silêncio.
    if fields in ("title_abstract", "both") and lang and lang != "en":
        result.warnings.append("map.warn_non_english")
    if fields in ("title_abstract", "both") and result.method_used == "ngram":
        result.warnings.append("map.warn_ngram_backend")

    cols = set(getattr(df, "columns", []))
    use_kw = fields in ("keywords", "both") and "keywords" in cols
    use_txt = fields in ("title_abstract", "both")

    # ── termos por documento (uma entrada por linha do df, SEMPRE — mesmo vazia) ──
    doc_terms: list[list[str]] = []
    raw_bags: list[list[str]] = []      # com repetições, para a contagem total
    for i in range(len(df)):
        row = df.iloc[i]
        bag: list[str] = []
        if use_kw:
            bag.extend(split_keywords(row.get("keywords", "")))
        if use_txt:
            texto = " ".join(
                str(row.get(c, "") or "") for c in ("title", "abstract") if c in cols
            ).strip()
            if texto:
                bag.extend(extract_noun_phrases(texto, result.method_used, extra_stop_words))
        # Thesaurus antes de contar: funde as variantes num termo só.
        raw_bags.append([apply_thesaurus(t, th) for t in bag])
        # `doc_terms` é sempre PRESENÇA por documento (dedup), nos dois modos de contagem:
        # é o que a coocorrência precisa, e é onde `both` deixa de duplicar o termo que
        # aparece tanto na keyword quanto no texto. A diferença binário/total fica só na
        # contagem abaixo — senão o dedup daqui tornaria aquele ramo redundante.
        doc_terms.append(list(dict.fromkeys(raw_bags[-1])))

    result.doc_terms = doc_terms

    # ── contagem ──
    counts: Counter = Counter()
    doc_freq: Counter = Counter()
    for raw_bag, presentes in zip(raw_bags, doc_terms):
        if binary_count:
            counts.update(presentes)      # uma vez por documento
        else:
            counts.update(raw_bag)        # todas as ocorrências
        doc_freq.update(presentes)

    result.total_unique_before_threshold = len(counts)
    if not counts:
        return result

    limiar = max(1, int(min_occurrences or 1))
    kept = {t for t, n in counts.items() if n >= limiar}
    if not kept:
        result.warnings.append("map.warn_threshold_empty")
        return result

    # Relevância só sobre os termos que ficaram: o custo é O(T²) e o limiar é justamente
    # o que mantém T na faixa recomendada pelo guia (1.000–2.000 termos).
    kept_doc_terms = [[t for t in bag if t in kept] for bag in doc_terms]
    relevance = compute_relevance(kept_doc_terms)

    # ── métricas por termo para o overlay ──
    anos: dict[str, list[int]] = {}
    cits: dict[str, list[float]] = {}
    has_year = "year" in cols
    has_cit = "citations" in cols
    for i, bag in enumerate(kept_doc_terms):
        if not bag:
            continue
        row = df.iloc[i]
        # `or 0` não basta: coluna ausente numa das linhas vira NaN, e int(NaN) levanta.
        y = _as_int(row.get("year")) if has_year else 0
        c = row.get("citations", None) if has_cit else None
        for t in set(bag):
            if y > 0:
                anos.setdefault(t, []).append(y)
            if c is not None and not _is_nan(c):
                cits.setdefault(t, []).append(float(c))

    termos: list[TermInfo] = []
    for t in sorted(kept):                      # sorted → determinismo
        ys = anos.get(t, [])
        cs = cits.get(t, [])
        termos.append(TermInfo(
            term=t,
            occurrences=int(counts[t]),
            documents=int(doc_freq[t]),
            relevance=float(relevance.get(t, 0.0)),
            # None, não 0: "sem dado" é diferente de "ano zero". O overlay pinta de cinza.
            avg_year=round(sum(ys) / len(ys), 1) if ys else None,
            avg_citations=round(sum(cs) / len(cs), 2) if cs else None,
            first_year=min(ys) if ys else None,
        ))

    # Ordem estável e útil: relevância desc, ocorrências desc, termo asc.
    termos.sort(key=lambda x: (-x.relevance, -x.occurrences, x.term))
    result.terms = termos
    return result


def _is_nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _as_int(v) -> int:
    """Inteiro tolerante: None, NaN, "" e texto não-numérico viram 0 (= "sem dado")."""
    if v is None or _is_nan(v):
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def threshold_preview(
    df,
    thresholds: Sequence[int] = (1, 2, 3, 5, 10, 20),
    fields: str = "both",
    method: str = "auto",
    binary_count: bool = True,
    thesaurus: dict[str, str] | None = None,
    extra_stop_words: set[str] | None = None,
) -> dict[int, int]:
    """Quantos termos sobram para cada limiar — alimenta o "limiar 10 → 1.847 termos" da UI.

    Extrai UMA vez e reaproveita a contagem para todos os limiares (varrer o corpus por
    limiar seria N vezes o custo por nada).
    """
    base = extract_terms(df, fields=fields, method=method, binary_count=binary_count,
                         min_occurrences=1, thesaurus=thesaurus,
                         extra_stop_words=extra_stop_words)
    counts = Counter()
    for t in base.terms:
        counts[t.term] = t.occurrences
    return {int(k): sum(1 for n in counts.values() if n >= int(k))
            for k in sorted(set(int(t) for t in thresholds))}


def suggest_threshold(df, target: int = 1500, **kwargs) -> int:
    """Limiar que aproxima a contagem de termos do alvo (o guia recomenda 1.000–2.000).

    Devolve o menor limiar cuja contagem fica <= alvo; se nem o limiar 1 passa do alvo,
    devolve 1 (o corpus é pequeno e não há o que cortar).
    """
    preview = threshold_preview(df, thresholds=range(1, 51), **kwargs)
    for limiar in sorted(preview):
        if preview[limiar] <= target:
            return limiar
    return max(preview) if preview else 1
