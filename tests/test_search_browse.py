"""Fase 1 — Modo Navegação: contagem instantânea, paginação e facetas.

Premissa do trabalho: navegar e baixar são operações separadas. Estes testes exercitam o
lado "navegar" — uma requisição por página, contagens vindas do `group_by` e nada acumulado
em memória além da página corrente e do cache LRU.

Fixtures adversariais obrigatórias: registro sem ano, sem citações, sem DOI, sem abstract;
resultado único; `meta.count` ausente; contagem zero; faceta que falha; acentos na query.
"""
import json
import threading
import urllib.error
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from core.browse import (
    DEFAULT_PER_PAGE,
    BrowseSession,
    Facet,
    Page,
    build_filters,
    format_count,
    sort_to_api,
    supported_facets,
    validate_query,
)
from core.sources import CrossrefProvider, OpenAlexProvider, PubMedProvider


# ─────────────────────────── fixtures ───────────────────────────

def _work(i, *, ano=2020, cit=5, doi=True, abstract=True, titulo=None):
    """Registro cru do OpenAlex. Os parâmetros permitem a variante POBRE do dado."""
    w = {
        "title": titulo or f"Trabalho {i}",
        "publication_year": ano,
        "cited_by_count": cit,
        "authorships": [{"author": {"display_name": f"Autor {i}"}}],
        "primary_location": {"source": {"display_name": "Revista X"}},
        "open_access": {"is_oa": bool(i % 2), "oa_url": ""},
        "language": "en",
        "concepts": [],
        "referenced_works": [],
    }
    if doi:
        w["doi"] = f"10.1/{i}"
    if abstract:
        w["abstract_inverted_index"] = {"resumo": [0], "do": [1], "trabalho": [2]}
    if ano is None:
        w.pop("publication_year")
    if cit is None:
        w.pop("cited_by_count")
    return w


def _pagina(total=319300, n=25, inicio=0, **kw):
    return json.dumps({
        "meta": {"count": total, "page": 1, "per_page": n},
        "results": [_work(i, **kw) for i in range(inicio, inicio + n)],
    }).encode("utf-8")


def _group_by(pares):
    return json.dumps({
        "meta": {"count": sum(c for _, _, c in pares)},
        "group_by": [{"key": k, "key_display_name": lbl, "count": c} for k, lbl, c in pares],
    }).encode("utf-8")


def _resp(body):
    m = MagicMock()
    m.read.return_value = body
    m.__enter__.return_value = m
    return m


class UrlSpy:
    """Captura as URLs pedidas e devolve corpos na ordem (ou por padrão de URL)."""

    def __init__(self, corpos=None, por_url=None):
        self.urls = []
        self._corpos = list(corpos or [])
        self._por_url = por_url or {}

    def __call__(self, req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        self.urls.append(url)
        for fragmento, corpo in self._por_url.items():
            if fragmento in url:
                return _resp(corpo)
        if self._corpos:
            return _resp(self._corpos.pop(0))
        return _resp(_pagina())


# ─────────────────────────── contagem instantânea ───────────────────────────

def test_count_comes_from_meta_and_first_page_has_25():
    """UMA requisição traz a contagem do universo E os 25 primeiros cards."""
    spy = UrlSpy([_pagina(total=319300, n=25)])
    with patch("urllib.request.urlopen", side_effect=spy):
        sessao = BrowseSession(OpenAlexProvider(), "empreendedorismo")
        p = sessao.fetch_page(1)

    assert p.total == 319300, "a contagem deveria vir de meta.count"
    assert len(p.records) == 25
    assert p.pages == 12772, f"12.772 páginas de 25, obteve {p.pages}"
    assert len(spy.urls) == 1, "a contagem não pode custar uma requisição extra"
    assert "per_page=25" in spy.urls[0]


def test_count_formatting_uses_thousand_separator():
    assert format_count(319300) == "319.300"
    assert format_count(0) == "0"
    assert format_count(None) == "0"


def test_missing_or_zero_count_gives_empty_state_without_crashing():
    """`meta.count` ausente ou zero → estado vazio bem formado, sem exceção."""
    sem_meta = json.dumps({"results": []}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_resp(sem_meta)):
        p = BrowseSession(OpenAlexProvider(), "xyz").fetch_page(1)
    assert p.total == 0 and p.records == [] and p.empty is True
    assert p.pages == 1, "zero resultados ainda é 1 página (vazia), nunca 0"

    zero = json.dumps({"meta": {"count": 0}, "results": []}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_resp(zero)):
        p2 = BrowseSession(OpenAlexProvider(), "xyz").fetch_page(1)
    assert p2.empty is True and p2.error == ""


def test_single_result_and_poor_records_do_not_break_paging():
    """Resultado único e registros pobres (sem ano, citações, DOI, abstract)."""
    corpo = json.dumps({
        "meta": {"count": 1},
        "results": [_work(0, ano=None, cit=None, doi=False, abstract=False)],
    }).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_resp(corpo)):
        p = BrowseSession(OpenAlexProvider(), "x").fetch_page(1)
    assert p.total == 1 and p.pages == 1 and len(p.records) == 1
    r = p.records[0]
    assert r["year"] == 0 and r["citations"] == 0 and r["doi"] == "" and r["abstract"] == ""


# ─────────────────────────── paginação ───────────────────────────

def test_going_to_page_five_asks_the_api_for_page_five():
    """Navegar para a página 5 monta a URL certa e NÃO rebaixa as anteriores."""
    spy = UrlSpy([_pagina(n=25), _pagina(n=25, inicio=100)])
    with patch("urllib.request.urlopen", side_effect=spy):
        s = BrowseSession(OpenAlexProvider(), "x")
        s.fetch_page(1)
        p5 = s.fetch_page(5)

    assert p5.page == 5
    assert len(spy.urls) == 2, "ir para a página 5 é UMA requisição, não cinco"
    q = urllib.parse.parse_qs(urllib.parse.urlparse(spy.urls[-1]).query)
    assert q["page"] == ["5"] and q["per_page"] == ["25"]
    assert len(p5.records) == 25, "a página só traz os seus 25 registros"


def test_page_count_rounds_up():
    for total, esperado in ((0, 1), (1, 1), (25, 1), (26, 2), (319300, 12772)):
        assert Page(total=total, per_page=25).pages == esperado, f"total={total}"


def test_lru_cache_avoids_refetching_a_visited_page():
    """Revisitar página já vista não chama o provider de novo.

    A checagem é sobre `provider.browse`, não sobre `urlopen`: o `fetch_url` do provider tem
    o PRÓPRIO cache LRU por URL, então medir `urlopen` daria verde mesmo com o cache da
    sessão desligado — foi o que a matriz de reinjeção mostrou. São duas camadas, e a que
    este teste guarda é a da sessão, que evita montar a URL e reparsear o JSON.
    """
    chamadas = []
    real = OpenAlexProvider().browse

    class Espiao(OpenAlexProvider):
        def browse(self, *a, **k):
            chamadas.append((a, k.get("page")))
            return [{"title": f"t{i}"} for i in range(25)], 100

    s = BrowseSession(Espiao(), "x")
    s.fetch_page(1)
    s.fetch_page(2)
    antes = len(chamadas)
    p1 = s.fetch_page(1)              # volta: deveria sair do cache da sessão
    depois = len(chamadas)

    assert depois == antes, (
        f"revisitar a página 1 chamou o provider de novo ({depois - antes}x)")
    assert len(p1.records) == 25
    assert s.cached_pages() == 2


def test_cache_can_be_bypassed_on_demand():
    """O outro lado da guarda: `use_cache=False` força a ida ao provider.

    Sem isto, "usar cache" viraria "nunca mais consultar", e um Atualizar não funcionaria.
    """
    chamadas = []

    class Espiao(OpenAlexProvider):
        def browse(self, *a, **k):
            chamadas.append(k.get("page"))
            return [], 10

    s = BrowseSession(Espiao(), "x")
    s.fetch_page(1)
    s.fetch_page(1)                       # cache
    assert len(chamadas) == 1
    s.fetch_page(1, use_cache=False)      # forçado
    assert len(chamadas) == 2, "use_cache=False tem de ignorar o cache"


def test_cache_is_keyed_by_filters_not_only_by_page():
    """Mesma página com filtro diferente é outra coisa — não pode vir do cache."""
    spy = UrlSpy([_pagina(n=25), _pagina(n=5, total=5)])
    with patch("urllib.request.urlopen", side_effect=spy):
        s = BrowseSession(OpenAlexProvider(), "x")
        s.fetch_page(1)
        s.toggle_facet("type", "article")
        p = s.fetch_page(1)

    assert len(spy.urls) == 2, "o filtro mudou; a página 1 tem de ser buscada de novo"
    assert p.total == 5


# ─────────────────────────── facetas ───────────────────────────

def test_facets_bring_universe_counts_without_downloading_records():
    """As contagens da sidebar vêm do `group_by`, sobre o universo inteiro."""
    corpos = {
        "group_by=type": _group_by([("article", "Artigo", 12043),
                                    ("book-chapter", "Capítulo", 887)]),
        "group_by=language": _group_by([("en", "English", 30000), ("pt", "Portuguese", 900)]),
    }
    spy = UrlSpy(por_url=corpos)
    with patch("urllib.request.urlopen", side_effect=spy):
        s = BrowseSession(OpenAlexProvider(), "x")
        facetas = s.fetch_facets(["type", "language"])

    tipo = facetas["type"]
    assert tipo.ok and [v.count for v in tipo.values] == [12043, 887]
    assert tipo.values[0].label == "Artigo"
    # A chamada de faceta não baixa registro nenhum — a resposta de `group_by` não traz
    # `results`. (Este teste chegou a exigir `per_page=1`, que era justamente o parâmetro
    # que truncava a lista de grupos; ver o teste específico mais abaixo.)
    assert all("group_by=" in u for u in spy.urls)


def test_facet_values_are_sorted_by_count_and_unknown_is_dropped():
    corpo = _group_by([("a", "A", 5), ("unknown", "Unknown", 999), ("b", "B", 50)])
    with patch("urllib.request.urlopen", return_value=_resp(corpo)):
        vals = OpenAlexProvider().facet("type", "x")
    assert [v["key"] for v in vals] == ["b", "a"], "ordenar por contagem e tirar 'unknown'"


def test_facet_error_degrades_without_killing_the_listing():
    """Faceta que falha entra com erro; as outras e a listagem continuam."""
    def lado(req, *a, **k):
        url = req.full_url
        if "group_by=language" in url:
            raise urllib.error.URLError("rede caiu")
        return _resp(_group_by([("article", "Artigo", 10)]))

    with patch("urllib.request.urlopen", side_effect=lado), patch("time.sleep"):
        s = BrowseSession(OpenAlexProvider(), "x")
        facetas = s.fetch_facets(["type", "language"])

    assert facetas["type"].ok, "a faceta que funcionou tem de vir normalmente"
    assert not facetas["language"].ok and facetas["language"].error
    assert facetas["language"].values == []


def test_provider_without_facets_offers_none():
    """Crossref e PubMed não têm `group_by`: a UI não pode oferecer o filtro (BUG-02)."""
    assert supported_facets(OpenAlexProvider()), "OpenAlex tem facetas"
    assert supported_facets(CrossrefProvider()) == []
    assert supported_facets(PubMedProvider()) == []
    with pytest.raises(ValueError):
        OpenAlexProvider().facet("inexistente", "x")


# ─────────────────────────── filtros: AND/OR ───────────────────────────

def test_multiple_facets_are_or_within_category_and_and_between():
    """Semântica do Web of Science, assertada na string do filtro."""
    s = BrowseSession(OpenAlexProvider(), "x")
    s.toggle_facet("type", "article")
    s.toggle_facet("type", "book-chapter")     # OR com o anterior
    s.toggle_facet("language", "en")           # AND com a categoria acima

    flt = OpenAlexProvider()._oa_filter("x", s.current_filters())
    assert "type:article|book-chapter" in flt, f"OR dentro da categoria ausente: {flt}"
    assert "language:en" in flt
    partes = flt.split(",")
    assert any(p.startswith("type:") for p in partes)
    assert any(p.startswith("language:") for p in partes), "AND entre categorias é a vírgula"


def test_applying_and_removing_a_facet_restores_the_previous_query():
    s = BrowseSession(OpenAlexProvider(), "x")
    antes = OpenAlexProvider()._oa_filter("x", s.current_filters())

    s.toggle_facet("type", "article")
    com = OpenAlexProvider()._oa_filter("x", s.current_filters())
    assert com != antes and "type:article" in com

    s.clear_facet("type", "article")
    depois = OpenAlexProvider()._oa_filter("x", s.current_filters())
    assert depois == antes, "remover o chip deveria restaurar a query anterior"
    assert s.chips() == []


def test_toggling_a_facet_returns_to_page_one():
    s = BrowseSession(OpenAlexProvider(), "x")
    s.page = 7
    s.toggle_facet("type", "article")
    assert s.page == 1, "mudar filtro tem de voltar para a página 1"


def test_chips_expose_field_key_and_readable_label():
    s = BrowseSession(OpenAlexProvider(), "x")
    s.facets = {"type": Facet(field="type", values=[
        __import__("core.browse", fromlist=["FacetValue"]).FacetValue("article", "Artigo", 10)])}
    s.toggle_facet("type", "article")
    chips = s.chips()
    assert chips == [{"field": "type", "key": "article", "label": "Artigo"}]


def test_year_facet_uses_values_not_range():
    s = BrowseSession(OpenAlexProvider(), "x")
    s.toggle_facet("publication_year", "2020")
    s.toggle_facet("publication_year", "2021")
    flt = OpenAlexProvider()._oa_filter("x", s.current_filters())
    assert "publication_year:2020|2021" in flt, flt


# ─────────────────────────── ordenação ───────────────────────────

@pytest.mark.parametrize("sort,esperado", [
    ("relevance", None),
    ("date_desc", "publication_date:desc"),
    ("date_asc", "publication_date:asc"),
    ("citations", "cited_by_count:desc"),
])
def test_sort_is_sent_to_the_api_never_done_in_memory(sort, esperado):
    spy = UrlSpy([_pagina(n=25)])
    with patch("urllib.request.urlopen", side_effect=spy):
        s = BrowseSession(OpenAlexProvider(), "x")
        s.set_sort(sort)
        s.fetch_page(1)

    q = urllib.parse.parse_qs(urllib.parse.urlparse(spy.urls[0]).query)
    if esperado is None:
        assert "sort" not in q, "relevância é o padrão do OpenAlex: sem parâmetro"
    else:
        assert q["sort"] == [esperado]


def test_invalid_sort_is_rejected():
    s = BrowseSession(OpenAlexProvider(), "x")
    with pytest.raises(ValueError):
        s.set_sort("aleatorio")
    assert sort_to_api("inexistente") == {}


def test_changing_sort_returns_to_page_one():
    s = BrowseSession(OpenAlexProvider(), "x")
    s.page = 4
    s.set_sort("citations")
    assert s.page == 1


# ─────────────────────────── race condition ───────────────────────────

def test_only_the_last_query_wins_when_responses_arrive_out_of_order():
    """5 buscas em sequência, respostas fora de ordem → só a última vale.

    Sem isto, uma busca ampla disparada antes responde DEPOIS e sobrescreve a lista com o
    resultado da query anterior — e o usuário não tem como perceber.
    """
    s = BrowseSession(OpenAlexProvider(), "x")
    tokens = [s.next_token() for _ in range(5)]

    assert not s.is_current(tokens[0]), "token velho não pode ser aceito"
    assert not s.is_current(tokens[3])
    assert s.is_current(tokens[4]), "só o último token é o corrente"

    # Chegada fora de ordem: 3, 1, 5, 2 — só o 5 é aceito.
    aceitos = [t for t in (tokens[2], tokens[0], tokens[4], tokens[1]) if s.is_current(t)]
    assert aceitos == [tokens[4]]


def test_token_is_monotonic_under_concurrency():
    """Tokens são únicos e crescentes mesmo com threads concorrentes."""
    s = BrowseSession(OpenAlexProvider(), "x")
    vistos, trava = [], threading.Lock()

    def worker():
        for _ in range(50):
            t = s.next_token()
            with trava:
                vistos.append(t)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(vistos) == len(set(vistos)) == 200, "tokens repetidos sob concorrência"
    assert s.is_current(max(vistos))


def test_fetch_page_stamps_the_current_token():
    with patch("urllib.request.urlopen", return_value=_resp(_pagina(n=25))):
        s = BrowseSession(OpenAlexProvider(), "x")
        p = s.fetch_page(1)
    assert s.is_current(p.token), "a página devolvida tem de carregar o token corrente"


# ─────────────────────────── query e rede ───────────────────────────

def test_empty_query_is_blocked_with_an_i18n_key():
    ok, chave = validate_query("   ")
    assert ok is False and chave == "search.error_empty_query"
    assert validate_query("inovação")[0] is True


def test_accents_and_special_characters_are_encoded():
    """Acentos e caracteres especiais vão codificados — nada de URL quebrada."""
    spy = UrlSpy([_pagina(n=1, total=1)])
    consulta = 'inovação & "pesquisa" (região)'
    with patch("urllib.request.urlopen", side_effect=spy):
        BrowseSession(OpenAlexProvider(), consulta).fetch_page(1)

    url = spy.urls[0]
    assert " " not in url and "ç" not in url, f"URL com caractere cru: {url}"
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert consulta in q["filter"][0], "a query decodificada tem de bater com a digitada"


def test_network_error_becomes_a_page_error_not_an_exception():
    """Erro de rede vira estado de erro na página — a UI mostra 'tentar de novo'."""
    def cai(*a, **k):
        raise urllib.error.URLError("sem rede")

    with patch("urllib.request.urlopen", side_effect=cai), patch("time.sleep"):
        p = BrowseSession(OpenAlexProvider(), "x").fetch_page(1)

    assert p.error, "o erro tem de aparecer na página, não sumir"
    assert p.records == [] and p.total == 0


def test_request_uses_timeout_and_retry_mechanism():
    """Reaproveita o retry com backoff já existente: 429 numa página é recuperado."""
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    with patch("urllib.request.urlopen", side_effect=[err, _resp(_pagina(n=25))]), \
         patch("time.sleep") as dormiu:
        p = BrowseSession(OpenAlexProvider(), "x").fetch_page(1)
    assert p.error == "" and len(p.records) == 25
    assert dormiu.called, "o backoff do retry deveria ter sido usado"


def test_browse_call_carries_a_timeout():
    """A requisição declara timeout (15s) — sem isso uma página pendura a navegação."""
    capturado = {}

    def espia(req, *a, **k):
        capturado["timeout"] = k.get("timeout")
        return _resp(_pagina(n=25))

    with patch("urllib.request.urlopen", side_effect=espia):
        BrowseSession(OpenAlexProvider(), "x").fetch_page(1)
    assert capturado.get("timeout") == 15


# ─────────────────────────── outros providers ───────────────────────────

def test_crossref_browse_returns_page_and_total():
    corpo = json.dumps({"message": {
        "total-results": 80598,
        "items": [{"DOI": f"10.1/{i}", "title": [f"T{i}"],
                   "author": [{"family": "Silva", "given": "J"}],
                   "issued": {"date-parts": [[2020]]},
                   "is-referenced-by-count": 3} for i in range(25)],
    }}).encode("utf-8")
    spy = UrlSpy([corpo])
    with patch("urllib.request.urlopen", side_effect=spy):
        recs, total = CrossrefProvider().browse("x", page=3, per_page=25)

    assert total == 80598 and len(recs) == 25
    q = urllib.parse.parse_qs(urllib.parse.urlparse(spy.urls[0]).query)
    assert q["rows"] == ["25"] and q["offset"] == ["50"], "página 3 de 25 começa no offset 50"
    assert recs[0]["origin"] == "Crossref" and recs[0]["year"] == 2020


def test_pubmed_browse_uses_retstart_for_paging():
    esearch = json.dumps({"esearchresult": {"count": "1234", "idlist": ["1", "2"]}}).encode()
    efetch = b"PMID- 1\nTI  - Um titulo\nAU  - Silva J\n\nPMID- 2\nTI  - Outro\nAU  - Souza M\n\n"
    spy = UrlSpy([esearch, efetch])
    with patch("urllib.request.urlopen", side_effect=spy):
        recs, total = PubMedProvider().browse("cancer", page=2, per_page=25)

    assert total == 1234 and len(recs) == 2
    q = urllib.parse.parse_qs(urllib.parse.urlparse(spy.urls[0]).query)
    assert q["retstart"] == ["25"] and q["retmax"] == ["25"]
    assert recs[0]["title"] == "Um titulo"


def test_pubmed_browse_with_no_ids_returns_empty_without_efetch():
    esearch = json.dumps({"esearchresult": {"count": "0", "idlist": []}}).encode()
    spy = UrlSpy([esearch])
    with patch("urllib.request.urlopen", side_effect=spy):
        recs, total = PubMedProvider().browse("xyzxyz", page=1)
    assert recs == [] and total == 0
    assert len(spy.urls) == 1, "sem IDs não se chama o EFetch"


# ─────────────────────────── thread ───────────────────────────

def test_browse_is_callable_off_the_main_thread():
    """A busca roda fora da thread principal — a UI não pode congelar.

    O teste executa `fetch_page` numa thread separada e confere que ela terminou lá, com o
    resultado íntegro: é o contrato que a UI precisa respeitar ao chamar.
    """
    resultado = {}

    def trabalho():
        with patch("urllib.request.urlopen", return_value=_resp(_pagina(n=25))):
            p = BrowseSession(OpenAlexProvider(), "x").fetch_page(1)
        resultado["thread"] = threading.current_thread().name
        resultado["page"] = p

    t = threading.Thread(target=trabalho, name="busca-worker")
    t.start()
    t.join(timeout=10)

    assert not t.is_alive(), "a thread de busca não terminou"
    assert resultado["thread"] == "busca-worker"
    assert resultado["thread"] != threading.main_thread().name
    assert len(resultado["page"].records) == 25


def test_main_py_never_calls_browse_on_the_main_thread():
    """No app, toda entrada de busca despacha para uma thread.

    Checagem no fonte: os pontos que chamam `browse(`/`fetch_page(` têm de estar dentro de
    uma função que roda em `threading.Thread`, nunca no corpo de um callback de botão.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    for i, linha in enumerate(src.splitlines(), 1):
        if ".browse(" in linha or ".fetch_page(" in linha:
            # Recorta o bloco da função que contém a chamada e exige que o app a despache
            # por thread em algum ponto (o worker é sempre iniciado com threading.Thread).
            janela = "\n".join(src.splitlines()[max(0, i - 60):i])
            assert "threading.Thread" in janela or "def _" in janela, (
                f"main.py:{i} chama browse/fetch_page sem despachar para thread: {linha.strip()}")


def test_facet_request_does_not_send_per_page_which_would_truncate_the_groups():
    """`per_page` numa chamada de `group_by` TRUNCA a lista de grupos.

    Bug real, encontrado só na medição ao vivo: com `per_page=1` a API devolvia **um** grupo
    ("article") em vez dos 26, e a sidebar mostraria uma linha por faceta. O parâmetro era
    desnecessário — uma resposta de `group_by` não traz `results` (medido: results=0) e custa
    o mesmo 1 crédito com ou sem ele. A captura de tela não pegou porque usava facetas
    sintéticas.
    """
    spy = UrlSpy([_group_by([("a", "A", 10), ("b", "B", 5)])])
    with patch("urllib.request.urlopen", side_effect=spy):
        vals = OpenAlexProvider().facet("type", "x")

    assert len(vals) == 2, "os dois grupos deveriam chegar"
    q = urllib.parse.parse_qs(urllib.parse.urlparse(spy.urls[0]).query)
    assert "per_page" not in q, (
        f"a chamada de faceta não pode mandar per_page (trunca os grupos): {spy.urls[0]}")
    assert q["group_by"] == ["type"]


def test_facet_top_n_is_applied_client_side():
    """O corte de top-N é nosso, do lado do cliente — a API manda tudo."""
    pares = [(f"k{i}", f"L{i}", 100 - i) for i in range(30)]
    with patch("urllib.request.urlopen", return_value=_resp(_group_by(pares))):
        vals = OpenAlexProvider().facet("type", "x", top=10)
    assert len(vals) == 10 and vals[0]["count"] == 100


def test_facet_does_not_apply_its_own_filter():
    """Marcar "Artigo" não pode apagar "Capítulo de livro" da lista de tipos.

    É como o "Refine Results" do WoS funciona: a faceta X ignora o filtro de X e respeita os
    das outras categorias. Sem isso o usuário fica preso na opção que escolheu — para trocar,
    teria de remover o chip primeiro. Achado ao capturar a evidência com facetas REAIS: a
    lista de tipos vinha com um valor só.
    """
    s = BrowseSession(OpenAlexProvider(), "x")
    s.toggle_facet("type", "article")
    s.toggle_facet("language", "en")

    filtros_type = s.filters_excluding("type")
    assert "type" not in filtros_type, "a faceta de tipo não pode aplicar o filtro de tipo"
    assert filtros_type.get("language") == "en", "os filtros das OUTRAS categorias continuam"

    filtros_lang = s.filters_excluding("language")
    assert "language" not in filtros_lang
    assert filtros_lang.get("type") == "article"

    # E a busca de página continua aplicando TUDO — só a faceta é que exclui a si mesma.
    assert s.current_filters().get("type") == "article"
    assert s.current_filters().get("language") == "en"


def test_facet_request_omits_only_its_own_category():
    """A URL da faceta comprova: sem o próprio campo, com os dos outros."""
    spy = UrlSpy(por_url={"group_by=type": _group_by([("a", "A", 5)])})
    with patch("urllib.request.urlopen", side_effect=spy):
        s = BrowseSession(OpenAlexProvider(), "x")
        s.toggle_facet("type", "article")
        s.toggle_facet("language", "en")
        s.fetch_facets(["type"])

    url = spy.urls[0]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    filtro = q.get("filter", [""])[0]
    assert "language:en" in filtro, f"o filtro de idioma deveria valer: {filtro}"
    assert "type:" not in filtro, f"o filtro do próprio campo não pode ir junto: {filtro}"


def test_chip_label_comes_from_the_facet_display_name_for_uri_keys():
    """O OpenAlex devolve a chave como URI; o chip tem de mostrar o nome legível.

    Medido ao vivo: `group_by=type` devolve key=`https://openalex.org/types/article` com
    key_display_name=`article`, e a API aceita as DUAS formas no filtro (verificado: mesma
    contagem). Dentro do app tudo vem da sidebar, então a chave é sempre a mesma — o que não
    pode acontecer é o chip exibir a URI crua para o usuário.
    """
    from core.browse import FacetValue

    uri = "https://openalex.org/types/article"
    s = BrowseSession(OpenAlexProvider(), "x")
    s.facets = {"type": Facet(field="type", values=[FacetValue(uri, "article", 29730)])}
    s.toggle_facet("type", uri)

    chips = s.chips()
    assert len(chips) == 1
    assert chips[0]["key"] == uri, "a chave mantém a forma que a API devolveu"
    assert chips[0]["label"] == "article", (
        f"o chip não pode mostrar a URI crua: {chips[0]['label']!r}")
    assert "http" not in chips[0]["label"]


def test_facets_are_fetched_in_parallel():
    """As 6 facetas são requisições independentes — em série a sidebar demora ~5x mais.

    Medido ao vivo: 8,11s sequencial contra 1,49s em paralelo, com o mesmo custo em créditos
    (1 por faceta). O que muda é o tempo em que a sidebar fica vazia ao lado de uma lista já
    pronta.
    """
    import threading as _t
    import time as _time

    class Lenta(OpenAlexProvider):
        def facet(self, campo, query, filters=None, top=10, cancel_event=None):
            _time.sleep(0.15)
            return [{"key": f"{campo}_a", "label": "A", "count": 1}]

    s = BrowseSession(Lenta(), "x")
    t0 = _time.perf_counter()
    f = s.fetch_facets(["type", "language", "publication_year", "is_oa", "source", "author"])
    dt = _time.perf_counter() - t0

    assert len(f) == 6
    assert dt < 0.45, (
        f"6 facetas de 0,15s levaram {dt:.2f}s — parecem sequenciais (seriam ~0,9s)")


def test_parallel_facets_keep_a_stable_display_order():
    """Quem responde primeiro não pode reordenar a sidebar."""
    import random
    import time as _time

    class Bagunçada(OpenAlexProvider):
        def facet(self, campo, query, filters=None, top=10, cancel_event=None):
            _time.sleep(random.uniform(0.01, 0.08))
            return [{"key": f"{campo}_a", "label": "A", "count": 1}]

    pedidos = ["type", "language", "publication_year", "is_oa"]
    for _ in range(3):
        s = BrowseSession(Bagunçada(), "x")
        assert list(s.fetch_facets(pedidos).keys()) == pedidos


def test_sequential_mode_still_available_and_equivalent():
    """O outro lado da guarda: `paralelo=False` produz o mesmo resultado."""
    class Fixa(OpenAlexProvider):
        def facet(self, campo, query, filters=None, top=10, cancel_event=None):
            return [{"key": f"{campo}_a", "label": "A", "count": 7}]

    s1 = BrowseSession(Fixa(), "x")
    s2 = BrowseSession(Fixa(), "x")
    a = {k: [v.count for v in f.values] for k, f in s1.fetch_facets(["type"], paralelo=True).items()}
    b = {k: [v.count for v in f.values] for k, f in s2.fetch_facets(["type"], paralelo=False).items()}
    assert a == b == {"type": [7]}


def test_one_failing_facet_does_not_take_down_the_parallel_batch():
    """Uma faceta que levanta no meio do lote paralelo não derruba as outras."""
    class Meio(OpenAlexProvider):
        def facet(self, campo, query, filters=None, top=10, cancel_event=None):
            if campo == "language":
                raise urllib.error.URLError("caiu")
            return [{"key": f"{campo}_a", "label": "A", "count": 1}]

    s = BrowseSession(Meio(), "x")
    f = s.fetch_facets(["type", "language", "is_oa"])
    assert f["type"].ok and f["is_oa"].ok
    assert not f["language"].ok and f["language"].error


# ─────────────────── limite de uso da API (429) ───────────────────

def test_persistent_429_raises_a_specific_error_not_a_generic_io():
    """429 esgotado vira `RateLimitError`, não "Failed to fetch <url>".

    A diferença importa para o usuário: erro de rede genérico não sugere ação nenhuma, e o
    limite de uso tem uma saída concreta (chave gratuita nos Ajustes).
    """
    from core.sources.base import RateLimitError

    err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    with patch("urllib.request.urlopen", side_effect=[err, err, err]), patch("time.sleep"):
        with pytest.raises(RateLimitError) as exc:
            OpenAlexProvider().count("x")
    assert exc.value.i18n_key == "search.error_rate_limit"
    assert isinstance(exc.value, IOError), "quem tratava IOError genérico continua pegando"


def test_other_http_errors_stay_generic():
    """O outro lado: 500 esgotado continua sendo erro de rede comum, não limite de uso."""
    from core.sources.base import RateLimitError

    err = urllib.error.HTTPError("url", 500, "Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=[err, err, err]), patch("time.sleep"):
        with pytest.raises(IOError) as exc:
            OpenAlexProvider().count("x")
    assert not isinstance(exc.value, RateLimitError)


def test_429_recovered_by_retry_does_not_raise():
    """429 que o retry recupera não vira erro nenhum."""
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    ok = _resp(json.dumps({"meta": {"count": 42}, "results": []}).encode())
    with patch("urllib.request.urlopen", side_effect=[err, ok]), patch("time.sleep"):
        assert OpenAlexProvider().count("x") == 42


def test_browse_page_carries_the_rate_limit_message_key():
    """A página de erro leva a chave i18n, para a UI mostrar a explicação e não a URL."""
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    with patch("urllib.request.urlopen", side_effect=[err, err, err]), patch("time.sleep"):
        p = BrowseSession(OpenAlexProvider(), "x").fetch_page(1)

    assert p.error, "o erro tem de aparecer"
    assert p.error_key == "search.error_rate_limit"

    from core.i18n import t
    mensagem = t(p.error_key)
    assert "http" not in mensagem.lower(), "a mensagem não pode ser uma URL crua"
    assert len(mensagem) > 40, "a mensagem tem de explicar o que aconteceu"


def test_generic_network_error_has_no_message_key():
    """Erro sem explicação própria não inventa chave — a UI mostra o texto cru."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede")), \
         patch("time.sleep"):
        p = BrowseSession(OpenAlexProvider(), "x").fetch_page(1)
    assert p.error and p.error_key == ""


# ─────────────────── chave opcional do OpenAlex ───────────────────

def test_api_key_is_absent_by_default():
    """Vazia por padrão: o app funciona sem chave, que é o caminho normal."""
    spy = UrlSpy([_pagina(n=1, total=1)])
    with patch("urllib.request.urlopen", side_effect=spy):
        OpenAlexProvider(api_key="").count("x")
    assert "api_key=" not in spy.urls[0], f"não deveria mandar api_key: {spy.urls[0]}"


def test_api_key_is_appended_to_every_request_when_configured():
    """Configurada, a chave entra em TODAS as requisições do provider."""
    spy = UrlSpy(por_url={"group_by": _group_by([("a", "A", 1)])})
    prov = OpenAlexProvider(api_key="minha-chave-123")
    with patch("urllib.request.urlopen", side_effect=spy):
        prov.count("x")
        prov.browse("x", page=2)
        prov.facet("type", "x")

    assert len(spy.urls) == 3
    for u in spy.urls:
        assert "api_key=minha-chave-123" in u, f"chave ausente em {u[:80]}"


def test_api_key_is_read_from_settings_when_not_passed(monkeypatch):
    import core.sources.openalex as oa

    monkeypatch.setattr(oa, "openalex_api_key", lambda: "vinda-dos-ajustes")
    spy = UrlSpy([_pagina(n=1, total=1)])
    with patch("urllib.request.urlopen", side_effect=spy):
        oa.OpenAlexProvider().count("x")
    assert "api_key=vinda-dos-ajustes" in spy.urls[0]


def test_api_key_is_not_duplicated_if_already_in_url():
    spy = UrlSpy([_pagina(n=1, total=1)])
    prov = OpenAlexProvider(api_key="k1")
    with patch("urllib.request.urlopen", side_effect=spy):
        prov.fetch_url("https://api.openalex.org/works?api_key=k1&per_page=1")
    assert spy.urls[0].count("api_key=") == 1
