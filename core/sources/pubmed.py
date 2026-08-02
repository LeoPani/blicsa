import urllib.parse
import json
import logging
import re
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider

logger = logging.getLogger("PubMedProvider")

# PubMed usa códigos ISO 639-2 ([LA]); o app envia ISO 639-1 (pt, en...).
_ISO639_1_TO_2 = {
    "pt": "por", "en": "eng", "fr": "fre", "es": "spa", "de": "ger",
    "it": "ita", "ru": "rus", "zh": "chi", "ja": "jpn", "ko": "kor",
}


def _pubmed_lang_code(code: str) -> Optional[str]:
    """Converte ISO 639-1 -> 639-2 para o filtro [LA] do PubMed.
    Aceita também um 639-2 já válido. Desconhecido -> None (não aplicar filtro)."""
    c = str(code).strip().lower()
    if c in _ISO639_1_TO_2:
        return _ISO639_1_TO_2[c]
    if c in _ISO639_1_TO_2.values():
        return c
    return None


class PubMedProvider(SearchProvider):
    def count(self, query: str, filters: Optional[Dict[str, Any]] = None, cancel_event=None) -> int:
        """Total de resultados (esearchresult.count) com retmax=0 — request barata."""
        term_parts = [query.strip()] if query.strip() else []
        f = filters or {}
        if f.get("year_start") and f.get("year_end"):
            term_parts.append(f"({f['year_start']}:{f['year_end']}[DP])")
        if f.get("type"):
            term_parts.append(f"({f['type']}[PT])")
        if f.get("language"):
            la = _pubmed_lang_code(f["language"])
            if la:
                term_parts.append(f"{la}[LA]")
        term = " AND ".join(term_parts) if term_parts else "all[Filter]"
        params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 0}
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=0.35))
        return int(data.get("esearchresult", {}).get("count", 0))

    # O PubMed não tem `group_by`; as facetas ficariam mentindo na UI (origem do BUG-02).
    FACETS: Dict[str, str] = {}

    def _term(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """Monta o `term` do E-utilities a partir da query + filtros."""
        partes = [query.strip()] if query.strip() else []
        f = filters or {}
        if f.get("year_start") and f.get("year_end"):
            partes.append(f"({f['year_start']}:{f['year_end']}[DP])")
        if f.get("type"):
            partes.append(f"({f['type']}[PT])")
        if f.get("language"):
            la = _pubmed_lang_code(f["language"])
            if la:
                partes.append(f"{la}[LA]")
        return " AND ".join(partes) if partes else "all[Filter]"

    def _parse_medline(self, texto: str) -> list[Dict[str, Any]]:
        """MEDLINE cru → lista de dicionários por tag (mesmo parser do `search`)."""
        registros, atual, tag_atual = [], {}, None
        for linha in texto.splitlines():
            if not linha.strip():
                if atual:
                    registros.append(atual)
                    atual, tag_atual = {}, None
                continue
            m = re.match(r"^([A-Z0-9]{2,4})\s*-\s*(.*)$", linha)
            if m:
                tag, valor = m.group(1), m.group(2).strip()
                tag_atual = tag
                atual[tag] = (atual[tag] + "; " + valor) if tag in atual else valor
            elif tag_atual and linha.startswith("      "):
                atual[tag_atual] = atual.get(tag_atual, "") + " " + linha.strip()
        if atual:
            registros.append(atual)
        return registros

    def _record_from_medline(self, r: Dict[str, Any]) -> Dict[str, Any]:
        kw = r.get("MH", r.get("OT", r.get("KW", "")))
        dp = r.get("DP", r.get("DA", "0"))
        m_ano = re.search(r"\b(19|20)\d{2}\b", dp)
        doi_raw = r.get("LID", r.get("AID", ""))
        m_doi = re.search(r"([^\s]+)\s+\[doi\]", doi_raw)
        return {
            "authors": r.get("AU", r.get("FAU", "")),
            "title": r.get("TI", ""),
            "year": int(m_ano.group()) if m_ano else 0,
            "source": r.get("JT", r.get("TA", "")),
            "keywords": kw,
            "abstract": r.get("AB", ""),
            "citations": 0,
            "doi": m_doi.group(1) if m_doi else doi_raw.strip(),
            "references": "",
            "origin": "PubMed",
            "language": r.get("LA", ""),
            "is_oa": False,
            "oa_url": "",
        }

    def browse(self, query: str, filters: Optional[Dict[str, Any]] = None,
               page: int = 1, per_page: int = 25, sort: Optional[str] = None, cancel_event=None):
        """Uma página via ESearch(retstart) + EFetch do lote. Devolve (registros, total)."""
        por_pagina = max(1, min(100, int(per_page)))
        inicio = max(0, (max(1, int(page)) - 1) * por_pagina)
        params = {"db": "pubmed", "term": self._term(query, filters), "retmode": "json",
                  "retmax": por_pagina, "retstart": inicio}
        if ((filters or {}).get("sort") or sort) == "date":
            params["sort"] = "pub_date"
        url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
               + urllib.parse.urlencode(params))
        dados = json.loads(self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=0.35))
        res = dados.get("esearchresult", {})
        total = int(res.get("count", 0) or 0)
        ids = res.get("idlist", []) or []
        if not ids:
            return [], total

        efetch = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
                  + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids),
                                            "retmode": "text", "rettype": "medline"}))
        texto = self.fetch_url(efetch, cancel_event=cancel_event, rate_limit_delay=0.35)
        return [self._record_from_medline(r) for r in self._parse_medline(texto)], total

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        # PubMed Rate Limit: max 3 requests per second
        rate_limit_delay = 0.35
        
        # 1. Build term
        term_parts = [query.strip()] if query.strip() else []
        if filters:
            if filters.get("year_start") and filters.get("year_end"):
                term_parts.append(f"({filters['year_start']}:{filters['year_end']}[DP])")
            elif filters.get("year_start"):
                term_parts.append(f"({filters['year_start']}:3000[DP])")
            elif filters.get("year_end"):
                term_parts.append(f"(1800:{filters['year_end']}[DP])")
                
            if filters.get("type"):
                term_parts.append(f"({filters['type']}[PT])")
            if filters.get("is_oa"):
                term_parts.append("free full text[SB]")
            if filters.get("language"):
                la = _pubmed_lang_code(filters["language"])
                if la:
                    term_parts.append(f"{la}[LA]")
                else:
                    logger.warning(
                        f"Idioma '{filters['language']}' sem mapeamento ISO 639-2; "
                        f"filtro de idioma NÃO aplicado no PubMed (evita zero silencioso)."
                    )

        term = " AND ".join(term_parts) if term_parts else "all[Filter]"

        # BUG-A: rastreio de parada.
        self.stop_reason = None
        self.stop_error = False
        self.pages_fetched = 0
        # Total REAL da base (esearchresult.count), independente do retmax pedido.
        self.total_available = 0

        # 2. Run ESearch to get PMIDs
        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        esearch_params = {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": max_results,
            "retstart": 0
        }
        # Ordenação server-side (PubMed não tem citações; 'date' → pub_date, resto = relevância).
        if (filters or {}).get("sort") == "date":
            esearch_params["sort"] = "pub_date"
        
        query_str = urllib.parse.urlencode(esearch_params)
        url = f"{esearch_url}?{query_str}"
        
        try:
            raw_data = self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=rate_limit_delay)
            esearch_data = json.loads(raw_data)
        except Exception as e:
            self.stop_reason = f"erro de rede na ESearch: {e}"
            self.stop_error = True
            logger.error(f"[PubMed] parou: {self.stop_reason}")
            return

        id_list = esearch_data.get("esearchresult", {}).get("idlist", [])
        total_results = int(esearch_data.get("esearchresult", {}).get("count", len(id_list)))
        self.total_available = total_results

        if not id_list:
            self.stop_reason = "exauriu (sem resultados)"
            return

        # Limit to max_results
        id_list = id_list[:max_results]
        
        # 3. Fetch details using EFetch in batches of 200 (since we limit by max_results anyway, typically one batch)
        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        batch_size = 100
        count_fetched = 0
        
        for i in range(0, len(id_list), batch_size):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Search cancelled by user")
                
            batch_ids = id_list[i : i + batch_size]
            efetch_params = {
                "db": "pubmed",
                "id": ",".join(batch_ids),
                "retmode": "text",
                "rettype": "medline"
            }
            
            efetch_query_str = urllib.parse.urlencode(efetch_params)
            url = f"{efetch_url}?{efetch_query_str}"
            
            self.pages_fetched += 1
            try:
                medline_text = self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=rate_limit_delay)
            except Exception as e:
                self.stop_reason = f"erro de rede na EFetch (lote {self.pages_fetched}): {e}"
                self.stop_error = True
                logger.error(f"[PubMed] parou: {self.stop_reason}")
                break
                
            # Parse MEDLINE format
            raw_records = []
            current = {}
            current_tag = None
            
            for line in medline_text.splitlines():
                if not line.strip():
                    if current:
                        raw_records.append(current)
                        current = {}
                        current_tag = None
                    continue
                m = re.match(r"^([A-Z0-9]{2,4})\s*-\s*(.*)$", line)
                if m:
                    tag, value = m.group(1), m.group(2).strip()
                    current_tag = tag
                    if tag in current:
                        current[tag] += "; " + value
                    else:
                        current[tag] = value
                elif current_tag and line.startswith("      "):
                    current[current_tag] = current.get(current_tag, "") + " " + line.strip()
                    
            if current:
                raw_records.append(current)
                
            for r in raw_records:
                kw = r.get("MH", r.get("OT", r.get("KW", "")))
                
                # Extract year
                dp = r.get("DP", r.get("DA", "0"))
                year_match = re.search(r"\b(19|20)\d{2}\b", dp)
                year = int(year_match.group()) if year_match else 0
                
                doi_raw = r.get("LID", r.get("AID", ""))
                doi_match = re.search(r"([^\s]+)\s+\[doi\]", doi_raw)
                doi = doi_match.group(1) if doi_match else doi_raw.strip()
                
                record = {
                    "authors":    r.get("AU", r.get("FAU", "")),
                    "title":      r.get("TI", ""),
                    "year":       year,
                    "source":     r.get("JT", r.get("TA", "")),
                    "keywords":   kw,
                    "abstract":   r.get("AB", ""),
                    "citations":  0, # PubMed doesn't return citation counts in medline format by default
                    "doi":        doi,
                    "references": "",
                    "origin":     "PubMed",
                    "language":   r.get("LA", ""),
                    "is_oa":      False,
                    "oa_url":     ""
                }
                yield record
                count_fetched += 1

            if progress_cb:
                progress_cb(count_fetched, len(id_list))

        if self.stop_reason is None:
            self.stop_reason = "atingiu limite" if count_fetched >= max_results else "exauriu (todos os PMIDs)"
        logger.info(f"[PubMed] parou: {self.stop_reason} · lotes={self.pages_fetched} · registros={count_fetched}")
