"""Rede caída e busca sem resultados — Etapa 4, item 10.

Os dois cenários ficaram como **não verificados** na Auditoria 1, Fase 2 §5: a sonda travava
além de cinco minutos e a causa não fora isolada.

**A causa era a sonda, não o app.** Sem substituir o `messagebox`, o worker abre um modal de
verdade e fica esperando um clique que nunca vem. Com o modal capturado, os dois cenários
levam **1,1 s** e nenhuma exceção escapa do worker.

A verificação, porém, expôs o defeito que estava atrás: as duas mensagens eram **português
fixo**, e a de rede caída ainda repassava `<urlopen error [Errno 8] nodename nor servname
provided, or not known>` — sem nada dizendo "verifique sua conexão".
"""

import socket
import threading
import time
import urllib.error

import pytest

from core import i18n
from core.sources.base import diagnosticar_busca

IDIOMAS = ("pt_BR", "en", "fr")

#: Teto generoso, mas muito abaixo dos cinco minutos que a sonda antiga levava. Se um modal
#: real voltar a abrir, ou um backoff passar a bloquear, este número denuncia.
LIMITE_S = 30


@pytest.fixture(autouse=True)
def restaura_idioma():
    anterior = i18n.get_lang()
    yield
    i18n.load_locales(anterior)


@pytest.fixture
def app(monkeypatch):
    """App com os `messagebox` capturados — sem isto o worker abre modal e trava o teste."""
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.withdraw()
    janela.update_idletasks()

    vistos: list[tuple[str, str, str]] = []
    for tipo in ("showinfo", "showerror", "showwarning"):
        monkeypatch.setattr(
            f"tkinter.messagebox.{tipo}",
            lambda titulo, msg="", *a, _t=tipo, **k: vistos.append((_t, str(titulo), str(msg))))
    janela._vistos = vistos
    yield janela
    janela.destroy()


def _busca(app, fake, provedor="openalex"):
    """Roda o worker real com o provedor substituído. Devolve `(mensagens, segundos)`."""
    import core.sources.openalex as oa

    app._vistos.clear()
    original = oa.OpenAlexProvider.search
    oa.OpenAlexProvider.search = fake
    inicio = time.perf_counter()
    try:
        app._search_worker("clima urbano", provedor, 50, {}, threading.Event())
        for _ in range(20):
            app.update()
            time.sleep(0.05)
    finally:
        oa.OpenAlexProvider.search = original
    return list(app._vistos), time.perf_counter() - inicio


def _sem_resultado(self, *a, **k):
    return iter([])


def _rede_caida(self, *a, **k):
    raise urllib.error.URLError("[Errno 8] nodename nor servname provided, or not known")
    yield  # noqa: unreachable — faz do objeto um gerador, como o provedor real


# ── Os dois cenários, agora verificados ──────────────────────────────────────────

@pytest.mark.parametrize("idioma", IDIOMAS)
def test_busca_sem_resultados_avisa_e_orienta(idioma, app):
    i18n.load_locales(idioma)

    mensagens, segundos = _busca(app, _sem_resultado)

    assert segundos < LIMITE_S, f"a busca vazia levou {segundos:.1f}s"
    assert mensagens, "busca sem resultados não avisou nada"
    tipo, titulo, texto = mensagens[0]
    assert tipo == "showinfo", "corpus vazio não é erro — é resultado"
    assert texto == i18n.t("busca.sem_resultado")
    assert len(texto) > 40, "a mensagem não orienta o que tentar em seguida"


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_rede_caida_explica_em_vez_de_mostrar_errno(idioma, app):
    i18n.load_locales(idioma)

    mensagens, segundos = _busca(app, _rede_caida)

    assert segundos < LIMITE_S, f"a busca com rede caída levou {segundos:.1f}s"
    assert mensagens, "rede caída não avisou nada"
    tipo, titulo, texto = mensagens[0]
    assert tipo == "showerror"
    assert texto == i18n.t("busca.erro_sem_conexao")
    for jargao in ("Errno", "urlopen", "Traceback", "URLError", "nodename"):
        assert jargao not in texto, f"jargão na tela em {idioma}: {texto!r}"


def test_nenhum_dos_dois_deixa_excecao_escapar_do_worker(app):
    """O worker roda em thread: exceção escapando some sem que o usuário veja nada."""
    for fake in (_sem_resultado, _rede_caida):
        mensagens, _ = _busca(app, fake)
        assert mensagens, "cenário terminou em silêncio"


def test_o_detalhe_tecnico_da_rede_vai_para_o_log(app, caplog):
    with caplog.at_level("INFO"):
        _busca(app, _rede_caida)

    assert "URLError" in caplog.text, "o detalhe técnico não foi registrado"
    assert "busca.erro_sem_conexao" in caplog.text, "o log não diz qual diagnóstico saiu"


# ── O diagnóstico, caso a caso ───────────────────────────────────────────────────

@pytest.mark.parametrize("erro,esperado", [
    (urllib.error.URLError("dns"), "busca.erro_sem_conexao"),
    (socket.gaierror("dns"), "busca.erro_sem_conexao"),
    (TimeoutError(), "busca.erro_sem_conexao"),
    (ConnectionResetError(), "busca.erro_sem_conexao"),
    (urllib.error.HTTPError("u", 429, "Too Many", {}, None), "busca.erro_limite"),
    (urllib.error.HTTPError("u", 403, "Forbidden", {}, None), "busca.erro_bloqueado"),
    (urllib.error.HTTPError("u", 401, "Unauthorized", {}, None), "busca.erro_bloqueado"),
    (urllib.error.HTTPError("u", 500, "Server Error", {}, None), "busca.erro_provedor"),
    (ValueError("outra coisa"), "busca.erro_desconhecido"),
])
def test_cada_falha_de_busca_tem_diagnostico_proprio(erro, esperado):
    """`HTTPError` é subclasse de `URLError`: checado antes, senão todo 429 viraria
    'sem conexão' e o usuário esperaria a internet voltar por causa de um limite de taxa."""
    assert diagnosticar_busca(erro) == esperado


def test_limite_e_sem_conexao_nao_dizem_a_mesma_coisa():
    """Um pede para esperar um minuto, o outro para checar a internet. Confundir os dois
    manda o usuário resolver o problema errado."""
    assert i18n.t("busca.erro_limite") != i18n.t("busca.erro_sem_conexao")


# ── Paridade e tradução ──────────────────────────────────────────────────────────

def _chaves_de_busca() -> set[str]:
    """Da fonte real de `core/sources/base.py` e do `main.py`, não de lista fixa aqui."""
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    chaves = set()
    for arquivo in ("core/sources/base.py", "main.py"):
        fonte = (raiz / arquivo).read_text(encoding="utf-8")
        chaves |= {n.value for n in ast.walk(ast.parse(fonte))
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and n.value.startswith("busca.")}
    assert len(chaves) >= 6, f"poucas chaves extraídas: {chaves}"
    return chaves


def test_toda_chave_de_busca_existe_nos_tres_catalogos():
    import json
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    chaves = _chaves_de_busca()
    for idioma in IDIOMAS:
        catalogo = json.loads((raiz / f"locales/{idioma}.json").read_text(encoding="utf-8"))
        faltando = sorted(chaves - set(catalogo))
        assert not faltando, f"{idioma} sem: {faltando}"


def test_as_mensagens_de_busca_sao_traduzidas_de_fato():
    import json
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    catalogos = {i: json.loads((raiz / f"locales/{i}.json").read_text(encoding="utf-8"))
                 for i in IDIOMAS}
    copiadas = [c for c in _chaves_de_busca()
                if len({catalogos[i][c] for i in IDIOMAS}) < 3]
    assert not copiadas, f"mensagens idênticas em dois ou mais catálogos: {copiadas}"


def test_erro_no_meio_do_download_nao_refaz_a_busca_sem_filtros(app):
    """Antes: qualquer TypeError no meio do download caía num `except TypeError` que refazia a
    busca inteira SEM os filtros, sem Cancelar, e somava os resultados aos já baixados."""
    import core.sources.openalex as oa
    chamadas = []

    def fake(self, query, filters=None, max_results=100, progress_cb=None, cancel_event=None):
        chamadas.append(dict(filters or {}))
        yield {"title": "Artigo 1", "authors": "A", "year": 2020, "doi": "10.1000/1"}
        raise TypeError("campo inesperado na resposta da API")

    app._vistos.clear()
    original = oa.OpenAlexProvider.search
    oa.OpenAlexProvider.search = fake
    try:
        app._search_worker("clima", "openalex", 50, {"year_start": 2020}, threading.Event())
        for _ in range(20):
            app.update()
            time.sleep(0.05)
    finally:
        oa.OpenAlexProvider.search = original
    assert chamadas == [{"year_start": 2020}], f"a busca foi refeita: {chamadas}"
