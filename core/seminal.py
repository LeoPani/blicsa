"""Contagens verificáveis para obras citadas e autores dos artigos do corpus."""

from collections import Counter
from difflib import SequenceMatcher
import re
import unicodedata

import pandas as pd


REFERENCE_COLUMNS = ("CR", "References", "Cited References", "references")
OPENALEX_WORK_ID = re.compile(r"^(?:https?://openalex\.org/)?(W\d+)$", re.I)
DOI = re.compile(r"10\.\d{4,9}/[^\s,;]+", re.I)


def _plain(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def reference_column(df: pd.DataFrame | None) -> str | None:
    if df is None:
        return None
    return next((name for name in REFERENCE_COLUMNS if name in df.columns), None)


def reference_key(reference: str) -> str:
    """Identificador estável; DOI e OpenAlex unem variações da mesma obra."""
    work = OPENALEX_WORK_ID.fullmatch(reference.strip())
    if work:
        return f"openalex:{work.group(1).upper()}"
    doi = DOI.search(reference)
    if doi:
        return f"doi:{doi.group().rstrip('.,)').lower()}"
    return re.sub(r"\s+", " ", reference).strip().casefold()


def top_references(df: pd.DataFrame | None, limit: int = 20) -> list[tuple[str, int]]:
    """Conta a presença de cada obra em artigos distintos, sem duplicatas na mesma célula."""
    column = reference_column(df)
    if column is None or df is None:
        return []
    counts: Counter[str] = Counter()
    displays: dict[str, str] = {}
    for cell in df[column]:
        seen: set[str] = set()
        raw = "" if cell is None or pd.isna(cell) else str(cell)
        for part in re.split(r"[;\n]", raw):
            reference = _plain(part)
            key = reference_key(reference) if reference else ""
            if key and key not in seen:
                counts[key] += 1
                displays.setdefault(key, reference)
                seen.add(key)
    return [(displays[key], count) for key, count in counts.most_common(limit)]


def split_authors(value: object) -> list[str]:
    """Separa antes de normalizar para não colar todos os coautores num só nome."""
    if value is None or pd.isna(value):
        return []
    return [author for part in str(value).split(";")
            if (author := _plain(part)) and author.casefold() not in {"nan", "none"}]


def author_key(author: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", author).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_name.casefold()).strip()


def reference_metadata_consistent(openalex: dict, crossref: dict) -> bool:
    """Rejeita um ID cuja obra mudou de título/ano entre OpenAlex e o DOI.

    Alguns registros OpenAlex podem conter título, autores, DOI e resumo de
    trabalhos diferentes. Consultar o DOI na fonte registradora evita enviar
    essa mistura à IA como se fosse uma única obra.
    """
    title_a = author_key(str(openalex.get("title") or ""))
    title_b = author_key(str(crossref.get("title") or ""))
    if not title_a or not title_b:
        return False
    similarity = SequenceMatcher(None, title_a, title_b).ratio()
    tokens_a, tokens_b = set(title_a.split()), set(title_b.split())
    overlap = len(tokens_a & tokens_b) / max(1, min(len(tokens_a), len(tokens_b)))
    if similarity < 0.65 and overlap < 0.75:
        return False
    year_a = int(openalex.get("year") or 0)
    year_b = int(crossref.get("year") or 0)
    return not (year_a and year_b and abs(year_a - year_b) > 2)


def ranked_corpus_authors(df: pd.DataFrame, limit: int = 15) -> list[dict]:
    """Autores dos artigos do corpus por citações recebidas, com obra ligada por autoria exata.

    Este ranking não mede autores citados nas referências; o nome da seção precisa dizê-lo.
    """
    by_author: dict[str, dict] = {}
    for _, row in df.iterrows():
        try:
            citations = max(0, int(row.get("citations") or 0))
        except (TypeError, ValueError):
            citations = 0
        for author in split_authors(row.get("authors")):
            key = author_key(author)
            if not key:
                continue
            item = by_author.setdefault(key, {
                "author": author, "citations": 0, "papers": 0,
                "top_title": "", "top_year": 0, "top_citations": -1,
            })
            item["citations"] += citations
            item["papers"] += 1
            if citations > item["top_citations"]:
                item["top_title"] = _plain(row.get("title"))
                item["top_year"] = row.get("year") or 0
                item["top_citations"] = citations
    return sorted(by_author.values(), key=lambda x: (-x["citations"], x["author"].casefold()))[:limit]
