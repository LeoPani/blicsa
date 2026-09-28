"""Tipos de documento comparáveis entre bases bibliográficas.

O valor vazio significa que a fonte ou o projeto antigo não informou o tipo. Não se
infere ``article`` a partir do nome de uma revista: isso fabricaria uma contagem.
"""

from collections import Counter


_ALIASES = {
    "article": "article",
    "journal article": "article",
    "journal-article": "article",
    "original article": "article",
    "research article": "article",
    "review": "review",
    "review article": "review",
    "review-article": "review",
    "conference paper": "conference-paper",
    "conference-paper": "conference-paper",
    "proceedings paper": "conference-paper",
    "proceedings-article": "conference-paper",
    "inproceedings": "conference-paper",
    "conference abstract": "conference-abstract",
    "conference-abstract": "conference-abstract",
    "meeting abstract": "conference-abstract",
    "book": "book",
    "book chapter": "book-chapter",
    "book-chapter": "book-chapter",
    "incollection": "book-chapter",
    "preprint": "preprint",
    "posted-content": "preprint",
    "dataset": "dataset",
    "dissertation": "dissertation",
    "thesis": "dissertation",
    "report": "report",
    "report-series": "report",
    "standard": "standard",
    "journal-issue": "other",
    "journal-volume": "other",
    "other": "other",
}

# Tipos restantes do vocabulário atual do OpenAlex. Mantemos a categoria de origem em vez
# de achatar tudo em "other", para que a distribuição continue auditável.
_OPENALEX_TYPES = {
    "book-review", "data-paper", "editorial", "erratum", "letter", "libguides",
    "paratext", "peer-review", "reference-entry", "retraction", "software",
    "software-paper", "supplementary-materials",
}


def normalize_document_type(value: object) -> str:
    """Devolve a categoria canônica ou ``""`` quando o tipo é desconhecido."""
    if value is None:
        return ""
    raw = str(value).strip().lower().replace("_", "-")
    if not raw or raw in {"nan", "none", "unknown", "not specified"}:
        return ""
    # O WoS pode marcar o mesmo item "Article; Proceedings Paper". A indicação de
    # congresso é mais específica do que a etiqueta genérica de artigo.
    parts = [part.strip() for part in raw.split(";") if part.strip()]
    if len(parts) > 1:
        mapped = [normalize_document_type(part) for part in parts]
        for preferred in ("conference-paper", "conference-abstract", "review", "article"):
            if preferred in mapped:
                return preferred
        return next((kind for kind in mapped if kind), "")
    return _ALIASES.get(raw, raw if raw in _OPENALEX_TYPES else "other")


_SUMMARY_TYPES = {
    "article", "review", "conference-paper", "conference-abstract", "book",
    "book-chapter", "preprint", "dataset", "dissertation", "report", "standard",
}


def document_type_counts(df) -> dict[str, int]:
    """Conta tipos preservados no corpus; ``unknown`` representa metadado ausente."""
    if df is None or getattr(df, "empty", True):
        return {}
    if "document_type" not in df.columns:
        return {"unknown": len(df)}
    kinds = (normalize_document_type(value) or "unknown"
             for value in df["document_type"])
    counts = Counter(kind if kind in _SUMMARY_TYPES or kind == "unknown" else "other"
                     for kind in kinds)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
