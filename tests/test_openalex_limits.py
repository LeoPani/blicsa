"""Os dois limites de resultados do OpenAlex, que são de naturezas diferentes.

* **Importação** (`search`) usa cursor: `cursor=*` seguindo `next_cursor` até o fim. **Não tem
  teto.** Um conjunto de 25.000 registros tem que voltar com 25.000.
* **Navegação** (`browse`) usa `page`: a API recusa `page × per_page > 10.000`. O teto existe e
  não dá para contorná-lo — o que dá é **avisar direito**, dizendo que a importação alcança o
  conjunto inteiro, em vez de erro genérico ou página em branco.

Todos os testes são offline, com fixtures sintéticas geradas aqui. O único que toca a rede está
marcado `live` e é desmarcado por padrão.
"""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from core.browse import BrowseSession
from core.sources.base import PaginationLimitError
from core.sources.openalex import OpenAlexProvider


def _resposta(corpo: str):
    """Resposta HTTP falsa no mesmo formato que o resto da suíte usa.

    Precisa de `headers`: o provider lê os cabeçalhos de orçamento da API a cada resposta,
    e um objeto sem eles cai no `except Exception` genérico do `fetch_url`, que faz 3
    tentativas com backoff e devolve "Failed to fetch" — um teste que falharia por motivo
    errado, depois de 7 segundos dormindo.
    """
    m = MagicMock()
    m.read.return_value = corpo.encode("utf-8")
    m.headers = {}
    m.__enter__.return_value = m
    return m


# ── fixture sintética: um universo de N registros paginado por cursor ──────────────

class FakeOpenAlex:
    """API do OpenAlex falsa, com paginação por cursor fiel ao contrato real.

    Fiel de propósito nos detalhes que já morderam este código:
    * `next_cursor` **ausente** na última página (não `None`, não string vazia);
    * `meta.count` é o total do universo, não o da página;
    * o cursor é opaco — quem consome não pode inferir posição a partir dele.
    """

    def __init__(self, total: int, per_page_max: int = 200):
        self.total = total
        self.per_page_max = per_page_max
        self.urls: list[str] = []
        self.paginas_servidas = 0

    def __call__(self, req, *a, **kw):
        url = getattr(req, "full_url", str(req))
        self.urls.append(url)
        self.paginas_servidas += 1

        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(url).query)
        per_page = min(int(q.get("per_page", ["25"])[0]), self.per_page_max)
        cursor = q.get("cursor", ["*"])[0]

        inicio = 0 if cursor == "*" else int(cursor)
        fim = min(inicio + per_page, self.total)
        # `title` e `doi` únicos por índice: `_normalize_work` descarta o `id` do OpenAlex,
        # então a identidade do registro no teste tem que vir de campos que sobrevivem à
        # normalização — senão "25.000 registros distintos" viraria vacuamente verdadeiro.
        results = [{"id": f"https://openalex.org/W{i}",
                    "title": f"Trabalho {i}",
                    "display_name": f"Trabalho {i}",
                    "doi": f"https://doi.org/10.1234/w{i}",
                    "publication_year": 2020,
                    "authorships": [], "primary_location": {},
                    "cited_by_count": 0}
                   for i in range(inicio, fim)]

        meta = {"count": self.total, "per_page": per_page}
        if fim < self.total:
            meta["next_cursor"] = str(fim)      # ausente na última página, como na API real

        return _resposta(json.dumps({"meta": meta, "results": results}))


# ── 1. Importação por cursor: sem teto ────────────────────────────────────────────

def test_importacao_por_cursor_traz_os_25000():
    """25.000 registros pedidos, 25.000 entregues. É o número que 'ilimitado' promete.

    Se a importação usasse `page`, ela pararia em 10.000 — este teste é a guarda contra
    alguém trocar o cursor por paginação numerada de novo."""
    fake = FakeOpenAlex(total=25_000)
    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("bibliometria", max_results=25_000))

    assert len(registros) == 25_000, f"esperava 25000, veio {len(registros)}"
    # Sem duplicatas nem buracos: o cursor avançou certo, página por página.
    titulos = {r.get("title") for r in registros}
    assert len(titulos) == 25_000, "houve registro repetido ou perdido no avanço do cursor"
    assert titulos == {f"Trabalho {i}" for i in range(25_000)}, "faltou ou sobrou registro"
    # 25.000 ÷ 200 por página = 125 requisições.
    assert fake.paginas_servidas == 125, f"páginas: {fake.paginas_servidas}"


def test_importacao_nunca_manda_o_parametro_page():
    """O contrato do item 2: nenhuma URL da importação pode conter `page=`.

    `per_page` é legítimo e contém a substring "page", então a checagem olha os parâmetros
    de verdade em vez de fazer `"page" in url` — que passaria sempre."""
    from urllib.parse import urlparse, parse_qs

    fake = FakeOpenAlex(total=3_000)
    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        list(prov.search("x", max_results=3_000))

    assert fake.urls, "a importação não fez requisição nenhuma"
    for url in fake.urls:
        params = parse_qs(urlparse(url).query)
        assert "page" not in params, f"importação usou paginação numerada: {url}"
        assert "cursor" in params, f"importação sem cursor: {url}"
    # A primeira requisição abre o cursor; as seguintes usam o token devolvido.
    assert parse_qs(urlparse(fake.urls[0]).query)["cursor"] == ["*"]


def test_importacao_passa_de_10000_sem_tropecar():
    """A fronteira que derruba a navegação não existe aqui: 10.001 é só mais um registro."""
    fake = FakeOpenAlex(total=10_001)
    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=10_000_000))
    assert len(registros) == 10_001


def test_importacao_para_quando_a_fixture_acaba_antes_do_pedido():
    """Adversarial: pediram 25.000, a base só tem 700. Para em 700, sem laço infinito."""
    fake = FakeOpenAlex(total=700)
    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=25_000))
    assert len(registros) == 700
    assert prov.stop_reason and "cursor encerrado" in prov.stop_reason


def test_importacao_nao_entra_em_laco_com_cursor_repetido():
    """Adversarial: API defeituosa devolvendo SEMPRE o mesmo `next_cursor`.

    Sem a guarda `next_cursor == params['cursor']`, isto rodaria para sempre."""
    class CursorTravado(FakeOpenAlex):
        """Serve SEMPRE a primeira página e SEMPRE o mesmo `next_cursor`.

        A fixture precisa continuar respondendo com sucesso — se ela estourar ao ver o
        cursor opaco, o teste passa a exercitar o tratamento de erro de rede e a guarda do
        laço nunca chega a ser testada."""
        def __call__(self, req, *a, **kw):
            self.urls.append(getattr(req, "full_url", str(req)))
            self.paginas_servidas += 1
            results = [{"title": f"Trabalho {i}", "display_name": f"Trabalho {i}",
                        "doi": f"https://doi.org/10.1234/w{i}", "publication_year": 2020,
                        "authorships": [], "primary_location": {}, "cited_by_count": 0}
                       for i in range(200)]
            return _resposta(json.dumps(
                {"meta": {"count": self.total, "next_cursor": "TRAVADO"}, "results": results}))

    fake = CursorTravado(total=25_000)
    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=25_000))

    assert fake.paginas_servidas <= 3, "não parou no cursor repetido — risco de laço infinito"
    assert prov.stop_reason and "cursor encerrado" in prov.stop_reason
    assert len(registros) < 25_000


# ── 2. Navegação: teto de 10.000 com mensagem própria ─────────────────────────────

def test_provider_declara_o_teto_da_navegacao():
    assert OpenAlexProvider.BROWSE_MAX_RESULTS == 10_000
    # Base sem teto declarado continua em 0 (= sem teto), para não afetar outros providers.
    from core.sources.base import SearchProvider
    assert SearchProvider.BROWSE_MAX_RESULTS == 0


def test_pagina_400_passa_e_401_avisa():
    """A fronteira exata com 25 por página: 400 × 25 = 10.000 é a última permitida.

    Os dois lados da guarda no mesmo teste — se ela fosse `>=` em vez de `>`, a página 400
    (legítima) seria recusada; se não existisse, a 401 devolveria erro genérico."""
    fake = FakeOpenAlex(total=500_000)
    prov = OpenAlexProvider()

    with patch("urllib.request.urlopen", side_effect=fake):
        registros, total = prov.browse("x", page=400, per_page=25)
    assert total == 500_000
    assert registros, "a página 400 é legítima e não pode ser recusada"

    with pytest.raises(PaginationLimitError) as exc:
        prov.browse("x", page=401, per_page=25)
    assert exc.value.i18n_key == "browse.error_page_limit"
    assert exc.value.limite == 10_000


def test_teto_nao_gasta_requisicao():
    """Pedir além do teto não pode consumir crédito: o teto é conhecido de antemão."""
    prov = OpenAlexProvider()
    with patch("urllib.request.urlopen") as mock:
        with pytest.raises(PaginationLimitError):
            prov.browse("x", page=999, per_page=25)
    assert mock.call_count == 0, "gastou requisição para receber um 400 previsível"


def test_fronteira_acompanha_o_per_page():
    """O teto é `page × per_page`, não um número fixo de páginas: com 200 por página a
    fronteira cai na página 50, não na 400."""
    prov = OpenAlexProvider()
    fake = FakeOpenAlex(total=500_000)
    with patch("urllib.request.urlopen", side_effect=fake):
        registros, _ = prov.browse("x", page=50, per_page=200)
    assert registros, "50 × 200 = 10.000 ainda é permitido"

    with pytest.raises(PaginationLimitError):
        prov.browse("x", page=51, per_page=200)


def test_paginator_devolve_a_mensagem_e_mantem_o_total():
    """O que a UI recebe: `error_key` traduzível e o total preservado.

    O total importa — é o que dá sentido a "refine a busca ou importe o conjunto completo"."""
    fake = FakeOpenAlex(total=319_300)
    prov = OpenAlexProvider()
    pag = BrowseSession(prov, query="bibliometria", per_page=25)

    with patch("urllib.request.urlopen", side_effect=fake):
        primeira = pag.fetch_page(1)
    assert primeira.total == 319_300

    with patch("urllib.request.urlopen", side_effect=fake) as mock:
        limite = pag.fetch_page(401)
    assert limite.error_key == "browse.error_page_limit"
    assert limite.total == 319_300, "o total sumiu — a sugestão de importar perde o sentido"
    assert limite.records == [], "não pode vir registro junto do estado de erro"
    assert mock.call_count == 0


def test_mensagem_existe_nos_tres_idiomas_e_diz_o_que_fazer():
    """Mensagem via t(), nunca erro genérico — e tem que carregar os TRÊS elementos.

    A primeira versão deste teste só procurava a substring "import" em qualquer lugar do
    texto, e a mensagem a menciona duas vezes: apagar a sugestão de importar deixava o teste
    verde. Exigir os três conceitos separadamente é o que faz dele uma guarda de verdade.
    """
    import json as _json

    # Por idioma: o número do limite, o termo de "refinar" e o termo de "importar".
    EXIGIDO = {
        "pt_BR": ("10.000", ("refine", "refinar"), ("importe", "importar")),
        "en":    ("10,000", ("refine", "refining"), ("import",)),
        "fr":    ("10 000", ("affinez", "affiner"), ("importez", "importer")),
    }

    for loc, (numero, refinar, importar) in EXIGIDO.items():
        with open(f"locales/{loc}.json", encoding="utf-8") as f:
            txt = _json.load(f).get("browse.error_page_limit", "")
        baixo = txt.lower()

        assert txt, f"{loc}: chave ausente"
        assert numero in txt, f"{loc}: não diz qual é o limite ({numero})"
        assert any(p in baixo for p in refinar), \
            f"{loc}: não sugere refinar a busca — {refinar}"
        assert any(p in baixo for p in importar), \
            f"{loc}: não sugere importar o conjunto completo — {importar}"
        # Erro genérico é curto por natureza; a explicação acionável, não.
        assert len(txt) > 120, f"{loc}: mensagem curta demais para explicar a saída"


def test_http_400_da_api_vira_a_mesma_mensagem():
    """Rede de segurança: se o teto da API mudar e o pré-cheque ficar defasado, o 400 ainda
    tem que virar a mensagem explicativa — nunca 'Failed to fetch https://...'."""
    prov = OpenAlexProvider()
    prov.BROWSE_MAX_RESULTS = 0          # simula o pré-cheque desligado/defasado
    erro = urllib.error.HTTPError("https://api.openalex.org/works", 400, "Bad Request", {}, None)

    with patch("urllib.request.urlopen", side_effect=erro):
        with pytest.raises(PaginationLimitError) as exc:
            prov.browse("x", page=9999, per_page=25)
    assert exc.value.i18n_key == "browse.error_page_limit"


def test_outros_erros_http_nao_viram_limite_de_pagina():
    """O outro lado: só o 400 vira PaginationLimitError. Um 404 continua sendo um 404 —
    senão qualquer falha da API viraria "refine sua busca", escondendo o problema real."""
    prov = OpenAlexProvider()
    prov.BROWSE_MAX_RESULTS = 0
    erro = urllib.error.HTTPError("https://api.openalex.org/works", 404, "Not Found", {}, None)

    with patch("urllib.request.urlopen", side_effect=erro):
        with pytest.raises(urllib.error.HTTPError):
            prov.browse("x", page=2, per_page=25)


# ── 3. Teste live (desmarcado por padrão) ─────────────────────────────────────────

@pytest.mark.live
def test_live_cursor_avanca_alem_de_10000():
    """Contra a API real: o cursor passa da fronteira que derruba a navegação.

    Pequeno de propósito — pede 10.050 registros de um universo grande, o suficiente para
    cruzar os 10.000 e nada além disso. Roda com `-m live`."""
    prov = OpenAlexProvider()
    registros = list(prov.search("bibliometrics", max_results=10_050))

    assert len(registros) > 10_000, (
        f"o cursor parou em {len(registros)} — se parou exatamente em 10.000, "
        "a importação voltou a usar paginação numerada")
    assert prov.total_available > 10_050


# ── 4. Pager: anuncia só o que existe ─────────────────────────────────────────────

def test_pager_anuncia_paginas_navegaveis_nao_as_teoricas():
    """366.949 resultados dariam 14.678 páginas de 25; só 400 abrem. O pager anuncia 400.

    Os dois lados: `pages` continua sendo a conta bruta (o cabeçalho precisa dela para dizer
    quantos resultados existem), `navigable_pages` é o que o pager pode oferecer."""
    from core.browse import Page

    p = Page(total=366_949, per_page=25, browse_max=10_000)
    assert p.pages == 14_678, "a conta bruta não pode mudar"
    assert p.navigable_pages == 400, "o pager tem que anunciar 400, não 14.678"
    assert p.clipped is True


def test_pager_sem_teto_anuncia_tudo():
    """Provider sem teto declarado: navegáveis == teóricas, e o rótulo não muda."""
    from core.browse import Page

    p = Page(total=366_949, per_page=25, browse_max=0)
    assert p.navigable_pages == p.pages == 14_678
    assert p.clipped is False


def test_pager_busca_pequena_nao_e_cortada():
    """O outro lado da guarda: 300 resultados cabem folgado no teto — nada de "navegáveis"."""
    from core.browse import Page

    p = Page(total=300, per_page=25, browse_max=10_000)
    assert p.navigable_pages == p.pages == 12
    assert p.clipped is False, "busca pequena não pode ganhar o rótulo de cortada"


def test_pager_acompanha_o_per_page():
    """Com 200 por página o teto vira 50 páginas, não 400."""
    from core.browse import Page

    assert Page(total=366_949, per_page=200, browse_max=10_000).navigable_pages == 50
    assert Page(total=366_949, per_page=100, browse_max=10_000).navigable_pages == 100


def test_pager_nunca_devolve_zero_paginas():
    """Adversarial: total 0 e per_page maior que o teto não podem zerar o pager."""
    from core.browse import Page

    assert Page(total=0, per_page=25, browse_max=10_000).navigable_pages == 1
    assert Page(total=5, per_page=999_999, browse_max=10_000).navigable_pages == 1


def test_sessao_propaga_o_teto_para_a_pagina():
    """O teto sai do provider e chega à Page sem ninguém precisar passar à mão."""
    fake = FakeOpenAlex(total=366_949)
    sess = BrowseSession(OpenAlexProvider(), query="x", per_page=25)
    with patch("urllib.request.urlopen", side_effect=fake):
        p = sess.fetch_page(1)
    assert p.browse_max == 10_000
    assert p.navigable_pages == 400 and p.pages == 14_678

    # Também na página vinda do cache: sem isso o pager mudaria de rótulo ao voltar.
    with patch("urllib.request.urlopen", side_effect=fake):
        cacheada = sess.fetch_page(1)
    assert cacheada.navigable_pages == 400, "página do cache perdeu o teto"
