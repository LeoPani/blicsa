"""Fase 4 — carga e anti-travamento do modo navegação.

O que este arquivo procura: vazamento de widget, thread pendurada e crescimento de memória
depois de muita troca de página e de faceta. São os três jeitos de a tela ir ficando pesada
sem ninguém notar até o app travar numa sessão longa.

Método declarado, para os números serem reproduzíveis:
* widgets — contagem recursiva de descendentes do `SearchFeedView` antes e depois;
* threads — `threading.enumerate()` antes e depois, desprezando as do próprio pytest;
* memória — `tracemalloc`, pico durante o ciclo.
Reproduzível por `pytest tests/test_search_stress.py -q -s`.
"""
import gc
import threading
import tracemalloc

import pytest

from core.browse import BrowseSession, Page
from core.sources import OpenAlexProvider

TROCAS_PAGINA = 20
TROCAS_FACETA = 20


def _ctk():
    return pytest.importorskip("customtkinter")


def _rec(i):
    return {"title": f"Artigo {i}", "year": 2020, "authors": "Silva, J", "source": "Rev X",
            "citations": i, "abstract": "resumo " * 10, "doi": f"10.1/{i}", "language": "en"}


def _page(n=25, page=1, total=1000):
    inicio = (page - 1) * n
    return Page(records=[_rec(i) for i in range(inicio, inicio + n)],
                total=total, page=page, per_page=n)


def _contar_widgets(w):
    total = 1
    for ch in w.winfo_children():
        total += _contar_widgets(ch)
    return total


class ProviderFalso(OpenAlexProvider):
    """Provider sintético: sem rede, mas com o mesmo contrato de browse/facet."""

    def __init__(self):
        super().__init__()
        self.chamadas_browse = 0
        self.chamadas_facet = 0

    def browse(self, query, filters=None, page=1, per_page=25, sort=None, cancel_event=None):
        self.chamadas_browse += 1
        inicio = (max(1, page) - 1) * per_page
        return [_rec(i) for i in range(inicio, inicio + per_page)], 1000

    def facet(self, campo, query, filters=None, top=10, cancel_event=None):
        self.chamadas_facet += 1
        return [{"key": f"{campo}_{i}", "label": f"{campo} {i}", "count": 100 - i}
                for i in range(5)]


def test_twenty_page_switches_do_not_leak_widgets_or_threads(capsys):
    """20 trocas de página: sem vazar widget, sem thread pendurada, sem inchar a memória."""
    ctk = _ctk()
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    root.geometry("1200x800+3000+3000")
    from ui.search_feed import SearchFeedView

    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None)
    fv.pack(fill="both", expand=True)
    try:
        fv.load_browse_page(_page(page=1))
        root.update()
        gc.collect()

        widgets_antes = _contar_widgets(fv)
        threads_antes = len(threading.enumerate())
        tracemalloc.start()
        base, _ = tracemalloc.get_traced_memory()

        for i in range(TROCAS_PAGINA):
            fv.load_browse_page(_page(page=(i % 8) + 1))
            root.update()

        gc.collect()
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        widgets_depois = _contar_widgets(fv)
        threads_depois = len(threading.enumerate())
        crescimento_mb = (pico - base) / (1024 * 1024)

        with capsys.disabled():
            print(f"\n[stress] {TROCAS_PAGINA} trocas de página · "
                  f"widgets {widgets_antes}→{widgets_depois} · "
                  f"threads {threads_antes}→{threads_depois} · "
                  f"memória +{crescimento_mb:.1f} MB")

        assert widgets_depois <= widgets_antes + 5, (
            f"vazamento de widgets: {widgets_antes} → {widgets_depois}")
        assert threads_depois <= threads_antes, (
            f"thread pendurada: {threads_antes} → {threads_depois}")
        assert crescimento_mb < 25, f"memória cresceu {crescimento_mb:.1f} MB em 20 páginas"
    finally:
        root.destroy()


def test_twenty_facet_toggles_do_not_leak(capsys):
    """20 alternâncias de faceta em sequência rápida, com a sidebar redesenhada a cada uma."""
    ctk = _ctk()
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    root.geometry("1200x800+3000+3000")
    from ui.search_feed import SearchFeedView

    prov = ProviderFalso()
    sessao = BrowseSession(prov, "x")
    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None)
    fv.pack(fill="both", expand=True)
    try:
        facetas = sessao.fetch_facets(["type", "language"])
        fv.load_browse_page(_page(page=1), session=sessao)
        fv.render_facets(facetas, ativos=sessao.active_facets)
        root.update()
        gc.collect()

        widgets_antes = _contar_widgets(fv)
        threads_antes = len(threading.enumerate())

        for i in range(TROCAS_FACETA):
            campo = "type" if i % 2 == 0 else "language"
            sessao.toggle_facet(campo, f"{campo}_{i % 5}")
            p = sessao.fetch_page(1)
            fv.load_browse_page(p, session=sessao)
            fv.render_facets(facetas, ativos=sessao.active_facets)
            fv.render_chips(sessao.chips())
            root.update()

        gc.collect()
        widgets_depois = _contar_widgets(fv)
        threads_depois = len(threading.enumerate())

        with capsys.disabled():
            print(f"[stress] {TROCAS_FACETA} alternâncias de faceta · "
                  f"widgets {widgets_antes}→{widgets_depois} · "
                  f"threads {threads_antes}→{threads_depois} · "
                  f"{prov.chamadas_browse} chamadas ao provider")

        assert widgets_depois <= widgets_antes + 10, (
            f"vazamento na sidebar/chips: {widgets_antes} → {widgets_depois}")
        assert threads_depois <= threads_antes
    finally:
        root.destroy()


def test_cache_keeps_the_provider_from_being_hammered():
    """Passear pelas mesmas páginas não multiplica requisições — o LRU faz seu trabalho."""
    prov = ProviderFalso()
    sessao = BrowseSession(prov, "x")
    for _ in range(4):
        for pagina in (1, 2, 3):
            sessao.fetch_page(pagina)
    assert prov.chamadas_browse == 3, (
        f"12 navegações por 3 páginas deveriam custar 3 requisições, custaram "
        f"{prov.chamadas_browse}")


def test_lru_does_not_grow_without_bound():
    """O cache tem teto: navegar 100 páginas não guarda 100 páginas em memória."""
    from core.browse import CACHE_PAGINAS

    sessao = BrowseSession(ProviderFalso(), "x")
    for pagina in range(1, 101):
        sessao.fetch_page(pagina)
    assert sessao.cached_pages() == CACHE_PAGINAS, (
        f"o cache guardou {sessao.cached_pages()} páginas, teto é {CACHE_PAGINAS}")


def test_rapid_sequential_queries_settle_on_the_last_one():
    """Rajada de buscas: só a última vale, e o estado final é o dela."""
    sessao = BrowseSession(ProviderFalso(), "x")
    tokens = [sessao.next_token() for _ in range(50)]
    assert sum(1 for t in tokens if sessao.is_current(t)) == 1
    assert sessao.is_current(tokens[-1])


def test_session_state_is_deterministic_across_hash_seeds():
    """Filtros e chips não podem depender da ordem de iteração de dict/set.

    Roda em subprocessos com PYTHONHASHSEED diferente: dentro de um mesmo processo a ordem é
    estável e o problema não apareceria — foi assim que o bug de clusters não-determinísticos
    escapou nos mapas.
    """
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, '.');"
        "from core.browse import BrowseSession;"
        "from core.sources import OpenAlexProvider;"
        "s = BrowseSession(OpenAlexProvider(), 'x');"
        "[s.toggle_facet(c, v) for c, v in "
        " [('type','article'),('type','book'),('language','en'),('language','pt'),"
        "  ('publication_year','2020'),('publication_year','2021')]];"
        "print(OpenAlexProvider()._oa_filter('x', s.current_filters()));"
        "print(sorted((c['field'], c['key']) for c in s.chips()))"
    )
    saidas = []
    for semente in ("0", "1", "424242"):
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": semente, "PATH": "/usr/bin:/bin"})
        assert r.returncode == 0, f"subprocesso falhou (seed={semente}): {r.stderr[-300:]}"
        saidas.append(r.stdout.strip())

    assert saidas[0] == saidas[1] == saidas[2], (
        "a string do filtro muda conforme PYTHONHASHSEED:\n" + "\n---\n".join(saidas))


# ─────────────────── orçamento da API ───────────────────

def test_rate_limit_headers_are_captured_when_present():
    """O orçamento informado pela API fica disponível para a UI avisar.

    O OpenAlex passou a devolver um modelo de créditos (medido: 1.000/dia sem chave, 10 por
    página, 1 por `group_by`). Capturar é barato e evita o usuário descobrir o teto com um
    429 no meio de uma busca.
    """
    from unittest.mock import MagicMock, patch

    class Headers(dict):
        pass

    h = Headers({"X-RateLimit-Remaining": "792", "X-RateLimit-Limit": "1000",
                 "X-RateLimit-Credits-Used": "10", "X-RateLimit-Reset": "39569",
                 "X-RateLimit-Remaining-USD": "0.0792"})
    resp = MagicMock()
    resp.read.return_value = b'{"meta": {"count": 1}, "results": []}'
    resp.headers = h
    resp.__enter__.return_value = resp

    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", return_value=resp):
        prov.count("x")

    assert prov.rate_limit["remaining"] == 792.0
    assert prov.rate_limit["limit"] == 1000.0
    assert prov.rate_limit["used_by_last"] == 10.0


def test_missing_rate_limit_headers_do_not_break_the_request():
    """O outro lado: API que não manda os headers (Crossref, PubMed) segue funcionando."""
    from unittest.mock import MagicMock, patch

    resp = MagicMock()
    resp.read.return_value = b'{"meta": {"count": 7}, "results": []}'
    resp.headers = {}
    resp.__enter__.return_value = resp

    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", return_value=resp):
        assert prov.count("x") == 7
    assert prov.rate_limit == {}, "sem headers, o orçamento fica vazio — não inventa número"
