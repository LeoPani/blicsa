import urllib.parse
import json
import logging
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider

logger = logging.getLogger("OpenAlexProvider")

class OpenAlexProvider(SearchProvider):
    _FIELD_MAP = {
        "title":    "title.search",
        "author":   "authorships.author.display_name.search",
        "abstract": "title_and_abstract.search",
        "all":      "default.search",
    }

    def _oa_filter(self, query: str, filters: Optional[Dict[str, Any]]) -> str:
        """Valor de `filter=` a partir de filtros padrão + busca por campo (busca avançada)."""
        f = filters or {}
        fp = []
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
        # Linhas de busca avançada por campo (ANDadas via vírgula no OpenAlex).
        for field, value in (f.get("fields") or []):
            v = str(value).strip()
            if v:
                fp.append(f"{self._FIELD_MAP.get(field, 'default.search')}:{v}")
        if query and query.strip():
            fp.append(f"default.search:{query.strip()}")
        return ",".join(fp)

    def _normalize_work(self, w: Dict[str, Any]) -> Dict[str, Any]:
        authors = "; ".join(
            a.get("author", {}).get("display_name", "")
            for a in w.get("authorships", []) if a.get("author", {}).get("display_name"))
        kws = "; ".join(c.get("display_name", "") for c in w.get("concepts", []) if c.get("display_name"))
        abstract = w.get("abstract", "") or ""
        if not abstract and w.get("abstract_inverted_index"):
            inv = w["abstract_inverted_index"]
            word_pos = [(pos, word) for word, positions in inv.items() for pos in positions]
            abstract = " ".join(wd for _, wd in sorted(word_pos))
        src = ""
        if w.get("primary_location") and w["primary_location"].get("source"):
            src = w["primary_location"]["source"].get("display_name", "") or ""
        oa_info = w.get("open_access", {})
        return {
            "authors": authors, "title": w.get("title", "") or "",
            "year": int(w.get("publication_year") or 0), "source": src, "keywords": kws,
            "abstract": abstract, "citations": int(w.get("cited_by_count", 0)),
            "doi": w.get("doi", "") or "", "references": "; ".join(w.get("referenced_works", [])),
            "origin": "OpenAlex", "language": str(w.get("language") or ""),
            "is_oa": bool(oa_info.get("is_oa", False)), "oa_url": str(oa_info.get("oa_url") or ""),
        }

    def count(self, query: str, filters: Optional[Dict[str, Any]] = None, cancel_event=None) -> int:
        """Total de resultados numa ÚNICA request barata (nada é baixado)."""
        params: Dict[str, Any] = {"per_page": 1, "mailto": "blicsa.app@gmail.com"}
        flt = self._oa_filter(query, filters)
        if flt:
            params["filter"] = flt
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        return int(data.get("meta", {}).get("count", 0))

    def browse(self, query: str, filters: Optional[Dict[str, Any]] = None,
               page: int = 1, per_page: int = 25, sort: Optional[str] = None, cancel_event=None):
        """Paginação BÁSICA pulável (tipo Scopus): devolve (records_da_página, total).
        Não colhe tudo — só a página pedida. Navega os primeiros ~10.000 do OpenAlex."""
        params: Dict[str, Any] = {"per_page": max(1, min(200, per_page)),
                                  "page": max(1, page), "mailto": "blicsa.app@gmail.com"}
        flt = self._oa_filter(query, filters)
        if flt:
            params["filter"] = flt
        oa_sort = {"citations": "cited_by_count:desc",
                   "date": "publication_date:desc"}.get((filters or {}).get("sort") or sort)
        if oa_sort:
            params["sort"] = oa_sort
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        total = int(data.get("meta", {}).get("count", 0))
        records = [self._normalize_work(w) for w in data.get("results", [])]
        return records, total

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        base_url = "https://api.openalex.org/works"
        params: Dict[str, Any] = {
            "per_page": min(100, max_results),
            "cursor": "*",
            "mailto": "blicsa.app@gmail.com"
        }

        if filters and filters.get("fields"):
            # Busca avançada por campo (Coletar estilo Scopus) — construtor unificado.
            flt = self._oa_filter(query, filters)
            if flt:
                params["filter"] = flt
        else:
            # Caminho legado: filtros simples + sintaxe TITLE()/AUTHOR() na query.
            import re
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

            q_str = query.strip()
            if re.search(r'(TITLE|AUTHOR|YEAR|TITLE-ABS-KEY)\(', q_str):
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
