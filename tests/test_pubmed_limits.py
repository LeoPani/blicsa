"""O teto do PubMed: o que dá para eliminar e o que é da API.

O defeito era a importação mandar UMA ESearch com `retmax=max_results` e ficar com a lista de
PMIDs: pedir 25.000 devolvia 10.000 **sem aviso nenhum**, com `stop_reason = "atingiu limite"`
— indistinguível de um limite que o usuário tivesse pedido.

A hipótese de trabalho era que `usehistory=y` + paginação por WebEnv removeria o teto, como o
cursor removeu no OpenAlex. **Ela foi refutada contra a API real** (2026-08-04): o EFetch
recusa `retstart >= 9999` mesmo com histórico válido, e o NCBI responde por escrito que 9.999
é o máximo para PubMed, sugerindo o EDirect para ir além.

O que ficou, então:

* `usehistory=y` continua (uma ESearch só, sem trafegar lista de PMIDs — mais barato);
* o teto de 9.999 é da API e **não é mais silencioso**: `truncated_by_api` + trilha nomeando
  o NCBI, com o total real da base preservado;
* a navegação tem o mesmo teto e agora dá a mesma mensagem honesta do OpenAlex, com o nome
  da fonte trocado.
"""

import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from core.sources.base import PaginationLimitError
from core.sources.pubmed import (PUBMED_EFETCH_BATCH, PUBMED_MAX_FETCHABLE,
                                 PubMedProvider)


@pytest.fixture(autouse=True)
def _sem_espera_de_rate_limit(request):
    """Anula a pausa de 0,35 s por requisição (limite de 3/s do NCBI) nos testes offline.

    Uma importação de 25.000 são 125 EFetch: 44 segundos dormindo sem verificar nada. A
    pausa é do cliente HTTP e não participa da lógica sob teste. O teste `live` fica de
    fora — lá a conversa é com o NCBI de verdade e respeitar o limite é obrigatório.
    """
    if request.node.get_closest_marker("live"):
        yield
        return
    with patch("core.sources.base.time.sleep", lambda *_a, **_k: None):
        yield


def _resposta(corpo: str):
    m = MagicMock()
    m.read.return_value = corpo.encode("utf-8")
    m.headers = {}
    m.__enter__.return_value = m
    return m


def _medline(inicio: int, quantos: int) -> str:
    """Bloco MEDLINE com `quantos` registros a partir de `inicio`."""
    blocos = []
    for i in range(inicio, inicio + quantos):
        blocos.append(
            f"PMID- {100000 + i}\n"
            f"TI  - Estudo {i}\n"
            f"AU  - Autor {i}\n"
            f"DP  - 2021\n"
            f"JT  - Revista Sintética\n"
            f"AID - 10.9999/p{i} [doi]\n"
            f"AB  - Resumo do estudo {i}.\n"
        )
    return "\n".join(blocos) + "\n"


class FakePubMed:
    """E-utilities falso com histórico, fiel ao contrato real do NCBI.

    Detalhes que importam e que o código já dependeu:
    * o `retmode=json` devolve as chaves em MINÚSCULAS (`webenv`, `querykey`);
    * com `usehistory=y` e `retmax=0` o `idlist` vem **vazio** — os PMIDs ficam no servidor;
    * o EFetch pagina por `retstart`/`retmax` sobre o conjunto do histórico;
    * passado o fim do conjunto, o EFetch devolve corpo vazio (não erro).
    """

    def __init__(self, total: int, com_historico: bool = True):
        self.total = total
        self.com_historico = com_historico
        self.esearches = 0
        self.efetches = 0
        self.urls: list[str] = []

    def __call__(self, req, *a, **kw):
        url = getattr(req, "full_url", str(req))
        self.urls.append(url)
        q = parse_qs(urlparse(url).query)

        if "esearch" in url:
            self.esearches += 1
            res = {"count": str(self.total), "idlist": []}
            if self.com_historico and q.get("usehistory", [""])[0] == "y":
                res["webenv"] = "NCID_FAKE_1"
                res["querykey"] = "1"
            else:
                # Sem histórico: devolve a fatia de PMIDs pedida, limitada pelo teto do NCBI.
                inicio = int(q.get("retstart", ["0"])[0])
                quantos = min(int(q.get("retmax", ["0"])[0]), max(0, 10_000 - inicio))
                res["idlist"] = [str(100000 + i) for i in range(inicio, inicio + quantos)]
            return _resposta(json.dumps({"esearchresult": res}))

        self.efetches += 1
        inicio = int(q.get("retstart", ["0"])[0])
        pedidos = int(q.get("retmax", ["0"])[0] or 0)
        if "id" in q:                      # caminho degradado: EFetch por lista de PMIDs
            ids = q["id"][0].split(",")
            return _resposta(_medline(int(ids[0]) - 100000, len(ids)))
        quantos = max(0, min(pedidos, self.total - inicio))
        return _resposta(_medline(inicio, quantos) if quantos else "")


# ── 1. Importação: o teto de 10.000 deixou de existir ─────────────────────────────

def test_teto_da_api_e_9999_e_nao_e_silencioso():
    """O teto do PubMed **não** foi eliminado — ele é da API e `usehistory=y` não o remove.

    Medido contra o NCBI em 2026-08-04: `retstart=10000` devolve HTTP 400 com
    "'retstart' cannot be larger than 9998. For PubMed, ESearch can only retrieve the first
    9,999 records matching the query."

    O que MUDOU, e é o que este teste protege: o corte deixou de ser silencioso. Antes
    voltavam 10.000 com `stop_reason = "atingiu limite"` — indistinguível de um limite que o
    usuário tivesse pedido. Agora a trilha nomeia o NCBI e o total real continua visível."""
    fake = FakePubMed(total=25_000)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("cancer", max_results=25_000))

    assert len(registros) == PUBMED_MAX_FETCHABLE == 9_999
    assert prov.truncated_by_api is True, "o corte pela API tem que ser sinalizado"
    assert "teto do PubMed" in prov.stop_reason and "NCBI" in prov.stop_reason
    assert "atingiu limite" not in prov.stop_reason, "não pode se disfarçar de limite do usuário"
    assert prov.total_available == 25_000, "o total real da base continua visível"
    assert len(prov.stop_reason) <= 90, "a trilha corta em 90 caracteres"
    assert fake.esearches == 1, "o histórico existe para NÃO repetir a ESearch"


def test_abaixo_do_teto_nao_marca_truncagem():
    """O outro lado da guarda: 5.000 numa base de 25.000 é limite do usuário, não da API."""
    fake = FakePubMed(total=25_000)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=5_000))
    assert len(registros) == 5_000
    assert prov.truncated_by_api is False
    assert prov.stop_reason == "atingiu limite"


def test_esearch_pede_historico_e_nao_pede_pmids():
    """O contrato da correção: `usehistory=y` e `retmax=0` na ESearch.

    `retmax=0` é o que torna a requisição barata — e é justamente o `retmax` grande que o
    NCBI truncava em 10.000."""
    fake = FakePubMed(total=500)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        list(prov.search("x", max_results=500))

    q = parse_qs(urlparse(fake.urls[0]).query)
    assert "esearch" in fake.urls[0]
    assert q["usehistory"] == ["y"], "a ESearch não pediu histórico"
    assert q["retmax"] == ["0"], "a ESearch voltou a pedir a lista inteira de PMIDs"


def test_efetch_pagina_pelo_historico():
    """Cada EFetch carrega WebEnv/query_key e avança `retstart` — nunca lista de PMIDs."""
    fake = FakePubMed(total=600)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        list(prov.search("x", max_results=600))

    efetches = [u for u in fake.urls if "efetch" in u]
    assert len(efetches) == 3
    starts = []
    for u in efetches:
        q = parse_qs(urlparse(u).query)
        assert q["WebEnv"] == ["NCID_FAKE_1"]
        assert q["query_key"] == ["1"]
        assert "id" not in q, "EFetch pelo histórico não manda lista de PMIDs"
        starts.append(int(q["retstart"][0]))
    assert starts == [0, 200, 400], f"retstart não avançou direito: {starts}"


def test_fronteira_exata_do_teto():
    """9.999 passa inteiro; 10.000 é onde a API corta — os dois lados da mesma guarda."""
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=FakePubMed(total=9_999)):
        registros = list(prov.search("x", max_results=10_000_000))
    assert len(registros) == 9_999
    assert prov.truncated_by_api is False, "9.999 cabe: não é truncagem"

    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=FakePubMed(total=10_000)):
        registros = list(prov.search("x", max_results=10_000_000))
    assert len(registros) == 9_999
    assert prov.truncated_by_api is True, "10.000 não cabe: é truncagem e tem que aparecer"


def test_limite_pedido_continua_valendo():
    """O outro lado: tirar o teto da API não é ignorar o limite que o usuário pediu."""
    fake = FakePubMed(total=25_000)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=350))
    assert len(registros) == 350
    assert prov.stop_reason == "atingiu limite"
    assert prov.truncated_by_api is False
    assert prov.total_available == 25_000, "o total da base tem que sobreviver ao limite"


def test_base_menor_que_o_pedido_para_sem_laco():
    """Adversarial: pediram 25.000, a base tem 450."""
    fake = FakePubMed(total=450)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=25_000))
    assert len(registros) == 450
    assert "exauriu" in prov.stop_reason


def test_efetch_vazio_no_meio_nao_vira_laco_infinito():
    """Adversarial: o histórico expira e o EFetch passa a devolver corpo vazio.

    Sem a saída por lote vazio, `retstart` nunca avançaria e o laço giraria para sempre."""
    class HistoricoExpira(FakePubMed):
        def __call__(self, req, *a, **kw):
            url = getattr(req, "full_url", str(req))
            if "efetch" in url and self.efetches >= 2:
                self.efetches += 1
                self.urls.append(url)
                return _resposta("")
            return super().__call__(req, *a, **kw)

    fake = HistoricoExpira(total=25_000)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=25_000))

    assert len(registros) == 400, "devia ter os 2 lotes servidos antes de expirar"
    assert fake.efetches <= 4, "não parou no lote vazio — risco de laço infinito"
    assert "exauriu" in prov.stop_reason


def test_sem_resultado_nenhum_nao_faz_efetch():
    fake = FakePubMed(total=0)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("termo impossível", max_results=1000))
    assert registros == []
    assert fake.efetches == 0, "gastou EFetch para um conjunto vazio"
    assert prov.stop_reason == "exauriu (sem resultados)"


def test_sem_historico_degrada_mas_diz_que_degradou():
    """Adversarial: o NCBI não devolve WebEnv. O teto volta — e a trilha ADMITE isso.

    É a diferença entre o defeito antigo e um limite aceitável: truncar em silêncio
    escondia; truncar dizendo o motivo deixa o usuário decidir."""
    fake = FakePubMed(total=25_000, com_historico=False)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros = list(prov.search("x", max_results=25_000))

    assert len(registros) == PUBMED_MAX_FETCHABLE, "sem histórico o teto do NCBI é real"
    assert "histórico do PubMed indisponível" in prov.stop_reason, (
        "o motivo específico da degradação tem que vencer o motivo genérico do teto")
    assert prov.total_available == 25_000, "o total real continua visível"


def test_registros_do_historico_tem_o_mesmo_formato_de_sempre():
    """A reescrita trocou o parser embutido pelo `_record_from_medline` compartilhado —
    o formato do registro não pode ter mudado junto."""
    fake = FakePubMed(total=1)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        (r,) = list(prov.search("x", max_results=1))

    assert set(r) == {"authors", "title", "year", "source", "keywords", "document_type", "abstract",
                      "citations", "doi", "references", "origin", "language",
                      "is_oa", "oa_url"}
    assert r["title"] == "Estudo 0"
    assert r["year"] == 2021
    assert r["doi"] == "10.9999/p0"
    assert r["origin"] == "PubMed"


# ── 2. Navegação: teto real, mensagem honesta ─────────────────────────────────────

def test_navegacao_declara_teto_e_avisa_na_fronteira():
    """Mesma regra do OpenAlex: 400 × 25 passa, 401 × 25 avisa."""
    assert PubMedProvider.BROWSE_MAX_RESULTS == 10_000

    fake = FakePubMed(total=500_000)
    prov = PubMedProvider()
    with patch("urllib.request.urlopen", side_effect=fake):
        registros, total = prov.browse("x", page=100, per_page=100)
    assert total == 500_000 and registros, "100 × 100 = 10.000 ainda é navegável"

    with patch("urllib.request.urlopen") as mock:
        with pytest.raises(PaginationLimitError) as exc:
            prov.browse("x", page=101, per_page=100)
    assert mock.call_count == 0, "gastou requisição para um limite já conhecido"
    assert exc.value.i18n_key == "browse.error_page_limit"


def test_mensagem_nomeia_a_fonte_certa():
    """A mesma chave i18n serve as duas fontes; o que muda é o nome — e ele tem que estar
    certo, senão a mensagem do PubMed falaria de OpenAlex."""
    from core.browse import error_i18n_args
    from core.i18n import get_lang, set_lang, t
    from core.sources.openalex import OpenAlexProvider

    original = get_lang()
    try:
        set_lang("pt_BR")
        for prov, nome in ((PubMedProvider(), "PubMed"), (OpenAlexProvider(), "OpenAlex")):
            with pytest.raises(PaginationLimitError) as exc:
                prov.browse("x", page=9999, per_page=100)
            args = error_i18n_args(exc.value)
            assert args == {"fonte": nome}
            texto = t("browse.error_page_limit", **args)
            assert texto.startswith(f"O {nome} permite navegar")
            assert "{fonte}" not in texto, "o parâmetro não foi substituído"
    finally:
        set_lang(original)


@pytest.mark.live
def test_live_pubmed_para_em_9999_e_avisa():
    """Contra o NCBI real: o teto é 9.999 e o app o comunica em vez de esconder.

    Este teste começou como "passa dos 10.000" — a hipótese de que `usehistory=y` removeria
    o teto. Ele reprovou contra a API real (HTTP 400 no lote com `retstart=10000`), e o
    NCBI respondeu por escrito que 9.999 é o máximo para PubMed. O teste agora protege o
    comportamento verdadeiro: colher o máximo possível e DIZER que houve corte."""
    prov = PubMedProvider()
    registros = list(prov.search("cancer", max_results=10_050))

    assert len(registros) == PUBMED_MAX_FETCHABLE, (
        f"colheu {len(registros)}; o teto medido da API é {PUBMED_MAX_FETCHABLE}")
    assert prov.truncated_by_api is True
    assert prov.stop_error is False, "teto da API não é erro de rede"
    assert prov.total_available > 1_000_000, "a base de 'cancer' é grande; total real perdido?"
    assert "histórico do PubMed indisponível" not in (prov.stop_reason or "")
