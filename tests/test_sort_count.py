"""Ordenação server-side + count barato (aviso de contagem)."""
import json
from unittest.mock import patch, MagicMock

from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider


def _resp(body: str):
    m = MagicMock()
    m.read.return_value = body.encode("utf-8")
    m.__enter__.return_value = m
    return m


def test_openalex_count_one_request():
    body = json.dumps({"meta": {"count": 212340}, "results": [{}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        n = OpenAlexProvider().count("innovation", {"year_start": 2020, "is_oa": True})
    assert n == 212340 and mock.call_count == 1
    url = mock.call_args[0][0].full_url
    assert "per_page=1" in url and "publication_year" in url and "is_oa" in url


def test_openalex_sort_citations_and_date():
    body = json.dumps({"meta": {"count": 1, "next_cursor": None},
                       "results": [{"title": "T", "publication_year": 2020}]})
    for key, expect in [("citations", "cited_by_count%3Adesc"), ("date", "publication_date%3Adesc")]:
        with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
            list(OpenAlexProvider().search("x", filters={"sort": key}, max_results=1))
        assert expect in mock.call_args_list[0][0][0].full_url, key


def test_openalex_sort_relevance_is_default_no_param():
    body = json.dumps({"meta": {"count": 1, "next_cursor": None},
                       "results": [{"title": "T", "publication_year": 2020}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        list(OpenAlexProvider().search("x", filters={"sort": "relevance"}, max_results=1))
    assert "sort=" not in mock.call_args_list[0][0][0].full_url


def test_crossref_sort_citations():
    body = json.dumps({"message": {"total-results": 1, "next-cursor": None,
                                    "items": [{"title": ["T"], "DOI": "10/x"}]}})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        list(CrossrefProvider().search("x", filters={"sort": "citations"}, max_results=1))
    url = mock.call_args_list[0][0][0].full_url
    assert "is-referenced-by-count" in url and "order=desc" in url


def test_pubmed_sort_date():
    es = json.dumps({"esearchresult": {"count": "1", "idlist": ["1"]}})
    ef = "PMID- 1\nTI  - T\nAU  - X\nDP  - 2020\n\n"
    with patch("urllib.request.urlopen", side_effect=[_resp(es), _resp(ef)]) as mock:
        list(PubMedProvider().search("x", filters={"sort": "date"}, max_results=1))
    assert "sort=pub_date" in mock.call_args_list[0][0][0].full_url


def test_sort_key_not_leaked_into_filter():
    """'sort' em filters não pode virar filtro (só parâmetro de ordenação)."""
    body = json.dumps({"meta": {"count": 1, "next_cursor": None},
                       "results": [{"title": "T", "publication_year": 2020}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        list(OpenAlexProvider().search("x", filters={"sort": "citations"}, max_results=1))
    url = mock.call_args_list[0][0][0].full_url
    assert "sort%3A" not in url and "filter=sort" not in url


def test_crossref_count_rows_zero():
    body = json.dumps({"message": {"total-results": 3450869}})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        n = CrossrefProvider().count("saude", {"year_start": 2020})
    assert n == 3450869
    url = mock.call_args[0][0].full_url
    assert "rows=0" in url and "from-pub-date" in url


def test_pubmed_count_retmax_zero():
    body = json.dumps({"esearchresult": {"count": "45231"}})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        n = PubMedProvider().count("saude")
    assert n == 45231
    assert "retmax=0" in mock.call_args[0][0].full_url


def test_browse_field_search_and_paging():
    body = json.dumps({"meta": {"count": 3402}, "results": [
        {"title": "Inovação X", "publication_year": 2023, "cited_by_count": 40,
         "authorships": [{"author": {"display_name": "Silva"}}], "doi": "10/x"}]})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        recs, total = OpenAlexProvider().browse(
            "", filters={"fields": [("title", "inovação"), ("author", "silva")], "sort": "citations"},
            page=2, per_page=25)
    assert total == 3402 and len(recs) == 1 and recs[0]["citations"] == 40
    url = mock.call_args[0][0].full_url
    assert "title.search" in url and "display_name.search" in url
    assert "page=2" in url and "cited_by_count" in url


def test_browse_per_page_capped_200():
    body = json.dumps({"meta": {"count": 1}, "results": []})
    with patch("urllib.request.urlopen", return_value=_resp(body)) as mock:
        OpenAlexProvider().browse("x", per_page=999)
    assert "per_page=200" in mock.call_args[0][0].full_url


# ── Limite do campo Qtd: sem teto (a proteção é o aviso de volume) ──

def _limit_for(digitado: str, ilimitado: bool = False) -> tuple:
    """Chama _current_limit com stubs dos dois widgets que ele lê (sem subir a UI).
    Devolve (limite, conteúdo do campo depois) — o campo não deve ser reescrito."""
    import types
    import main

    class _Stub:
        def __init__(self, v): self.v = v
        def get(self): return self.v

    o = types.SimpleNamespace(_search_max_entry=_Stub(digitado),
                              _search_unlimited_var=_Stub(ilimitado))
    return main.BlicsaApp._current_limit(o), o._search_max_entry.get()


def test_qtd_field_has_no_ceiling():
    """Ilimitado tem que ser ilimitado: o número digitado no campo Qtd vale, sem teto.
    Antes, valores acima de 10000 eram cortados (e o campo reescrito) — o usuário pedia
    50000 e recebia 10000. A proteção contra colher demais é o aviso de volume
    (test_count_dialog_threshold abaixo), não um corte do valor pedido."""
    assert _limit_for("50000") == (50000, "50000")
    assert _limit_for("999999") == (999999, "999999")
    assert _limit_for("10001") == (10001, "10001"), "10000 não pode mais ser um teto"


def test_qtd_vazio_e_ilimitado_de_verdade():
    """Campo vazio = ILIMITADO. O padrão de 1000 contradizia "vazio = ilimitado": quem não
    digitava nada recebia um teto silencioso de 1000 que nunca pediu.

    Regra única: número positivo vale exatamente; qualquer outra coisa é ilimitado, porque
    nenhuma delas expressa um limite. A proteção continua sendo o aviso de volume."""
    UNLIMITED = 10_000_000
    assert _limit_for("")[0] == UNLIMITED, "vazio tem que ser ilimitado, não 1000"
    assert _limit_for("   ")[0] == UNLIMITED, "só espaços é o mesmo que vazio"
    assert _limit_for("0")[0] == UNLIMITED, "zero não é um limite"
    assert _limit_for("-5")[0] == UNLIMITED, "negativo não é um limite"
    assert _limit_for("abc")[0] == UNLIMITED, "texto inválido não vira teto de 1000"
    assert _limit_for("1000", ilimitado=True)[0] == UNLIMITED

    # O outro lado da guarda: número positivo continua valendo exatamente, sem virar
    # ilimitado por acidente — senão o campo perderia a função.
    assert _limit_for("1000")[0] == 1000
    assert _limit_for("1")[0] == 1, "o menor limite válido tem que ser respeitado"
    assert _limit_for(" 250 ")[0] == 250, "espaços em volta não invalidam o número"


def test_qtd_vazio_nao_reescreve_o_campo():
    """Ilimitado por vazio não pode "corrigir" o campo para 1000 na cara do usuário."""
    assert _limit_for("") == (10_000_000, ""), "o campo tem que continuar vazio"


def test_count_dialog_threshold_is_the_real_protection():
    """O aviso de volume (_search_after_count) é o que segura colheita grande sem querer:
    dispara quando a base tem mais de 2000 E o limite pedido passa de 2000. Sem o teto,
    quem pede 50000 continua passando por ele — a proteção não foi perdida."""
    import main

    chamou = {}

    class _Fake:
        _set_idle = lambda self, *a, **k: None
        def search_to_dataset(self, *a): chamou["direto"] = True
        def _show_count_dialog(self, *a): chamou["dialogo"] = True

    def cenario(n_base, limite):
        chamou.clear()
        main.BlicsaApp._search_after_count(_Fake(), n_base, "q", "openalex", limite, {})
        return "dialogo" if chamou.get("dialogo") else "direto"

    assert cenario(319_300, 50_000) == "dialogo", "limite alto em base grande deve avisar"
    assert cenario(319_300, 10_000_000) == "dialogo", "Ilimitado em base grande deve avisar"
    assert cenario(319_300, 1000) == "direto", "limite baixo não precisa de aviso"
    assert cenario(500, 50_000) == "direto", "base pequena não precisa de aviso"
