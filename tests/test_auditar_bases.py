"""Testes OFFLINE de `scripts/auditar_bases.py` (auditoria das bases contra as APIs).

Nada aqui usa a rede. Uma "internet falsa" (`_Internet`) responde às URLs dos dois lados da
comparação — o código real do Blicsa (via patch de `SearchProvider.fetch_url`) e o cliente
direto do script (via `abrir` injetável) — a partir das fixtures REAIS gravadas em
`tests/fixtures/`. Assim os dois caminhos leem o mesmo dado cru, e o que se testa é a lógica
de comparação, classificação, robustez e o relatório.
"""
from __future__ import annotations

import importlib.util
import json
import re
import time
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

import pytest

from tests.conftest import load_fixture, serve

RAIZ = Path(__file__).resolve().parent.parent


def _carregar_script():
    spec = importlib.util.spec_from_file_location("auditar_bases",
                                                  RAIZ / "scripts" / "auditar_bases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ab = _carregar_script()


# ── Internet falsa a partir das fixtures ─────────────────────────────────────────────

def _medline_para_xml(texto: str) -> str:
    """MEDLINE (fixture real) → PubmedArticleSet XML mínimo, para o lado "direto"."""
    from core.sources.pubmed import PubMedProvider
    arts = []
    for r in PubMedProvider(api_key="")._parse_medline(texto):
        ano = re.search(r"\b(19|20)\d{2}\b", r.get("DP", ""))
        autores = "".join(
            f"<Author><LastName>{escape(a.rsplit(' ', 1)[0])}</LastName>"
            f"<Initials>{escape(a.rsplit(' ', 1)[-1]) if ' ' in a else ''}</Initials></Author>"
            for a in [x.strip() for x in r.get("AU", "").split(";") if x.strip()])
        doi = None
        for tag in ("LID", "AID"):
            m = re.search(r"(\S+)\s+\[doi\]", r.get(tag, ""))
            if m:
                doi = m.group(1)
                break
        ids = f'<ArticleId IdType="pubmed">{r.get("PMID", "")}</ArticleId>'
        if doi:
            ids += f'<ArticleId IdType="doi">{escape(doi)}</ArticleId>'
        resumo = (f"<Abstract><AbstractText>{escape(r['AB'])}</AbstractText></Abstract>"
                  if r.get("AB") else "")
        arts.append(
            f"<PubmedArticle><MedlineCitation><PMID>{r.get('PMID', '')}</PMID><Article>"
            f"<Journal><JournalIssue><PubDate><Year>{ano.group() if ano else ''}</Year></PubDate>"
            f"</JournalIssue><Title>{escape(r.get('JT', ''))}</Title></Journal>"
            f"<ArticleTitle>{escape(r.get('TI', ''))}</ArticleTitle>{resumo}"
            f"<AuthorList>{autores}</AuthorList></Article></MedlineCitation>"
            f"<PubmedData><ArticleIdList>{ids}</ArticleIdList></PubmedData></PubmedArticle>")
    return "<?xml version='1.0'?><PubmedArticleSet>" + "".join(arts) + "</PubmedArticleSet>"


class _Internet:
    """Responde às URLs das 4 bases com as fixtures reais. `fora` = hosts "fora do ar"."""

    def __init__(self, fora=(), total_openalex_direto=None, alterar_openalex=None):
        self.oa = load_fixture("openalex_rel_bibliometric.json")
        self.cr = load_fixture("crossref_rel_bibliometric.json")
        self.pm_medline = load_fixture("pubmed_rel_bibliometric_efetch.json")
        self.pm_xml = _medline_para_xml(self.pm_medline)
        self.pm_pmids = re.findall(r"^PMID- (\d+)", self.pm_medline, flags=re.M)
        self.fora = set(fora)
        self.total_openalex_direto = total_openalex_direto
        self.alterar_openalex = alterar_openalex or (lambda w: w)
        self.urls = []

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        p = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(p.query)
        if p.netloc in self.fora:
            raise urllib.error.URLError("simulado: base fora do ar")
        if p.netloc == "api.openalex.org":
            if p.path == "/works":
                if q.get("per_page") == ["1"] and self.total_openalex_direto is not None:
                    dados = json.loads(self.oa)
                    dados["meta"]["count"] = self.total_openalex_direto
                    return json.dumps(dados)
                return self.oa
            wid = p.path.rsplit("/", 1)[-1]
            for w in json.loads(self.oa)["results"]:
                if w["id"].endswith("/" + wid):
                    return json.dumps(self.alterar_openalex(dict(w)))
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if p.netloc == "api.crossref.org":
            if p.path == "/works":
                return self.cr
            doi = urllib.parse.unquote(p.path[len("/works/"):]).lower()
            for it in json.loads(self.cr)["message"]["items"]:
                if it["DOI"].lower() == doi:
                    return json.dumps({"status": "ok", "message": it})
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if p.netloc == "eutils.ncbi.nlm.nih.gov":
            if p.path.endswith("esearch.fcgi"):
                termo = q.get("term", [""])[0]
                if q.get("usehistory") == ["y"]:
                    return json.dumps({"esearchresult": {"count": "30839", "webenv": "W1",
                                                         "querykey": "1", "idlist": []}})
                if "[doi]" in termo:
                    return json.dumps({"esearchresult": {"count": str(len(self.pm_pmids)),
                                                         "idlist": self.pm_pmids}})
                if "[ti]" in termo:
                    return json.dumps({"esearchresult": {"count": "0", "idlist": []}})
                return json.dumps({"esearchresult": {"count": "30839", "idlist": []}})
            if p.path.endswith("efetch.fcgi"):
                return self.pm_xml if q.get("retmode") == ["xml"] else self.pm_medline
        if p.netloc == "api.datacite.org":
            return json.dumps({"meta": {"total": 42}, "data": []})
        raise AssertionError(f"URL inesperada: {url}")


def _cliente(internet, **kw):
    return ab.HttpCliente("teste@exemplo.org", abrir=lambda url, h, t: internet(url),
                          dormir=lambda s: None, **kw)


class _BlicsaNaInternetFalsa:
    """Patch de fetch_url: o código REAL dos providers lê a mesma internet falsa."""

    def __init__(self, internet):
        self.internet = internet

    def __enter__(self):
        def falso(_self, url, *a, **kw):
            return self.internet(url)
        self._p = patch("core.sources.base.SearchProvider.fetch_url", autospec=True,
                        side_effect=falso)
        self._p.start()
        return self

    def __exit__(self, *a):
        self._p.stop()
        return False


def _auditar(internet, bases=("openalex", "crossref", "pubmed", "datacite"), **kw):
    with _BlicsaNaInternetFalsa(internet):
        return ab.auditar(["bibliometric analysis"], list(bases), limite=25, amostra=20,
                          cliente=_cliente(internet), log=lambda m: None, **kw)


# ── Classificação ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("campo,blicsa,api,esperado", [
    ("titulo", "Bibliometric Analysis of X.", "bibliometric analysis of x", ab.OK),
    ("titulo", "Bibliometric analysis of entrepreneurs", "Bibliometric analyses of entrepreneur", ab.PEQUENA),
    ("titulo", "Patent grace period", "Design science research in IS", ab.ERRADO),
    ("ano", 2020, 2020, ab.OK),
    ("ano", 2020, 2021, ab.PEQUENA),
    ("ano", 2018, 2021, ab.ERRADO),
    ("ano", 0, 2021, ab.ERRADO),
    ("primeiro_autor", "Shane Scott", "Shane Scott", ab.OK),
    ("primeiro_autor", "Livak KJ", "Livak K. J.", ab.OK),
    ("primeiro_autor", "Nees Jan van Eck", "Nees Jan van Eck", ab.OK),
    ("primeiro_autor", "", "Shane Scott", ab.ERRADO),
    ("primeiro_autor", "Silva João", "Pereira Ana", ab.ERRADO),
    ("n_autores", 3, 3, ab.OK),
    ("n_autores", 3, 4, ab.PEQUENA),
    ("n_autores", 100, 250, ab.ERRADO),
    ("revista", "Scientometrics", "Scientometrics", ab.OK),
    ("revista", "Journal of Informetrics", "Journal of informetrics.", ab.OK),
    ("revista", "Research Policy", "Res Policy (Amsterdam)", ab.ERRADO),
    ("doi", "https://doi.org/10.1/ABC", "10.1/abc", ab.OK),
    ("doi", "", "10.1/abc", ab.ERRADO),
    ("citacoes", 100, 100, ab.OK),
    ("citacoes", 100, 103, ab.PEQUENA),
    ("citacoes", 1000, 1040, ab.PEQUENA),
    ("citacoes", 10, 60, ab.ERRADO),
    ("resumo", True, True, ab.OK),
    ("resumo", False, True, ab.ERRADO),
    ("acesso_aberto", False, False, ab.OK),
    ("citacoes", 0, None, ab.NA),
])
def test_classificar(campo, blicsa, api, esperado):
    status, _ = ab.classificar(campo, blicsa, api)
    assert status == esperado


def test_comparar_totais_e_paginacao():
    assert ab.comparar_totais(1000, 1000)[0] == ab.OK
    assert ab.comparar_totais(327_499, 327_502)[0] == ab.PEQUENA
    assert ab.comparar_totais(1000, 25)[0] == ab.ERRADO
    assert ab.comparar_totais(None, 10)[0] == ab.NA
    # total cabe no limite: tinha de ir até o fim
    assert ab.checar_paginacao("openalex", 150, 150, 200)[0] == ab.OK
    assert "foi até o fim" in ab.checar_paginacao("openalex", 150, 150, 200)[1]
    assert ab.checar_paginacao("openalex", 150, 100, 200, "exauriu")[0] == ab.ERRADO
    # total maior que o limite: tinha de parar no limite
    assert ab.checar_paginacao("crossref", 5000, 200, 200)[0] == ab.OK
    assert ab.checar_paginacao("crossref", 5000, 300, 200)[0] == ab.ERRADO
    # PubMed: o teto do NCBI é o esperado, não falha do Blicsa
    assert ab.checar_paginacao("pubmed", 50_000, 9_999, 20_000)[0] == ab.OK
    assert ab.checar_paginacao("openalex", 500, 200, 1000, "erro de rede", True)[0] == ab.ERRADO
    assert ab.checar_paginacao("openalex", 500, 10, 1000, interrompido=True)[0] == ab.ERRADO


def test_escolher_amostra_espalhada():
    regs = list(range(100))
    idx = ab.escolher_amostra(regs, 20)
    assert len(idx) == 20 and idx[0] == 0 and idx[-1] == 99
    assert ab.escolher_amostra(list(range(5)), 20) == [0, 1, 2, 3, 4]


def test_sem_segredo_apaga_chave():
    url = "https://api.openalex.org/works?per_page=1&api_key=SEGREDO123&mailto=a%40b"
    assert "SEGREDO123" not in ab.sem_segredo(url)


def test_crossref_referencias_sem_doi_e_diferenca_pequena():
    rec = {"title": "T", "year": 2020, "authors": "A B", "source": "J", "doi": "10.1/x",
           "citations": 1, "abstract": "", "references": "", "is_oa": False}
    verdade = {"titulo": "T", "ano": 2020, "primeiro_autor": "A B", "n_autores": 1,
               "revista": "J", "doi": "10.1/x", "citacoes": 1, "resumo": False,
               "referencias": True, "acesso_aberto": False, "_refs_total": 12,
               "_refs_com_doi": 0}
    comp = ab.comparar_registro("crossref", rec, verdade)
    assert comp["campos"]["referencias"]["status"] == ab.PEQUENA
    verdade["_refs_com_doi"] = 5
    assert ab.comparar_registro("crossref", rec, verdade)["campos"]["referencias"]["status"] == ab.ERRADO


# ── A consulta direta reproduz os parâmetros do Blicsa ───────────────────────────────

FILTROS = {"year_start": 2015, "year_end": 2024, "sort": "relevance"}


def test_url_direta_openalex_tem_o_mesmo_filtro_do_blicsa():
    from core.sources import OpenAlexProvider
    with serve(load_fixture("openalex_rel_bibliometric.json")) as rec:
        list(OpenAlexProvider(api_key="").search("bibliometric analysis", FILTROS, max_results=5))
    blicsa = urllib.parse.parse_qs(urllib.parse.urlparse(rec.calls[0]).query)
    direta = urllib.parse.parse_qs(urllib.parse.urlparse(
        ab.url_total_openalex("bibliometric analysis", FILTROS, "x@y.z")).query)
    assert direta["filter"] == blicsa["filter"]


def test_url_direta_crossref_tem_a_mesma_consulta_do_blicsa():
    from core.sources import CrossrefProvider
    consulta = "(bibliometric AND analysis) OR entrepreneurship"
    with serve(load_fixture("crossref_rel_bibliometric.json")) as rec:
        list(CrossrefProvider().search(consulta, FILTROS, max_results=5))
    blicsa = urllib.parse.parse_qs(urllib.parse.urlparse(rec.calls[0]).query)
    direta = urllib.parse.parse_qs(urllib.parse.urlparse(
        ab.url_total_crossref(consulta, FILTROS, "x@y.z")).query)
    assert direta["query.bibliographic"] == blicsa["query.bibliographic"]
    assert direta["filter"] == blicsa["filter"]


@pytest.mark.parametrize("filtros", [FILTROS, {"year_start": 2018}, {"year_end": 2010}, {}])
def test_url_direta_pubmed_tem_o_mesmo_termo_do_blicsa(filtros):
    from core.sources import PubMedProvider
    vazio = json.dumps({"esearchresult": {"count": "0", "idlist": []}})
    with serve(vazio) as rec:
        list(PubMedProvider(api_key="").search("bibliometric analysis", filtros, max_results=5))
    blicsa = urllib.parse.parse_qs(urllib.parse.urlparse(rec.calls[0]).query)
    direta = urllib.parse.parse_qs(urllib.parse.urlparse(
        ab.url_total_pubmed("bibliometric analysis", filtros, "x@y.z")).query)
    assert direta["term"] == blicsa["term"]


# ── Verdade lida das fixtures reais ──────────────────────────────────────────────────

def test_verdade_openalex_bate_com_o_blicsa_na_fixture_vosviewer():
    from core.sources import OpenAlexProvider
    corpo = load_fixture("openalex_vosviewer.json")
    with serve(corpo):
        rec = list(OpenAlexProvider(api_key="").search("x", max_results=1))[0]
    verdade = ab.verdade_openalex(json.loads(corpo)["results"][0])
    comp = ab.comparar_registro("openalex", rec, verdade)
    assert {c["status"] for c in comp["campos"].values()} == {ab.OK}, comp


def test_verdade_crossref_bate_com_o_blicsa_na_fixture_shane():
    from core.sources import CrossrefProvider
    corpo = load_fixture("crossref_shane_doifilter.json")
    with serve(corpo):
        rec = list(CrossrefProvider().search("x", max_results=1))[0]
    verdade = ab.verdade_crossref(json.loads(corpo)["message"]["items"][0])
    comp = ab.comparar_registro("crossref", rec, verdade)
    assert comp["campos"]["doi"]["status"] == ab.OK
    assert comp["campos"]["primeiro_autor"]["status"] == ab.OK
    assert comp["campos"]["ano"]["status"] == ab.OK
    assert all(c["status"] in (ab.OK, ab.PEQUENA) for c in comp["campos"].values()), comp


def test_parse_pubmed_xml_campos_basicos():
    xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>11846609</PMID><Article>
      <Journal><JournalIssue><PubDate><MedlineDate>2001 Dec-2002 Jan</MedlineDate></PubDate>
      </JournalIssue><Title>Methods (San Diego, Calif.)</Title></Journal>
      <ArticleTitle>Analysis of relative gene expression data using <i>real-time</i> PCR.</ArticleTitle>
      <Abstract><AbstractText>The two most commonly used methods...</AbstractText></Abstract>
      <AuthorList><Author><LastName>Livak</LastName><Initials>KJ</Initials></Author>
      <Author><CollectiveName>PCR Consortium</CollectiveName></Author></AuthorList>
      <ELocationID EIdType="doi">10.1006/meth.2001.1262</ELocationID></Article></MedlineCitation>
      <PubmedData><ArticleIdList><ArticleId IdType="pmc">PMC123</ArticleId></ArticleIdList>
      <ReferenceList><Reference><Citation>x</Citation></Reference></ReferenceList></PubmedData>
      </PubmedArticle></PubmedArticleSet>"""
    v = ab.parse_pubmed_xml(xml)[0]
    assert v["ano"] == 2001 and v["doi"] == "10.1006/meth.2001.1262"
    assert v["primeiro_autor"] == "Livak KJ" and v["n_autores"] == 2
    assert v["titulo"].startswith("Analysis of relative") and "real-time" in v["titulo"]
    assert v["resumo"] and v["referencias"] and v["acesso_aberto"]
    assert v["citacoes"] is None
    assert ab.parse_pubmed_xml("isto não é xml") == []


# ── Auditoria completa na internet falsa ─────────────────────────────────────────────

def test_auditoria_completa_tudo_confere():
    res = _auditar(_Internet())
    assert not res["interrompido"] and not res["bases_caidas"]
    por_base = {e["base"]: e for e in res["execucoes"]}
    for base, total in (("openalex", 327_499), ("crossref", 6_401_500), ("pubmed", 30_839)):
        e = por_base[base]
        assert e["total_api"] == total
        assert e["blicsa"]["total_declarado"] == total
        assert e["blicsa"]["baixados"] == 25
        assert e["comparacao_total"]["status"] == ab.OK
        assert e["paginacao"]["status"] == ab.OK, e["paginacao"]
        r = e["amostra"]["resumo"]
        assert r["registros"] == 20 and r["nao_encontrados"] == 0, (base, r)
        assert r["pct_aceitavel"] == 100.0, (base, r)
        assert "Encontrados" in e["blicsa"]["trilha"]
    # PubMed: citações não se aplicam
    assert por_base["pubmed"]["amostra"]["resumo"]["por_campo"]["citacoes"][ab.NA] == 20
    assert por_base["datacite"]["total_api"] == 42 and "blicsa" not in por_base["datacite"]
    assert res["duplicatas"] and res["duplicatas"][0]["total_combinado"] == 75

    md = ab.gerar_markdown(res)
    assert "## O que isso significa para a sua pesquisa" in md
    assert "**Os totais batem.**" in md and "**O download é completo.**" in md
    assert "Crossref e resumos" in md and "PubMed só cobre biomedicina" in md
    assert "Google Scholar" in md
    for nome in ("## OpenAlex", "## Crossref", "## PubMed", "## DataCite"):
        assert nome in md
    assert "| Título |" in md and "Suspeitas encontradas lendo o código" in md


def test_total_divergente_e_campo_errado_aparecem_no_relatorio():
    def estragar(w):
        w["cited_by_count"] = int(w.get("cited_by_count") or 0) * 2 + 500
        return w
    res = _auditar(_Internet(total_openalex_direto=999_999, alterar_openalex=estragar),
                   bases=("openalex",))
    e = res["execucoes"][0]
    assert e["comparacao_total"]["status"] == ab.ERRADO
    pc = e["amostra"]["resumo"]["por_campo"]["citacoes"]
    assert pc[ab.ERRADO] == 20 and pc["pct_ok"] == 0
    md = ab.gerar_markdown(res)
    assert "Atenção — total divergente" in md and "**ERRADO**" in md


def test_base_indisponivel_e_registrada_e_as_outras_seguem():
    chamadas = []

    def executor(base, *a, **kw):
        chamadas.append(base)
        return ab.rodar_blicsa(base, *a, **kw)

    inicio = time.perf_counter()
    res = _auditar(_Internet(fora={"eutils.ncbi.nlm.nih.gov"}), executor=executor)
    assert time.perf_counter() - inicio < 30
    assert "pubmed" in res["bases_caidas"]
    assert "pubmed" not in chamadas, "base caída não pode rodar a busca do Blicsa (travaria)"
    por_base = {e["base"]: e for e in res["execucoes"]}
    assert por_base["pubmed"]["status"] == "indisponível"
    assert por_base["openalex"]["amostra"]["resumo"]["pct_aceitavel"] == 100.0
    md = ab.gerar_markdown(res)
    assert "**Indisponível:**" in md and "Não deu para conferir PubMed" in md


def test_todas_as_bases_fora_do_ar_gera_relatorio(tmp_path):
    def sem_rede(url, headers, timeout):
        raise urllib.error.URLError("simulado: sem rede")
    inicio = time.perf_counter()
    rc = ab.main(["--saida", str(tmp_path), "--email", "a@b.c", "--consulta", "x",
                  "--consulta", "y"], abrir=sem_rede)
    assert rc == 0
    assert time.perf_counter() - inicio < 10
    mds = list(tmp_path.glob("auditoria_bases_*.md"))
    jss = list(tmp_path.glob("auditoria_bases_*.json"))
    assert len(mds) == 1 and len(jss) == 1
    md = mds[0].read_text(encoding="utf-8")
    assert md.count("**Indisponível:**") == 4
    dados = json.loads(jss[0].read_text(encoding="utf-8"))
    assert set(dados["bases_caidas"]) == {"openalex", "crossref", "pubmed", "datacite"}
    assert all(e["status"] == "indisponível" for e in dados["execucoes"])


def test_ctrl_c_salva_o_parcial(tmp_path):
    def executor(base, *a, **kw):
        if base == "crossref":
            raise KeyboardInterrupt
        return ab.rodar_blicsa(base, *a, **kw)
    res = _auditar(_Internet(), executor=executor)
    assert res["interrompido"] and "Crossref" in res["onde_parou"]
    assert res["execucoes"][0]["base"] == "openalex" and "blicsa" in res["execucoes"][0]
    assert res["execucoes"][-1]["status"] == "interrompido"
    md, js = ab.salvar(res, tmp_path)
    assert "INTERROMPIDA" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["interrompido"] is True


def test_erro_no_codigo_do_blicsa_nao_derruba_a_auditoria():
    def executor(base, *a, **kw):
        raise RuntimeError("quebrou")
    res = _auditar(_Internet(), bases=("openalex", "crossref"), executor=executor)
    assert [e["status"] for e in res["execucoes"]] == ["erro no Blicsa"] * 2
    ab.gerar_markdown(res)


def test_retry_com_backoff_e_retry_after():
    esperas = []
    falhas = [urllib.error.HTTPError("u", 503, "x", {}, None),
              urllib.error.HTTPError("u", 429, "x", {"Retry-After": "4"}, None)]

    def abrir(url, h, t):
        if falhas:
            raise falhas.pop(0)
        return '{"ok": 1}'
    c = ab.HttpCliente("a@b.c", abrir=abrir, dormir=esperas.append, espera_inicial=0.5)
    assert c.get_json("https://exemplo.org/x") == {"ok": 1}
    assert esperas == [0.5, 4.0]
    c2 = ab.HttpCliente("a@b.c", dormir=lambda s: None,
                        abrir=lambda u, h, t: (_ for _ in ()).throw(
                            urllib.error.HTTPError(u, 403, "x", {}, None)))
    with pytest.raises(ab.FalhaDeRede):
        c2.get_texto("https://exemplo.org/y")


def test_duplicatas_entre_bases_tratadas_pela_dedup():
    oa = [{"title": "Patent grace periods and innovation", "doi": "https://doi.org/10.1/AB",
           "year": 2020, "authors": "Silva J", "origin": "OpenAlex"},
          {"title": "Outro artigo qualquer", "doi": "https://doi.org/10.1/zz",
           "year": 2019, "authors": "Lima P", "origin": "OpenAlex"}]
    cr = [{"title": "Patent Grace Periods and Innovation.", "doi": "10.1/ab",
           "year": 2020, "authors": "Silva João", "origin": "Crossref"}]
    d = ab.duplicatas_entre_bases({"openalex": oa, "crossref": cr})
    assert d["dois_em_mais_de_uma_base"] == 1 and d["tratados"] == 1
    assert d["por_par"] == {"Crossref + OpenAlex": 1}
    assert d["apos_dedup"] == 2 and d["pares_entre_bases_por_motivo"] == {"doi": 1}
    assert ab.duplicatas_dentro(oa + [dict(oa[0])]) == 1
    assert ab.apos_dedup(oa + cr)[0] == 2


# ── Bugs corrigidos durante a auditoria ──────────────────────────────────────────────

def test_pubmed_doi_so_no_aid_e_pii_nao_vira_doi():
    from core.sources.pubmed import PubMedProvider
    p = PubMedProvider(api_key="")
    r = p._record_from_medline({"TI": "x", "LID": "S0140-6736(20)30183-5 [pii]",
                                "AID": "S0140-6736(20)30183-5 [pii]; 10.1016/S0140-6736(20)30183-5 [doi]"})
    assert r["doi"] == "10.1016/S0140-6736(20)30183-5"
    r = p._record_from_medline({"TI": "x", "LID": "S0140-6736(20)30183-5 [pii]"})
    assert r["doi"] == ""
    r = p._record_from_medline({"TI": "x", "LID": "10.1/abc [doi]; S01 [pii]"})
    assert r["doi"] == "10.1/abc"


def test_crossref_autor_institucional_nao_some():
    from core.sources import CrossrefProvider
    item = {"title": ["T"], "DOI": "10.1/x", "issued": {"date-parts": [[2020]]},
            "author": [{"name": "WHO Collaborating Group"}, {"family": "Shane", "given": "Scott"}]}
    corpo = json.dumps({"message": {"total-results": 1, "items": [item], "next-cursor": None}})
    with serve(corpo):
        rec = list(CrossrefProvider().search("x", max_results=1))[0]
    assert rec["authors"] == "WHO Collaborating Group; Shane Scott"
    assert CrossrefProvider()._normalize_item(item)["authors"] == rec["authors"]


@pytest.mark.parametrize("filtros", [{"year_start": 2018}, {"year_end": 2010},
                                     {"is_oa": True}, {"year_start": 2015, "year_end": 2020}])
def test_pubmed_count_browse_e_search_usam_o_mesmo_termo(filtros):
    from core.sources import PubMedProvider
    vazio = json.dumps({"esearchresult": {"count": "0", "idlist": []}})
    termos = []
    for chamar in (lambda p: p.count("q", filtros),
                   lambda p: p.browse("q", filtros),
                   lambda p: list(p.search("q", filtros, max_results=5))):
        with serve(vazio) as rec:
            chamar(PubMedProvider(api_key=""))
        termos.append(urllib.parse.parse_qs(urllib.parse.urlparse(rec.calls[0]).query)["term"][0])
    assert termos[0] == termos[1] == termos[2], termos
    assert termos[0] != "q"
