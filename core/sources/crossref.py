import urllib.parse
import json
import logging
import re
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider

logger = logging.getLogger("CrossrefProvider")

_LD_SEED_SET = False


def _detect_lang(text: str) -> Optional[str]:
    """Detecta idioma (ISO 639-1) via langdetect. None se falhar/indisponível."""
    global _LD_SEED_SET
    try:
        import langdetect
        if not _LD_SEED_SET:
            langdetect.DetectorFactory.seed = 0  # determinismo
            _LD_SEED_SET = True
        return langdetect.detect(text)
    except Exception:
        return None


def _record_matches_language(record: Dict[str, Any], wanted: str) -> bool:
    """A API do Crossref não filtra idioma de forma confiável; filtramos localmente.
    Usa o campo 'language' da API quando presente; senão detecta no título+abstract.
    Texto ausente ou detecção falha -> mantém (não descarta silenciosamente)."""
    wanted = str(wanted).strip().lower()[:2]
    api_lang = str(record.get("language") or "").strip().lower()[:2]
    if api_lang:
        return api_lang == wanted
    text = f"{record.get('title', '')} {record.get('abstract', '')}".strip()
    if not text:
        return True
    det = _detect_lang(text)
    if det is None:
        return True
    return det.lower()[:2] == wanted


class CrossrefProvider(SearchProvider):
    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        base_url = "https://api.crossref.org/works"

        # BUG-02: Crossref não filtra idioma de forma confiável -> filtro client-side.
        wanted_lang = (filters or {}).get("language")
        self.language_filtered_count = 0

        # Build filters
        filter_parts = []
        if filters:
            if filters.get("year_start"):
                filter_parts.append(f"from-pub-date:{filters['year_start']}-01-01")
            if filters.get("year_end"):
                filter_parts.append(f"until-pub-date:{filters['year_end']}-12-31")
            if filters.get("type"):
                # Map typical types to Crossref schema type
                t = filters["type"]
                if t == "journal-article":
                    filter_parts.append("type:journal-article")
                elif t == "book":
                    filter_parts.append("type:book")
                else:
                    filter_parts.append(f"type:{t}")


        params: Dict[str, Any] = {
            "rows": min(100, max_results),
            "cursor": "*"
        }
        if query.strip():
            import re
            q_str = re.sub(r'\b(AND|OR|NOT)\b', ' ', query, flags=re.IGNORECASE)
            q_str = re.sub(r'[\(\)]', ' ', q_str)
            q_str = re.sub(r'\s+', ' ', q_str).strip()
            params["query.bibliographic"] = q_str
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        # Crossref politeness
        params["mailto"] = self.mailto

        count_fetched = 0
        total_results = None
        # BUG-A: rastreio explícito do motivo de parada.
        self.stop_reason = None
        self.stop_error = False
        self.pages_fetched = 0

        while count_fetched < max_results:
            if cancel_event and cancel_event.is_set():
                self.stop_reason = "cancelado"
                raise InterruptedError("Search cancelled by user")

            query_str = urllib.parse.urlencode(params)
            url = f"{base_url}?{query_str}"

            self.pages_fetched += 1
            try:
                raw_data = self.fetch_url(url, cancel_event=cancel_event)
                data = json.loads(raw_data)
            except Exception as e:
                self.stop_reason = f"erro de rede na página {self.pages_fetched}: {e}"
                self.stop_error = True
                logger.error(f"[Crossref] parou: {self.stop_reason}")
                break

            message = data.get("message", {})
            results = message.get("items", [])

            if total_results is None:
                total_results = message.get("total-results", len(results))

            if not results:
                self.stop_reason = "exauriu (sem resultados)"
                break

            for w in results:
                if count_fetched >= max_results:
                    break

                has_cc_license = False
                licenses = w.get("license", [])
                for lic in licenses:
                    url_lic = lic.get("URL", "")
                    if "creative-commons" in url_lic.lower() or "creativecommons" in url_lic.lower():
                        has_cc_license = True
                        break

                # Post-filter Open Access in Python for Crossref if requested
                if filters and filters.get("is_oa") is not None:
                    if filters["is_oa"] and not has_cc_license:
                        continue
                    if not filters["is_oa"] and has_cc_license:
                        continue

                authors = "; ".join(
                    f"{a.get('family', '')} {a.get('given', '')}".strip()
                    for a in w.get("author", [])
                )
                
                issued = (w.get("issued") or {}).get("date-parts", [[0]])[0]
                year = issued[0] if issued else 0
                title = " ".join(w.get("title", [""]))
                source = " ".join(w.get("container-title", [""]))
                kws = "; ".join(w.get("subject", []))
                abstract = re.sub(r"<[^>]+>", " ", w.get("abstract", "") or "").strip()
                
                refs = "; ".join(
                    r.get("DOI", "") for r in w.get("reference", []) if r.get("DOI")
                )

                record = {
                    "authors":    authors,
                    "title":      title,
                    "year":       int(year or 0),
                    "source":     source,
                    "keywords":   kws,
                    "abstract":   abstract,
                    "citations":  int(w.get("is-referenced-by-count", 0)),
                    "doi":        (w.get("DOI", "") or "").strip(),
                    "references": refs,
                    "origin":     "Crossref",
                    "language":   str(w.get("language") or ""),
                    "is_oa":      has_cc_license,
                    "oa_url":     "" # Not provided as a direct download link by crossref usually
                }

                # Filtro de idioma client-side (BUG-02): descartados são CONTADOS.
                if wanted_lang and not _record_matches_language(record, wanted_lang):
                    self.language_filtered_count += 1
                    continue

                yield record
                count_fetched += 1

            if progress_cb and total_results:
                progress_cb(count_fetched, min(max_results, total_results))

            next_cursor = message.get("next-cursor")
            if not next_cursor or next_cursor == params.get("cursor"):
                self.stop_reason = "cursor encerrado (fim dos resultados)"
                break
            params["cursor"] = next_cursor

        if self.stop_reason is None:
            self.stop_reason = "atingiu limite"
        logger.info(f"[Crossref] parou: {self.stop_reason} · páginas={self.pages_fetched} · registros={count_fetched}")
