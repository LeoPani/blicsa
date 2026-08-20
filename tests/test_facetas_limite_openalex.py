"""Facetas que falham por franquia esgotada precisam DIZER isso.

Medido no app, com a franquia real zerada: as seis facetas do OpenAlex (`type`, `language`,
`publication_year`, `is_oa`, `source`, `author`) são seis `group_by` de 1 crédito cada,
disparados em paralelo. Com um crédito restante, uma ganha a corrida e cinco levam 429 —
que foi exatamente o que o usuário viu: "Tipo de documento" carregado e os outros cinco com
"Não foi possível carregar este filtro".

O defeito não estava na busca nem no provider. `core/browse.py` **já** preenchia
`Facet.error_key` com `search.error_rate_limit`, e `ui/search_feed.py` renderizava o texto
genérico fixo, jogando fora a única mensagem que dizia o que houve e o que fazer. O usuário
via cinco filtros quebrados sem pista de que tinha esbarrado na franquia diária.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from core.browse import BrowseSession, Facet, error_i18n_args, error_i18n_key
from core.sources.base import AuthError, RateLimitError
from core.sources.openalex import OpenAlexProvider

RAIZ = Path(__file__).resolve().parent.parent
FACETAS = ["type", "language", "publication_year", "is_oa", "source", "author"]


@pytest.fixture
def feed():
    """O SearchFeedView real, dentro de uma janela real."""
    import customtkinter as ctk

    from ui.search_feed import SearchFeedView

    try:
        raiz = ctk.CTk()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    raiz.withdraw()
    # Assinatura real: (master, on_import_confirm, on_cancel, on_expand).
    vista = SearchFeedView(raiz, lambda *a, **k: None, lambda: None,
                           lambda *a, **k: None)
    yield vista
    raiz.destroy()


def _textos(widget) -> list[str]:
    """Todo texto desenhado na sidebar, na ordem em que aparece.

    Só os widgets do CustomTkinter: cada CTkLabel embrulha um Label do tkinter com o MESMO
    texto, e contar os dois dobra tudo — o que fez a primeira versão deste módulo acusar
    "explicação repetida 2 vezes" sobre uma sidebar que a mostrava uma vez só.
    """
    import customtkinter as ctk

    saida = []
    marcados = (ctk.CTkLabel, ctk.CTkButton, ctk.CTkCheckBox)

    def varre(w):
        for filho in w.winfo_children():
            if isinstance(filho, marcados):
                try:
                    txt = filho.cget("text")
                    if isinstance(txt, str) and txt.strip():
                        saida.append(txt)
                except Exception:
                    pass
            varre(filho)

    varre(widget)
    return saida


class ProviderComTeto(OpenAlexProvider):
    """Provider real com a franquia esgotada a partir da N-ésima faceta.

    `creditos=1` reproduz o estado exato que o usuário encontrou: a primeira faceta passa,
    as cinco seguintes levam 429.
    """

    def __init__(self, creditos=0, **kw):
        super().__init__(api_key="", **kw)
        self.creditos = creditos
        self.pedidos = 0

    def fetch_url(self, url, *a, **kw):
        self.pedidos += 1
        if self.creditos <= 0:
            raise RateLimitError(url)
        self.creditos -= 1
        return json.dumps({"meta": {"count": 1},
                           "group_by": [{"key": "article", "key_display_name": "Article",
                                         "count": 42}]})


# ── A causa: 429 vira error_key, e a UI tem que usá-lo ──────────────────────────

def test_faceta_com_429_carrega_a_chave_da_mensagem_especifica():
    """Isto já funcionava. O teste existe para o dia em que alguém trocar o tipo do erro:
    sem `i18n_key`, a sidebar volta silenciosamente ao texto genérico."""
    assert error_i18n_key(RateLimitError("u")) == "search.error_rate_limit"


def test_franquia_esgotada_derruba_as_facetas_e_preserva_a_explicacao():
    """Caminho do app: `fetch_facets` com a franquia zerada."""
    sessao = BrowseSession(ProviderComTeto(creditos=0), "bibliometrics")

    facetas = sessao.fetch_facets(campos=FACETAS, paralelo=False)

    assert len(facetas) == len(FACETAS)
    assert all(not f.ok for f in facetas.values()), "alguma faceta passou sem crédito"
    assert all(f.error_key == "search.error_rate_limit" for f in facetas.values()), (
        {c: f.error_key for c, f in facetas.items()})


def test_um_credito_restante_reproduz_o_que_o_usuario_viu():
    """Uma carrega, cinco falham — em série, a primeira da ordem é a `type`."""
    sessao = BrowseSession(ProviderComTeto(creditos=1), "bibliometrics")

    facetas = sessao.fetch_facets(campos=FACETAS, paralelo=False)

    assert facetas["type"].ok, "a primeira faceta devia ter passado"
    quebradas = [c for c, f in facetas.items() if not f.ok]
    assert quebradas == FACETAS[1:], quebradas


def test_a_sidebar_mostra_a_mensagem_da_franquia_e_nao_a_generica(feed):
    """O defeito, no widget: a explicação existia e a UI desenhava o texto fixo."""
    from core.i18n import t

    facetas = {c: Facet(field=c, error="429", error_key="search.error_rate_limit")
               for c in FACETAS}

    feed.render_facets(facetas)

    textos = " ".join(_textos(feed.sidebar))
    assert t("search.error_rate_limit") in textos, (
        "a sidebar não mostra a mensagem da franquia esgotada")


def test_a_explicacao_aparece_uma_vez_e_nao_uma_por_faceta(feed):
    """Seis cópias de um parágrafo numa coluna de 210px empurram para fora da tela
    justamente os filtros que funcionaram."""
    from core.i18n import t

    facetas = {c: Facet(field=c, error="429", error_key="search.error_rate_limit")
               for c in FACETAS}

    feed.render_facets(facetas)

    textos = _textos(feed.sidebar)
    assert textos.count(t("search.error_rate_limit")) == 1, (
        f"a explicação foi repetida {textos.count(t('search.error_rate_limit'))} vezes")


def test_facetas_que_funcionaram_continuam_desenhadas(feed):
    """Adversarial: o aviso não pode comer os filtros que carregaram. É o caso real —
    "Tipo de documento" tinha valores e precisava continuar clicável."""
    from core.browse import FacetValue

    facetas = {"type": Facet(field="type",
                             values=[FacetValue("article", "Article", 42),
                                     FacetValue("book", "Book", 7)])}
    facetas.update({c: Facet(field=c, error="429", error_key="search.error_rate_limit")
                    for c in FACETAS[1:]})

    feed.render_facets(facetas)

    textos = " ".join(_textos(feed.sidebar))
    assert "Article" in textos and "Book" in textos, (
        "os valores da faceta que funcionou sumiram da sidebar")


def test_erro_sem_mensagem_propria_cai_no_texto_generico(feed):
    """Adversarial: falha de rede comum não tem explicação própria, e inventar uma seria
    pior — mandaria o usuário conferir uma franquia que não é o problema."""
    from core.i18n import t

    facetas = {"type": Facet(field="type", error="Connection refused", error_key="")}

    feed.render_facets(facetas)

    textos = " ".join(_textos(feed.sidebar))
    assert t("facet.error") in textos
    assert t("search.error_rate_limit") not in textos


def test_mensagem_parametrizada_chega_com_o_valor_e_nao_com_a_chave(feed):
    """`search.error_auth` traz `{fonte}`. Sem `Facet.error_args`, a sidebar mostraria a
    chave literal `{fonte}` para o usuário."""
    erro = AuthError("u", 401, "OpenAlex")
    facetas = {"type": Facet(field="type", error=str(erro),
                             error_key=error_i18n_key(erro),
                             error_args=error_i18n_args(erro))}

    feed.render_facets(facetas)

    textos = " ".join(_textos(feed.sidebar))
    assert "{fonte}" not in textos, "o parâmetro da mensagem não foi aplicado"
    assert "OpenAlex" in textos


def test_fetch_facets_propaga_os_args_do_erro():
    """O elo entre o provider e a sidebar: sem isto o teste acima passaria e o app não."""
    class ProviderCom401(OpenAlexProvider):
        def fetch_url(self, url, *a, **kw):
            raise AuthError(url, 401, "OpenAlex")

    sessao = BrowseSession(ProviderCom401(api_key=""), "x")

    facetas = sessao.fetch_facets(campos=["type"], paralelo=False)

    assert facetas["type"].error_args == {"fonte": "OpenAlex"}, facetas["type"].error_args


# ── A mensagem tem que dizer o tamanho do ganho ─────────────────────────────────

@pytest.mark.parametrize("idioma", ["pt_BR", "en", "fr"])
def test_a_mensagem_quantifica_a_franquia_nos_tres_idiomas(idioma):
    """Dizia só "aumenta esse limite". Com o fim do polite pool, a chave é o que separa
    1.000 de 10.000 créditos por dia — e o usuário precisa saber que vale a pena."""
    cat = json.loads((RAIZ / "locales" / f"{idioma}.json").read_text(encoding="utf-8"))
    msg = cat["search.error_rate_limit"]

    assert "10" in msg, f"{idioma}: a mensagem não quantifica o ganho: {msg!r}"
    assert any(m in msg for m in ("1.000", "1,000", "1 000")), f"{idioma}: {msg!r}"
    assert "openalex.org/settings/api" in msg, f"{idioma}: falta o endereço para criar"


# ── Rede real ──────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_live_o_429_do_openalex_chega_como_RateLimitError():
    """Só a rede real prova que o 429 vira o tipo certo em vez de IOError genérico.

    Tolerante por necessidade: só há 429 para observar quando a franquia está esgotada, e
    ela zera à meia-noite UTC. Com crédito disponível, o teste confirma o outro lado — que
    a chamada passa.
    """
    prov = OpenAlexProvider(api_key="")
    try:
        valores = prov.facet("type", "bibliometrics", top=5)
        assert isinstance(valores, list)
    except RateLimitError as e:
        assert e.i18n_key == "search.error_rate_limit"
    except urllib.error.HTTPError as e:  # pragma: no cover
        pytest.fail(f"429 subiu como HTTPError cru em vez de RateLimitError: {e.code}")
