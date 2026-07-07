import re
import difflib
import pandas as pd
from pathlib import Path


# ── Deduplication helpers ───────────────────────────────────────────────────

def _norm_doi(d: str) -> str:
    d = (d or "").lower().strip()
    for pfx in ("https://doi.org/", "http://doi.org/",
                "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(pfx):
            d = d[len(pfx):]
    return d.rstrip("/")


def _norm_title(t: str) -> str:
    t = re.sub(r"[^\w\s]", "", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def _first_surname(authors: str) -> str:
    first = (authors or "").split(";")[0].split(",")[0].strip()
    return first.lower()


def find_duplicates(
    df: pd.DataFrame,
    title_threshold: float = 0.93,
) -> list[tuple[int, int, str]]:
    """
    Return [(keep_idx, remove_idx, reason)] using the df's original index.
    Three passes: DOI → fuzzy title (same year bucket) → (surname, year).
    """
    PRIO = {"Scopus": 0, "Web of Science": 1, "Crossref": 2,
            "OpenAlex": 3, "BibTeX": 4, "PubMed": 5}
    order = sorted(df.index, key=lambda i: PRIO.get(df.at[i, "origin"], 9))

    dupes: list[tuple[int, int, str]] = []
    remove_set: set[int] = set()

    # ── Pass 1: normalised DOI ──────────────────────────────────────────
    seen_doi: dict[str, int] = {}
    no_doi: list[int] = []
    for i in order:
        doi = _norm_doi(str(df.at[i, "doi"]))
        if doi:
            if doi in seen_doi:
                dupes.append((seen_doi[doi], i, "DOI duplicado"))
                remove_set.add(i)
            else:
                seen_doi[doi] = i
        else:
            no_doi.append(i)

    # ── Pass 2: title similarity within year bucket ─────────────────────
    buckets: dict[int, list[int]] = {}
    for i in no_doi:
        if i in remove_set:
            continue
        yr = int(df.at[i, "year"] or 0)
        buckets.setdefault(yr, []).append(i)

    for indices in buckets.values():
        for a, i1 in enumerate(indices):
            if i1 in remove_set:
                continue
            t1 = _norm_title(str(df.at[i1, "title"]))
            if len(t1) < 8:
                continue
            for i2 in indices[a + 1:]:
                if i2 in remove_set:
                    continue
                t2 = _norm_title(str(df.at[i2, "title"]))
                ratio = difflib.SequenceMatcher(None, t1, t2, autojunk=False).ratio()
                if ratio >= title_threshold:
                    dupes.append((i1, i2, f"Título similar ({ratio:.0%})"))
                    remove_set.add(i2)

    # ── Pass 3: (first surname, year) + relaxed title check ────────────
    remaining = [i for i in order if i not in remove_set]
    author_year: dict[tuple[str, int], int] = {}
    for i in remaining:
        sur = _first_surname(str(df.at[i, "authors"]))
        yr  = int(df.at[i, "year"] or 0)
        if not sur or not yr:
            continue
        key = (sur, yr)
        if key in author_year:
            j  = author_year[key]
            t1 = _norm_title(str(df.at[j, "title"]))
            t2 = _norm_title(str(df.at[i, "title"]))
            ratio = difflib.SequenceMatcher(None, t1, t2, autojunk=False).ratio()
            if ratio >= 0.75:
                dupes.append((j, i, f"Autor+Ano ({ratio:.0%})"))
                remove_set.add(i)
        else:
            author_year[key] = i

    return dupes

_EMPTY = pd.Series(dtype=str)
_EMPTY_INT = pd.Series(dtype=float)


class BibliometricParser:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.df: pd.DataFrame | None = None

    # ------------------------------------------------------------------ #
    #  Scopus CSV                                                          #
    # ------------------------------------------------------------------ #
    def load_scopus_csv(self) -> pd.DataFrame:
        raw = pd.read_csv(self.file_path)
        df = pd.DataFrame()
        df["authors"]    = raw.get("Authors",       _EMPTY.copy()).fillna("")
        df["title"]      = raw.get("Title",          _EMPTY.copy()).fillna("")
        df["year"]       = raw.get("Year",           _EMPTY_INT.copy()).fillna(0).astype(int)
        df["source"]     = raw.get("Source title",   _EMPTY.copy()).fillna("")
        df["keywords"]   = raw.get("Author Keywords",_EMPTY.copy()).fillna("")
        df["abstract"]   = raw.get("Abstract",       _EMPTY.copy()).fillna("")
        df["citations"]  = raw.get("Cited by",       _EMPTY_INT.copy()).fillna(0).astype(int)
        df["doi"]        = raw.get("DOI",            _EMPTY.copy()).fillna("")
        df["references"] = raw.get("References",     _EMPTY.copy()).fillna("")
        df["origin"]     = "Scopus"
        self.df = df
        return self.df

    # ------------------------------------------------------------------ #
    #  Web of Science TXT                                                  #
    # ------------------------------------------------------------------ #
    def load_wos_txt(self) -> pd.DataFrame:
        raw = pd.read_csv(self.file_path, sep="\t", skiprows=1, encoding="utf-8-sig")
        df = pd.DataFrame()
        df["authors"]    = raw.get("AU", _EMPTY.copy()).fillna("")
        df["title"]      = raw.get("TI", _EMPTY.copy()).fillna("")
        df["year"]       = raw.get("PY", _EMPTY_INT.copy()).fillna(0).astype(int)
        df["source"]     = raw.get("SO", _EMPTY.copy()).fillna("")
        df["keywords"]   = raw.get("DE", _EMPTY.copy()).fillna("")
        df["abstract"]   = raw.get("AB", _EMPTY.copy()).fillna("")
        df["citations"]  = raw.get("TC", _EMPTY_INT.copy()).fillna(0).astype(int)
        df["doi"]        = raw.get("DI", _EMPTY.copy()).fillna("")
        df["references"] = raw.get("CR", _EMPTY.copy()).fillna("")
        df["origin"]     = "Web of Science"
        self.df = df
        return self.df

    # ------------------------------------------------------------------ #
    #  BibTeX                                                              #
    # ------------------------------------------------------------------ #
    def load_bibtex(self) -> pd.DataFrame:
        import bibtexparser
        with open(self.file_path, encoding="utf-8") as f:
            bib_db = bibtexparser.load(f)
        records = []
        for entry in bib_db.entries:
            records.append({
                "authors":    entry.get("author", ""),
                "title":      entry.get("title", ""),
                "year":       int(entry.get("year", 0) or 0),
                "source":     entry.get("journal", entry.get("booktitle", "")),
                "keywords":   entry.get("keywords", ""),
                "abstract":   entry.get("abstract", ""),
                "citations":  0,
                "doi":        entry.get("doi", ""),
                "references": "",
                "origin":     "BibTeX",
            })
        self.df = pd.DataFrame(records)
        return self.df

    # ------------------------------------------------------------------ #
    #  PubMed MEDLINE (.txt / .nbib)                                      #
    # ------------------------------------------------------------------ #
    def load_pubmed_medline(self) -> pd.DataFrame:
        text = self.file_path.read_text(encoding="utf-8", errors="replace")
        raw_records: list[dict[str, str]] = []
        current: dict[str, str] = {}
        current_tag: str | None = None

        for line in text.splitlines():
            if not line.strip():
                if current:
                    raw_records.append(current)
                    current = {}
                    current_tag = None
                continue
            # MEDLINE field lines: "TAG - value" (tag is 2-4 chars, followed by " - ")
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

        rows = []
        for r in raw_records:
            # Keywords: prefer MeSH (MH) then Other Terms (OT)
            kw = r.get("MH", r.get("OT", r.get("KW", "")))
            rows.append({
                "authors":    r.get("AU", r.get("FAU", "")),
                "title":      r.get("TI", ""),
                "year":       self._extract_year(r.get("DP", r.get("DA", "0"))),
                "source":     r.get("JT", r.get("TA", "")),
                "keywords":   kw,
                "abstract":   r.get("AB", ""),
                "citations":  0,
                "doi":        r.get("LID", r.get("AID", "")).replace(" [doi]", "").strip(),
                "references": "",
                "origin":     "PubMed",
            })
        self.df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[
                "authors","title","year","source","keywords",
                "abstract","citations","doi","references","origin",
            ])
        )
        return self.df

    # ------------------------------------------------------------------ #
    #  OpenAlex JSON                                                       #
    # ------------------------------------------------------------------ #
    def load_openalex_json(self) -> pd.DataFrame:
        import json
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        # Accept list of works or {results: [...]} wrapper
        if isinstance(data, dict):
            works = data.get("results", data.get("works", [data]))
        else:
            works = data

        rows = []
        for w in works:
            authors = "; ".join(
                a.get("author", {}).get("display_name", "")
                for a in w.get("authorships", [])
            )
            kws = "; ".join(
                c.get("display_name", "") for c in w.get("concepts", [])
            )
            abstract = w.get("abstract", "") or ""
            if not abstract and w.get("abstract_inverted_index"):
                inv = w["abstract_inverted_index"]
                word_pos: list[tuple[int, str]] = []
                for word, positions in inv.items():
                    for pos in positions:
                        word_pos.append((pos, word))
                abstract = " ".join(wd for _, wd in sorted(word_pos))

            src = ""
            if w.get("primary_location"):
                src_obj = (w["primary_location"] or {}).get("source") or {}
                src = src_obj.get("display_name", "")

            rows.append({
                "authors":    authors,
                "title":      w.get("title", "") or "",
                "year":       int(w.get("publication_year") or 0),
                "source":     src,
                "keywords":   kws,
                "abstract":   abstract,
                "citations":  int(w.get("cited_by_count") or 0),
                "doi":        w.get("doi", "") or "",
                "references": "",
                "origin":     "OpenAlex",
            })
        self.df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[
                "authors","title","year","source","keywords",
                "abstract","citations","doi","references","origin",
            ])
        )
        return self.df

    # ------------------------------------------------------------------ #
    #  Crossref JSON                                                       #
    # ------------------------------------------------------------------ #
    def load_crossref_json(self) -> pd.DataFrame:
        """Parse Crossref API works response.
        Accepts: {message:{items:[...]}} wrapper, {items:[...]} or bare list.
        """
        import json, re as _re
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("message", data).get("items", [data])
        else:
            items = list(data)

        rows = []
        for w in items:
            authors = "; ".join(
                f"{a.get('family', '')} {a.get('given', '')}".strip()
                for a in w.get("author", [])
            )
            issued = (w.get("issued") or {}).get("date-parts", [[0]])[0]
            year   = issued[0] if issued else 0
            title  = " ".join(w.get("title", [""]))
            source = " ".join(w.get("container-title", [""]))
            kws    = "; ".join(w.get("subject", []))
            abstract = _re.sub(r"<[^>]+>", " ", w.get("abstract", "") or "").strip()
            refs   = "; ".join(
                r.get("DOI", "") for r in w.get("reference", []) if r.get("DOI")
            )
            rows.append({
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
            })
        self.df = (
            pd.DataFrame(rows) if rows
            else pd.DataFrame(columns=[
                "authors","title","year","source","keywords",
                "abstract","citations","doi","references","origin",
            ])
        )
        return self.df

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_year(text: str) -> int:
        m = re.search(r"\b(19|20)\d{2}\b", text)
        return int(m.group()) if m else 0

    
    # ------------------------------------------------------------------ #
    #  PDF Full-Text                                                       #
    # ------------------------------------------------------------------ #
    def load_pdf(self) -> pd.DataFrame:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber is not installed. Please install it.")
        full_text = ""
        try:
            with pdfplumber.open(self.file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: full_text += t + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        import pandas as pd
        df = pd.DataFrame()
        df["authors"]    = pd.Series([""], dtype=str)
        df["title"]      = pd.Series([self.file_path.name], dtype=str)
        df["year"]       = pd.Series([2024], dtype=int)
        df["source"]     = pd.Series(["PDF File"], dtype=str)
        df["keywords"]   = pd.Series([""], dtype=str)
        df["abstract"]   = pd.Series([full_text], dtype=str)
        df["citations"]  = pd.Series([0], dtype=int)
        df["doi"]        = pd.Series([""], dtype=str)
        df["references"] = pd.Series([""], dtype=str)
        df["origin"]     = "PDF Full-Text"
        self.df = df
        return self.df

    def load_ris(self) -> pd.DataFrame:
        text = self.file_path.read_text(encoding="utf-8", errors="replace")
        records = []
        current = {}
        
        # Tags are normally 2 characters, followed by a space, a dash, and a space (e.g., 'TI  - ')
        pattern = re.compile(r"^([A-Z0-9]{2})\s*-\s*(.*)$")
        
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line == "ER": # End of Record
                if current:
                    records.append(current)
                    current = {}
                continue
            
            m = pattern.match(line)
            if m:
                tag, val = m.group(1), m.group(2).strip()
                if tag in ("AU", "A1", "A2"):
                    current.setdefault("authors", []).append(val)
                elif tag in ("TI", "T1"):
                    current["title"] = val
                elif tag in ("PY", "Y1"):
                    # Extract 4-digit year
                    yr_m = re.search(r"\b(19|20)\d{2}\b", val)
                    current["year"] = int(yr_m.group()) if yr_m else 0
                elif tag in ("T2", "JO", "JF", "JA"):
                    current["source"] = val
                elif tag == "KW":
                    current.setdefault("keywords", []).append(val)
                elif tag in ("AB", "N2"):
                    current["abstract"] = val
                elif tag == "DO":
                    current["doi"] = val
            
        if current:
            records.append(current)
            
        rows = []
        for r in records:
            authors_str = "; ".join(r.get("authors", []))
            keywords_str = "; ".join(r.get("keywords", []))
            rows.append({
                "authors":    authors_str,
                "title":      r.get("title", ""),
                "year":       r.get("year", 0),
                "source":     r.get("source", ""),
                "keywords":   keywords_str,
                "abstract":   r.get("abstract", ""),
                "citations":  0,
                "doi":        r.get("doi", ""),
                "references": "",
                "origin":     "RIS",
            })
            
        self.df = (
            pd.DataFrame(rows) if rows
            else pd.DataFrame(columns=[
                "authors","title","year","source","keywords",
                "abstract","citations","doi","references","origin",
            ])
        )
        return self.df

    @staticmethod
    def merge(*dataframes: pd.DataFrame) -> pd.DataFrame:
        combined = pd.concat(list(dataframes), ignore_index=True)
        combined.drop_duplicates(subset=["doi", "title"], keep="first", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        return combined
