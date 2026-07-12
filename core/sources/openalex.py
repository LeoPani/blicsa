import urllib.parse
import json
import logging
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider

logger = logging.getLogger("OpenAlexProvider")

class OpenAlexProvider(SearchProvider):
    def count(self, query: str, filters: Optional[Dict[str, Any]] = None, cancel_event=None) -> int:
        """Total de resultados numa ÚNICA request barata (nada é baixado)."""
        # Reusa a montagem de filtro de search() rodando um search 'a seco' de 1 página:
        # mais simples e sem duplicar a lógica de filtros.
        params: Dict[str, Any] = {"per_page": 1, "mailto": "blicsa.app@gmail.com"}
        fp = []
        f = filters or {}
        if f.get("year_start") and f.get("year_end"):
            fp.append(f"publication_year:{f['year_start']}-{f['year_end']}")
        elif f.get("year_start"):
            fp.append(f"publication_year:>{int(f['year_start']) - 1}")
        elif f.get("year_end"):
            fp.append(f"publication_year:<{int(f['year_end']) + 1}")
        if f.get("type"):
            fp.append(f"type:{f['type']}")
        if f.get("is_oa") is not None:
            fp.append(f"is_oa:{str(f['is_oa']).lower()}")
        if f.get("language"):
            fp.append(f"language:{f['language']}")
        if query.strip():
            fp.append(f"default.search:{query.strip()}")
        if fp:
            params["filter"] = ",".join(fp)
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        return int(data.get("meta", {}).get("count", 0))

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        base_url = "https://api.openalex.org/works"
        
        # Build filters
        filter_parts = []
        if filters:
            if filters.get("year_start") and filters.get("year_end"):
                filter_parts.append(f"publication_year:{filters['year_start']}-{filters['year_end']}")
            elif filters.get("year_start"):
                filter_parts.append(f"publication_year:>{int(filters['year_start']) - 1}")
            elif filters.get("year_end"):
                filter_parts.append(f"publication_year:<{int(filters['year_end']) + 1}")
                
            if filters.get("type"):
                filter_parts.append(f"type:{filters['type']}")
            if filters.get("is_oa") is not None:
                filter_parts.append(f"is_oa:{str(filters['is_oa']).lower()}")
            if filters.get("language"):
                filter_parts.append(f"language:{filters['language']}")

        params: Dict[str, Any] = {
            "per_page": min(100, max_results),
            "cursor": "*",
            "mailto": "blicsa.app@gmail.com"
        }
        
        import re
        q_str = query.strip()
        
        # Parse Scopus-like Query Builder syntax
        if re.search(r'(TITLE|AUTHOR|YEAR|TITLE-ABS-KEY)\(', q_str):
            oa_filters = []
            for match in re.finditer(r'(TITLE-ABS-KEY|TITLE|AUTHOR|YEAR)\("?([^")]+)"?\)', q_str):
                field, val = match.groups()
                val = val.strip()
                if field == "TITLE":
                    oa_filters.append(f"title.search:{val}")
                elif field == "AUTHOR":
                    oa_filters.append(f"author.id:{val}") # we'll use raw search below for names
                elif field == "YEAR":
                    oa_filters.append(f"publication_year:{val}")
                elif field == "TITLE-ABS-KEY":
                    oa_filters.append(f"default.search:{val}")
            
            # For Authors OpenAlex prefers author.search but it's not a standard filter for /works,
            # works filter uses authorships.author.display_name.search or raw search.
            # Actually, `default.search` handles everything nicely in a single query.
            # Let's rebuild it cleanly:
            for match in re.finditer(r'(TITLE-ABS-KEY|TITLE|AUTHOR|YEAR)\("?([^")]+)"?\)', q_str):
                field, val = match.groups()
                val = val.strip()
                if field == "TITLE":
                    filter_parts.append(f"title.search:{val}")
                elif field == "YEAR":
                    filter_parts.append(f"publication_year:{val}")
                elif field == "AUTHOR":
                    filter_parts.append(f"authorships.author.display_name.search:{val}")
                elif field == "TITLE-ABS-KEY":
                    filter_parts.append(f"default.search:{val}")
            
            # Clear q_str so we rely entirely on filters
            q_str = ""

        if q_str.strip():
            filter_parts.append(f"default.search:{q_str.strip()}")
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        # Ordenação server-side ("relevance" = padrão do OpenAlex, sem param).
        oa_sort = {"citations": "cited_by_count:desc",
                   "date": "publication_date:desc"}.get((filters or {}).get("sort"))
        if oa_sort:
            params["sort"] = oa_sort

        count_fetched = 0
        total_results = None
        # BUG-A: rastreio explícito do motivo de parada (nada de parada silenciosa).
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
                # fetch_url já faz 3 tentativas com backoff 1s/2s/4s antes de levantar.
                raw_data = self.fetch_url(url, cancel_event=cancel_event)
                data = json.loads(raw_data)
            except Exception as e:
                self.stop_reason = f"erro de rede na página {self.pages_fetched}: {e}"
                self.stop_error = True
                logger.error(f"[OpenAlex] parou: {self.stop_reason}")
                break

            results = data.get("results", [])
            meta = data.get("meta", {})
            
            if total_results is None:
                total_results = meta.get("count", len(results))

            if not results:
                self.stop_reason = "exauriu (sem resultados)"
                break

            for w in results:
                if count_fetched >= max_results:
                    break
                
                # Normalize OpenAlex structure to standard record schema
                authors = "; ".join(
                    a.get("author", {}).get("display_name", "")
                    for a in w.get("authorships", []) if a.get("author", {}).get("display_name")
                )
                kws = "; ".join(
                    c.get("display_name", "")
                    for c in w.get("concepts", []) if c.get("display_name")
                )
                
                abstract = w.get("abstract", "") or ""
                if not abstract and w.get("abstract_inverted_index"):
                    inv = w["abstract_inverted_index"]
                    word_pos = []
                    for word, positions in inv.items():
                        for pos in positions:
                            word_pos.append((pos, word))
                    abstract = " ".join(wd for _, wd in sorted(word_pos))

                src = ""
                if w.get("primary_location") and w["primary_location"].get("source"):
                    src = w["primary_location"]["source"].get("display_name", "") or ""

                oa_info = w.get("open_access", {})
                is_oa = bool(oa_info.get("is_oa", False))
                oa_url = str(oa_info.get("oa_url") or "")
                lang = str(w.get("language") or "")

                record = {
                    "authors":    authors,
                    "title":      w.get("title", "") or "",
                    "year":       int(w.get("publication_year") or 0),
                    "source":     src,
                    "keywords":   kws,
                    "abstract":   abstract,
                    "citations":  int(w.get("cited_by_count", 0)),
                    "doi":        w.get("doi", "") or "",
                    "references": "; ".join(w.get("referenced_works", [])),
                    "origin":     "OpenAlex",
                    "language":   lang,
                    "is_oa":      is_oa,
                    "oa_url":     oa_url,
                }
                yield record
                count_fetched += 1

            if progress_cb and total_results:
                progress_cb(count_fetched, min(max_results, total_results))

            next_cursor = meta.get("next_cursor")
            if not next_cursor or next_cursor == params.get("cursor"):
                self.stop_reason = "cursor encerrado (fim dos resultados)"
                break
            params["cursor"] = next_cursor

        if self.stop_reason is None:
            self.stop_reason = "atingiu limite"
        logger.info(f"[OpenAlex] parou: {self.stop_reason} · páginas={self.pages_fetched} · registros={count_fetched}")
