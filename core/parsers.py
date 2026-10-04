import re
import difflib
import pandas as pd
from pathlib import Path

from core.i18n import t
from core.document_types import normalize_document_type


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

#: Colunas de um resultado vazio. `document_type` faltava aqui e no RIS/PDF: o resumo por
#: tipo de documento tratava esses corpora como de schema antigo.
_COLUNAS = ["authors", "title", "year", "source", "document_type", "keywords",
            "abstract", "citations", "doi", "references", "origin"]


def ler_csv_tolerante(caminho, **kwargs) -> pd.DataFrame:
    """Lê CSV exportado direto da base OU reaberto e salvo no Excel.

    O Excel em português grava com `;` e em Windows-1252. Abrir o CSV do Scopus no Excel e
    salvar de novo — passo comum para "dar uma olhada" — fazia a importação falhar com erro
    de codificação (auditoria 2026-09, W1). O separador vem do cabeçalho; a codificação é
    tentada em UTF-8 e, se não servir, em Windows-1252.
    """
    with open(caminho, "rb") as f:
        cabeca = f.read(65536)
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = cabeca.decode(codificacao)
        except UnicodeDecodeError:
            continue
        primeira = texto.splitlines()[0] if texto else ""
        sep = ";" if primeira.count(";") > primeira.count(",") else ","
        try:
            return pd.read_csv(caminho, sep=sep, encoding=codificacao, **kwargs)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(caminho, encoding="latin-1", **kwargs)


def ler_texto_tolerante(caminho) -> str:
    """Texto de um export bibliográfico, qualquer que seja a codificação que a base usou.

    UTF-16 só aparece com BOM (o "Tab-delimited (Win)" antigo do WoS). UTF-8 pode vir com ou
    sem BOM; o BOM não pode sobrar na primeira linha, senão a primeira etiqueta (`TY`, `PMID`,
    `FN`) deixa de ser reconhecida. O que não for UTF-8 válido é Windows-1252: é como o EndNote
    e o JabRef antigos no Windows gravam, e ler em UTF-8 estrito derrubava a importação inteira
    por causa de um `é` (BibTeX) ou trocava acentos por `�` (RIS, MEDLINE).
    """
    dados = Path(caminho).read_bytes()
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return dados.decode("utf-16")
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


def _ano(valor) -> int:
    """Ano de quatro dígitos dentro de qualquer valor (`2020`, `"2020a"`, `"JAN 2026"`,
    `2020.0`, `None`). Sem ano reconhecível devolve 0, que o app trata como "sem ano"."""
    if valor is None:
        return 0
    if isinstance(valor, float):
        if valor != valor:          # NaN
            return 0
        valor = int(valor)
    m = re.search(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)", str(valor))
    return int(m.group()) if m else 0


def _inteiro(valor) -> int:
    """Contagem de citações vinda de texto: vazio, `"12"`, `"12.0"` e `NaN` não derrubam."""
    try:
        n = float(str(valor).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0
    return int(n) if n == n else 0


#: Marcadores que as bases põem no lugar de um campo vazio. Lidos como dado, viram um
#: "autor" que aparece em centenas de artigos (mapa de coautoria) e um termo "abstract
#: available" no mapa de termos do resumo.
_MARCADORES_VAZIOS = {
    "[no author name available]", "[anonymous]", "anonymous", "[no abstract available]",
    "[no author id available]",
}


def _sem_marcador(valor: str) -> str:
    texto = str(valor or "").strip()
    return "" if texto.lower() in _MARCADORES_VAZIOS else texto


_RE_DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)


class BibliometricParser:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.df: pd.DataFrame | None = None

    # ------------------------------------------------------------------ #
    #  CSV do próprio Blicsa (schema canônico em minúsculas)               #
    # ------------------------------------------------------------------ #
    def load_blicsa_csv(self) -> pd.DataFrame:
        """CSV no schema do Blicsa: o que "Exportar corpus (CSV)" grava e o formato de
        `docs/sample_dataset.csv`. Sem este leitor o arquivo caía no leitor Scopus, que não
        acha nenhuma coluna e devolve 0 registros sem erro (B1, auditoria 2026-09)."""
        from core.project import normalize_dataframe
        raw = ler_csv_tolerante(self.file_path, dtype=str, keep_default_na=False)
        df = normalize_dataframe(raw)
        if "origin" in df.columns:
            df["origin"] = df["origin"].where(df["origin"].astype(str).str.strip() != "",
                                              "Blicsa CSV")
        self.df = df
        return self.df

    @staticmethod
    def is_blicsa_csv_header(first_line: str) -> bool:
        """Cabeçalho do schema do Blicsa? Exige os nomes exatos em minúsculas, o que o
        distingue do Scopus (`Authors`, `Title`, `Year`, com maiúscula)."""
        cols = {c.strip().strip('"') for c in first_line.lstrip("\ufeff").split(",")}
        return {"authors", "title", "year"} <= cols

    # ------------------------------------------------------------------ #
    #  Scopus CSV                                                          #
    # ------------------------------------------------------------------ #
    def load_scopus_csv(self) -> pd.DataFrame:
        raw = ler_csv_tolerante(self.file_path)

        def col(nome: str) -> pd.Series:
            # Coluna ausente vira coluna vazia DO MESMO TAMANHO: uma Series vazia aqui
            # deixava `NaN` (e não "") nos registros quando o usuário desmarcava o campo
            # no diálogo de exportação do Scopus.
            if nome in raw.columns:
                return raw[nome]
            return pd.Series("", index=raw.index, dtype=object)

        df = pd.DataFrame(index=raw.index)
        # "[No author name available]" e "[No abstract available]" são marcadores do Scopus,
        # não dados: viravam um autor fantasma presente em todo registro sem autoria e o
        # termo "abstract available" no mapa de termos do resumo.
        df["authors"]    = col("Authors").fillna("").map(_sem_marcador)
        df["title"]      = col("Title").fillna("")
        # `_ano`/`_inteiro` em vez de `astype(int)`: uma célula com texto (planilha mexida no
        # Excel) derrubava o arquivo inteiro com "invalid literal for int()".
        df["year"]       = col("Year").map(_ano).astype(int)
        df["source"]     = col("Source title").fillna("")
        df["document_type"] = col("Document Type").fillna("").map(normalize_document_type)
        df["keywords"]   = col("Author Keywords").fillna("")
        df["abstract"]   = col("Abstract").fillna("").map(_sem_marcador)
        df["citations"]  = col("Cited by").map(_inteiro).astype(int)
        df["doi"]        = col("DOI").fillna("")
        df["references"] = col("References").fillna("")
        df["origin"]     = "Scopus"
        self.df = df.reset_index(drop=True)
        return self.df

    # ------------------------------------------------------------------ #
    #  Web of Science TXT                                                  #
    # ------------------------------------------------------------------ #
    #: Etiquetas do WoS que guardam uma LISTA, um item por linha (autores, endereços,
    #: referências). Nas demais (TI, SO, DE, ID, AB, WC...) a linha de continuação é o mesmo
    #: texto quebrado na largura da página e precisa ser emendada com espaço: emendar com
    #: `; ` partia o título em dois e criava a palavra-chave "Knowledge" separada de
    #: "structure" quando o DE quebrava no meio do termo.
    _WOS_LISTAS = {"AU", "AF", "BA", "BF", "CA", "GP", "ED", "BE", "CR", "C1", "C3"}

    def _wos_e_etiquetado(self) -> bool:
        """O `.txt` do Web of Science vem em dois sabores, e só um tem tabulação.

        *Tab delimited* é uma planilha com cabeçalho de siglas. *Plain text* é etiquetado,
        um campo por linha (`AU Silva, J`), registros fechados por `ER` — e é a opção que a
        interface do WoS oferece primeiro. Lido como TSV, o etiquetado produz **zero
        registros e nenhum erro**: o usuário importava o arquivo certo e via um corpus vazio.
        """
        for linha in ler_texto_tolerante(self.file_path).splitlines():
            if "\t" in linha:
                return False
            if linha.startswith(("PT ", "PT\t")):
                return True
        return False

    def _load_wos_etiquetado(self) -> pd.DataFrame:
        """Export *plain text* do WoS: `TAG valor`, continuação com três espaços, `ER` fecha.

        `FN`/`VR` (cabeçalho do arquivo) e `EF` (fim) não pertencem a registro nenhum.
        """
        registros: list[dict] = []
        atual: dict[str, str] = {}
        tag: str | None = None

        for bruta in ler_texto_tolerante(self.file_path).splitlines():
            linha = bruta.rstrip("\r\n")
            if not linha.strip():
                continue
            if linha.startswith("ER") and linha[2:].strip() == "":
                if atual:
                    registros.append(atual)
                atual, tag = {}, None
                continue
            if linha.startswith("EF") and linha[2:].strip() == "":
                break
            if linha.startswith("   ") and tag:
                # Continuação. Em listas (autores, referências) cada linha é um item, e o
                # separador é `; ` porque é o que o resto do Blicsa espera. No resto é texto
                # quebrado pela largura da linha.
                junta = "; " if tag in self._WOS_LISTAS else " "
                anterior = atual.get(tag, "")
                atual[tag] = f"{anterior}{junta}{linha.strip()}" if anterior else linha.strip()
                continue
            nova = linha[:2].strip()
            if len(nova) == 2 and linha[2:3] in (" ", ""):
                tag = nova
                if tag in ("FN", "VR"):
                    tag = None
                    continue
                atual[tag] = linha[3:].strip()

        if atual:                      # arquivo sem `ER` no último registro
            registros.append(atual)

        campos = ["AU", "TI", "PY", "EY", "EA", "SO", "DT", "DE", "ID", "AB", "TC", "DI",
                  "CR", "LA", "UT"]
        return pd.DataFrame(
            [{c: r.get(c, "") for c in campos} for r in registros],
            columns=campos,
        )

    def _load_wos_tabulado(self) -> pd.DataFrame:
        """Export *Tab delimited* do WoS.

        O arquivo real começa direto no cabeçalho de siglas (`PT\tAU\t...`), com BOM. A
        versão antiga deste leitor pulava a primeira linha sempre (`skiprows=1`), pensada para
        um arquivo com linha `FN` antes do cabeçalho: no arquivo real o cabeçalho era
        descartado, o primeiro artigo virava cabeçalho e todos os campos saíam `nan`, sem erro.

        `QUOTE_NONE` porque o WoS não usa aspas como delimitador: um título com `"` abria uma
        "célula entre aspas" que engolia as linhas seguintes. `index_col=False` porque cada
        linha de dados termina com uma tabulação a mais que o cabeçalho.
        """
        import csv
        import io
        linhas = ler_texto_tolerante(self.file_path).splitlines()
        while linhas and "\t" not in linhas[0]:
            linhas.pop(0)               # `FN ...` de exports antigos
        if not linhas:
            return pd.DataFrame()
        # Tabulação sobrando no fim da linha: tirá-la só encurta a linha, e campo que falta
        # no fim vira vazio. Mantida, o pandas avisa "loss of data" a cada importação.
        linhas = [linhas[0]] + [ln.rstrip("\t") for ln in linhas[1:]]
        return pd.read_csv(io.StringIO("\n".join(linhas)), sep="\t", dtype=str,
                           keep_default_na=False, quoting=csv.QUOTE_NONE, index_col=False)

    def load_wos_txt(self) -> pd.DataFrame:
        if self._wos_e_etiquetado():
            raw = self._load_wos_etiquetado()
        else:
            raw = self._load_wos_tabulado()

        def col(nome: str) -> pd.Series:
            if nome in raw.columns:
                return raw[nome].fillna("").astype(str)
            return pd.Series("", index=raw.index, dtype=object)

        df = pd.DataFrame(index=raw.index)
        df["authors"]    = col("AU").map(_sem_marcador)
        df["title"]      = col("TI")
        # Registro em *Early Access* não tem PY: o ano está em EY (ou no fim de EA, "JAN
        # 2026"). Um único registro assim derrubava o arquivo inteiro com
        # "invalid literal for int()".
        df["year"]       = [(_ano(py) or _ano(ey) or _ano(ea))
                            for py, ey, ea in zip(col("PY"), col("EY"), col("EA"))]
        df["year"]       = df["year"].astype(int)
        df["source"]     = col("SO")
        df["document_type"] = col("DT").map(normalize_document_type)
        df["keywords"]   = col("DE")
        df["abstract"]   = col("AB")
        df["citations"]  = col("TC").map(_inteiro).astype(int)
        df["doi"]        = col("DI")
        df["references"] = col("CR")
        df["origin"]     = "Web of Science"
        self.df = df.reset_index(drop=True)
        return self.df

    # ------------------------------------------------------------------ #
    #  BibTeX                                                              #
    # ------------------------------------------------------------------ #
    #: `@type` do BibTeX que o vocabulário comum não conhece pelo nome.
    _BIBTEX_TIPOS = {
        "conference": "inproceedings", "phdthesis": "thesis", "mastersthesis": "thesis",
        "techreport": "report", "inbook": "incollection",
    }

    @staticmethod
    def _bibtex_autores(campo: str) -> str:
        """`Silva, J. and Souza, M.` → `Silva, J.; Souza, M.`.

        Os demais formatos chegam com `; ` e parte do app (índice h, Sankey, rótulo da
        citação direta) separa autores por `;` ou, na falta dele, por vírgula: com `and`,
        "Silva, J. and Souza, M." virava três pessoas ("Silva", "J. and Souza", "M.").
        O `and` só separa fora de chaves: `{Barnes and Noble}` é um autor só.
        """
        nomes, atual, nivel, i = [], [], 0, 0
        texto = " ".join(str(campo or "").split())
        while i < len(texto):
            c = texto[i]
            if c == "{":
                nivel += 1
            elif c == "}":
                nivel = max(0, nivel - 1)
            if nivel == 0 and texto[i:i + 5].lower() == " and ":
                nomes.append("".join(atual))
                atual, i = [], i + 5
                continue
            atual.append(c)
            i += 1
        nomes.append("".join(atual))
        # As chaves ficam: quem chama ainda converte o LaTeX (`Gon{\c{c}}alves`) e só então
        # as tira.
        return "; ".join(n.strip() for n in nomes if n.strip())

    @staticmethod
    def _bibtex_texto(valor: str) -> str:
        r"""Tira chaves de proteção e normaliza o Unicode que o conversor de LaTeX devolve
        decomposto (`{\'\i}` sai como "ı" + acento solto, que não casa com "í")."""
        import unicodedata
        texto = str(valor or "").replace("{", "").replace("}", "")
        texto = unicodedata.normalize("NFC", texto.replace("ı́", "í"))
        return " ".join(texto.split())

    def load_bibtex(self) -> pd.DataFrame:
        import bibtexparser
        from bibtexparser.bparser import BibTexParser
        from bibtexparser.customization import convert_to_unicode

        # `common_strings` resolve `month = aug` (Zotero); `convert_to_unicode` transforma
        # `{\'e}`, `\c{c}` e `{\~a}` em letras: sem ele, "Jos{\'e}" e "José" eram dois
        # autores diferentes no mapa de coautoria.
        # A conversão é feita depois de separar os autores: ela tira as chaves, e é a chave
        # que diz que o `and` de `{Barnes and Noble}` faz parte do nome.
        parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
        bib_db = bibtexparser.loads(ler_texto_tolerante(self.file_path), parser=parser)
        txt = self._bibtex_texto

        def unicode(valor: str) -> str:
            return convert_to_unicode({"v": valor})["v"]

        records = []
        for bruto in bib_db.entries:
            autores = "; ".join(unicode(a) for a in
                                self._bibtex_autores(bruto.get("author", "")).split("; ") if a)
            entry = convert_to_unicode(dict(bruto))
            # O export BibTeX do Scopus traz os campos que o CSV traz, com outros nomes:
            # `author_keywords`, `references`, `type` e as citações dentro de `note`
            # ("Cited by: 12" ou, nos exports antigos, "cited By 12").
            nota = entry.get("note", "")
            m_cit = re.search(r"cited\s+by\s*:?\s*(\d+)", nota, re.I)
            tipo = entry.get("type") or self._BIBTEX_TIPOS.get(
                entry.get("ENTRYTYPE", "").lower(), entry.get("ENTRYTYPE", ""))
            records.append({
                "authors":    txt(autores).replace(" ;", ";"),
                "title":      txt(entry.get("title", "")),
                "year":       _ano(entry.get("year", "")),
                "source":     txt(entry.get("journal", entry.get("booktitle", ""))),
                "document_type": normalize_document_type(tipo),
                "keywords":   txt(entry.get("author_keywords") or entry.get("keywords", "")),
                "abstract":   txt(entry.get("abstract", "")),
                "citations":  int(m_cit.group(1)) if m_cit else 0,
                "doi":        entry.get("doi", "").strip(),
                "references": txt(entry.get("references", "")),
                "origin":     "BibTeX",
            })
        self.df = pd.DataFrame(records) if records else pd.DataFrame(columns=_COLUNAS)
        return self.df

    # ------------------------------------------------------------------ #
    #  PubMed MEDLINE (.txt / .nbib)                                      #
    # ------------------------------------------------------------------ #
    def load_pubmed_medline(self) -> pd.DataFrame:
        text = ler_texto_tolerante(self.file_path)
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
            # Keywords: prefer MeSH (MH) then Other Terms (OT). O `*` do MeSH só marca o
            # assunto principal: "*Humans" e "Humans" são o mesmo descritor.
            kw = r.get("MH", r.get("OT", r.get("KW", "")))
            kw = "; ".join(k.strip().lstrip("*") for k in kw.split(";") if k.strip())
            # O DOI é o identificador marcado com `[doi]`, em LID ou AID. Antes vinha o
            # primeiro LID inteiro, que costuma ser o `[pii]` da editora
            # ("S0140-6736(20)30183-5 [pii]; 10.1016/...") e a deduplicação por DOI falhava.
            ids = f"{r.get('LID', '')}; {r.get('AID', '')}"
            m_doi = re.search(r"(\S+)\s*\[doi\]", ids)
            rows.append({
                "authors":    r.get("AU", r.get("FAU", "")),
                "title":      r.get("TI", ""),
                "year":       self._extract_year(r.get("DP", r.get("DA", "0"))),
                "source":     r.get("JT", r.get("TA", "")),
                "document_type": normalize_document_type(r.get("PT", "")),
                "keywords":   kw,
                "abstract":   r.get("AB", ""),
                "citations":  0,
                "doi":        m_doi.group(1) if m_doi else "",
                "references": "",
                "origin":     "PubMed",
                "language":   r.get("LA", ""),
            })
        self.df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLUNAS)
        return self.df

    # ------------------------------------------------------------------ #
    #  OpenAlex JSON                                                       #
    # ------------------------------------------------------------------ #
    def load_openalex_json(self) -> pd.DataFrame:
        import json
        data = json.loads(ler_texto_tolerante(self.file_path))
        # Accept list of works or {results: [...]} wrapper
        if isinstance(data, dict):
            works = data.get("results", data.get("works", [data]))
        else:
            works = data

        rows = []
        for w in works:
            if not isinstance(w, dict):
                continue
            # Autor sem nome (`"display_name": null`) acontece no OpenAlex e derrubava o
            # arquivo inteiro com TypeError no `join`.
            authors = "; ".join(
                ((a or {}).get("author") or {}).get("display_name") or ""
                for a in (w.get("authorships") or [])
                if ((a or {}).get("author") or {}).get("display_name")
            )
            # `display_name` (formato atual) ou `keyword` (formato de 2023 das keywords).
            itens = w.get("keywords") or w.get("concepts") or []
            kws = "; ".join(
                (c.get("display_name") or c.get("keyword") or "") for c in itens
                if isinstance(c, dict) and (c.get("display_name") or c.get("keyword"))
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
                src = src_obj.get("display_name", "") or ""
            oa = w.get("open_access") or {}

            rows.append({
                "authors":    authors,
                "title":      w.get("title") or w.get("display_name") or "",
                "year":       int(w.get("publication_year") or 0),
                "source":     src,
                "document_type": normalize_document_type(w.get("type")),
                "keywords":   kws,
                "abstract":   abstract,
                "citations":  int(w.get("cited_by_count") or 0),
                "doi":        w.get("doi", "") or "",
                # Mesmo formato da busca integrada (`core/sources/openalex.py`): sem
                # `referenced_works` e `id`, um JSON do OpenAlex importado não gerava
                # cocitação, acoplamento nem citação direta.
                "references": "; ".join(r for r in (w.get("referenced_works") or []) if r),
                "openalex_id": str(w.get("id") or ""),
                "origin":     "OpenAlex",
                "language":   str(w.get("language") or ""),
                "is_oa":      bool(oa.get("is_oa", False)),
                "oa_url":     str(oa.get("oa_url") or ""),
            })
        self.df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLUNAS)
        return self.df

    # ------------------------------------------------------------------ #
    #  Crossref JSON                                                       #
    # ------------------------------------------------------------------ #
    def load_crossref_json(self) -> pd.DataFrame:
        """Parse Crossref API works response.
        Accepts: {message:{items:[...]}} wrapper, {items:[...]}, a single work
        ({message:{...work...}} from /works/{doi}) or bare list.
        """
        import json, re as _re
        data = json.loads(ler_texto_tolerante(self.file_path))
        if isinstance(data, dict):
            # `/works/{doi}` devolve UM work em `message`, sem `items`. Antes o envelope
            # inteiro era tratado como o work e saía um registro todo vazio.
            msg = data.get("message", data)
            items = msg.get("items", [msg]) if isinstance(msg, dict) else []
        else:
            items = list(data)

        rows = []
        for w in items:
            if not isinstance(w, dict):
                continue
            # Autor institucional vem em `name`, sem `family`/`given`.
            nomes = [
                (f"{a.get('family', '')} {a.get('given', '')}".strip() or a.get("name", "")).strip()
                for a in (w.get("author") or [])
            ]
            authors = "; ".join(n for n in nomes if n)
            issued = ((w.get("issued") or {}).get("date-parts") or [[0]])[0]
            year   = issued[0] if issued else 0
            title  = " ".join(w.get("title") or [""])
            source = " ".join(w.get("container-title") or [""])
            kws    = "; ".join(w.get("subject") or [])
            # O `<jats:title>Abstract</jats:title>` é rótulo de seção, não texto.
            abstract = _re.sub(r"<jats:title>.*?</jats:title>", " ", w.get("abstract", "") or "")
            abstract = " ".join(_re.sub(r"<[^>]+>", " ", abstract).split())
            refs   = "; ".join(
                r.get("DOI", "") for r in (w.get("reference") or []) if r.get("DOI")
            )
            rows.append({
                "authors":    authors,
                "title":      title,
                "year":       int(year or 0),
                "source":     source,
                "document_type": normalize_document_type(w.get("type")),
                "keywords":   kws,
                "abstract":   abstract,
                "citations":  int(w.get("is-referenced-by-count", 0) or 0),
                "doi":        (w.get("DOI", "") or "").strip(),
                "references": refs,
                "origin":     "Crossref",
                "language":   str(w.get("language") or ""),
            })
        self.df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLUNAS)
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
            raise RuntimeError(t("deps.missing_pdf", pkg="pdfplumber"))
        full_text = ""
        titulo_meta = ""
        try:
            with pdfplumber.open(self.file_path) as pdf:
                titulo_meta = str((getattr(pdf, "metadata", None) or {}).get("Title") or "")
                for page in pdf.pages:
                    # `texto`, não `t`: uma variável local `t` sombreava a função de
                    # tradução `t()` usada no `except ImportError` acima (B5).
                    texto = page.extract_text()
                    if texto: full_text += texto + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        # DOI impresso no próprio artigo (cabeçalho ou rodapé da primeira página).
        m_doi = _RE_DOI.search(full_text[:20000])
        df = pd.DataFrame()
        df["authors"]    = pd.Series([""], dtype=str)
        df["title"]      = pd.Series([titulo_meta.strip() or self.file_path.name], dtype=str)
        # 0 = "sem ano". Antes era 2024 fixo: todo PDF entrava no corpus como sendo de 2024 e
        # contaminava a linha do tempo e o filtro de período.
        df["year"]       = pd.Series([0], dtype=int)
        df["source"]     = pd.Series(["PDF File"], dtype=str)
        df["document_type"] = pd.Series([""], dtype=str)
        df["keywords"]   = pd.Series([""], dtype=str)
        df["abstract"]   = pd.Series([full_text], dtype=str)
        df["citations"]  = pd.Series([0], dtype=int)
        df["doi"]        = pd.Series([m_doi.group().rstrip(".,;)") if m_doi else ""], dtype=str)
        df["references"] = pd.Series([""], dtype=str)
        df["origin"]     = "PDF Full-Text"
        self.df = df
        return self.df

    # ------------------------------------------------------------------ #
    #  RIS (Scopus, Zotero, Mendeley, EndNote, WoS)                        #
    # ------------------------------------------------------------------ #
    #: `TY` do RIS → vocabulário de `normalize_document_type`.
    _RIS_TIPOS = {
        "JOUR": "article", "JFULL": "article", "EJOUR": "article", "MGZN": "article",
        "NEWS": "other", "CONF": "conference-paper", "CPAPER": "conference-paper",
        "CHAP": "book-chapter", "ECHAP": "book-chapter", "BOOK": "book", "EBOOK": "book",
        "EDBOOK": "book", "THES": "dissertation", "RPRT": "report", "DATA": "dataset",
        "STAND": "standard", "UNPB": "preprint",
    }
    #: Rótulos que o Scopus põe depois de "References:" quando junta tudo num `N1` só.
    _RIS_N1_ROTULOS = ("Correspondence Address", "Export Date", "Cited By", "Funding details",
                       "Funding text", "Tradenames", "Manufacturers", "Chemicals/CAS",
                       "Molecular Sequence Numbers", "Sponsors", "Publisher", "Conference name",
                       "Conference date", "Conference code", "CODEN",
                       "Language of Original Document", "Abbreviated Source Title", "PubMed ID")

    @classmethod
    def _ris_nota(cls, nota: str, atual: dict) -> None:
        """`N1` do Scopus: "Cited By :12", "References: a; b; c" (linhas separadas ou tudo
        numa linha só, conforme a versão do export)."""
        m = re.search(r"Cited By\s*:\s*(\d+)", nota, re.I)
        if m:
            atual["citations"] = int(m.group(1))
        m = re.search(r"References\s*:\s*", nota)
        if m:
            resto = nota[m.end():]
            rotulos = "|".join(re.escape(r) for r in cls._RIS_N1_ROTULOS)
            corte = re.search(rf";\s*(?:{rotulos})\s*:", resto, re.I)
            if corte:
                resto = resto[:corte.start()]
            atual["references"] = resto.strip().rstrip(";").strip()

    def load_ris(self) -> pd.DataFrame:
        """RIS: `TG  - valor`, um campo por linha, registro aberto por `TY` e fechado por
        `ER  - `.

        Antes o fim de registro só era reconhecido se a linha fosse exatamente "ER". No RIS
        real (Scopus, Zotero, Mendeley, EndNote) a linha é "ER  - ", com hífen: **todos os
        registros do arquivo viravam um só**, com os autores de todos somados e o título do
        último. Agora `ER` fecha em qualquer grafia, e um `TY` novo também fecha o anterior.
        """
        text = ler_texto_tolerante(self.file_path)
        records: list[dict] = []
        current: dict = {}
        ultima: str | None = None

        # Etiqueta: letra + letra/dígito, espaços, hífen. `ER  -` sem nada depois também casa.
        pattern = re.compile(r"^([A-Z][A-Z0-9])\s*-(?:\s(.*))?$")
        continua = {"AB": "abstract", "N2": "abstract", "TI": "title", "T1": "title"}

        def fechar():
            nonlocal current, ultima
            if any(not k.startswith("_") for k in current):
                records.append(current)
            current, ultima = {}, None

        for bruta in text.splitlines():
            line = bruta.strip()
            if not line:
                continue
            if line == "ER":
                fechar()
                continue
            m = pattern.match(line)
            if not m:
                # Continuação sem etiqueta (resumo quebrado em várias linhas pelo EndNote).
                if ultima in continua:
                    chave = continua[ultima]
                    current[chave] = f"{current.get(chave, '')} {line}".strip()
                continue
            tag, val = m.group(1), (m.group(2) or "").strip()
            ultima = tag
            if tag == "ER":
                fechar()
            elif tag == "TY":
                if current:
                    fechar()
                current["_ty"] = val.upper()
            elif tag in ("AU", "A1"):
                # A2/ED são editores (organizadores do livro): não são coautores.
                if val:
                    current.setdefault("authors", []).append(val)
            elif tag in ("TI", "T1"):
                if val and not current.get("title"):
                    current["title"] = val
            elif tag in ("PY", "Y1", "DA"):
                ano = _ano(val)
                prio = ("PY", "Y1", "DA").index(tag)
                if ano and prio < current.get("_ano_prio", 9):
                    current["year"], current["_ano_prio"] = ano, prio
            elif tag in ("T2", "JF", "JO", "BT", "JA", "J2"):
                prio = ("T2", "JF", "JO", "BT", "JA", "J2").index(tag)
                if val and prio < current.get("_src_prio", 9):
                    current["source"], current["_src_prio"] = val, prio
            elif tag == "KW":
                if val:
                    current.setdefault("keywords", []).append(val)
            elif tag in ("AB", "N2"):
                if val and (tag == "AB" or "abstract" not in current):
                    current["abstract"] = val
            elif tag == "DO":
                if val:
                    current["doi"] = val
            elif tag == "UR" and "doi" not in current:
                m_doi = re.search(r"doi\.org/(10\.\S+)", val)
                if m_doi:
                    current["doi"] = m_doi.group(1)
            elif tag == "N1":
                self._ris_nota(val, current)
            elif tag == "M3":
                current["_m3"] = val
            elif tag == "LA":
                current["language"] = val

        fechar()

        rows = []
        for r in records:
            # M3 é o tipo do Scopus ("Review", "Conference paper"); nos outros gerenciadores
            # é texto livre, então só vale se for um tipo reconhecido.
            tipo = normalize_document_type(r.get("_m3", ""))
            if tipo in ("", "other"):
                ty = r.get("_ty", "")
                tipo = normalize_document_type(self._RIS_TIPOS.get(ty, ty))
            rows.append({
                "authors":    "; ".join(r.get("authors", [])),
                "title":      r.get("title", ""),
                "year":       r.get("year", 0),
                "source":     r.get("source", ""),
                "document_type": tipo,
                "keywords":   "; ".join(r.get("keywords", [])),
                "abstract":   r.get("abstract", ""),
                "citations":  r.get("citations", 0),
                "doi":        r.get("doi", ""),
                "references": r.get("references", ""),
                "origin":     "RIS",
                "language":   r.get("language", ""),
            })

        self.df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLUNAS)
        return self.df

    @staticmethod
    def merge(*dataframes: pd.DataFrame) -> pd.DataFrame:
        combined = pd.concat(list(dataframes), ignore_index=True)
        combined.drop_duplicates(subset=["doi", "title"], keep="first", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        return combined
