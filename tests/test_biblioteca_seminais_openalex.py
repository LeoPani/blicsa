"""A biblioteca de seminais consultando o OpenAlex de verdade — e reclamando quando não dá.

O enriquecimento de referências **nunca funcionou**. Montava `?q=…&limit=1` na mão, e
`limit` não existe no OpenAlex: a API responde `400 Bad Request` ("The 'limit' parameter is
not valid. Did you mean 'per-page'?"). Como a chamada inteira vivia dentro de um
`except Exception: pass`, todo artigo sem DOI legível saía com "Não identificado pela API
OpenAlex" no lugar do título e do resumo, e o diálogo final dizia "Sucesso" com o mesmo
texto de sempre. Nenhum teste falhava porque nenhum teste olhava para cá.

As duas chamadas soltas também não passavam pelo `fetch_url` do `OpenAlexProvider`, então
nunca receberiam a chave da API — o que deixou de ser detalhe quando o OpenAlex
descontinuou o polite pool em fevereiro de 2026 e o `mailto` virou identificação sem
franquia associada.

Os testes de rede real estão marcados `live` e ficam fora da execução padrão (ver
`pytest.ini`). Rodar com: `pytest -m live`. Eles existem porque estrutura correta não é
comportamento correto: a primeira versão desta correção montava a consulta certa, passava
em qualquer dublê, e devolvia o artigo ERRADO contra a API de verdade.
"""

from __future__ import annotations

import json
import re
import urllib.error

import pytest

from core.sources.base import (AuthError, PaginationLimitError, RateLimitError,
                               SearchProvider)
from core.sources.openalex import OpenAlexProvider

VOSVIEWER = ("Van Eck NJ, Waltman L, 2010, Software survey: VOSviewer, a computer program "
             "for bibliometric mapping")
OSTROM = ("[12] Ostrom E., 1990, Governing the commons: the evolution of institutions for "
          "collective action")


@pytest.fixture
def app():
    """A janela real: `_enriquecer_referencia` é método dela, e o worker é o caminho."""
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.withdraw()
    janela.update_idletasks()
    yield janela
    janela.destroy()


class _RedeFalsa(SearchProvider):
    """Substitui SÓ a camada de rede.

    Fica ENTRE `OpenAlexProvider` e `SearchProvider` na MRO de propósito: assim o
    `fetch_url` do OpenAlex — que é quem anexa `api_key=` — continua rodando de verdade, e o
    que este dublê captura é a URL final, já com a chave. A primeira versão substituía o
    `fetch_url` do OpenAlex e por isso não via chave nenhuma: o teste da chave passava a
    testar o dublê.
    """

    def fetch_url(self, url, *a, **kw):
        self.urls.append(url)
        if self.erro is not None:
            raise self.erro
        if "/works/https://doi.org/" in url:
            if self.doi_corpo is None:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return self.doi_corpo
        return self.corpos.pop(0) if self.corpos else json.dumps({"meta": {"count": 0},
                                                                  "results": []})


class ProviderFalso(OpenAlexProvider, _RedeFalsa):
    """`_oa_filter`, `browse`, `_normalize_work` e o `fetch_url` do OpenAlex de verdade —
    só a requisição HTTP é dublada. É onde o defeito do `limit` estava: entre a montagem da
    URL e a resposta."""

    def __init__(self, corpos=None, erro=None, doi_corpo=None, **kw):
        super().__init__(api_key="", **kw)
        self.corpos = list(corpos or [])
        self.erro = erro
        self.doi_corpo = doi_corpo
        self.urls: list[str] = []


def _obra(titulo, resumo="Um resumo qualquer.", oa=False, doi="https://doi.org/10.1/x"):
    return {"id": "https://openalex.org/W1", "title": titulo, "display_name": titulo,
            "publication_year": 2010, "cited_by_count": 3, "doi": doi,
            "abstract_inverted_index": {p: [i] for i, p in enumerate(resumo.split())},
            "open_access": {"is_oa": oa, "oa_url": "https://oa.example/x.pdf" if oa else None},
            "authorships": [], "concepts": [], "referenced_works": []}


def _pagina(*obras):
    return json.dumps({"meta": {"count": len(obras)}, "results": list(obras)})


# ── O defeito central: `limit` não existe, `per_page` existe ─────────────────────

def test_a_consulta_textual_nao_manda_mais_o_parametro_limit(app):
    """`limit` fazia a API responder 400 a TODA busca textual, desde sempre."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Software survey: VOSviewer, a computer "
                                               "program for bibliometric mapping"))])

    app._enriquecer_referencia(prov, VOSVIEWER)

    assert prov.urls, "nenhuma requisição foi feita"
    url = prov.urls[-1]
    assert "limit=" not in url.replace("per_page=", ""), (
        f"o parâmetro inválido `limit` voltou à URL: {url}")
    assert "per_page=" in url, f"a paginação correta não foi usada: {url}"


def test_a_requisicao_passa_pelo_provider_e_leva_o_mailto_do_projeto(app):
    """As chamadas soltas mandavam o endereço escrito à mão num User-Agent e nunca
    receberiam a chave da API, porque não passavam pelo `fetch_url` do provider."""
    from core.sources.base import MAILTO

    prov = ProviderFalso(corpos=[_pagina(_obra("Governing the Commons: The Evolution of "
                                               "Institutions for Collective Action"))])

    app._enriquecer_referencia(prov, OSTROM)

    import urllib.parse

    assert f"mailto={MAILTO}" in urllib.parse.unquote(prov.urls[-1]), (
        "a requisição não leva o MAILTO de core/sources/base.py")


def test_a_chave_da_api_e_anexada_quando_configurada(app):
    """O ganho concreto de passar pelo provider: sem chave a franquia é dez vezes menor."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Governing the Commons: The Evolution of "
                                               "Institutions for Collective Action"))])
    prov.api_key = "minha-chave-openalex"

    app._enriquecer_referencia(prov, OSTROM)

    assert "api_key=minha-chave-openalex" in prov.urls[-1], (
        "a chave dos Ajustes não chegou à requisição")


# ── O DOI manda; a busca textual é palpite ──────────────────────────────────────

def test_com_doi_resolvido_nao_ha_busca_textual(app):
    """Resolver por identificador exato é O artigo. Completar com outro trabalho colaria
    o resumo errado sob o título certo — e gastaria 10 créditos para piorar o dado."""
    prov = ProviderFalso(doi_corpo=json.dumps(_obra("O Artigo Certo", "Resumo certo.")))

    dados, motivo = app._enriquecer_referencia(prov, "Autor A, 2001, doi:10.1234/abc")

    assert dados["title"] == "O Artigo Certo"
    assert dados["abstract"] == "Resumo certo."
    assert motivo == ""
    assert len(prov.urls) == 1, f"houve busca textual desnecessária: {prov.urls}"


def test_doi_sem_resumo_avisa_em_vez_de_chutar_outro_artigo(app):
    prov = ProviderFalso(doi_corpo=json.dumps(_obra("O Artigo Certo", resumo="")))

    dados, motivo = app._enriquecer_referencia(prov, "Autor A, 2001, doi:10.1234/abc")

    assert dados["title"] == "O Artigo Certo"
    assert motivo == "resumo não disponível no OpenAlex", motivo
    assert len(prov.urls) == 1


def test_doi_inexistente_cai_para_a_busca_textual(app):
    """404 no DOI não é o fim: a referência ainda pode ser achada pelo título."""
    prov = ProviderFalso(doi_corpo=None,
                         corpos=[_pagina(_obra("Governing the Commons: The Evolution of "
                                               "Institutions for Collective Action"))])

    dados, _ = app._enriquecer_referencia(
        prov, "Ostrom E, 1990, Governing the commons: the evolution of institutions "
              "for collective action, doi:10.9999/nao-existe")

    assert dados["title"], "o 404 do DOI matou a busca textual"
    assert len(prov.urls) == 2


# ── A conferência: dado errado é pior que dado ausente ──────────────────────────

def test_resultado_que_nao_confere_e_recusado(app):
    """Medido contra a API real: a referência do VOSviewer devolvia "Bibliometric mapping
    of computer and information ethics" como primeiro resultado. Gravar isso no arquivo do
    artigo seminal entrega o dado errado sem o usuário ter como desconfiar."""
    prov = ProviderFalso(corpos=[_pagina(
        _obra("Bibliometric mapping of computer and information ethics"))])

    dados, motivo = app._enriquecer_referencia(prov, VOSVIEWER)

    assert dados["title"] is None, "título de outro artigo foi aceito"
    assert dados["abstract"] is None, "resumo de outro artigo foi aceito"
    assert motivo == "resultado não confere com a referência", motivo


def test_referencia_truncada_com_titulo_certo_e_aceita(app):
    """A direção da comparação importa. Referências vêm truncadas o tempo todo; medindo
    título -> referência, o Callon de 1991 batia 46% contra o artigo CERTO."""
    prov = ProviderFalso(corpos=[_pagina(_obra(
        "Co-word analysis as a tool for describing the network of interactions between "
        "basic and technological research"))])

    dados, motivo = app._enriquecer_referencia(
        prov, "Callon M, Courtial JP, Laville F, 1991, Co-word analysis as a tool for "
              "describing the network of interactions")

    assert dados["title"], f"artigo certo recusado: {motivo}"
    assert motivo == ""


def test_titulo_curto_legitimo_e_aceito(app):
    """Piso de dois termos: "Pedagogia do oprimido" é um título inteiro."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Pedagogia do oprimido"))])

    dados, motivo = app._enriquecer_referencia(prov, "Freire P, 1968, Pedagogia do oprimido")

    assert dados["title"] == "Pedagogia do oprimido", motivo


def test_referencia_de_um_termo_so_nao_e_conferivel(app):
    """Adversarial: com um termo só, qualquer coisa "confere" a 100%."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Bibliometria aplicada a qualquer coisa"))])

    dados, motivo = app._enriquecer_referencia(prov, "Silva, 2020, Bibliometria")

    assert dados["title"] is None
    assert motivo == "referência curta demais para conferir o resultado", motivo


# ── Entradas adversariais ───────────────────────────────────────────────────────

@pytest.mark.parametrize("ref", ["", "   ", "[,,,] ,,, 1999 ,,,", "1999", "[12]"])
def test_referencia_sem_texto_pesquisavel_nao_gasta_requisicao(app, ref):
    prov = ProviderFalso(corpos=[_pagina(_obra("Qualquer"))])

    dados, motivo = app._enriquecer_referencia(prov, ref)

    assert dados["title"] is None
    assert prov.urls == [], f"gastou crédito com referência vazia: {prov.urls}"
    assert motivo, "falhou em silêncio"


def test_virgula_da_referencia_nao_vira_filtro_do_openalex(app):
    """No OpenAlex a vírgula separa filtros com AND. A referência crua virava meia dúzia
    de filtros inválidos e a API respondia 400 — que o `browse` ainda classificava como
    limite de paginação."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Software survey: VOSviewer, a computer "
                                               "program for bibliometric mapping"))])

    app._enriquecer_referencia(prov, VOSVIEWER)

    filtro = prov.urls[-1].split("filter=")[1].split("&")[0]
    assert filtro.count("%2C") == 0 and "," not in filtro, (
        f"a referência entrou com vírgula no filter=: {filtro}")


def test_400_de_sintaxe_nao_e_chamado_de_limite_de_paginacao(app):
    """`page=1 × per_page=1` não excede teto nenhum. Repassar a mensagem de paginação
    mandaria o usuário refinar uma busca que nunca chegou a ser feita."""
    prov = ProviderFalso(erro=PaginationLimitError(10_000, 1, 1, "OpenAlex"))

    dados, motivo = app._enriquecer_referencia(prov, OSTROM)

    assert dados["title"] is None
    assert motivo == "a referência não pôde ser convertida em consulta válida", motivo


def test_nenhum_resultado_e_reportado_e_nao_engolido(app):
    prov = ProviderFalso(corpos=[_pagina()])

    dados, motivo = app._enriquecer_referencia(prov, "Fulano F, 1899, Artigo que nao existe")

    assert motivo == "nenhum resultado no OpenAlex", motivo


# ── Credencial e teto: sobem, não viram "não identificado" ──────────────────────

@pytest.mark.parametrize("erro,nome", [
    (AuthError("u", 401, "OpenAlex"), "AuthError"),
    (RateLimitError("u"), "RateLimitError"),
])
def test_credencial_e_teto_interrompem_em_vez_de_sumir(app, erro, nome):
    """Devolver None para os dois apagava a segunda situação: a biblioteca inteira saía
    com "não identificado" e o usuário nunca saberia que a chave é que estava errada."""
    prov = ProviderFalso(erro=erro)

    with pytest.raises(type(erro)):
        app._enriquecer_referencia(prov, OSTROM)


def test_get_by_doi_deixa_a_credencial_subir(app):
    """O `except Exception` do `get_by_doi` transformava 401 em "DOI não encontrado"."""
    prov = ProviderFalso(erro=AuthError("u", 401, "OpenAlex"))

    with pytest.raises(AuthError):
        prov.get_by_doi("10.1234/abc")


def test_get_by_doi_continua_devolvendo_none_para_nao_encontrado(app):
    """O outro lado da mesma moeda: 404 não pode virar exceção."""
    prov = ProviderFalso(doi_corpo=None)

    assert prov.get_by_doi("10.1234/nao-existe") is None


# ── O caminho do app: o worker e o diálogo final ────────────────────────────────

def _rodar_worker(app, tmp_path, refs, monkeypatch, provider):
    """Roda o worker de verdade, capturando o diálogo que o usuário veria."""
    import main as blicsa

    visto = {}
    for tipo in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(f"tkinter.messagebox.{tipo}",
                            lambda t, m, _k=tipo: visto.update(tipo=_k, titulo=t, corpo=m))
    monkeypatch.setattr(blicsa.webbrowser, "open", lambda *a, **k: None)
    monkeypatch.setattr("core.sources.openalex.OpenAlexProvider",
                        lambda *a, **k: provider)
    monkeypatch.setattr(blicsa.BlicsaApp, "_set_idle", lambda self, *a: None)

    app._create_seminal_library_worker(tmp_path, refs)
    app.update()
    return visto


def test_o_worker_grava_o_titulo_encontrado_no_arquivo(app, tmp_path, monkeypatch):
    """O caminho inteiro: worker -> provider -> conferência -> arquivo em disco."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Governing the Commons: The Evolution of "
                                               "Institutions for Collective Action",
                                               "Resumo do Ostrom."))])

    _rodar_worker(app, tmp_path, [(OSTROM, 7)], monkeypatch, prov)

    escritos = list(tmp_path.glob("*_DESCRICAO.txt"))
    assert escritos, "nenhum arquivo de descrição foi gravado"
    texto = escritos[0].read_text(encoding="utf-8")
    assert "Governing the Commons" in texto, "o título encontrado não foi para o arquivo"
    assert "Resumo do Ostrom." in texto
    assert "Não identificado pela API OpenAlex" not in texto


def test_pendencias_aparecem_no_dialogo_em_vez_de_Sucesso(app, tmp_path, monkeypatch):
    """O `except Exception: pass` mais o "Sucesso" fixo foram o que escondeu por tanto
    tempo que a busca textual respondia 400 a cada chamada."""
    prov = ProviderFalso(corpos=[_pagina(), _pagina()])

    visto = _rodar_worker(app, tmp_path,
                          [("Fulano F, 1899, Artigo inexistente um", 3),
                           ("Beltrano B, 1888, Artigo inexistente dois", 2)],
                          monkeypatch, prov)

    assert visto["tipo"] == "showwarning", (
        f"anunciou {visto['tipo']} com 2 de 2 referências não resolvidas")
    assert "2 de 2" in visto["corpo"], visto["corpo"]
    assert "nenhum resultado no OpenAlex" in visto["corpo"]


def test_tudo_resolvido_ainda_anuncia_sucesso(app, tmp_path, monkeypatch):
    """A correção não pode transformar sucesso legítimo em alarme."""
    prov = ProviderFalso(corpos=[_pagina(_obra("Governing the Commons: The Evolution of "
                                               "Institutions for Collective Action",
                                               "Resumo."))])

    visto = _rodar_worker(app, tmp_path, [(OSTROM, 4)], monkeypatch, prov)

    assert visto["tipo"] == "showinfo", visto
    assert "Sucesso" in visto["titulo"]


def test_credencial_recusada_interrompe_e_diz_o_que_houve(app, tmp_path, monkeypatch):
    """Sem isto, 300 referências levariam 300 vezes o mesmo 401 e o diálogo diria
    "Sucesso" com 300 arquivos vazios de metadados."""
    from core.i18n import t

    prov = ProviderFalso(erro=AuthError("u", 401, "OpenAlex"))

    visto = _rodar_worker(app, tmp_path, [(OSTROM, 5), (VOSVIEWER, 4)], monkeypatch, prov)

    assert visto["tipo"] == "showwarning", visto
    assert t("search.error_auth", fonte="OpenAlex")[:40] in visto["corpo"], visto["corpo"]
    assert len(prov.urls) == 1, (
        f"insistiu depois do 401 em vez de parar na primeira: {len(prov.urls)} requisições")


# ── 401 como erro reconhecido, distinto de falha de rede ────────────────────────

def test_401_vira_AuthError_e_nao_e_repetido():
    """401 não estava na lista de retry nem virava tipo próprio: subia como HTTPError cru,
    indistinguível de qualquer outra falha, depois de três tentativas inúteis."""
    tentativas = {"n": 0}

    class Prov(OpenAlexProvider):
        def _abrir(self, url):
            tentativas["n"] += 1
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    prov = Prov(api_key="")

    import urllib.request
    original = urllib.request.urlopen

    def _falso(req, timeout=None):
        tentativas["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    urllib.request.urlopen = _falso
    try:
        with pytest.raises(AuthError) as exc:
            prov.count("x")
    finally:
        urllib.request.urlopen = original

    assert tentativas["n"] == 1, f"repetiu uma credencial recusada {tentativas['n']} vezes"
    assert exc.value.codigo == 401
    assert exc.value.fonte == "OpenAlex", "a mensagem não diz qual chave conferir"


def test_401_e_distinto_de_limite_e_de_falha_de_rede():
    """Três situações, três tipos, três ações do usuário: conferir a chave, esperar, ou
    checar a conexão. Um `IOError` genérico para as três apagaria a diferença."""
    assert not issubclass(AuthError, RateLimitError)
    assert not issubclass(RateLimitError, AuthError)
    assert AuthError.i18n_key != RateLimitError.i18n_key


def test_429_continua_sendo_repetido_e_nao_virou_AuthError():
    """Adversarial sobre a própria correção: mover o 401 para fora do retry não pode ter
    levado o 429 junto — ali a repetição com backoff é o comportamento certo."""
    tentativas = {"n": 0}
    prov = OpenAlexProvider(api_key="")

    import urllib.request
    original = urllib.request.urlopen

    def _falso(req, timeout=None):
        tentativas["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    urllib.request.urlopen = _falso
    try:
        with pytest.raises(RateLimitError):
            prov.count("x")
    finally:
        urllib.request.urlopen = original

    assert tentativas["n"] == 3, f"o 429 deixou de ser repetido ({tentativas['n']})"


def test_mensagem_do_401_existe_nos_tres_idiomas():
    """A mensagem precisa dizer que a CREDENCIAL foi recusada, não "erro de rede"."""
    from pathlib import Path

    raiz = Path(__file__).parent.parent
    for idioma in ("pt_BR", "en", "fr"):
        cat = json.loads((raiz / "locales" / f"{idioma}.json").read_text(encoding="utf-8"))
        assert "search.error_auth" in cat, f"{idioma}: falta search.error_auth"
        texto = cat["search.error_auth"]
        assert "{fonte}" in texto, f"{idioma}: a mensagem não diz de qual fonte é a chave"
        assert "401" in texto, f"{idioma}: a mensagem não identifica o código"


def test_a_dica_da_chave_openalex_fala_do_ganho_de_franquia():
    """A dica dizia "amplia o limite diário", como se fosse detalhe para quem esbarra. Com
    o fim do polite pool, a chave é o que separa 1.000 de 10.000 créditos por dia."""
    from pathlib import Path

    raiz = Path(__file__).parent.parent
    for idioma in ("pt_BR", "en", "fr"):
        cat = json.loads((raiz / "locales" / f"{idioma}.json").read_text(encoding="utf-8"))
        dica = cat["settings.openalex_key_hint"]
        assert "10" in dica and ("1.000" in dica or "1,000" in dica or "1 000" in dica), (
            f"{idioma}: a dica não quantifica o ganho: {dica!r}")


# ── Rede real: estrutura correta não é comportamento correto ────────────────────

@pytest.mark.live
def test_live_a_busca_textual_corrigida_encontra_o_artigo():
    """A prova de que o `per_page` conserta o que o `limit` quebrava — na API de verdade.

    Este é o teste que a versão anterior desta correção não teria passado: ela montava a
    consulta com os nomes dos autores juntos, o que afunda a relevância, e devolvia
    "Bibliometric mapping of computer and information ethics" para a referência do
    VOSviewer. Em qualquer dublê teria ficado verde.
    """
    import main as blicsa

    app = blicsa.BlicsaApp.__new__(blicsa.BlicsaApp)
    dados, motivo = app._enriquecer_referencia(OpenAlexProvider(), VOSVIEWER)

    assert motivo in ("", "resumo não disponível no OpenAlex"), motivo
    assert "VOSviewer" in (dados["title"] or ""), (
        f"achou outro artigo: {dados['title']!r}")


@pytest.mark.live
def test_live_o_mailto_sozinho_nao_da_mais_franquia():
    """O polite pool acabou em fevereiro de 2026. Este teste é a evidência viva: se um dia
    o `mailto` voltar a valer, ele fica vermelho e a dica da chave precisa ser reescrita."""
    import urllib.request

    base = "https://api.openalex.org/works?per_page=1"
    limites = {}
    for nome, url, ua in (("com_mailto", base + "&mailto=blicsa.app@gmail.com",
                           "Blicsa/1.0 (mailto:blicsa.app@gmail.com)"),
                          ("sem_mailto", base, "python-urllib/3")):
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=20) as r:
            limites[nome] = r.headers.get("X-RateLimit-Limit")

    assert limites["com_mailto"] == limites["sem_mailto"], (
        f"o mailto voltou a mudar a franquia: {limites}")


@pytest.mark.live
def test_live_chave_invalida_devolve_401_e_nao_degrada_para_anonimo():
    """O que justifica o `AuthError`: uma chave errada não cai para o acesso gratuito, ela
    derruba a requisição. Um caractere a menos no campo dos Ajustes tirava a busca do ar."""
    prov = OpenAlexProvider(api_key="chave_que_nao_existe_123")

    with pytest.raises(AuthError) as exc:
        prov.count("bibliometrics")

    assert exc.value.codigo == 401
