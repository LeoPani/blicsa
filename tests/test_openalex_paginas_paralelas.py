"""Importação do OpenAlex por páginas numeradas em paralelo (até 10.000 registros).

Medido em 04/10 na internet do autor: 1000 registros de 18,1 s (cursor, uma página por vez)
para 5,5 s (4 páginas em paralelo, resposta comprimida, só os campos usados), mesmos IDs.
Acima de 10.000 a API recusa a paginação numerada: aí continua o cursor.
"""
import json
import threading
import time
import urllib.error
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from core.sources.openalex import OpenAlexProvider


@pytest.fixture(autouse=True)
def _paralelo(monkeypatch):
    monkeypatch.setattr(OpenAlexProvider, "PAGINAS_PARALELAS", 4)


class FakePaginas:
    """OpenAlex falso que responde `page`/`per_page` (e `cursor`), com latência e em
    qualquer ordem de chegada, como a API real."""

    def __init__(self, total, falha_na_pagina=None, atraso=0.01):
        self.total, self.falha, self.atraso = total, falha_na_pagina, atraso
        self.urls, self.trava = [], threading.Lock()
        self.simultaneos = self.max_simultaneos = 0

    def __call__(self, req, *a, **kw):
        url = getattr(req, "full_url", str(req))
        with self.trava:
            self.urls.append(url)
            self.simultaneos += 1
            self.max_simultaneos = max(self.max_simultaneos, self.simultaneos)
        try:
            q = parse_qs(urlparse(url).query)
            pp = int(q["per_page"][0])
            if "page" in q:
                pg = int(q["page"][0])
                if pg * pp > 10_000:
                    raise urllib.error.HTTPError(url, 400, "page too deep", {}, None)
                if pg == self.falha:
                    raise urllib.error.HTTPError(url, 500, "erro", {}, None)
                ini = (pg - 1) * pp
                time.sleep(self.atraso * (5 - pg % 5))      # chegam fora de ordem
                meta = {"count": self.total}
            else:
                cur = q.get("cursor", ["*"])[0]
                ini = 0 if cur == "*" else int(cur)
                meta = {"count": self.total}
                if ini + pp < self.total:
                    meta["next_cursor"] = str(ini + pp)
            fim = min(ini + pp, self.total)
            corpo = json.dumps({"meta": meta, "results": [
                {"id": f"https://openalex.org/W{i}", "title": f"Trabalho {i}",
                 "publication_year": 2020, "authorships": []} for i in range(ini, fim)]})
            m = MagicMock()
            m.read.return_value = corpo.encode()
            m.headers = {}
            m.__enter__.return_value = m
            return m
        finally:
            with self.trava:
                self.simultaneos -= 1


def _buscar(fake, n, **kw):
    prov = OpenAlexProvider(api_key="")
    with patch("urllib.request.urlopen", side_effect=fake), patch("time.sleep") if kw.pop("sem_sleep", False) else _nada():
        regs = list(prov.search("x", max_results=n, **kw))
    return prov, regs


class _nada:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_mil_registros_em_ordem_sem_repetir_nem_perder():
    fake = FakePaginas(total=54_440)
    prov, regs = _buscar(fake, 1000)
    assert [r["title"] for r in regs] == [f"Trabalho {i}" for i in range(1000)]
    assert prov.total_available == 54_440 and prov.stop_reason == "atingiu limite"
    assert fake.max_simultaneos > 1, "as páginas não foram pedidas em paralelo"
    pages = sorted(int(parse_qs(urlparse(u).query)["page"][0]) for u in fake.urls)
    assert pages == [1, 2, 3, 4, 5]


def test_pede_so_os_campos_usados_e_sem_cursor():
    fake = FakePaginas(total=300)
    _buscar(fake, 1000)
    for u in fake.urls:
        q = parse_qs(urlparse(u).query)
        assert "cursor" not in q and "page" in q
        assert "abstract_inverted_index" in q["select"][0] and "referenced_works" in q["select"][0]


def test_base_menor_que_o_pedido_termina_no_fim():
    fake = FakePaginas(total=450)
    prov, regs = _buscar(fake, 1000)
    assert len(regs) == 450 and prov.stop_reason == "fim dos resultados"


def test_falha_numa_pagina_entrega_o_anterior_e_avisa():
    fake = FakePaginas(total=5000, falha_na_pagina=3)
    prov, regs = _buscar(fake, 1000, sem_sleep=True)
    assert len(regs) == 400                       # páginas 1 e 2
    assert prov.stop_error and "erro de rede na página 3" in prov.stop_reason


def test_acima_de_10000_volta_ao_cursor():
    fake = FakePaginas(total=12_000)
    prov, regs = _buscar(fake, 12_000)
    assert len(regs) == 12_000
    assert all("cursor" in parse_qs(urlparse(u).query) for u in fake.urls)


def test_exatamente_10000_usa_paginas_e_nao_estoura_o_teto():
    fake = FakePaginas(total=20_000, atraso=0)
    prov, regs = _buscar(fake, 10_000)
    assert len(regs) == 10_000 and not prov.stop_error


def test_cancelar_interrompe():
    ev = threading.Event()
    fake = FakePaginas(total=5000)
    prov = OpenAlexProvider(api_key="")
    with patch("urllib.request.urlopen", side_effect=fake):
        it = prov.search("x", max_results=2000, cancel_event=ev)
        next(it)
        ev.set()
        with pytest.raises(InterruptedError):
            list(it)
    assert prov.stop_reason == "cancelado"


def test_progresso_chega_ao_alvo():
    fake = FakePaginas(total=800)
    vistos = []
    prov = OpenAlexProvider(api_key="")
    with patch("urllib.request.urlopen", side_effect=fake):
        list(prov.search("x", max_results=1000, progress_cb=lambda a, b: vistos.append((a, b))))
    assert vistos[-1] == (800, 800)


def test_resposta_comprimida_e_descomprimida_e_cabecalho_mentiroso_nao_quebra():
    import gzip
    corpo = json.dumps({"meta": {"count": 1}, "results": [{"id": "W1", "title": "T"}]}).encode()
    for conteudo, enc in ((gzip.compress(corpo), "gzip"), (corpo, "gzip"), (corpo, None)):
        m = MagicMock()
        m.read.return_value = conteudo
        m.headers = {"Content-Encoding": enc} if enc else {}
        m.__enter__.return_value = m
        prov = OpenAlexProvider(api_key="")
        with patch("urllib.request.urlopen", return_value=m):
            regs = list(prov.search("x", max_results=10))
        assert [r["title"] for r in regs] == ["T"], enc


def test_repetidos_entre_paginas_sao_descartados_e_completados():
    """A ordem por relevância muda entre pedidos: a página 3 repete 2 registros da 2."""
    class Desliza(FakePaginas):
        def __call__(self, req, *a, **kw):
            url = getattr(req, "full_url", str(req))
            q = parse_qs(urlparse(url).query)
            r = super().__call__(req, *a, **kw)
            if q.get("page") == ["3"]:
                d = json.loads(r.read.return_value)
                d["results"][:2] = [{"id": "https://openalex.org/W398", "title": "Trabalho 398"},
                                    {"id": "https://openalex.org/W399", "title": "Trabalho 399"}]
                r.read.return_value = json.dumps(d).encode()
            return r
    fake = Desliza(total=5000, atraso=0)
    prov, regs = _buscar(fake, 1000)
    ids = [r["openalex_id"] for r in regs]
    assert len(regs) == 1000 and len(set(ids)) == 1000
    pages = sorted(int(parse_qs(urlparse(u).query)["page"][0]) for u in fake.urls)
    assert pages == [1, 2, 3, 4, 5, 6]             # uma página extra completou os 2


def test_429_respeita_retry_after(monkeypatch):
    import core.sources.base as B
    esperas = []
    monkeypatch.setattr(B.time, "sleep", lambda s: esperas.append(s))
    chamadas = {"n": 0}
    ok = FakePaginas(total=10, atraso=0)

    def urlopen(req, *a, **kw):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise urllib.error.HTTPError("u", 429, "Too Many", {"Retry-After": "7"}, None)
        return ok(req)
    prov = OpenAlexProvider(api_key="")
    with patch("urllib.request.urlopen", side_effect=urlopen):
        regs = list(prov.search("x", max_results=10))
    assert len(regs) == 10 and 7.0 in esperas
