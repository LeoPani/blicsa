"""A chave de IA valendo NA SESSÃO — o fio entre a tela de configuração e as chamadas.

O defeito que estes testes fecham: `AIOnboardingPanel` gravava a chave com `set_api_key()`,
e os sete pontos de IA do app montam o `AIAnalyst` com `self._api_key_var.get()`. Essa
variável era preenchida uma única vez, no `__init__`. Quem colava a chave lia
"Conectado. Modelo: openai/gpt-oss-120b", via o chat abrir com a saudação, perguntava, e
recebia "API Key não configurada nos Ajustes". Só passava a funcionar reiniciando o app.

Havia 23 testes cobrindo `ai/onboarding.py` — todos verdes, todos sobre o defeito. Eles
testavam `testar_chave()`, `mascarar()`, `tem_chave()`: as peças, cada uma correta. O que
estava quebrado era a montagem. Por isso **nenhum teste deste módulo chama
`ai.onboarding`**: todos entram pelo painel que o usuário vê ou pelo método que o botão
dispara, e saem no cabeçalho HTTP que chega ao provedor.

O espelho tem o mesmo formato: `_remover_chave` apagava do keyring e a sessão seguia usando
a chave removida até o app fechar.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

CHAVE = "gsk_" + "T3st3Fals4" * 5            # comprimento de chave real, valor sintético
OUTRA_CHAVE = "gsk_" + "0utr4Fals4" * 5


# ── Infraestrutura: o app de verdade, com as threads em linha ────────────────────

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
def sem_thread(monkeypatch):
    """`threading.Thread(...).start()` roda o alvo na hora, na thread principal.

    Mesmo gatilho, mesmo worker, mesmo renderizador — só o paralelismo sai, e sai por
    necessidade: os workers devolvem resultado por `self.after(0, ...)`, que exige o
    `mainloop`. Num teste, que bombeia `update()`, chamar `after` de outra thread levanta
    `RuntimeError: main thread is not in main loop`.
    """
    import main as blicsa
    import ui.ai_onboarding_panel as painel_mod

    class ThreadSincrona:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._alvo, self._args = target, args
            self._kwargs = kwargs or {}

        def start(self):
            self._alvo(*self._args, **self._kwargs)

    monkeypatch.setattr(blicsa.threading, "Thread", ThreadSincrona)
    monkeypatch.setattr(painel_mod.threading, "Thread", ThreadSincrona)
    return ThreadSincrona


def _bombear(app, ate, limite=5.0):
    """Roda o laço de eventos até `ate()` ou o limite. Os `after` do app são reais."""
    fim = time.time() + limite
    while time.time() < fim:
        app.update()
        if ate():
            return True
        time.sleep(0.01)
    return False


def _bombear_por(app, segundos):
    """Bombeia por um tempo fixo. Para quando o esperado é que NADA aconteça."""
    fim = time.time() + segundos
    while time.time() < fim:
        app.update()
        time.sleep(0.01)


class _RespostaFalsa:
    """Um stream SSE com uma resposta e o `[DONE]`, como o provedor devolve."""

    def __init__(self, texto="Resposta do modelo."):
        self._linhas = [
            b'data: ' + json.dumps({"choices": [{"delta": {"content": texto}}]}).encode(),
            b'data: [DONE]',
        ]

    def __iter__(self):
        return iter(self._linhas)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def provedor(monkeypatch):
    """Substitui a rede no ponto mais tardio possível: o `urlopen` do cliente.

    Tardio de propósito. Trocar o `AIAnalyst` por um dublê deixaria de fora justamente o
    trecho onde o defeito vivia — a montagem do analista a partir de `_api_key_var`. Aqui
    o que se observa é o cabeçalho `Authorization` que saiu do app.
    """
    visto = {"chamadas": 0, "auth": None, "url": None}

    def _urlopen_falso(req, timeout=None):
        visto["chamadas"] += 1
        visto["auth"] = req.get_header("Authorization")
        visto["url"] = req.full_url
        return _RespostaFalsa()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen_falso)
    return visto


def _painel(app):
    painel = app._blink_onboarding
    assert painel is not None, "o onboarding devia estar na tela e não está"
    return painel


def _salvar_pelo_painel(app, chave, monkeypatch, status="ok"):
    """Percorre o passo 3: digitar no campo e apertar "Testar e salvar".

    O diagnóstico de rede é dublado — ele já tem 23 testes próprios e bater no Groq de
    verdade tornaria a suíte dependente de rede. O que NÃO é dublado é nada depois disso:
    gravação, sincronização da sessão, troca de tela.
    """
    import ui.ai_onboarding_panel as painel_mod
    from ai.onboarding import ResultadoTeste

    resultado = (ResultadoTeste("ok", "ai.key_ok", modelo="openai/gpt-oss-120b")
                 if status == "ok" else ResultadoTeste(status, f"ai.key_{status}"))
    monkeypatch.setattr(painel_mod, "testar_chave", lambda *a, **kw: resultado)

    painel = _painel(app)
    painel._campo_chave.delete(0, "end")
    painel._campo_chave.insert(0, chave)
    painel._testar_e_salvar()
    if status == "ok":
        # O painel só sai da tela 700 ms depois de gravar (`after(700, on_saved)`).
        _bombear(app, lambda: app._blink_onboarding is None)
    else:
        # Chave recusada não fecha o painel: esperar o limite inteiro seria 5 s de suíte
        # gastos para confirmar que nada aconteceu. 1 s passa folgado dos 700 ms.
        _bombear_por(app, 1.0)


def _textos_do_historico(app) -> str:
    """Tudo o que está escrito na conversa — bolhas e painéis de erro."""
    partes = []

    def varre(widget):
        for filho in widget.winfo_children():
            try:
                texto = filho.cget("text")
                if isinstance(texto, str) and texto:
                    partes.append(texto)
            except Exception:
                pass
            try:
                if filho.winfo_class() == "Text":
                    partes.append(filho.get("1.0", "end"))
            except Exception:
                pass
            varre(filho)

    varre(app._research_chat_history_main)
    return "\n".join(partes)


# ── O isolamento, que também é código e também erra ──────────────────────────────

def test_a_suite_nao_alcanca_o_settings_nem_o_keyring_reais():
    """Guarda contra o isolamento voltar a ser decorativo.

    Não é hipótese: `tests/test_ai_onboarding.py` se isolava com
    `monkeypatch.setattr(cs, "SETTINGS_PATH", …, raising=False)` sobre um nome que
    `core/settings.py` nunca teve. O monkeypatch criava o atributo, ninguém o lia, e os
    testes gravavam a chave sintética no `settings.json` REAL do usuário. No start
    seguinte, `migrate_api_key_from_json()` a promovia ao keyring do SO e sobrescrevia a
    chave verdadeira — rodar a suíte desconfigurava o app.

    Um monkeypatch que não pega é silencioso por natureza: todos os testes ficam verdes e o
    dano acontece fora deles. Este assert é o que faz barulho.
    """
    from platformdirs import user_config_dir

    import core.settings as cs

    real = (Path(user_config_dir("blicsa")) / "settings.json").resolve()
    assert cs.settings_path().resolve() != real, (
        "a suíte está escrevendo no settings.json real do usuário")

    cofre = cs._keyring()
    assert cofre is not None and type(cofre).__name__ == "_KeyringDeMentira", (
        "a suíte está escrevendo no keyring real do sistema operacional")


# ── O bloqueador ─────────────────────────────────────────────────────────────────

def test_app_sem_chave_abre_no_onboarding(app):
    """Ponto de partida de todo o resto: usuário novo, cofre vazio."""
    assert app._blink_onboarding is not None, "sem chave, o Blink devia abrir no onboarding"
    assert app._api_key_var.get() == ""


def test_chave_salva_pelo_painel_vale_na_sessao_sem_reiniciar(app, monkeypatch, sem_thread):
    """O fio que faltava, medido onde ele arrebentava."""
    _salvar_pelo_painel(app, CHAVE, monkeypatch)

    assert app._blink_onboarding is None, "salva a chave, o onboarding devia sair da tela"
    assert app._api_key_var.get() == CHAVE, (
        "a chave foi gravada mas a sessão não a enxerga — é o defeito original: "
        "as sete chamadas de IA leem `_api_key_var`, não o keyring")


def test_os_sete_pontos_de_ia_recebem_a_chave_recem_salva(app, monkeypatch, sem_thread):
    """`_get_ai_analyst` é o construtor comum de Sankey, temático, historiografia e
    seminais. Se ele nasce sem chave, quatro telas quebram de uma vez."""
    _salvar_pelo_painel(app, CHAVE, monkeypatch)

    analista = app._get_ai_analyst()
    assert analista.api_key == CHAVE, "o analista das outras telas nasceu sem a chave"


def test_pergunta_logo_apos_o_onboarding_chega_ao_provedor_com_a_chave(
        app, monkeypatch, sem_thread, provedor):
    """O caminho completo do usuário novo: colar, salvar, perguntar, ser respondido.

    É o teste que o defeito original derrubaria, e o único que observa o cabeçalho que
    efetivamente saiu do app.
    """
    _salvar_pelo_painel(app, CHAVE, monkeypatch)

    app._research_chat_input_main.insert(0, "quais são as frentes de pesquisa?")
    app._blink_enviar()
    _bombear(app, lambda: provedor["chamadas"] > 0)
    app.update()

    assert provedor["chamadas"] == 1, "a pergunta não chegou ao provedor"
    assert provedor["auth"] == f"Bearer {CHAVE}", (
        "a requisição saiu sem a chave que o usuário acabou de salvar")

    from core.i18n import t
    conversa = _textos_do_historico(app)
    assert "Resposta do modelo." in conversa, "a resposta não chegou à conversa"
    assert t("ai.error_title") not in conversa, (
        "o usuário salvou a chave e ainda assim levou o painel vermelho de erro")


def test_chave_colada_com_espacos_chega_limpa_ao_provedor(
        app, monkeypatch, sem_thread, provedor):
    """Copiar do console do Groq costuma trazer espaço ou quebra de linha junto.

    `Bearer  gsk_…\\n` é rejeitado com 401 e manda o usuário conferir uma chave correta.
    """
    _salvar_pelo_painel(app, f"  {CHAVE}\n", monkeypatch)

    app._research_chat_input_main.insert(0, "oi")
    app._blink_enviar()
    _bombear(app, lambda: provedor["chamadas"] > 0)

    assert provedor["auth"] == f"Bearer {CHAVE}", (
        "espaço em volta da chave sobreviveu até o cabeçalho HTTP")


def test_chave_reprovada_nao_entra_na_sessao(app, monkeypatch, sem_thread):
    """Adversarial: o provedor recusa. Nada pode ser gravado nem passar a valer."""
    _salvar_pelo_painel(app, CHAVE, monkeypatch, status="invalida")

    assert app._blink_onboarding is not None, "chave recusada não devia fechar o onboarding"
    assert app._api_key_var.get() == "", "chave recusada pelo provedor entrou na sessão"


def test_chave_salva_nao_fica_em_texto_plano_no_json(app, monkeypatch, sem_thread):
    """Com keyring disponível, o JSON não pode guardar cópia legível."""
    import core.settings as cs

    _salvar_pelo_painel(app, CHAVE, monkeypatch)

    assert "api_key" not in cs.get_settings(), "a chave ficou em texto plano no settings.json"


# ── O espelho ────────────────────────────────────────────────────────────────────

def test_remover_a_chave_para_de_valer_na_hora(app, monkeypatch, sem_thread):
    """Antes: apagava do keyring e a sessão seguia usando a chave até o app fechar."""
    _salvar_pelo_painel(app, CHAVE, monkeypatch)
    assert app._get_ai_analyst().api_key == CHAVE

    app._remover_chave_da_ia()

    assert app._api_key_var.get() == "", "a chave removida continuou valendo na sessão"
    assert app._get_ai_analyst().api_key in (None, ""), (
        "o analista das outras telas ainda nasce com a chave removida")
    assert app._blink_onboarding is not None, "removida a chave, o Blink devia voltar ao onboarding"


def test_apos_remover_nenhuma_tela_de_ia_alcanca_o_provedor(
        app, monkeypatch, sem_thread, provedor):
    """A prova pelo lado da rede, por FORA do Blink.

    A primeira versão deste teste mandava a pergunta pelo chat e passava mesmo com o
    defeito reinjetado: quem a barrava era a trava do onboarding, não a invalidação da
    chave. Verde pelo motivo errado é pior que vermelho — o teste dizia cobrir a remoção e
    cobria a trava.

    Sankey, mapa temático, historiografia e obras seminais não passam pelo Blink: montam o
    analista por `_get_ai_analyst()` e vão direto à rede. É lá que a chave removida
    apareceria.
    """
    from ai.client import AIClientError

    _salvar_pelo_painel(app, CHAVE, monkeypatch)
    app._remover_chave_da_ia()

    with pytest.raises(AIClientError):
        list(app._get_ai_analyst().chat_history_stream([{"role": "user", "content": "oi"}]))

    assert provedor["chamadas"] == 0, (
        "saiu requisição usando uma chave que o usuário tinha removido")


def test_o_botao_dos_ajustes_dispara_o_metodo_de_remocao(app):
    """Guarda contra o método existir e o botão continuar ligado no antigo — que é
    exatamente como o defeito espelho nasceu."""
    app._show_settings()
    app.update()

    from core.i18n import t
    rotulo = t("ai.key_remove")
    encontrados = []

    def varre(widget):
        for filho in widget.winfo_children():
            try:
                if filho.cget("text") == rotulo and str(filho.cget("command")):
                    encontrados.append(filho)
            except Exception:
                pass
            varre(filho)

    for janela in app.winfo_children():
        varre(janela)

    assert encontrados, f"nenhum botão '{rotulo}' na tela de Ajustes"


def test_remover_com_chave_no_ambiente_reflete_o_ambiente(app, monkeypatch, sem_thread):
    """Adversarial e contraintuitivo: `AI_API_KEY` tem precedência sobre o keyring.

    Apagar o keyring NÃO deixa a sessão sem chave nesse caso, e a variável tem que dizer a
    verdade sobre o que vai ser usado em vez de fingir que zerou.
    """
    _salvar_pelo_painel(app, CHAVE, monkeypatch)
    monkeypatch.setenv("AI_API_KEY", OUTRA_CHAVE)

    app._remover_chave_da_ia()

    assert app._api_key_var.get() == OUTRA_CHAVE, (
        "a sessão mentiu sobre qual chave está valendo depois da remoção")


def test_remover_nao_regrava_a_chave_pelo_debounce(app, monkeypatch, sem_thread):
    """Adversarial sobre o efeito colateral da própria correção.

    `_api_key_var` tem um `trace` que persiste no keyring 900 ms após cada escrita. Se a
    sincronização programática não suspendesse esse trace, remover a chave com `AI_API_KEY`
    no ambiente **gravaria a do ambiente dentro do keyring** — remover viraria salvar.
    """
    import core.settings as cs

    _salvar_pelo_painel(app, CHAVE, monkeypatch)
    monkeypatch.setenv("AI_API_KEY", OUTRA_CHAVE)

    app._remover_chave_da_ia()
    _bombear(app, lambda: False, limite=1.4)     # passa dos 900 ms do debounce

    monkeypatch.delenv("AI_API_KEY", raising=False)
    # Comprimento, não valor: a mensagem de falha do pytest não pode virar log com chave.
    assert len(cs.get_api_key()) == 0, (
        "o debounce regravou no keyring uma chave que o usuário mandou remover")


# ── O chat travado enquanto o onboarding está na tela ────────────────────────────

def test_nao_da_para_enviar_com_o_onboarding_na_tela(app, sem_thread, provedor):
    """O painel substitui o histórico; a caixa de texto e o botão continuam montados.

    Sem trava, dava para perguntar por cima do onboarding e receber o painel vermelho de
    erro — que é justamente o que o onboarding existe para o usuário nunca ver.
    """
    assert app._blink_onboarding is not None

    app._research_chat_input_main.configure(state="normal")
    app._research_chat_input_main.insert(0, "pergunta por cima do onboarding")
    app._blink_enviar()
    app.update()

    assert provedor["chamadas"] == 0, "enviou pergunta com o onboarding na tela"
    assert "pergunta por cima do onboarding" not in _textos_do_historico(app), (
        "a mensagem entrou na conversa mesmo sem chave configurada")


def test_entrada_e_sugestoes_ficam_desabilitadas_no_onboarding(app):
    """A trava também precisa ser visível: campo aceso que não faz nada é pior que campo
    apagado."""
    assert str(app._research_chat_input_main.cget("state")) == "disabled"
    assert str(app._blink_send_btn.cget("state")) == "disabled"
    for botao in app._blink_sug_btns:
        assert str(botao.cget("state")) == "disabled", "sugestão clicável sem chave"


def test_salva_a_chave_e_o_chat_volta_a_aceitar_pergunta(app, monkeypatch, sem_thread):
    """A trava tem que ser levantada junto com o onboarding, não só na próxima abertura."""
    _salvar_pelo_painel(app, CHAVE, monkeypatch)

    assert str(app._research_chat_input_main.cget("state")) == "normal"
    assert str(app._blink_send_btn.cget("state")) == "normal"
    for botao in app._blink_sug_btns:
        assert str(botao.cget("state")) == "normal"


def test_trocar_de_idioma_sem_chave_nao_derruba_o_app(app):
    """Adversarial encontrado no cruzamento de dois módulos, não no caminho feliz.

    `_refresh_language` chama `_build_layout`, que remonta a aba do Blink inteira. Enquanto
    remonta, `_research_chat_input_main` ainda aponta para o widget da montagem ANTERIOR, já
    destruído. A primeira versão da trava chamava `configure` nele e levantava
    `TclError: invalid command name` — trocar de idioma sem chave configurada matava o app.

    A suíte pegou isso porque `tests/test_fluxo_auditoria.py` já exercitava a troca de
    idioma; sozinho, este módulo ficaria verde sobre o defeito.
    """
    assert app._blink_onboarding is not None

    app._refresh_language()
    app.update()

    assert app._blink_onboarding is not None, "o onboarding sumiu na troca de idioma"
    assert str(app._research_chat_input_main.cget("state")) == "disabled", (
        "a trava não sobreviveu à remontagem do layout")


def test_remover_a_chave_trava_o_chat_de_novo(app, monkeypatch, sem_thread):
    """Ida e volta completa: configurar, usar, remover, e a tela volta ao estado inicial."""
    _salvar_pelo_painel(app, CHAVE, monkeypatch)
    app._remover_chave_da_ia()
    app.update()

    assert str(app._research_chat_input_main.cget("state")) == "disabled"
    assert str(app._blink_send_btn.cget("state")) == "disabled"
