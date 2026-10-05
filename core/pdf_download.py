"""Baixar os PDFs de acesso aberto do corpus para uma pasta.

O botão antigo olhava só o `oa_url` dos registros marcados como acesso aberto e gravava
qualquer resposta como `.pdf`. Três problemas, todos silenciosos:

1. Corpus importado do Scopus ou do Web of Science não traz `is_oa`/`oa_url`: nada era
   baixado, sem explicação.
2. O `oa_url` costuma ser a página do artigo no site do editor, não o PDF. O arquivo salvo
   era HTML com extensão `.pdf`, contado como "sucesso"; o pesquisador só descobria ao abrir.
3. Sem pasta escolhida, sem cancelar, sem saber o que faltou.

Aqui, para cada registro, juntam-se candidatos de várias fontes (o próprio registro,
Unpaywall pelo DOI, OpenAlex, arXiv), baixa-se o primeiro que é PDF de verdade (os bytes
começam com `%PDF-`) e, quando o link é uma página, procura-se nela o `citation_pdf_url`,
a meta tag que os editores publicam para o Google Scholar. Tudo o que não deu certo vai
para um relatório CSV na pasta, com o link para abrir no navegador.

A rede entra por funções injetáveis (`buscar_json`, `abrir_url`): os testes rodam offline.
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from core.sources.base import MAILTO  # importa base: configura os certificados

# ── Situações possíveis de cada registro ────────────────────────────────────────────
BAIXADO = "baixado"
JA_EXISTIA = "ja_existia"
SEM_ACESSO_ABERTO = "sem_acesso_aberto"     # nenhuma fonte conhece versão aberta
SO_PAGINA = "so_pagina"                     # há versão aberta, mas o link não entrega PDF
FALHOU = "falhou"                           # erro de rede/servidor em todos os candidatos
SEM_IDENTIFICADOR = "sem_identificador"     # sem DOI e sem link: não há o que procurar
CANCELADO = "cancelado"

SITUACOES = (BAIXADO, JA_EXISTIA, SEM_ACESSO_ABERTO, SO_PAGINA, FALHOU, SEM_IDENTIFICADOR,
             CANCELADO)

LIMITE_BYTES = 80 * 1024 * 1024          # PDF maior que isso é anomalia (ou não é artigo)
TIMEOUT = 30
INTERVALO_POR_HOST = 1.0                 # educação com os servidores dos editores
NOME_RELATORIO = "blicsa_pdfs_relatorio.csv"


def _user_agent(email: str) -> str:
    # Alguns editores recusam clientes sem cara de navegador; o mailto identifica o app
    # (boa prática pedida por Unpaywall e OpenAlex).
    return f"Mozilla/5.0 (compatible; Blicsa/2.1; mailto:{email})"


# ── Nome do arquivo ─────────────────────────────────────────────────────────────────
def _ascii(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return texto.encode("ascii", "ignore").decode("ascii")


def _slug(texto: str, limite: int) -> str:
    texto = re.sub(r"[^\w\s-]", "", _ascii(texto).lower())
    texto = re.sub(r"[-\s_]+", "-", texto).strip("-")
    return texto[:limite].rstrip("-")


def nome_arquivo(registro: dict, usados: set[str]) -> str:
    """`Sobrenome_Ano_inicio-do-titulo.pdf`, único dentro de `usados` (sem diferenciar
    maiúsculas, por causa do macOS e do Windows)."""
    autores = str(registro.get("authors") or "")
    primeiro = autores.split(";")[0].split(",")[0].strip()
    sobrenome = _slug(primeiro.split()[-1] if " " in primeiro and "," not in autores.split(";")[0]
                      else primeiro, 30) or "sem-autor"
    try:
        ano = int(float(registro.get("year") or 0))
    except (TypeError, ValueError):
        ano = 0
    titulo = _slug(registro.get("title") or "", 60) or "sem-titulo"
    base = f"{sobrenome.capitalize()}_{ano if ano else 'sd'}_{titulo}"
    nome, n = f"{base}.pdf", 2
    while nome.lower() in usados:
        nome, n = f"{base}-{n}.pdf", n + 1
    usados.add(nome.lower())
    return nome


# ── Identificadores ─────────────────────────────────────────────────────────────────
def doi_limpo(valor) -> str:
    m = re.search(r"10\.\d{4,9}/\S+", str(valor or ""))
    return m.group(0).rstrip(".;,)").lower() if m else ""


def _id_openalex(valor) -> str:
    m = re.search(r"\b(W\d+)\b", str(valor or ""), re.IGNORECASE)
    return m.group(1).upper() if m else ""


# ── Candidatos ──────────────────────────────────────────────────────────────────────
@dataclass
class Candidatos:
    pdfs: list[str] = field(default_factory=list)      # links que deveriam ser PDF
    erros_consulta: list[str] = field(default_factory=list)  # Unpaywall/OpenAlex sem resposta
    paginas: list[str] = field(default_factory=list)   # páginas do artigo (landing pages)
    conhecido_aberto: bool = False                      # alguma fonte diz que há versão aberta

    def _add(self, lista: list[str], url) -> None:
        url = str(url or "").strip()
        if url.startswith(("http://", "https://")) and url not in self.pdfs + self.paginas:
            lista.append(url)

    def pdf(self, url) -> None:
        self._add(self.pdfs, url)

    def pagina(self, url) -> None:
        self._add(self.paginas, url)

    def todos(self) -> list[str]:
        return self.pdfs + self.paginas


def _parece_pdf(url: str) -> bool:
    caminho = urllib.parse.urlparse(url).path.lower()
    return caminho.endswith(".pdf") or "/pdf/" in caminho or "/pdf" == caminho[-4:]


def _consultar(c: "Candidatos", buscar_json, url: str, fonte: str):
    try:
        return buscar_json(url)
    except Exception as exc:          # rede, 5xx, 429: anotado para o relatório
        c.erros_consulta.append(f"{fonte}: {type(exc).__name__}: {exc}"[:120])
        return None


def candidatos(registro: dict, buscar_json: Callable[[str], Optional[dict]],
               email: str = MAILTO) -> Candidatos:
    """Junta os links possíveis do PDF deste registro, do mais provável ao menos."""
    c = Candidatos()
    doi = doi_limpo(registro.get("doi"))

    # 1. O próprio registro (busca integrada do OpenAlex grava `oa_url`).
    oa_url = str(registro.get("oa_url") or "")
    if oa_url:
        c.conhecido_aberto = True
        (c.pdf if _parece_pdf(oa_url) else c.pagina)(oa_url)

    # 2. arXiv: o DOI já diz onde está o PDF.
    m = re.match(r"10\.48550/arxiv\.(.+)", doi)
    if m:
        c.conhecido_aberto = True
        c.pdf(f"https://arxiv.org/pdf/{m.group(1)}")

    # 3. Unpaywall pelo DOI: cobre corpus do Scopus/WoS, que não trazem acesso aberto.
    if doi:
        dados = _consultar(c, buscar_json, f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}"
                           f"?email={urllib.parse.quote(email)}", "Unpaywall")
        if isinstance(dados, dict) and dados.get("is_oa"):
            c.conhecido_aberto = True
            locais = [dados.get("best_oa_location") or {}] + list(dados.get("oa_locations") or [])
            for loc in locais:
                if isinstance(loc, dict):
                    c.pdf(loc.get("url_for_pdf"))
            for loc in locais:
                if isinstance(loc, dict):
                    c.pagina(loc.get("url_for_landing_page") or loc.get("url"))

    # 4. OpenAlex: às vezes conhece repositórios (institucionais, PMC) que o Unpaywall não lista.
    oa_id = _id_openalex(registro.get("openalex_id"))
    alvo = (f"https://api.openalex.org/works/{oa_id}" if oa_id else
            f"https://api.openalex.org/works/https://doi.org/{doi}" if doi else "")
    if alvo:
        dados = _consultar(c, buscar_json, f"{alvo}?mailto={urllib.parse.quote(email)}"
                           "&select=open_access,best_oa_location,locations", "OpenAlex")
        if isinstance(dados, dict):
            if (dados.get("open_access") or {}).get("is_oa"):
                c.conhecido_aberto = True
            locais = [dados.get("best_oa_location") or {}] + list(dados.get("locations") or [])
            for loc in locais:
                if isinstance(loc, dict) and loc.get("is_oa"):
                    c.pdf(loc.get("pdf_url"))
            for loc in locais:
                if isinstance(loc, dict) and loc.get("is_oa"):
                    c.pagina(loc.get("landing_page_url"))
            oa = (dados.get("open_access") or {}).get("oa_url")
            if oa:
                (c.pdf if _parece_pdf(oa) else c.pagina)(oa)

    # 5. Semantic Scholar, só se ninguém deu link direto de PDF: muitas vezes o link aberto
    #    das outras fontes é a página do editor (10 de 30 na verificação ao vivo de 04/10).
    if doi and not c.pdfs:
        dados = _consultar(c, buscar_json, "https://api.semanticscholar.org/graph/v1/paper/"
                           f"DOI:{urllib.parse.quote(doi)}?fields=openAccessPdf", "Semantic Scholar")
        url = ((dados or {}).get("openAccessPdf") or {}).get("url") if isinstance(dados, dict) else None
        if url:
            c.conhecido_aberto = True
            c.pdf(url)
    return c


# ── Rede ────────────────────────────────────────────────────────────────────────────
class _Educado:
    """Garante um intervalo mínimo entre pedidos ao mesmo servidor."""

    def __init__(self, intervalo: float):
        self.intervalo = intervalo
        self._ultimo: dict[str, float] = {}
        self._trava = threading.Lock()

    def esperar(self, url: str) -> None:
        host = urllib.parse.urlparse(url).netloc
        with self._trava:
            agora = time.monotonic()
            pronto = self._ultimo.get(host, 0.0) + self.intervalo
            self._ultimo[host] = max(agora, pronto)
        if pronto > agora:
            time.sleep(pronto - agora)


def abrir_url_padrao(url: str, email: str = MAILTO, timeout: float = TIMEOUT):
    """Resposta HTTP aberta (objeto com .read(n) e .headers)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": _user_agent(email),
        "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.5",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def buscar_json_padrao(url: str, email: str = MAILTO) -> Optional[dict]:
    """JSON da API; None se a obra não existe lá (404). Falha de rede LEVANTA: "sem conexão"
    não pode virar "sem acesso aberto" no relatório."""
    import urllib.error
    try:
        with abrir_url_padrao(url, email, timeout=20) as r:
            return json.loads(r.read(5_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


_META_PDF = re.compile(
    r"""<meta[^>]+name\s*=\s*["']citation_pdf_url["'][^>]*>""", re.IGNORECASE)
_CONTEUDO = re.compile(r"""content\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def link_pdf_na_pagina(pagina_html: str, url_base: str) -> str:
    """O `citation_pdf_url` da página do artigo, se o editor o publica."""
    for tag in _META_PDF.findall(pagina_html or ""):
        m = _CONTEUDO.search(tag)
        if m:
            return urllib.parse.urljoin(url_base, html.unescape(m.group(1).strip()))
    return ""


class _NaoEhPdf(Exception):
    def __init__(self, pagina: str, url_final: str):
        super().__init__("não é PDF")
        self.pagina = pagina
        self.url_final = url_final


def _baixar_para(url: str, destino: str, abrir_url, cancelar: threading.Event,
                 limite: int = LIMITE_BYTES) -> None:
    """Baixa `url` para `destino` só se o conteúdo for PDF; senão levanta _NaoEhPdf com o
    HTML (para procurar o citation_pdf_url). Escreve em `.part` e renomeia no fim: um
    download interrompido nunca deixa um PDF pela metade com nome de pronto."""
    with abrir_url(url) as resp:
        inicio = resp.read(1024)
        if not inicio.lstrip()[:5] == b"%PDF-":
            resto = resp.read(500_000) if len(inicio) == 1024 else b""
            url_final = getattr(resp, "url", None) or url
            raise _NaoEhPdf((inicio + resto).decode("utf-8", "replace"), url_final)
        parcial = destino + ".part"
        total = len(inicio)
        try:
            with open(parcial, "wb") as f:
                f.write(inicio)
                while True:
                    if cancelar.is_set():
                        raise InterruptedError
                    bloco = resp.read(256 * 1024)
                    if not bloco:
                        break
                    total += len(bloco)
                    if total > limite:
                        raise ValueError("arquivo grande demais")
                    f.write(bloco)
            os.replace(parcial, destino)
        finally:
            if os.path.exists(parcial):
                try:
                    os.remove(parcial)
                except OSError:
                    pass


# ── Resultado ───────────────────────────────────────────────────────────────────────
@dataclass
class ResultadoRegistro:
    indice: int
    titulo: str
    ano: str
    doi: str
    situacao: str
    arquivo: str = ""
    link: str = ""          # onde o pesquisador pode tentar pelo navegador
    detalhe: str = ""


@dataclass
class Resumo:
    pasta: str
    total: int = 0
    resultados: list[ResultadoRegistro] = field(default_factory=list)
    relatorio: str = ""

    def contagem(self) -> dict[str, int]:
        c = {s: 0 for s in SITUACOES}
        for r in self.resultados:
            c[r.situacao] = c.get(r.situacao, 0) + 1
        return c


def _processar(i: int, registro: dict, pasta: str, nome: str, buscar_json, abrir_url,
               cancelar: threading.Event, educado: _Educado, email: str) -> ResultadoRegistro:
    titulo = str(registro.get("title") or "")
    ano = str(registro.get("year") or "")
    doi = doi_limpo(registro.get("doi"))
    r = ResultadoRegistro(i, titulo, ano, doi, FALHOU)
    destino = os.path.join(pasta, nome)

    if cancelar.is_set():
        r.situacao = CANCELADO
        return r
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        r.situacao, r.arquivo = JA_EXISTIA, nome
        return r
    if not doi and not registro.get("oa_url") and not _id_openalex(registro.get("openalex_id")):
        r.situacao, r.detalhe = SEM_IDENTIFICADOR, "sem DOI nem link"
        return r

    c = candidatos(registro, buscar_json, email)
    r.link = (c.paginas[0] if c.paginas else c.pdfs[0] if c.pdfs else
              f"https://doi.org/{doi}" if doi else "")
    if not c.todos():
        if c.erros_consulta:
            r.situacao, r.detalhe = FALHOU, "sem resposta de " + "; ".join(c.erros_consulta)
        else:
            r.situacao = SEM_ACESSO_ABERTO if (doi or c.conhecido_aberto) else SEM_IDENTIFICADOR
        return r

    erros, viu_pagina = [], False
    fila, tentados = list(c.todos()), set()
    while fila and len(tentados) < 8:
        url = fila.pop(0)
        if url in tentados:
            continue
        tentados.add(url)
        if cancelar.is_set():
            r.situacao = CANCELADO
            return r
        educado.esperar(url)
        try:
            _baixar_para(url, destino, abrir_url, cancelar)
            r.situacao, r.arquivo, r.link, r.detalhe = BAIXADO, nome, url, ""
            return r
        except _NaoEhPdf as e:
            viu_pagina = True
            achado = link_pdf_na_pagina(e.pagina, e.url_final)
            if achado and achado not in tentados:
                fila.insert(0, achado)
        except InterruptedError:
            r.situacao = CANCELADO
            return r
        except Exception as e:      # rede, 403 do editor, timeout, arquivo grande
            erros.append(f"{type(e).__name__}: {e}"[:120])
    if viu_pagina:
        r.situacao, r.detalhe = SO_PAGINA, "o link abre a página do artigo, não o PDF"
    else:
        r.situacao, r.detalhe = FALHOU, (erros[-1] if erros else "")
    return r


def baixar_corpus(registros: Iterable[dict], pasta: str, *,
                  buscar_json: Optional[Callable[[str], Optional[dict]]] = None,
                  abrir_url=None, ao_progresso: Optional[Callable[[int, int, Resumo], None]] = None,
                  cancelar: Optional[threading.Event] = None, email: str = MAILTO,
                  concorrencia: int = 4, intervalo_por_host: float = INTERVALO_POR_HOST) -> Resumo:
    """Baixa o que houver de acesso aberto. Nunca levanta por causa de um registro: cada
    problema vira uma linha do relatório."""
    registros = list(registros)
    os.makedirs(pasta, exist_ok=True)
    cancelar = cancelar or threading.Event()
    buscar_json = buscar_json or (lambda u: buscar_json_padrao(u, email))
    abrir_url = abrir_url or (lambda u: abrir_url_padrao(u, email))
    educado = _Educado(intervalo_por_host)

    # Nome é decidido antes, em ordem: o mesmo corpus dá os mesmos nomes numa segunda
    # rodada, e aí o que já foi baixado aparece como "já estava na pasta".
    nomes, vistos = [], set()
    for reg in registros:
        n = nome_arquivo(reg, vistos)
        nomes.append(n)
    resumo = Resumo(pasta=pasta, total=len(registros))
    trava = threading.Lock()
    feitos = [0]

    def tarefa(i):
        res = _processar(i, registros[i], pasta, nomes[i], buscar_json, abrir_url,
                         cancelar, educado, email)
        with trava:
            resumo.resultados.append(res)
            feitos[0] += 1
            n = feitos[0]
        if ao_progresso:
            try:
                ao_progresso(n, len(registros), resumo)
            except Exception:
                pass
        return res

    with ThreadPoolExecutor(max_workers=max(1, concorrencia)) as ex:
        list(ex.map(tarefa, range(len(registros))))

    resumo.resultados.sort(key=lambda r: r.indice)
    resumo.relatorio = escrever_relatorio(resumo)
    return resumo


def escrever_relatorio(resumo: Resumo) -> str:
    """CSV na pasta (abre no Excel em português: `;` e BOM)."""
    caminho = os.path.join(resumo.pasta, NOME_RELATORIO)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["situacao", "arquivo", "ano", "titulo", "doi", "link", "detalhe"])
        for r in resumo.resultados:
            w.writerow([r.situacao, r.arquivo, r.ano, r.titulo, r.doi, r.link, r.detalhe])
    return caminho
