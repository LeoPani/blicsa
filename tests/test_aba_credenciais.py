"""A aba de Credenciais como FONTE ÚNICA — e a dispersão que ela substitui.

Antes, configurar credencial acontecia em três lugares com três comportamentos:

- o painel de onboarding do Blink: testava a conexão, mascarava, tinha link de criação;
- o diálogo de Ajustes: mostrava a da IA mascarada e deixava colar a do OpenAlex em texto
  plano, sem teste e sem link;
- a barra de parâmetros do mapa: um campo "Chave API" cru — e era **esse** que alimentava
  as sete chamadas de IA, justamente o único sem teste de conexão e sem link.

Três implementações da mesma tarefa divergem. Estes testes fixam a fonte única e a não
regressão dos dois lugares que saíram: um quarto campo de credencial em qualquer outro
canto é o defeito voltando.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Os testadores entram com apelido: importados com o nome original, o pytest os COLETA
# como se fossem testes (prefixo `test`) e reporta erro de fixture inexistente. É a mesma
# armadilha que `tests/test_ai_onboarding.py` já documentava para o `testar_chave`.
from core.credenciais import CREDENCIAIS, PROVEDORES_IA, ResultadoTeste, mascarar, por_id
from core.credenciais import testar_ia as diagnosticar_ia
from core.credenciais import testar_openalex as diagnosticar_openalex
from core.credenciais import testar_pubmed as diagnosticar_pubmed

RAIZ = Path(__file__).resolve().parent.parent
CHAVE = "gsk_" + "T3st3Fals4" * 5
IDIOMAS = ("pt_BR", "en", "fr")


@pytest.fixture
def app():
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.withdraw()
    janela.update_idletasks()
    yield janela
    janela.destroy()


@pytest.fixture
def aba(app):
    app._switch_tab("credenciais")
    app.update()
    return app._credenciais_view


def _sem_rede(monkeypatch, resultado):
    """Troca SÓ a rede de cada testador, deixando o resto do caminho intacto."""
    import core.credenciais as mod

    for nome in ("testar_ia", "testar_openalex", "testar_pubmed"):
        monkeypatch.setattr(mod, nome, lambda *a, **kw: resultado)
    # As `Credencial` guardam a função por referência: recriar os slots é o que faz o
    # dublê valer para a aba, e não só para quem importa o módulo.
    novos = tuple(
        type(c)(id=c.id, titulo_i18n=c.titulo_i18n, explicacao_i18n=c.explicacao_i18n,
                url_criacao=c.url_criacao, testar=lambda *a, **kw: resultado,
                prefixo_i18n=c.prefixo_i18n, placeholder=c.placeholder,
                provedores=c.provedores)
        for c in mod.CREDENCIAIS)
    monkeypatch.setattr(mod, "CREDENCIAIS", novos)
    return novos


# ── A aba existe, tem os três blocos e está na barra lateral ────────────────────

def test_a_aba_reune_as_tres_credenciais(aba):
    assert list(aba.blocos) == ["ai", "openalex", "pubmed"], list(aba.blocos)


def test_a_barra_lateral_leva_a_aba(app):
    """Guarda contra a aba existir e não ter como chegar nela."""
    from core.i18n import t

    assert "credenciais" in app._nav_btns, sorted(app._nav_btns)
    assert t("nav.credenciais") in app._nav_btns["credenciais"].cget("text")


def test_cada_bloco_tem_campo_teste_e_link(aba):
    """O contrato comum. O campo da barra de parâmetros não tinha os dois últimos."""
    for cred_id, bloco in aba.blocos.items():
        assert bloco._campo is not None, f"{cred_id}: sem campo"
        assert bloco._botao_salvar is not None, f"{cred_id}: sem teste de conexão"
        assert bloco._url_criacao().startswith("https://"), f"{cred_id}: sem link de criação"


def test_o_campo_e_mascarado_em_todos_os_blocos(aba):
    """Captura de tela da documentação é feita com o app configurado.

    A conferência é feita COM TEXTO no campo, que é quando o mascaramento importa: o
    CustomTkinter zera o `show` enquanto o placeholder está visível (senão o placeholder
    sairia como uma fileira de bolinhas) e o restaura assim que há conteúdo. Medir o campo
    vazio reprovaria um app que mascara corretamente.
    """
    for cred_id, bloco in aba.blocos.items():
        bloco._campo.insert(0, "conteudo-qualquer")
        bloco.update()
        assert bloco._campo.cget("show") == "•", f"{cred_id}: campo em texto plano"
        bloco._campo.delete(0, "end")


# ── Salvar e remover valem na hora ──────────────────────────────────────────────

def test_credencial_salva_vale_na_sessao_sem_reiniciar(app, aba, monkeypatch):
    """A exigência da Fase 1, agora para as três."""
    from core.settings import get_credencial

    import dataclasses

    bloco = aba.blocos["openalex"]
    # `Credencial` é frozen de propósito (é registro, não estado). Trocar o slot inteiro é
    # o jeito de dublar a rede sem furar a imutabilidade.
    bloco.credencial = dataclasses.replace(
        bloco.credencial,
        testar=lambda *a, **kw: ResultadoTeste("ok", "openalex.key_ok", modelo="10000"))
    bloco._campo.insert(0, CHAVE)
    bloco._concluir(bloco._executar_teste(CHAVE), CHAVE)
    app.update()

    assert get_credencial("openalex") == CHAVE, "a chave não foi para o cofre"
    from core.sources.openalex import openalex_api_key
    assert openalex_api_key() == CHAVE, "o provider não enxerga a chave recém-salva"


def test_chave_de_ia_salva_pela_aba_chega_aos_pontos_de_ia(app, aba):
    """`_api_key_var` alimenta as sete chamadas. Gravar no cofre e não sincronizar foi o
    defeito original do onboarding."""
    bloco = aba.blocos["ai"]
    bloco._concluir(ResultadoTeste("ok", "ai.key_ok", modelo="m"), CHAVE)
    app.update()

    assert app._api_key_var.get() == CHAVE
    assert app._get_ai_analyst().api_key == CHAVE


def test_trocar_a_chave_com_o_chat_ja_aberto_tambem_sincroniza(app, aba):
    """Isola a responsabilidade PRÓPRIA de `_ao_mudar_credencial`.

    Ao salvar a primeira chave, a sincronização acontece duas vezes: pela chamada direta e
    de novo dentro de `_ocultar_onboarding_ia`, herdado da Fase 1. Removendo a chamada
    direta, o teste de salvar continuava verde — verde por proteção redundante, não por
    cobertura. Trocando uma chave por OUTRA com o chat já aberto, o painel não muda de
    estado e só a chamada direta resta.
    """
    OUTRA = "gsk_" + "0utr4Fals4" * 5
    bloco = aba.blocos["ai"]
    bloco._concluir(ResultadoTeste("ok", "ai.key_ok", modelo="m"), CHAVE)
    app.update()
    assert app._blink_onboarding is None, "pré-condição: o chat precisa estar aberto"

    bloco._concluir(ResultadoTeste("ok", "ai.key_ok", modelo="m"), OUTRA)
    app.update()

    assert app._api_key_var.get() == OUTRA, (
        "a chave nova ficou no cofre e a sessão continuou com a antiga")
    assert app._get_ai_analyst().api_key == OUTRA


def test_remover_pela_aba_invalida_a_sessao(app, aba):
    bloco = aba.blocos["ai"]
    bloco._concluir(ResultadoTeste("ok", "ai.key_ok", modelo="m"), CHAVE)
    app.update()

    bloco._remover()
    app.update()

    assert app._api_key_var.get() == ""
    assert app._get_ai_analyst().api_key in (None, "")


def test_remover_a_chave_de_ia_devolve_o_blink_ao_convite(app, aba):
    bloco = aba.blocos["ai"]
    bloco._concluir(ResultadoTeste("ok", "ai.key_ok", modelo="m"), CHAVE)
    app.update()
    assert app._blink_onboarding is None

    bloco._remover()
    app.update()

    assert app._blink_onboarding is not None, "o Blink continuou como se tivesse chave"


# ── Só a credencial PROVADA inválida deixa de ser gravada ───────────────────────

@pytest.mark.parametrize("status,chave_i18n", [
    ("invalida", "openalex.key_invalid"),
    ("vazia", "openalex.key_empty"),
])
def test_credencial_provada_invalida_nao_e_gravada(aba, status, chave_i18n):
    """401/403 e campo vazio são prova sobre a credencial: nada vai para o cofre."""
    from core.settings import get_credencial

    bloco = aba.blocos["openalex"]
    bloco._concluir(ResultadoTeste(status, chave_i18n), CHAVE)

    assert get_credencial("openalex") == "", f"{status} foi gravado"


@pytest.mark.parametrize("status,chave_i18n", [
    ("limite", "openalex.key_rate_limit"),
    ("sem_internet", "openalex.key_offline"),
    ("erro", "openalex.key_error"),
])
def test_falha_que_nao_acusa_a_chave_ainda_grava(aba, status, chave_i18n):
    """Wi-fi caído, franquia esgotada e erro do provedor NÃO dizem nada sobre a chave.

    Era por aqui que as chaves se perdiam: o usuário colava, o teste falhava por um
    desses três motivos, a tela mostrava a mensagem vermelha e a chave era descartada em
    silêncio. Ele fechava o Blicsa e ela não estava lá — nunca tinha chegado ao cofre.
    """
    from core.settings import get_credencial

    bloco = aba.blocos["openalex"]
    bloco._concluir(ResultadoTeste(status, chave_i18n), CHAVE)

    assert get_credencial("openalex") == CHAVE, f"{status} descartou a chave"


def test_a_chave_guardada_sem_confirmacao_diz_isso_na_tela(aba):
    """Guardar em silêncio seria tão ruim quanto descartar: o usuário precisa saber."""
    from core.i18n import t

    bloco = aba.blocos["openalex"]
    bloco._concluir(ResultadoTeste("sem_internet", "openalex.key_offline"), CHAVE)

    texto = bloco._resultado.cget("text")
    assert texto == t("cred.salva_sem_confirmar", motivo=t("openalex.key_offline"))
    assert texto != t("openalex.key_offline"), "não distinguiu guardado de descartado"


def test_o_diagnostico_da_falha_aparece_na_tela(aba):
    from core.i18n import t

    bloco = aba.blocos["openalex"]
    bloco._concluir(ResultadoTeste("invalida", "openalex.key_invalid"), CHAVE)

    assert bloco._resultado.cget("text") == t("openalex.key_invalid")


def test_a_chave_nunca_aparece_inteira_depois_de_salva(aba):
    bloco = aba.blocos["pubmed"]
    bloco._concluir(ResultadoTeste("ok", "pubmed.key_ok", modelo="10"), CHAVE)

    estado = bloco._estado.cget("text")
    assert CHAVE not in estado, "a credencial apareceu inteira na tela"
    assert mascarar(CHAVE) in estado


# ── Provedor de IA selecionável, com o link acompanhando ────────────────────────

def test_o_link_de_criacao_muda_com_o_provedor(aba):
    """O botão mandaria quem escolheu OpenAI para o console do Groq."""
    bloco = aba.blocos["ai"]

    vistos = {}
    for provedor in PROVEDORES_IA:
        bloco._provedor_var.set(provedor)
        vistos[provedor] = bloco._url_criacao()

    assert len(set(vistos.values())) == len(PROVEDORES_IA), vistos
    assert "groq.com" in vistos["groq"]
    assert "openai.com" in vistos["openai"]


def test_o_groq_e_a_primeira_opcao_por_ser_a_gratuita():
    """A promessa do app é custo zero, e a lista é lida de cima para baixo."""
    assert next(iter(PROVEDORES_IA)) == "groq"


def test_o_teste_de_conexao_respeita_o_provedor_escolhido(aba, monkeypatch):
    """Testar sempre contra o Groq aprovaria uma chave da OpenAI que não vai funcionar —
    ou reprovaria uma que vai."""
    bloco = aba.blocos["ai"]
    visto = {}

    def _espiao(chave, base_url=None, modelo=None, **kw):
        visto["base_url"] = base_url
        return ResultadoTeste("ok", "ai.key_ok", modelo=str(modelo))

    import dataclasses

    bloco.credencial = dataclasses.replace(bloco.credencial, testar=_espiao)
    bloco._provedor_var.set("openai")

    bloco._executar_teste("sk-x")

    assert "openai.com" in (visto["base_url"] or ""), visto


# ── Fonte única: os campos antigos saíram ───────────────────────────────────────

def test_a_barra_de_parametros_do_mapa_nao_tem_mais_campo_de_chave(app):
    """Era o campo que alimentava as chamadas e o único sem teste e sem link."""
    encontrados = []

    def varre(w):
        for filho in w.winfo_children():
            try:
                var = filho.cget("textvariable")
                if var and str(var) == str(app._api_key_var):
                    encontrados.append(filho)
            except Exception:
                pass
            varre(filho)

    varre(app)
    assert not encontrados, (
        f"{len(encontrados)} campo(s) ainda ligados a _api_key_var fora da aba")


def test_os_ajustes_nao_colam_mais_credencial(app, monkeypatch):
    """O diálogo deixava colar a chave do OpenAlex em texto plano, sem teste e sem link."""
    app._show_settings()
    app.update()

    entradas = []

    def varre(w):
        for filho in w.winfo_children():
            if filho.winfo_class() == "Entry":
                entradas.append(filho)
            varre(filho)

    import tkinter as tk

    # Só o Toplevel do diálogo. Varrer o app inteiro pegaria os campos das outras abas —
    # inclusive os da própria aba de Credenciais, que devem existir.
    dialogos = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
    assert dialogos, "o diálogo de Ajustes não abriu"
    for janela in dialogos:
        varre(janela)

    assert not entradas, f"{len(entradas)} campo(s) de texto sobraram nos Ajustes"


def test_nenhuma_credencial_e_gravada_em_texto_plano_no_json():
    """A do OpenAlex nascia em `settings.json`. Com keyring, não pode sobrar cópia."""
    import core.settings as cs

    for nome in cs.CREDENCIAIS:
        cs.set_credencial(nome, CHAVE)
    s = cs.get_settings()

    for nome in cs.CREDENCIAIS:
        assert cs._CHAVE_JSON[nome] not in s, f"{nome} ficou legível no settings.json"


def test_credencial_antiga_do_json_e_migrada_para_o_cofre():
    """Quem já usa o app tem a chave do OpenAlex legível no disco. A migração a tira de lá
    sem o usuário precisar recolá-la."""
    import core.settings as cs

    cs.update_settings(openalex_api_key=CHAVE)

    assert cs.get_credencial("openalex") == CHAVE
    assert "openalex_api_key" not in cs.get_settings(), "a cópia em texto plano ficou"


# ── O Blink vira atalho, não uma segunda implementação ──────────────────────────

def test_o_convite_do_blink_leva_a_aba(app):
    """Antes era um fluxo completo duplicado: três passos, campo, teste e gravação."""
    assert app._blink_onboarding is not None, "sem chave, o Blink devia abrir no convite"

    app._blink_onboarding._ir()
    app.update()

    assert app._current_tab_key == "credenciais", app._current_tab_key


def test_o_convite_nao_grava_credencial():
    """Guarda contra a segunda implementação voltar."""
    fonte = (RAIZ / "ui" / "ai_onboarding_panel.py").read_text(encoding="utf-8")

    assert "set_api_key" not in fonte and "set_credencial" not in fonte, (
        "o convite do Blink voltou a gravar credencial por conta própria")
    assert "testar_chave" not in fonte and "testar_ia" not in fonte, (
        "o convite do Blink voltou a ter teste de conexão próprio")


# ── Diagnósticos distintos, como manda o padrão do ResultadoTeste ───────────────

@pytest.mark.parametrize("prefixo", ["ai", "openalex", "pubmed"])
def test_os_cinco_diagnosticos_sao_distintos_em_cada_provedor(prefixo):
    """"Deu erro" não distingue chave errada de wi-fi caído, e a ação é oposta."""
    cat = json.loads((RAIZ / "locales" / "pt_BR.json").read_text(encoding="utf-8"))
    sufixos = ["key_ok", "key_empty", "key_invalid", "key_offline", "key_rate_limit",
               "key_error"]

    faltando = [s for s in sufixos if f"{prefixo}.{s}" not in cat]
    assert not faltando, f"{prefixo}: faltam {faltando}"

    textos = [cat[f"{prefixo}.{s}"] for s in sufixos]
    assert len(set(textos)) == len(sufixos), f"{prefixo}: mensagens repetidas"


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_as_mensagens_novas_existem_nos_tres_idiomas(idioma):
    cat = json.loads((RAIZ / "locales" / f"{idioma}.json").read_text(encoding="utf-8"))
    base = json.loads((RAIZ / "locales" / "pt_BR.json").read_text(encoding="utf-8"))

    novas = [k for k in base if k.startswith(("cred.", "openalex.key", "pubmed.key",
                                              "nav.credenciais", "blink.sem_chave",
                                              "blink.ir_credenciais"))]
    faltando = [k for k in novas if k not in cat]
    assert not faltando, f"{idioma}: faltam {faltando}"


def test_a_explicacao_do_openalex_quantifica_a_franquia():
    for idioma in IDIOMAS:
        cat = json.loads((RAIZ / "locales" / f"{idioma}.json").read_text(encoding="utf-8"))
        txt = cat["cred.openalex_explicacao"]
        assert "10" in txt, f"{idioma}: {txt!r}"


def test_a_explicacao_do_pubmed_cita_o_ganho_de_taxa():
    for idioma in IDIOMAS:
        cat = json.loads((RAIZ / "locales" / f"{idioma}.json").read_text(encoding="utf-8"))
        txt = cat["cred.pubmed_explicacao"]
        assert "3" in txt and "10" in txt, f"{idioma}: {txt!r}"


# ── Adversariais do armazenamento ───────────────────────────────────────────────

def test_credenciais_nao_se_misturam_no_cofre():
    """Adversarial: três slots, um keyring. Um username errado faria a chave do PubMed
    virar a da IA — e o app tentaria autenticar no Groq com ela."""
    import core.settings as cs

    valores = {"ai": "gsk_aaa", "openalex": "oa_bbb", "pubmed": "nc_ccc"}
    for nome, v in valores.items():
        cs.set_credencial(nome, v)

    for nome, v in valores.items():
        assert cs.get_credencial(nome) == v, f"{nome} devolveu outra credencial"


def test_remover_uma_credencial_nao_apaga_as_outras():
    import core.settings as cs

    for nome in ("ai", "openalex", "pubmed"):
        cs.set_credencial(nome, f"chave-{nome}")

    cs.set_credencial("openalex", "")

    assert cs.get_credencial("openalex") == ""
    assert cs.get_credencial("ai") == "chave-ai"
    assert cs.get_credencial("pubmed") == "chave-pubmed"


@pytest.mark.parametrize("nome,env", [("ai", "GROQ_API_KEY"),
                                      ("openalex", "OPENALEX_API_KEY"),
                                      ("pubmed", "NCBI_API_KEY")])
def test_o_ambiente_tem_precedencia_sobre_o_cofre(monkeypatch, nome, env):
    """Fluxo de desenvolvimento. Se o cofre ganhasse, um `.env` deixaria de valer."""
    import core.settings as cs

    cs.set_credencial(nome, "do-cofre")
    monkeypatch.setenv(env, "do-ambiente")

    assert cs.get_credencial(nome) == "do-ambiente"


def test_chave_com_espacos_em_volta_e_limpa_ao_gravar():
    import core.settings as cs

    cs.set_credencial("pubmed", f"  {CHAVE}\n")

    assert cs.get_credencial("pubmed") == CHAVE


# ── A chave do PubMed precisa CHEGAR à requisição ───────────────────────────────

def test_a_chave_do_pubmed_entra_na_url_do_provider():
    """O PubMed monta URL em seis lugares. Sem um ponto único, a chave chegaria a alguns
    e a outros não — que foi como as chamadas soltas do `main.py` ficaram sem nenhuma."""
    from core.sources.pubmed import PubMedProvider

    prov = PubMedProvider(api_key="minha-chave-ncbi")
    vistas = []

    from core.sources.base import SearchProvider
    original = SearchProvider.fetch_url

    def _captura(self, url, *a, **kw):
        vistas.append(url)
        return json.dumps({"esearchresult": {"count": "0", "idlist": []}})

    SearchProvider.fetch_url = _captura
    try:
        prov.count("bibliometrics")
    finally:
        SearchProvider.fetch_url = original

    assert vistas, "nenhuma requisição foi montada"
    assert "api_key=minha-chave-ncbi" in vistas[-1], vistas[-1]


def test_sem_chave_o_pubmed_nao_manda_o_parametro():
    """Adversarial: `api_key=` vazio é diferente de ausente, e o NCBI recusa o vazio."""
    from core.sources.base import SearchProvider
    from core.sources.pubmed import PubMedProvider

    prov = PubMedProvider(api_key="")
    vistas = []
    original = SearchProvider.fetch_url

    def _captura(self, url, *a, **kw):
        vistas.append(url)
        return json.dumps({"esearchresult": {"count": "0", "idlist": []}})

    SearchProvider.fetch_url = _captura
    try:
        prov.count("x")
    finally:
        SearchProvider.fetch_url = original

    assert "api_key" not in vistas[-1], vistas[-1]


# ── Rede real: estrutura correta não é comportamento correto ────────────────────

@pytest.mark.live
def test_live_os_tres_testadores_classificam_chave_invalida():
    """O que só a rede real diz: cada provedor recusa de um jeito diferente.

    O NCBI **não** responde 401 — devolve 400 com `{"error":"API key invalid"}` no corpo.
    Classificar pelo código daria "erro, tente de novo em instantes" para uma chave que
    nunca vai funcionar.
    """
    assert diagnosticar_ia("gsk_chave_que_nao_existe_123").status == "invalida"
    assert diagnosticar_openalex("chave_que_nao_existe_123").status == "invalida"
    assert diagnosticar_pubmed("0" * 40).status == "invalida"


@pytest.mark.live
def test_live_o_diagnostico_nunca_carrega_a_credencial():
    """O corpo de erro do NCBI ECOA a chave de volta num campo `api-key`. Logar a resposta
    crua desse endpoint vazaria a credencial do usuário."""
    secreta = "9" * 40
    r = diagnosticar_pubmed(secreta)

    texto = f"{r.status} {r.chave_i18n} {r.detalhe} {r.modelo}"
    assert secreta not in texto, f"a credencial vazou no diagnóstico: {r.detalhe!r}"


@pytest.mark.live
def test_live_campo_vazio_nao_gasta_requisicao():
    """Adversarial barato: configurar o app não pode consumir cota."""
    for testador in (diagnosticar_ia, diagnosticar_openalex, diagnosticar_pubmed):
        assert testador("").status == "vazia"
