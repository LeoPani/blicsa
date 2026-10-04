#!/usr/bin/env python3
"""Auditoria das bases de dados do Blicsa — confere o que o app mostra contra a própria API.

Para que serve
==============
O pesquisador desconfia dos números das buscas. Este script responde, com evidência:

1. **O total está certo?** Pede à API de cada base, DIRETAMENTE (urllib, sem passar pelo
   código do Blicsa), quantos resultados ela declara para a consulta, com os mesmos filtros
   que o Blicsa usa — e compara com o "Encontrados" que o Blicsa mostra.
2. **Baixou tudo o que prometeu?** Roda a mesma busca pelo código real do Blicsa (o mesmo
   `provider.search(...)` que o app chama na importação) e registra: total declarado,
   baixados, limite, após deduplicação (o botão "Deduplicar" do Corpus) e tempo. Confere se a
   paginação foi até o fim quando o total cabia no limite.
3. **Os dados de cada artigo estão certos?** Sorteia 20 registros por base (espalhados do
   começo ao fim da lista), busca cada um direto na API pelo ID/DOI e compara campo a campo:
   título, ano, primeiro autor, número de autores, revista, DOI, citações, resumo presente,
   referências presentes, acesso aberto. Cada campo vira "ok", "diferença pequena" ou "errado".
4. **Duplicatas entre bases:** mesmo DOI no OpenAlex e no Crossref — a deduplicação do Blicsa
   (`core.parsers.find_duplicates`, a do botão "Deduplicar") pega?
5. Gera `auditoria_bases_<data>.md` (português simples, para ler) e `auditoria_bases_<data>.json`
   (dados brutos) na pasta de saída.

Como rodar (no Mac, com internet)
=================================
    cd ~/PyBibliomics && source venv/bin/activate && python scripts/auditar_bases.py --email seu@email

Outras opções:
    python scripts/auditar_bases.py --email seu@email --consulta "bibliometric analysis" --consulta "triple helix"
    python scripts/auditar_bases.py --email seu@email --limite 500 --saida ~/Desktop/auditoria
    python scripts/auditar_bases.py --email seu@email --bases openalex,crossref --ano-inicio 2015 --ano-fim 2024
    python scripts/auditar_bases.py --help

Leva alguns minutos (as APIs públicas pedem calma: o PubMed aceita 3 pedidos por segundo).
Ctrl+C a qualquer momento salva o que já foi auferido. Se uma base estiver fora do ar, ela é
marcada como "indisponível" e o script segue com as outras.

Polidez com as APIs
===================
* `mailto`/User-Agent com o e-mail de contato (`--email`; sem ele, o das configurações do app,
  e por fim o e-mail padrão do Blicsa). O e-mail é passado também ao provider do Blicsa, para
  que os dois lados da comparação usem a mesma identidade.
* Chaves de API (OpenAlex, NCBI) configuradas no app são usadas dos DOIS lados, pelo mesmo
  motivo; nunca aparecem no relatório (são apagadas das URLs).
* Timeout por pedido, novas tentativas com espera crescente em 429/5xx/falha de rede, e
  respeito ao `Retry-After`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import logging
import re
import socket
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# ── Constantes ────────────────────────────────────────────────────────────────────────

CONSULTAS_PADRAO = [
    "bibliometric analysis entrepreneurship",
    "design science research",
    "patent grace period",
]
BASES_PADRAO = ["openalex", "crossref", "pubmed", "datacite"]
NOMES = {"openalex": "OpenAlex", "crossref": "Crossref", "pubmed": "PubMed", "datacite": "DataCite"}
LIMITE_PADRAO = 200
AMOSTRA_PADRAO = 20
#: Teto duro do NCBI por busca (ver core/sources/pubmed.py, PUBMED_MAX_FETCHABLE).
TETO_PUBMED = 9_999

OK, PEQUENA, ERRADO, NA = "ok", "diferença pequena", "errado", "n/a"

CAMPOS = ["titulo", "ano", "primeiro_autor", "n_autores", "revista", "doi", "citacoes",
          "resumo", "referencias", "acesso_aberto"]
ROTULOS = {
    "titulo": "Título", "ano": "Ano", "primeiro_autor": "Primeiro autor",
    "n_autores": "Nº de autores", "revista": "Revista/fonte", "doi": "DOI",
    "citacoes": "Citações", "resumo": "Resumo presente", "referencias": "Referências presentes",
    "acesso_aberto": "Acesso aberto",
}

#: Onde a consulta direta NÃO é idêntica à do Blicsa — e por que isso não muda o total.
DIFERENCAS_METODO = {
    "openalex": (
        "Mesmo `filter=` que o Blicsa monta (`default.search:<consulta>` + filtros de ano). "
        "Muda só a paginação: a consulta direta pede `per_page=1` sem `cursor`, o Blicsa pede "
        "`per_page=min(200, limite)&cursor=*`. O `meta.count` não depende disso."),
    "crossref": (
        "Mesmo `query.bibliographic` (o Blicsa remove AND/OR/NOT e parênteses antes de enviar; "
        "a consulta direta faz a mesma limpeza) e mesmos filtros de data. A consulta direta "
        "usa `rows=0` sem `cursor`; o Blicsa usa `rows=min(100, limite)&cursor=*`. O "
        "`total-results` não depende disso."),
    "pubmed": (
        "Mesmo `term` do ESearch. A consulta direta usa `retmax=0` sem `usehistory`; o Blicsa "
        "usa `usehistory=y` e baixa pelo EFetch. O `count` não depende disso. Para conferir os "
        "registros, a consulta direta usa o EFetch em **XML** (o Blicsa lê o formato MEDLINE "
        "em texto) — dois caminhos independentes até o mesmo dado."),
    "datacite": (
        "O Blicsa **não pesquisa** no DataCite (só o usa para conferir um DOI isolado). O total "
        "aparece aqui apenas como referência: é onde ficam dados de pesquisa, teses de "
        "repositórios e preprints com DOI DataCite."),
}


class FalhaDeRede(Exception):
    """A base não respondeu (rede, bloqueio, limite de uso ou erro do servidor)."""

    def __init__(self, mensagem: str, tipo: str = "rede", codigo: Optional[int] = None):
        super().__init__(mensagem)
        self.tipo = tipo          # "rede" | "http" | "limite"
        self.codigo = codigo


class NaoEncontrado(Exception):
    """A API respondeu 404: o registro não existe com aquele identificador."""


def sem_segredo(url: str) -> str:
    """URL sem `api_key=` — o relatório pode ser compartilhado com o orientador."""
    return re.sub(r"(api_key=)[^&]+", r"\1***", str(url or ""))


# ── Cliente HTTP direto (independente do Blicsa) ──────────────────────────────────────

def _abrir_urllib(url: str, headers: Dict[str, str], timeout: float) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


class HttpCliente:
    """GET com timeout, novas tentativas com espera crescente e intervalo mínimo por host.

    `abrir(url, headers, timeout) -> str` é injetável: os testes passam uma "internet falsa".
    """

    #: Intervalo mínimo entre pedidos ao mesmo host (o NCBI exige no máximo 3/s sem chave).
    INTERVALOS = {"eutils.ncbi.nlm.nih.gov": 0.35, "api.crossref.org": 0.05,
                  "api.openalex.org": 0.05, "api.datacite.org": 0.1}

    def __init__(self, email: str, timeout: float = 20.0, tentativas: int = 3,
                 espera_inicial: float = 0.5, abrir: Optional[Callable] = None,
                 dormir: Callable[[float], None] = time.sleep):
        self.email = email
        self.timeout = timeout
        self.tentativas = max(1, int(tentativas))
        self.espera_inicial = espera_inicial
        self.abrir = abrir or _abrir_urllib
        self.dormir = dormir
        self._ultimo: Dict[str, float] = {}
        self.pedidos = 0

    def _respeitar_intervalo(self, url: str):
        host = urllib.parse.urlparse(url).netloc
        minimo = self.INTERVALOS.get(host, 0.0)
        if minimo <= 0:
            return
        decorrido = time.monotonic() - self._ultimo.get(host, 0.0)
        if decorrido < minimo:
            self.dormir(minimo - decorrido)
        self._ultimo[host] = time.monotonic()

    def get_texto(self, url: str) -> str:
        headers = {"User-Agent": f"BlicsaAuditoria/1.0 (mailto:{self.email})",
                   "Accept": "application/json, text/xml;q=0.9, */*;q=0.5"}
        espera = self.espera_inicial
        ultimo_erro: Optional[FalhaDeRede] = None
        for tentativa in range(self.tentativas):
            self._respeitar_intervalo(url)
            self.pedidos += 1
            try:
                return self.abrir(url, headers, self.timeout)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NaoEncontrado(sem_segredo(url)) from e
                if e.code in (429, 500, 502, 503, 504):
                    tipo = "limite" if e.code == 429 else "http"
                    ultimo_erro = FalhaDeRede(f"HTTP {e.code} em {sem_segredo(url)}", tipo, e.code)
                    pausa = espera
                    try:
                        ra = e.headers.get("Retry-After") if e.headers else None
                        if ra:
                            pausa = min(30.0, max(pausa, float(ra)))
                    except Exception:
                        pass
                else:
                    # 400/401/403 não melhoram com insistência.
                    raise FalhaDeRede(f"HTTP {e.code} em {sem_segredo(url)}", "http", e.code) from e
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
                    OSError) as e:
                motivo = getattr(e, "reason", e)
                ultimo_erro = FalhaDeRede(f"sem conexão ({motivo})", "rede")
                pausa = espera
            if tentativa < self.tentativas - 1:
                self.dormir(pausa)
                espera *= 2
        raise ultimo_erro or FalhaDeRede("falha desconhecida", "rede")

    def get_json(self, url: str) -> Any:
        texto = self.get_texto(url)
        try:
            return json.loads(texto)
        except ValueError as e:
            raise FalhaDeRede(f"resposta não é JSON em {sem_segredo(url)}", "http") from e


# ── URLs da consulta direta (reproduzem os providers; ver DIFERENCAS_METODO) ──────────

def _limpar_booleanos_crossref(consulta: str) -> str:
    """O que o CrossrefProvider faz antes de enviar (crossref.py, `search`)."""
    q = re.sub(r"\b(AND|OR|NOT)\b", " ", consulta, flags=re.IGNORECASE)
    q = re.sub(r"[\(\)]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _com_chave(url: str, chave: str) -> str:
    if chave:
        url += ("&" if "?" in url else "?") + "api_key=" + urllib.parse.quote(chave)
    return url


def url_total_openalex(consulta: str, filtros: Optional[dict], email: str, chave: str = "") -> str:
    f = filtros or {}
    partes = []
    if f.get("year_start") and f.get("year_end"):
        partes.append(f"publication_year:{f['year_start']}-{f['year_end']}")
    elif f.get("year_start"):
        partes.append(f"publication_year:>{int(f['year_start']) - 1}")
    elif f.get("year_end"):
        partes.append(f"publication_year:<{int(f['year_end']) + 1}")
    if consulta.strip():
        partes.append(f"default.search:{consulta.strip()}")
    params = {"per_page": 1, "mailto": email}
    if partes:
        params["filter"] = ",".join(partes)
    return _com_chave("https://api.openalex.org/works?" + urllib.parse.urlencode(params), chave)


def url_total_crossref(consulta: str, filtros: Optional[dict], email: str) -> str:
    f = filtros or {}
    params: Dict[str, Any] = {"rows": 0}
    if consulta.strip():
        params["query.bibliographic"] = _limpar_booleanos_crossref(consulta)
    partes = []
    if f.get("year_start"):
        partes.append(f"from-pub-date:{f['year_start']}-01-01")
    if f.get("year_end"):
        partes.append(f"until-pub-date:{f['year_end']}-12-31")
    if partes:
        params["filter"] = ",".join(partes)
    params["mailto"] = email
    return "https://api.crossref.org/works?" + urllib.parse.urlencode(params)


def termo_pubmed(consulta: str, filtros: Optional[dict]) -> str:
    f = filtros or {}
    partes = [consulta.strip()] if consulta.strip() else []
    if f.get("year_start") and f.get("year_end"):
        partes.append(f"({f['year_start']}:{f['year_end']}[DP])")
    elif f.get("year_start"):
        partes.append(f"({f['year_start']}:3000[DP])")
    elif f.get("year_end"):
        partes.append(f"(1800:{f['year_end']}[DP])")
    return " AND ".join(partes) if partes else "all[Filter]"


def url_total_pubmed(consulta: str, filtros: Optional[dict], email: str, chave: str = "") -> str:
    params = {"db": "pubmed", "term": termo_pubmed(consulta, filtros), "retmode": "json",
              "retmax": 0, "tool": "blicsa_auditoria", "email": email}
    return _com_chave("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
                      + urllib.parse.urlencode(params), chave)


def url_total_datacite(consulta: str, filtros: Optional[dict]) -> str:
    f = filtros or {}
    q = consulta.strip()
    if f.get("year_start") or f.get("year_end"):
        a, b = f.get("year_start") or "*", f.get("year_end") or "*"
        q = f"({q}) AND publicationYear:[{a} TO {b}]"
    return "https://api.datacite.org/dois?" + urllib.parse.urlencode(
        {"query": q, "page[size]": 1})


def total_direto(base: str, consulta: str, filtros: Optional[dict], cliente: HttpCliente,
                 chaves: Dict[str, str]) -> Tuple[int, str]:
    """(total declarado pela base, URL usada). Levanta FalhaDeRede se a base não responder."""
    if base == "openalex":
        url = url_total_openalex(consulta, filtros, cliente.email, chaves.get("openalex", ""))
        return int(cliente.get_json(url).get("meta", {}).get("count", 0)), url
    if base == "crossref":
        url = url_total_crossref(consulta, filtros, cliente.email)
        return int(cliente.get_json(url).get("message", {}).get("total-results", 0)), url
    if base == "pubmed":
        url = url_total_pubmed(consulta, filtros, cliente.email, chaves.get("pubmed", ""))
        dados = cliente.get_json(url).get("esearchresult", {})
        if "ERROR" in dados:
            raise FalhaDeRede(f"PubMed recusou a consulta: {dados['ERROR']}", "http")
        return int(dados.get("count", 0)), url
    if base == "datacite":
        url = url_total_datacite(consulta, filtros)
        return int(cliente.get_json(url).get("meta", {}).get("total", 0)), url
    raise ValueError(f"base desconhecida: {base}")


# ── "Verdade" de cada base, lida direto da resposta crua ──────────────────────────────

def _nome_crossref(a: dict) -> str:
    nome = f"{a.get('family') or ''} {a.get('given') or ''}".strip()
    return nome or str(a.get("name") or "").strip()


def verdade_openalex(w: dict) -> dict:
    nomes = []
    for a in w.get("authorships") or []:
        n = ((a or {}).get("author") or {}).get("display_name") or (a or {}).get("raw_author_name")
        if n:
            nomes.append(str(n))
    fonte = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    refs = w.get("referenced_works") or []
    return {
        "titulo": w.get("title") or w.get("display_name") or "",
        "ano": int(w.get("publication_year") or 0),
        "primeiro_autor": nomes[0] if nomes else "",
        "n_autores": len(nomes),
        "revista": fonte,
        "doi": w.get("doi") or "",
        "citacoes": int(w.get("cited_by_count") or 0),
        "resumo": bool(w.get("abstract_inverted_index")),
        "referencias": bool(refs) or int(w.get("referenced_works_count") or 0) > 0,
        "acesso_aberto": bool((w.get("open_access") or {}).get("is_oa")),
        "_id": str(w.get("id") or ""),
        "_refs_total": int(w.get("referenced_works_count") or len(refs)),
    }


def verdade_crossref(m: dict) -> dict:
    nomes = [n for n in (_nome_crossref(a) for a in (m.get("author") or [])) if n]
    partes = ((m.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    refs = m.get("reference") or []
    licencas = [str((l or {}).get("URL") or "").lower() for l in (m.get("license") or [])]
    titulos = m.get("title") or [""]
    revistas = m.get("container-title") or [""]
    return {
        "titulo": titulos[0] if titulos else "",
        "ano": int(partes[0] or 0),
        "primeiro_autor": nomes[0] if nomes else "",
        "n_autores": len(nomes),
        "revista": revistas[0] if revistas else "",
        "doi": m.get("DOI") or "",
        "citacoes": int(m.get("is-referenced-by-count") or 0),
        "resumo": bool(str(m.get("abstract") or "").strip()),
        "referencias": bool(refs) or int(m.get("reference-count") or 0) > 0,
        # O Crossref não tem campo de acesso aberto: o critério é licença Creative Commons,
        # o mesmo do Blicsa. Aqui é reimplementado de forma independente.
        "acesso_aberto": any("creativecommons" in u or "creative-commons" in u for u in licencas),
        "_refs_total": max(len(refs), int(m.get("reference-count") or 0)),
        "_refs_com_doi": sum(1 for r in refs if (r or {}).get("DOI")),
    }


def parse_pubmed_xml(texto: str) -> List[dict]:
    """EFetch `retmode=xml` → lista de "verdades" (uma por PubmedArticle)."""
    saida = []
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        return saida
    for art in raiz.iter("PubmedArticle"):
        mc = art.find("MedlineCitation")
        a = mc.find("Article") if mc is not None else None
        if a is None:
            continue
        titulo_el = a.find("ArticleTitle")
        titulo = "".join(titulo_el.itertext()).strip() if titulo_el is not None else ""
        ano = 0
        for caminho in ("Journal/JournalIssue/PubDate/Year", "ArticleDate/Year"):
            v = a.findtext(caminho)
            if v and v.strip().isdigit():
                ano = int(v.strip())
                break
        if not ano:
            md = a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or ""
            m = re.search(r"\b(19|20)\d{2}\b", md)
            ano = int(m.group()) if m else 0
        nomes = []
        for au in a.findall("AuthorList/Author"):
            sobrenome = au.findtext("LastName")
            if sobrenome:
                nomes.append(f"{sobrenome} {au.findtext('Initials') or ''}".strip())
            elif au.findtext("CollectiveName"):
                nomes.append(au.findtext("CollectiveName").strip())
        doi = ""
        pmc = False
        for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
            tipo = aid.get("IdType")
            if tipo == "doi" and not doi:
                doi = (aid.text or "").strip()
            if tipo == "pmc" and (aid.text or "").strip():
                pmc = True
        if not doi:
            for el in a.findall("ELocationID"):
                if el.get("EIdType") == "doi":
                    doi = (el.text or "").strip()
                    break
        resumo = any("".join(x.itertext()).strip() for x in a.findall("Abstract/AbstractText"))
        refs = art.findall("PubmedData/ReferenceList/Reference")
        saida.append({
            "titulo": titulo, "ano": ano,
            "primeiro_autor": nomes[0] if nomes else "", "n_autores": len(nomes),
            "revista": a.findtext("Journal/Title") or "",
            "doi": doi,
            "citacoes": None,                 # o PubMed não informa citações
            "resumo": resumo,
            "referencias": bool(refs),
            # Aproximação: ter cópia no PubMed Central = texto completo gratuito.
            "acesso_aberto": pmc,
            "_pmid": (mc.findtext("PMID") or "").strip(),
            "_refs_total": len(refs),
        })
    return saida


def campos_blicsa(rec: dict) -> dict:
    """O que o Blicsa guardou, nos mesmos nomes de campo da "verdade"."""
    autores = [a.strip() for a in str(rec.get("authors") or "").split(";") if a.strip()]
    refs = [r for r in str(rec.get("references") or "").split(";") if r.strip()]
    return {
        "titulo": str(rec.get("title") or ""),
        "ano": int(rec.get("year") or 0),
        "primeiro_autor": autores[0] if autores else "",
        "n_autores": len(autores),
        "revista": str(rec.get("source") or ""),
        "doi": str(rec.get("doi") or ""),
        "citacoes": int(rec.get("citations") or 0),
        "resumo": bool(str(rec.get("abstract") or "").strip()),
        "referencias": bool(refs),
        "acesso_aberto": bool(rec.get("is_oa")),
        "_refs_total": len(refs),
    }


# ── Comparação e classificação ────────────────────────────────────────────────────────

def norm_texto(s: Any) -> str:
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_doi(d: Any) -> str:
    d = str(d or "").strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
              "http://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d.strip().rstrip("/")


def _razao(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def classificar(campo: str, blicsa: Any, api: Any) -> Tuple[str, str]:
    """(status, explicação curta) para um campo. `api is None` = a base não informa."""
    if api is None:
        return NA, "a base não informa este campo"
    if campo == "titulo":
        a, b = norm_texto(blicsa), norm_texto(api)
        if a == b:
            return OK, ""
        r = _razao(a, b)
        if r >= 0.9:
            return PEQUENA, f"títulos {r:.0%} parecidos (pontuação/acentos/formatação)"
        return ERRADO, f"títulos só {r:.0%} parecidos"
    if campo == "ano":
        a, b = int(blicsa or 0), int(api or 0)
        if a == b:
            return OK, ""
        if a and b and abs(a - b) == 1:
            return PEQUENA, "1 ano de diferença (data online × impressa)"
        return ERRADO, f"{a} × {b}"
    if campo == "primeiro_autor":
        a, b = norm_texto(blicsa), norm_texto(api)
        if a == b:
            return OK, ""
        if not a or not b:
            return ERRADO, "autor ausente de um dos lados"
        ta, tb = set(a.split()), set(b.split())
        sobrenome_b = b.split()[0] if b.split() else ""
        if ta <= tb or tb <= ta or (sobrenome_b and sobrenome_b in ta and len(sobrenome_b) > 2):
            return OK, "mesmo autor, grafia diferente"
        if _razao(a, b) >= 0.85:
            return PEQUENA, "nomes muito parecidos"
        return ERRADO, f"'{blicsa}' × '{api}'"
    if campo == "n_autores":
        a, b = int(blicsa or 0), int(api or 0)
        if a == b:
            return OK, ""
        if abs(a - b) <= 1 or (b and abs(a - b) / b <= 0.10):
            return PEQUENA, f"{a} × {b}"
        return ERRADO, f"{a} × {b}"
    if campo == "revista":
        a, b = norm_texto(blicsa), norm_texto(api)
        if a == b:
            return OK, ""
        if not a and not b:
            return OK, ""
        if a and b and (a in b or b in a or _razao(a, b) >= 0.8):
            return PEQUENA, "nome da revista com grafia diferente"
        return ERRADO, f"'{blicsa}' × '{api}'"
    if campo == "doi":
        a, b = norm_doi(blicsa), norm_doi(api)
        if a == b:
            return OK, ""
        return ERRADO, f"'{blicsa}' × '{api}'"
    if campo == "citacoes":
        a, b = int(blicsa or 0), int(api or 0)
        if a == b:
            return OK, ""
        if abs(a - b) <= max(3, 0.05 * b):
            return PEQUENA, f"{a} × {b} (a base atualiza as contagens continuamente)"
        return ERRADO, f"{a} × {b}"
    # Campos sim/não.
    if bool(blicsa) == bool(api):
        return OK, ""
    sim = lambda v: "sim" if v else "não"
    return ERRADO, f"Blicsa: {sim(blicsa)} × base: {sim(api)}"


def comparar_registro(base: str, rec: dict, verdade: Optional[dict]) -> dict:
    b = campos_blicsa(rec)
    saida = {"titulo_blicsa": b["titulo"][:160], "doi_blicsa": b["doi"],
             "encontrado": verdade is not None, "campos": {}}
    if verdade is None:
        return saida
    for campo in CAMPOS:
        api = verdade.get(campo)
        if base == "pubmed" and campo == "citacoes":
            api = None
        status, detalhe = classificar(campo, b[campo], api)
        # Crossref: o Blicsa guarda só referências COM DOI (a rede de citações liga por DOI).
        if (base == "crossref" and campo == "referencias" and status == ERRADO
                and api and not b["referencias"] and verdade.get("_refs_com_doi", 0) == 0):
            status, detalhe = PEQUENA, (f"o Crossref lista {verdade.get('_refs_total', 0)} "
                                        "referência(s), nenhuma com DOI; o Blicsa guarda só "
                                        "as que têm DOI")
        saida["campos"][campo] = {"blicsa": b[campo] if not isinstance(b[campo], str)
                                  else b[campo][:160],
                                  "api": api if not isinstance(api, str) else api[:160],
                                  "status": status, "detalhe": detalhe}
    return saida


def resumir_amostra(comparacoes: List[dict]) -> dict:
    """Contagem por campo e % correto (ok) e % aceitável (ok + diferença pequena)."""
    por_campo = {}
    total_ok = total_aceit = total_aplic = 0
    for campo in CAMPOS:
        c = {OK: 0, PEQUENA: 0, ERRADO: 0, NA: 0}
        for comp in comparacoes:
            info = comp.get("campos", {}).get(campo)
            if info:
                c[info["status"]] += 1
        aplic = c[OK] + c[PEQUENA] + c[ERRADO]
        por_campo[campo] = dict(c, aplicaveis=aplic,
                                pct_ok=(100.0 * c[OK] / aplic) if aplic else None,
                                pct_aceitavel=(100.0 * (c[OK] + c[PEQUENA]) / aplic)
                                if aplic else None)
        total_ok += c[OK]
        total_aceit += c[OK] + c[PEQUENA]
        total_aplic += aplic
    return {
        "registros": len(comparacoes),
        "nao_encontrados": sum(1 for c in comparacoes if not c.get("encontrado")),
        "por_campo": por_campo,
        "pct_ok": (100.0 * total_ok / total_aplic) if total_aplic else None,
        "pct_aceitavel": (100.0 * total_aceit / total_aplic) if total_aplic else None,
    }


def comparar_totais(total_api: Optional[int], total_blicsa: Optional[int]) -> Tuple[str, str]:
    if total_api is None or total_blicsa is None:
        return NA, "sem um dos números"
    if total_api == total_blicsa:
        return OK, "iguais"
    dif = abs(total_api - total_blicsa)
    if dif <= 5 or (total_api and dif / total_api <= 0.005):
        return PEQUENA, f"diferença de {dif} (a base mudou entre as duas consultas)"
    return ERRADO, f"diferença de {dif}"


def checar_paginacao(base: str, total: int, baixados: int, limite: int,
                     stop_reason: str = "", stop_error: bool = False,
                     interrompido: bool = False) -> Tuple[str, str]:
    """O Blicsa baixou o que deveria? Quando total <= limite, tinha de ir até o fim."""
    esperado = min(int(limite), int(total or 0))
    if base == "pubmed":
        esperado = min(esperado, TETO_PUBMED)
    if interrompido:
        return ERRADO, "busca do Blicsa interrompida pelo tempo máximo da auditoria"
    if stop_error:
        return ERRADO, f"parou por erro: {stop_reason}"
    alcance = "foi até o fim dos resultados" if total <= limite else "parou no limite pedido"
    if baixados == esperado:
        return OK, f"{alcance} ({baixados} de {esperado} esperados)"
    if baixados < esperado:
        falta = esperado - baixados
        if falta <= max(2, 0.01 * esperado):
            return PEQUENA, f"faltaram {falta} de {esperado} ({stop_reason})"
        return ERRADO, f"faltaram {falta} de {esperado} ({stop_reason})"
    return ERRADO, f"baixou {baixados}, mais que os {esperado} esperados"


def escolher_amostra(registros: List[dict], n: int) -> List[int]:
    """Índices espaçados do começo ao fim (cobre a 1ª página e as últimas)."""
    total = len(registros)
    if total <= n:
        return list(range(total))
    if n <= 1:
        return [0]
    passo = (total - 1) / (n - 1)
    return sorted({round(i * passo) for i in range(n)})


def duplicatas_dentro(registros: List[dict]) -> int:
    """DOIs repetidos dentro de UMA busca (paginação que repete página, por exemplo)."""
    vistos, rep = set(), 0
    for r in registros:
        d = norm_doi(r.get("doi"))
        if not d:
            continue
        if d in vistos:
            rep += 1
        vistos.add(d)
    return rep


def apos_dedup(registros: List[dict]) -> Tuple[int, dict]:
    """Quantos sobram depois do botão "Deduplicar" do Corpus (core.parsers.find_duplicates)."""
    if not registros:
        return 0, {}
    import pandas as pd
    from core.parsers import find_duplicates
    df = pd.DataFrame(registros)
    for col in ("origin", "doi", "year", "title", "authors"):
        if col not in df.columns:
            df[col] = ""
    pares = find_duplicates(df, title_threshold=0.93)
    removidos = {ri for _, ri, _ in pares}
    motivos: Dict[str, int] = {}
    for _, _, motivo in pares:
        chave = ("doi" if motivo.startswith("DOI") else
                 "autor_ano" if motivo.startswith("Autor+Ano") else "titulo")
        motivos[chave] = motivos.get(chave, 0) + 1
    return len(df) - len(removidos), motivos


def duplicatas_entre_bases(regs_por_base: Dict[str, List[dict]]) -> dict:
    """Mesmo DOI em mais de uma base: existe? A deduplicação do Blicsa trata?"""
    import pandas as pd
    from core.parsers import find_duplicates

    todos, base_de = [], []
    for base, regs in regs_por_base.items():
        for r in regs:
            todos.append(r)
            base_de.append(base)
    saida = {"bases": sorted(regs_por_base), "total_combinado": len(todos),
             "dois_em_mais_de_uma_base": 0, "por_par": {}, "tratados": 0,
             "nao_tratados": [], "pares_entre_bases_por_motivo": {}, "apos_dedup": len(todos)}
    if not todos:
        return saida
    onde: Dict[str, set] = {}
    for i, r in enumerate(todos):
        d = norm_doi(r.get("doi"))
        if d:
            onde.setdefault(d, set()).add(base_de[i])
    compartilhados = {d: b for d, b in onde.items() if len(b) > 1}
    saida["dois_em_mais_de_uma_base"] = len(compartilhados)
    for bases in compartilhados.values():
        chave = " + ".join(NOMES.get(b, b) for b in sorted(bases))
        saida["por_par"][chave] = saida["por_par"].get(chave, 0) + 1

    df = pd.DataFrame(todos)
    for col in ("origin", "doi", "year", "title", "authors"):
        if col not in df.columns:
            df[col] = ""
    pares = find_duplicates(df, title_threshold=0.93)
    removidos = {ri for _, ri, _ in pares}
    saida["apos_dedup"] = len(df) - len(removidos)
    for k, ri, motivo in pares:
        if base_de[k] != base_de[ri]:
            chave = ("doi" if motivo.startswith("DOI") else
                     "autor_ano" if motivo.startswith("Autor+Ano") else "titulo")
            saida["pares_entre_bases_por_motivo"][chave] = \
                saida["pares_entre_bases_por_motivo"].get(chave, 0) + 1
    for d in compartilhados:
        idx = [i for i, r in enumerate(todos) if norm_doi(r.get("doi")) == d]
        restantes = [i for i in idx if i not in removidos]
        if len(restantes) == 1:
            saida["tratados"] += 1
        elif len(saida["nao_tratados"]) < 10:
            saida["nao_tratados"].append({"doi": d, "copias_restantes": len(restantes)})
    return saida


# ── Busca da "verdade" para a amostra ─────────────────────────────────────────────────

def verdades_openalex(regs: List[dict], cliente: HttpCliente, chave: str = "") -> List[Optional[dict]]:
    saida = []
    for r in regs:
        m = re.search(r"(W\d+)", str(r.get("openalex_id") or ""))
        if m:
            url = f"https://api.openalex.org/works/{m.group(1)}?mailto={urllib.parse.quote(cliente.email)}"
        elif norm_doi(r.get("doi")):
            url = (f"https://api.openalex.org/works/https://doi.org/{norm_doi(r.get('doi'))}"
                   f"?mailto={urllib.parse.quote(cliente.email)}")
        else:
            saida.append(None)
            continue
        try:
            saida.append(verdade_openalex(cliente.get_json(_com_chave(url, chave))))
        except NaoEncontrado:
            saida.append(None)
    return saida


def verdades_crossref(regs: List[dict], cliente: HttpCliente) -> List[Optional[dict]]:
    saida = []
    for r in regs:
        d = norm_doi(r.get("doi"))
        if not d:
            saida.append(None)
            continue
        url = ("https://api.crossref.org/works/" + urllib.parse.quote(d, safe="")
               + "?mailto=" + urllib.parse.quote(cliente.email))
        try:
            msg = cliente.get_json(url).get("message")
            saida.append(verdade_crossref(msg) if isinstance(msg, dict) else None)
        except NaoEncontrado:
            saida.append(None)
    return saida


def verdades_pubmed(regs: List[dict], cliente: HttpCliente, chave: str = "") -> List[Optional[dict]]:
    """DOI → PMID (uma ESearch com OR), sem DOI → título; depois um EFetch em XML."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    comum = {"tool": "blicsa_auditoria", "email": cliente.email}
    pmids: List[str] = []
    dois = [norm_doi(r.get("doi")) for r in regs]
    com_doi = [d for d in dois if d]
    if com_doi:
        termo = " OR ".join(f'"{d}"[doi]' for d in com_doi)
        url = base + "esearch.fcgi?" + urllib.parse.urlencode(
            dict(comum, db="pubmed", term=termo, retmode="json", retmax=len(com_doi) * 3))
        pmids += cliente.get_json(_com_chave(url, chave)).get("esearchresult", {}).get("idlist", [])
    for r, d in zip(regs, dois):
        if d or not str(r.get("title") or "").strip():
            continue
        titulo = re.sub(r"[\[\]\"]", " ", str(r["title"]))[:250]
        url = base + "esearch.fcgi?" + urllib.parse.urlencode(
            dict(comum, db="pubmed", term=f'"{titulo}"[ti]', retmode="json", retmax=3))
        pmids += cliente.get_json(_com_chave(url, chave)).get("esearchresult", {}).get("idlist", [])
    pmids = list(dict.fromkeys(str(p) for p in pmids))
    artigos: List[dict] = []
    for i in range(0, len(pmids), 100):
        url = base + "efetch.fcgi?" + urllib.parse.urlencode(
            dict(comum, db="pubmed", id=",".join(pmids[i:i + 100]), retmode="xml"))
        artigos += parse_pubmed_xml(cliente.get_texto(_com_chave(url, chave)))
    por_doi = {norm_doi(a["doi"]): a for a in artigos if a["doi"]}
    saida = []
    for r, d in zip(regs, dois):
        if d:
            saida.append(por_doi.get(d))
            continue
        alvo = norm_texto(r.get("title"))
        melhor = max(artigos, key=lambda a: _razao(norm_texto(a["titulo"]), alvo), default=None)
        if melhor and _razao(norm_texto(melhor["titulo"]), alvo) >= 0.9:
            saida.append(melhor)
        else:
            saida.append(None)
    return saida


def buscar_verdades(base: str, regs: List[dict], cliente: HttpCliente,
                    chaves: Dict[str, str]) -> List[Optional[dict]]:
    if base == "openalex":
        return verdades_openalex(regs, cliente, chaves.get("openalex", ""))
    if base == "crossref":
        return verdades_crossref(regs, cliente)
    if base == "pubmed":
        return verdades_pubmed(regs, cliente, chaves.get("pubmed", ""))
    return [None] * len(regs)


# ── A busca pelo código real do Blicsa ────────────────────────────────────────────────

def _trilha(total_encontrado: int, baixados: int, limite: int, motivo: str) -> str:
    """A mesma frase que `main.py::_search_worker` mostra (sem importar a UI)."""
    from core.i18n import t
    motivo = motivo or "concluída"
    motivo_ui = motivo if len(motivo) <= 90 else motivo[:87].rstrip() + "…"
    if total_encontrado > baixados and limite < 10_000_000:
        return t("search.trail_limited", found=total_encontrado, downloaded=baixados,
                 limit=limite, reason=motivo_ui)
    return t("search.trail", found=max(total_encontrado, baixados), downloaded=baixados,
             reason=motivo_ui)


def rodar_blicsa(base: str, consulta: str, limite: int, filtros: Optional[dict], email: str,
                 tempo_max: float = 600.0) -> dict:
    """Roda `provider.search(...)` exatamente como `main.py::_search_worker` o chama."""
    from core.sources import CrossrefProvider, OpenAlexProvider, PubMedProvider
    classe = {"openalex": OpenAlexProvider, "crossref": CrossrefProvider,
              "pubmed": PubMedProvider}[base]
    prov = classe(mailto=email)
    cancel = threading.Event()
    relogio = threading.Timer(tempo_max, cancel.set)
    relogio.daemon = True
    registros: List[dict] = []
    total_encontrado = 0
    interrompido = False

    def progresso(atual, total):
        nonlocal total_encontrado
        real = max(int(getattr(prov, "total_available", 0) or 0), total)
        total_encontrado = max(total_encontrado, real)

    t0 = time.perf_counter()
    relogio.start()
    try:
        for r in prov.search(query=consulta, filters=dict(filtros or {}), max_results=limite,
                             progress_cb=progresso, cancel_event=cancel):
            registros.append(r)
    except InterruptedError:
        interrompido = True
    finally:
        relogio.cancel()
    tempo = time.perf_counter() - t0
    total_encontrado = max(total_encontrado, int(getattr(prov, "total_available", 0) or 0))
    motivo = str(getattr(prov, "stop_reason", "") or "")
    return {
        "registros": registros,
        "total_declarado": int(getattr(prov, "total_available", 0) or 0),
        "encontrados_exibido": max(total_encontrado, len(registros)),
        "baixados": len(registros),
        "tempo_s": round(tempo, 2),
        "stop_reason": motivo,
        "stop_error": bool(getattr(prov, "stop_error", False)),
        "interrompido": interrompido,
        "paginas": int(getattr(prov, "pages_fetched", 0) or 0),
        "filtrados_idioma": int(getattr(prov, "language_filtered_count", 0) or 0),
        "trilha": _trilha(total_encontrado, len(registros), limite, motivo),
    }


# ── Orquestração ─────────────────────────────────────────────────────────────────────

def _agora() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def auditar(consultas: List[str], bases: List[str], limite: int, amostra: int,
            cliente: HttpCliente, chaves: Optional[Dict[str, str]] = None,
            filtros: Optional[dict] = None, tempo_max_base: float = 600.0,
            executor: Callable[..., dict] = rodar_blicsa,
            log: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> dict:
    """Roda a auditoria inteira. Nunca levanta por base caída; Ctrl+C devolve o parcial."""
    chaves = chaves or {}
    filtros_app = dict(filtros or {})
    filtros_app.setdefault("sort", "relevance")      # o que a tela de busca envia por padrão
    res: Dict[str, Any] = {
        "versao": 1, "inicio": _agora(), "fim": None, "consultas": list(consultas),
        "bases": list(bases), "limite": int(limite), "amostra": int(amostra),
        "filtros": filtros_app, "email": cliente.email, "interrompido": False,
        "onde_parou": "", "execucoes": [], "duplicatas": [], "bases_caidas": {},
        "metodo": {b: DIFERENCAS_METODO.get(b, "") for b in bases},
    }
    em_curso = ""
    # Sonda: o total da 1ª consulta em todas as bases AO MESMO TEMPO. Serve de checagem de
    # disponibilidade — sem rede, as bases caem juntas em segundos, não uma depois da outra.
    sonda: Dict[str, Any] = {}
    if consultas:
        def _sondar(b):
            try:
                sonda[b] = total_direto(b, consultas[0], filtros_app, cliente, chaves)
            except Exception as e:      # FalhaDeRede ou erro inesperado: registrado no laço
                sonda[b] = e
        fios = [threading.Thread(target=_sondar, args=(b,), daemon=True) for b in bases]
        t_sonda = time.perf_counter()
        for f in fios:
            f.start()
        try:
            for f in fios:
                f.join()
        except KeyboardInterrupt:
            res["interrompido"] = True
            res["onde_parou"] = "verificação inicial das bases"
            res["fim"] = _agora()
            res["pedidos_diretos"] = cliente.pedidos
            return res
        tempo_sonda = round(time.perf_counter() - t_sonda, 2)
    try:
        for consulta in consultas:
            regs_por_base: Dict[str, List[dict]] = {}
            for base in bases:
                em_curso = f"{NOMES.get(base, base)} · \"{consulta}\""
                ex: Dict[str, Any] = {"base": base, "consulta": consulta, "status": "ok"}
                res["execucoes"].append(ex)
                if base in res["bases_caidas"]:
                    ex.update(status="indisponível", motivo=res["bases_caidas"][base])
                    continue
                log(f"[{NOMES.get(base, base)}] \"{consulta}\": total direto na API…")
                t0 = time.perf_counter()
                try:
                    if consulta == consultas[0] and base in sonda:
                        pre = sonda.pop(base)
                        if isinstance(pre, BaseException):
                            raise pre
                        total_api, url = pre
                        t0 -= tempo_sonda
                    else:
                        total_api, url = total_direto(base, consulta, filtros_app, cliente, chaves)
                except FalhaDeRede as e:
                    ex.update(status="indisponível", motivo=str(e))
                    if e.tipo in ("rede", "limite") or (e.codigo or 0) >= 500 or e.codigo == 403:
                        res["bases_caidas"][base] = str(e)
                    log(f"  indisponível: {e}")
                    continue
                except NaoEncontrado as e:
                    ex.update(status="indisponível", motivo=f"HTTP 404 em {e}")
                    continue
                except Exception as e:      # resposta inesperada: registrar e seguir
                    ex.update(status="indisponível",
                              motivo=f"resposta inesperada ({type(e).__name__}: {e})")
                    log(f"  resposta inesperada: {e}")
                    continue
                ex.update(total_api=total_api, url_api=sem_segredo(url),
                          tempo_api_s=round(time.perf_counter() - t0, 2))
                if base == "datacite":
                    ex["observacao"] = DIFERENCAS_METODO["datacite"]
                    continue

                log(f"  total na API: {total_api}. Rodando a busca do Blicsa (limite {limite})…")
                try:
                    rb = executor(base, consulta, limite, filtros_app, cliente.email,
                                  tempo_max_base)
                except KeyboardInterrupt:
                    raise
                except Exception as e:  # o código do Blicsa falhou: registrar, não parar
                    ex.update(status="erro no Blicsa", motivo=f"{type(e).__name__}: {e}")
                    log(f"  erro no Blicsa: {e}")
                    continue
                registros = rb.pop("registros")
                ex["blicsa"] = rb
                k, motivos = apos_dedup(registros)
                ex["blicsa"]["apos_dedup"] = k
                ex["blicsa"]["dedup_motivos"] = motivos
                ex["blicsa"]["dois_repetidos_na_busca"] = duplicatas_dentro(registros)
                ex["blicsa"]["sem_doi"] = sum(1 for r in registros if not norm_doi(r.get("doi")))
                ex["comparacao_total"] = dict(zip(
                    ("status", "detalhe"), comparar_totais(total_api, rb["total_declarado"])))
                ex["paginacao"] = dict(zip(("status", "detalhe"), checar_paginacao(
                    base, rb["total_declarado"] or total_api, rb["baixados"], limite,
                    rb["stop_reason"], rb["stop_error"], rb["interrompido"])))
                if rb["stop_error"] and rb["baixados"] == 0:
                    ex["status"] = "indisponível"
                    ex["motivo"] = rb["stop_reason"]
                regs_por_base[base] = registros
                log(f"  Blicsa: {rb['trilha']} · após deduplicação {k} · {rb['tempo_s']}s")

                idx = escolher_amostra(registros, amostra)
                regs_amostra = [registros[i] for i in idx]
                if regs_amostra:
                    log(f"  conferindo {len(regs_amostra)} registros direto na API…")
                    try:
                        verdades = buscar_verdades(base, regs_amostra, cliente, chaves)
                        comps = [comparar_registro(base, r, v)
                                 for r, v in zip(regs_amostra, verdades)]
                        for i, c in zip(idx, comps):
                            c["posicao"] = i + 1
                        ex["amostra"] = {"comparacoes": comps, "resumo": resumir_amostra(comps)}
                    except FalhaDeRede as e:
                        ex["amostra"] = {"indisponivel": str(e)}
                        log(f"  amostra indisponível: {e}")
            if len([b for b in regs_por_base if regs_por_base[b]]) >= 2:
                em_curso = f"duplicatas entre bases · \"{consulta}\""
                res["duplicatas"].append(dict(consulta=consulta,
                                              **duplicatas_entre_bases(regs_por_base)))
        em_curso = ""
    except KeyboardInterrupt:
        res["interrompido"] = True
        res["onde_parou"] = em_curso
        if res["execucoes"] and "blicsa" not in res["execucoes"][-1] \
                and res["execucoes"][-1].get("status") == "ok" \
                and res["execucoes"][-1].get("base") != "datacite":
            res["execucoes"][-1].update(status="interrompido", motivo="Ctrl+C")
        log("\nInterrompido (Ctrl+C): salvando o que já foi auditado…")
    res["fim"] = _agora()
    res["pedidos_diretos"] = cliente.pedidos
    return res


# ── Relatório ────────────────────────────────────────────────────────────────────────

def _fmt(n: Any) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:.1f}".replace(".", ",")
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.0f}%"


def _icone(status: str) -> str:
    return {OK: "ok", PEQUENA: "diferença pequena", ERRADO: "**ERRADO**", NA: "n/a"}.get(
        status, status)


def _linha_de(arquivo: str, trecho: str) -> str:
    """`arquivo:linha` do trecho no código atual (linhas mudam; o trecho não)."""
    try:
        for n, linha in enumerate((RAIZ / arquivo).read_text(encoding="utf-8").splitlines(), 1):
            if trecho in linha:
                return f"{arquivo}:{n}"
    except OSError:
        pass
    return arquivo


def suspeitas_do_codigo() -> List[dict]:
    """O que a leitura do código de busca encontrou (estado: corrigido / aberto)."""
    return [
        {"estado": "corrigido", "onde": _linha_de("core/sources/pubmed.py", 'for tag in ("LID", "AID")'),
         "texto": "PubMed: quando o campo LID trazia só o identificador do editor (`[pii]`), "
                  "esse texto ia parar no campo DOI (ex.: `S0140-6736(20)30183-5 [pii]`), e um "
                  "DOI que só existia no AID era ignorado. Afetava links, exportação e a "
                  "deduplicação por DOI entre bases."},
        {"estado": "corrigido", "onde": _linha_de("core/sources/pubmed.py", "def _term("),
         "texto": "PubMed: a contagem (`count`) e a navegação (`browse`) montavam um termo "
                  "diferente da importação (`search`): ignoravam ano só-inicial/só-final e o "
                  "filtro de acesso aberto. Na navegação, esses filtros não tinham efeito e o "
                  "total mostrado não era o da importação."},
        {"estado": "corrigido", "onde": _linha_de("core/sources/crossref.py", "def _nome_autor("),
         "texto": "Crossref: autor institucional (só `name`, sem sobrenome/nome) virava texto "
                  "vazio — sumia da lista, o primeiro autor podia ficar em branco e a contagem "
                  "de autores ficava errada."},
        {"estado": "aberto", "onde": _linha_de("core/sources/crossref.py", 'filters.get("is_oa") is not None'),
         "texto": "Crossref + filtro 'acesso aberto': o filtro é aplicado no computador, depois "
                  "do download, mas o 'Encontrados' continua sendo o total SEM o filtro "
                  "(`total-results` da API) e a trilha não diz quantos foram descartados (para "
                  "idioma ela diz). O número exibido superestima o conjunto filtrado."},
        {"estado": "aberto", "onde": _linha_de("core/sources/crossref.py", '"published"'),
         "texto": "Crossref, ordenar por 'Mais recentes': a importação ordena por `published` "
                  "e a navegação por `issued` (crossref.py, `browse`). A lista navegada e a "
                  "importada podem vir em ordens diferentes."},
        {"estado": "aberto", "onde": _linha_de("core/sources/crossref.py", 'r.get("DOI", "") for r in w.get("reference"'),
         "texto": "Crossref: das referências, só as que têm DOI são guardadas. Referências "
                  "antigas, livros e literatura cinzenta (sem DOI) somem da rede de citações/"
                  "acoplamento. É escolha de projeto, mas não aparece para o usuário."},
        {"estado": "aberto", "onde": _linha_de("core/sources/openalex.py", "def count("),
         "texto": "OpenAlex: `count()` não interpreta a sintaxe legada TITLE()/AUTHOR()/YEAR() "
                  "que `search()` converte em busca por campo; para consultas nessa sintaxe, o "
                  "número do aviso de volume não é o da importação."},
        {"estado": "aberto", "onde": _linha_de("main.py", "except TypeError:"),
         "texto": "main.py, `_search_worker`: o `except TypeError` foi pensado para provider "
                  "sem parâmetro `filters`, mas pega QUALQUER TypeError levantado durante a "
                  "busca (inclusive no meio do download) e refaz a busca do zero SEM filtros, "
                  "sem passar o cancelamento ao provider e somando aos registros já baixados — duplicando e "
                  "misturando resultados não filtrados. (Não alterado: main.py está em edição "
                  "por outra pessoa.)"},
        {"estado": "conhecido", "onde": _linha_de("core/sources/pubmed.py", '"citations": 0,'),
         "texto": "PubMed nunca preenche citações, referências nem acesso aberto (o formato "
                  "MEDLINE não traz esses dados). Já documentado como OBS-04."},
    ]


def _significado(res: dict) -> List[str]:
    """Frases em linguagem simples, derivadas dos números medidos."""
    frases: List[str] = []
    execs = [e for e in res["execucoes"] if e.get("blicsa")]

    def campo_api(base, campo):
        """% da amostra em que a BASE (não o Blicsa) não tem o campo."""
        tot = sem = 0
        for e in execs:
            if e["base"] != base:
                continue
            for c in (e.get("amostra") or {}).get("comparacoes", []):
                info = c.get("campos", {}).get(campo)
                if info and info["api"] is not None:
                    tot += 1
                    sem += 0 if info["api"] else 1
        return (100.0 * sem / tot, tot) if tot else (None, 0)

    totais = [e for e in execs if e.get("comparacao_total")]
    errados_tot = [e for e in totais if e["comparacao_total"]["status"] == ERRADO]
    if totais and not errados_tot:
        frases.append("**Os totais batem.** Em todas as buscas conferidas, o 'Encontrados' que o "
                      "Blicsa mostra é o mesmo número que a base declara quando consultada "
                      "diretamente (diferenças de poucas unidades acontecem porque as bases "
                      "recebem artigos novos o tempo todo).")
    for e in errados_tot:
        frases.append(f"**Atenção — total divergente** em {NOMES[e['base']]} para "
                      f"\"{e['consulta']}\": a base declara {_fmt(e.get('total_api'))}, o Blicsa "
                      f"mostra {_fmt(e['blicsa']['total_declarado'])}. Vale investigar antes de "
                      "usar esse número no método.")
    pag = [e for e in execs if e.get("paginacao")]
    pag_ruins = [e for e in pag if e["paginacao"]["status"] == ERRADO]
    if pag and not pag_ruins:
        frases.append("**O download é completo.** Quando o total cabia no limite, o Blicsa baixou "
                      "todos os registros; quando não cabia, baixou exatamente o limite pedido. "
                      "Nenhuma busca parou no meio sem avisar.")
    for e in pag_ruins:
        frases.append(f"**Atenção — download incompleto** em {NOMES[e['base']]} para "
                      f"\"{e['consulta']}\": {e['paginacao']['detalhe']}.")
    for base in ("openalex", "crossref", "pubmed"):
        resumos = [(e.get("amostra") or {}).get("resumo") for e in execs if e["base"] == base]
        resumos = [r for r in resumos if r and r.get("pct_ok") is not None]
        if resumos:
            media = sum(r["pct_aceitavel"] for r in resumos) / len(resumos)
            frases.append(f"**{NOMES[base]}:** na amostra, {media:.0f}% dos campos conferidos "
                          "estão iguais aos da base (contando diferenças pequenas como certas).")
    pct, n = campo_api("crossref", "resumo")
    if pct is not None:
        frases.append(f"**Crossref e resumos:** {pct:.0f}% dos artigos da amostra (n={n}) não "
                      "têm resumo no próprio Crossref — não é falha do Blicsa, é a editora que "
                      "não depositou. Análises de termos (mapas de co-ocorrência a partir do "
                      "resumo) com dados do Crossref ficam pobres; prefira o OpenAlex para isso.")
    pct, n = campo_api("crossref", "referencias")
    if pct is not None:
        frases.append(f"**Crossref e referências:** {pct:.0f}% dos artigos da amostra (n={n}) não "
                      "têm lista de referências aberta no Crossref, e das que têm o Blicsa guarda "
                      "só as que possuem DOI. Acoplamento bibliográfico e co-citação com Crossref "
                      "subestimam as ligações.")
    pct, n = campo_api("openalex", "resumo")
    if pct is not None:
        frases.append(f"**OpenAlex e resumos:** {pct:.0f}% da amostra (n={n}) está sem resumo no "
                      "OpenAlex (algumas editoras não permitem a redistribuição do resumo).")
    pm = [e for e in execs if e["base"] == "pubmed"]
    oa = {e["consulta"]: e for e in execs if e["base"] == "openalex"}
    if pm:
        comparativos = []
        for e in pm:
            o = oa.get(e["consulta"])
            if o and o.get("total_api"):
                comparativos.append(f"\"{e['consulta']}\": {_fmt(e.get('total_api'))} no PubMed × "
                                    f"{_fmt(o['total_api'])} no OpenAlex")
        frases.append("**PubMed só cobre biomedicina e ciências da vida.** Para temas de gestão, "
                      "empreendedorismo, patentes e engenharia ele encontra pouco ou nada — "
                      "isso é cobertura da base, não erro da busca"
                      + (f" ({'; '.join(comparativos)})" if comparativos else "")
                      + ". Além disso, o PubMed não informa citações, referências nem acesso "
                      "aberto: no Blicsa esses campos ficam zerados/vazios para registros do PubMed.")
    if any(e["base"] == "openalex" for e in execs):
        frases.append("**Citações do OpenAlex não são as do Google Scholar.** O OpenAlex conta "
                      "citações entre os trabalhos que ele indexa; o Google Scholar conta também "
                      "teses, slides, preprints e páginas soltas, e costuma dar números bem "
                      "maiores. Scopus e Web of Science costumam dar números menores. Compare "
                      "citações só dentro da mesma base e informe a base e a data da coleta no "
                      "método.")
    dups = res.get("duplicatas") or []
    if dups:
        comp = sum(d["dois_em_mais_de_uma_base"] for d in dups)
        trat = sum(d["tratados"] for d in dups)
        frases.append(f"**Duplicatas entre bases:** {comp} artigo(s) apareceram com o mesmo DOI em "
                      f"mais de uma base; a deduplicação do Blicsa juntou {trat} deles. Lembre: "
                      "a busca não deduplica sozinha — ao juntar buscas de bases diferentes no "
                      "mesmo corpus, use o botão **Deduplicar** do Corpus.")
    if res.get("bases_caidas"):
        nomes = ", ".join(NOMES.get(b, b) for b in res["bases_caidas"])
        frases.append(f"**Não deu para conferir {nomes}** (a base não respondeu). Rode a "
                      "auditoria de novo mais tarde; nada foi concluído sobre essa base.")
    if res.get("interrompido"):
        frases.append("**Auditoria interrompida** antes do fim (Ctrl+C). Os números acima valem "
                      "só para o que foi conferido.")
    return frases


def gerar_markdown(res: dict) -> str:
    L: List[str] = []
    data = (res.get("inicio") or _agora())[:10]
    L.append(f"# Auditoria das bases de dados do Blicsa — {data}")
    L.append("")
    situacao = "INTERROMPIDA (parcial)" if res.get("interrompido") else "completa"
    L.append(f"- **Situação:** {situacao}"
             + (f" — parou em {res['onde_parou']}" if res.get("onde_parou") else ""))
    L.append(f"- **Início / fim:** {res.get('inicio')} / {res.get('fim')}")
    L.append("- **Consultas:** " + "; ".join(f"\"{c}\"" for c in res["consultas"]))
    L.append("- **Bases:** " + ", ".join(NOMES.get(b, b) for b in res["bases"]))
    L.append(f"- **Limite de download por busca:** {_fmt(res['limite'])} · "
             f"**amostra conferida:** até {res['amostra']} registros por base e consulta")
    filtros_vis = {k: v for k, v in (res.get("filtros") or {}).items() if k != "sort"}
    if filtros_vis:
        L.append(f"- **Filtros:** {filtros_vis}")
    L.append(f"- **E-mail de contato enviado às APIs:** {res.get('email')}")
    L.append("")
    L.append("Como ler: *Total na API* é o número que a base declara quando perguntada "
             "diretamente; *Encontrados* é o que o Blicsa mostra; *Baixados* é quantos o Blicsa "
             "trouxe; *Após dedup.* é quantos sobram depois do botão Deduplicar. Cada campo da "
             "amostra é classificado em **ok**, **diferença pequena** (aceitável — p. ex. "
             "citações que a base atualizou entre as duas consultas) ou **errado**.")
    L.append("")
    L.append("## O que isso significa para a sua pesquisa")
    L.append("")
    for f in _significado(res):
        L.append(f"- {f}")
    L.append("")

    for base in res["bases"]:
        nome = NOMES.get(base, base)
        execs = [e for e in res["execucoes"] if e["base"] == base]
        L.append(f"## {nome}")
        L.append("")
        if base in res.get("bases_caidas", {}):
            L.append(f"> **Indisponível:** {res['bases_caidas'][base]}")
            L.append("")
        if base == "datacite":
            L.append("| Consulta | Total no DataCite | Situação |")
            L.append("|---|---:|---|")
            for e in execs:
                L.append(f"| {e['consulta']} | {_fmt(e.get('total_api'))} | "
                         f"{e.get('status')}{(': ' + e['motivo']) if e.get('motivo') else ''} |")
            L.append("")
            L.append(DIFERENCAS_METODO["datacite"])
            L.append("")
            continue
        L.append("### Contagens")
        L.append("")
        L.append("| Consulta | Total na API | Encontrados (Blicsa) | Totais | Baixados | Limite | "
                 "Após dedup. | Paginação | Tempo |")
        L.append("|---|---:|---:|---|---:|---:|---:|---|---:|")
        for e in execs:
            b = e.get("blicsa")
            if not b:
                L.append(f"| {e['consulta']} | {_fmt(e.get('total_api'))} | — | — | — | "
                         f"{_fmt(res['limite'])} | — | {e.get('status')}"
                         f"{(': ' + e['motivo'][:80]) if e.get('motivo') else ''} | — |")
                continue
            L.append(f"| {e['consulta']} | {_fmt(e.get('total_api'))} | "
                     f"{_fmt(b['encontrados_exibido'])} | {_icone(e['comparacao_total']['status'])} | "
                     f"{_fmt(b['baixados'])} | {_fmt(res['limite'])} | {_fmt(b['apos_dedup'])} | "
                     f"{_icone(e['paginacao']['status'])} | {_fmt(b['tempo_s'])} s |")
        L.append("")
        for e in execs:
            b = e.get("blicsa")
            if not b:
                continue
            L.append(f"- \"{e['consulta']}\" — trilha exibida pelo Blicsa: `{b['trilha']} · após "
                     f"deduplicação {b['apos_dedup']}`. Paginação: {e['paginacao']['detalhe']}. "
                     f"Totais: {e['comparacao_total']['detalhe']}."
                     + (f" DOIs repetidos dentro da própria busca: {b['dois_repetidos_na_busca']}."
                        if b.get("dois_repetidos_na_busca") else "")
                     + (f" Registros sem DOI: {b['sem_doi']}." if b.get("sem_doi") else ""))
        L.append("")
        # Amostra: agregado das consultas.
        comps = [c for e in execs for c in (e.get("amostra") or {}).get("comparacoes", [])]
        indisp = [e for e in execs if (e.get("amostra") or {}).get("indisponivel")]
        if comps:
            r = resumir_amostra(comps)
            L.append(f"### Amostra conferida campo a campo ({r['registros']} registros)")
            L.append("")
            L.append(f"Campos corretos: **{_pct(r['pct_ok'])}** · corretos ou com diferença "
                     f"pequena: **{_pct(r['pct_aceitavel'])}**"
                     + (f" · registros não encontrados na consulta direta: {r['nao_encontrados']}"
                        if r["nao_encontrados"] else ""))
            L.append("")
            L.append("| Campo | ok | diferença pequena | errado | n/a | % correto |")
            L.append("|---|---:|---:|---:|---:|---:|")
            for campo in CAMPOS:
                c = r["por_campo"][campo]
                L.append(f"| {ROTULOS[campo]} | {c[OK]} | {c[PEQUENA]} | {c[ERRADO]} | {c[NA]} | "
                         f"{_pct(c['pct_ok'])} |")
            L.append("")
            erros = [(c, campo, info) for c in comps
                     for campo, info in c.get("campos", {}).items() if info["status"] == ERRADO]
            if erros:
                L.append("<details><summary>Campos marcados como errado (até 25)</summary>")
                L.append("")
                for c, campo, info in erros[:25]:
                    L.append(f"- *{c['titulo_blicsa'][:90]}* — {ROTULOS[campo]}: {info['detalhe']}")
                L.append("")
                L.append("</details>")
                L.append("")
            nao = [c for c in comps if not c.get("encontrado")]
            if nao:
                L.append("Não encontrados pela consulta direta (ID/DOI que o Blicsa guardou não "
                         "respondeu): " + "; ".join(
                             f"*{c['titulo_blicsa'][:70]}* ({c['doi_blicsa'] or 'sem DOI'})"
                             for c in nao[:10]))
                L.append("")
        for e in indisp:
            L.append(f"> Amostra de \"{e['consulta']}\" indisponível: {e['amostra']['indisponivel']}")
            L.append("")
        L.append(f"*Método:* {DIFERENCAS_METODO.get(base, '')}")
        L.append("")

    dups = res.get("duplicatas") or []
    L.append("## Duplicatas entre bases")
    L.append("")
    if not dups:
        L.append("Não houve duas bases com resultados na mesma consulta para comparar.")
    else:
        L.append("| Consulta | Registros somados | DOIs em mais de uma base | Tratados pela "
                 "deduplicação | Após dedup. |")
        L.append("|---|---:|---:|---:|---:|")
        for d in dups:
            L.append(f"| {d['consulta']} | {_fmt(d['total_combinado'])} | "
                     f"{_fmt(d['dois_em_mais_de_uma_base'])} | {_fmt(d['tratados'])} | "
                     f"{_fmt(d['apos_dedup'])} |")
        L.append("")
        for d in dups:
            if d["por_par"]:
                L.append(f"- \"{d['consulta']}\": " + "; ".join(
                    f"{k}: {v}" for k, v in d["por_par"].items())
                    + (f". Pares entre bases removidos por motivo: "
                       + ", ".join(f"{k}={v}" for k, v in d["pares_entre_bases_por_motivo"].items())
                       if d["pares_entre_bases_por_motivo"] else ""))
            if d["nao_tratados"]:
                L.append(f"  - **Não tratados:** " + ", ".join(x["doi"] for x in d["nao_tratados"]))
        L.append("")
        L.append("A deduplicação do Blicsa (botão Deduplicar no Corpus) compara primeiro o DOI "
                 "normalizado, depois títulos parecidos no mesmo ano (só entre registros sem "
                 "DOI) e por fim primeiro autor + ano. Um preprint e o artigo publicado têm DOIs "
                 "diferentes e, por isso, normalmente **não** são juntados.")
    L.append("")
    L.append("## Suspeitas encontradas lendo o código de busca")
    L.append("")
    for s in suspeitas_do_codigo():
        L.append(f"- **[{s['estado']}]** `{s['onde']}` — {s['texto']}")
    L.append("")
    L.append("---")
    L.append(f"Gerado por `scripts/auditar_bases.py` · {res.get('pedidos_diretos', 0)} pedidos "
             "diretos às APIs · dados brutos no arquivo .json de mesmo nome.")
    return "\n".join(L) + "\n"


def salvar(res: dict, pasta: Path) -> Tuple[Path, Path]:
    pasta = Path(pasta).expanduser()
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    md = pasta / f"auditoria_bases_{carimbo}.md"
    js = pasta / f"auditoria_bases_{carimbo}.json"
    js.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md.write_text(gerar_markdown(res), encoding="utf-8")
    return md, js


# ── CLI ─────────────────────────────────────────────────────────────────────────────

def email_padrao() -> Tuple[str, str]:
    """(e-mail, de onde veio): configurações do app → e-mail padrão do Blicsa."""
    try:
        from core.settings import get_settings
        cfg = get_settings()
        for chave in ("email", "mailto", "contact_email", "user_email"):
            v = str(cfg.get(chave) or "").strip()
            if "@" in v:
                return v, f"configurações do app ({chave})"
    except Exception:
        pass
    from core.sources.base import MAILTO
    return MAILTO, "e-mail padrão do Blicsa (use --email para usar o seu)"


def chaves_do_app() -> Dict[str, str]:
    chaves = {}
    try:
        from core.sources.openalex import openalex_api_key
        chaves["openalex"] = openalex_api_key()
    except Exception:
        pass
    try:
        from core.sources.pubmed import pubmed_api_key
        chaves["pubmed"] = pubmed_api_key()
    except Exception:
        pass
    return {k: v for k, v in chaves.items() if v}


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="auditar_bases.py",
        description="Confere, contra as próprias APIs, os totais, o download e os campos que o "
                    "Blicsa traz de OpenAlex, Crossref, PubMed (e o total do DataCite). Gera "
                    "auditoria_bases_<data>.md e .json.",
        epilog="Exemplo: cd ~/PyBibliomics && source venv/bin/activate && "
               "python scripts/auditar_bases.py --email seu@email")
    p.add_argument("--consulta", action="append", metavar="TEXTO",
                   help="consulta a auditar (repetível). Padrão: "
                        + "; ".join(f'"{c}"' for c in CONSULTAS_PADRAO))
    p.add_argument("--limite", type=int, default=LIMITE_PADRAO,
                   help=f"limite de download por busca, como no app (padrão {LIMITE_PADRAO})")
    p.add_argument("--amostra", type=int, default=AMOSTRA_PADRAO,
                   help=f"registros conferidos campo a campo por base e consulta (padrão {AMOSTRA_PADRAO})")
    p.add_argument("--saida", default="auditoria_bases",
                   help="pasta onde salvar o .md e o .json (padrão ./auditoria_bases)")
    p.add_argument("--email", help="e-mail de contato para as APIs (polite pool)")
    p.add_argument("--bases", default=",".join(BASES_PADRAO),
                   help="bases separadas por vírgula (padrão openalex,crossref,pubmed,datacite)")
    p.add_argument("--ano-inicio", type=int, help="filtro de ano inicial (igual ao do app)")
    p.add_argument("--ano-fim", type=int, help="filtro de ano final (igual ao do app)")
    p.add_argument("--timeout", type=float, default=20.0, help="timeout por pedido direto, em s")
    p.add_argument("--tentativas", type=int, default=3, help="tentativas por pedido direto")
    p.add_argument("--tempo-max-base", type=float, default=600.0,
                   help="tempo máximo da busca do Blicsa por base e consulta, em s")
    return p


def main(argv: Optional[List[str]] = None, abrir: Optional[Callable] = None,
         executor: Callable[..., dict] = rodar_blicsa) -> int:
    args = montar_parser().parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    bases = [b.strip().lower() for b in args.bases.split(",") if b.strip()]
    invalidas = [b for b in bases if b not in NOMES]
    if invalidas:
        print(f"Base desconhecida: {', '.join(invalidas)}. Use: {', '.join(NOMES)}", file=sys.stderr)
        return 2
    if args.email:
        email, origem = args.email.strip(), "--email"
    else:
        email, origem = email_padrao()
    filtros = {}
    if args.ano_inicio:
        filtros["year_start"] = args.ano_inicio
    if args.ano_fim:
        filtros["year_end"] = args.ano_fim
    consultas = args.consulta or list(CONSULTAS_PADRAO)
    print(f"E-mail de contato: {email} ({origem})", file=sys.stderr)
    cliente = HttpCliente(email, timeout=args.timeout, tentativas=args.tentativas, abrir=abrir)
    res = auditar(consultas, bases, max(1, args.limite), max(0, args.amostra), cliente,
                  chaves=chaves_do_app(), filtros=filtros, tempo_max_base=args.tempo_max_base,
                  executor=executor)
    md, js = salvar(res, Path(args.saida))
    print(f"\nRelatório: {md}\nDados brutos: {js}", file=sys.stderr)
    return 130 if res.get("interrompido") else 0


if __name__ == "__main__":
    sys.exit(main())
