"""O layout da aba Blink: rodapé embaixo, sugestões que somem, contexto que recolhe.

O defeito de ordem não era visível na montagem inicial e sim DEPOIS de configurar a chave.
`_build_tab_home` empacota histórico → entrada → sugestões, nessa ordem, o que põe a entrada
embaixo. Mas `_ocultar_onboarding_ia` re-empacota o histórico, e o `pack` manda quem é
empacotado por último para o FIM da fila: o histórico ia parar abaixo da entrada. O app
recém-aberto mostrava um layout e o app depois de salvar a chave mostrava outro.

Por isso o rodapé é preso com `side="bottom"`: aí a ordem em que cada um é (re)empacotado
deixa de importar. E por isso estes testes medem posição real em pixels, e não a ordem de
`winfo_children()` — a ordem de criação estava certa o tempo todo.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def app(monkeypatch):
    """App com chave de IA no ambiente: o Blink abre no chat, não no convite."""
    monkeypatch.setenv("AI_API_KEY", "gsk_" + "T3st3Fals4" * 5)
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.geometry("1380x840")
    janela.withdraw()
    janela._dispensa_boas_vindas()
    janela._switch_tab("home")
    janela.update()
    janela.update_idletasks()
    yield janela
    janela.destroy()


def _y(widget) -> int:
    return widget.winfo_rooty()


def _x(widget) -> int:
    return widget.winfo_rootx()


# ── O rodapé fica embaixo, e continua embaixo ───────────────────────────────────

def test_a_entrada_fica_abaixo_do_historico(app):
    assert _y(app._research_chat_input_main) > _y(app._research_chat_history_main), (
        "o campo de digitação está acima da conversa")


def test_o_botao_enviar_acompanha_a_entrada(app):
    assert abs(_y(app._blink_send_btn) - _y(app._research_chat_input_main)) <= 4, (
        "o botão Enviar descolou do campo")


def test_as_sugestoes_ficam_entre_a_conversa_e_a_entrada(app):
    sug = app._blink_sug_frame
    assert _y(app._research_chat_history_main) < _y(sug) < _y(app._research_chat_input_main)


def test_a_ordem_sobrevive_a_sair_do_convite_para_o_chat(app):
    """O defeito real: `_ocultar_onboarding_ia` re-empacota o histórico, e sem o rodapé
    preso ele ia para o fim da fila — ou seja, para baixo da entrada."""
    app._mostrar_onboarding_ia()
    app.update()
    app._ocultar_onboarding_ia()
    app.update()
    app.update_idletasks()

    assert _y(app._research_chat_input_main) > _y(app._research_chat_history_main), (
        "depois de configurar a chave, o campo apareceu ACIMA da conversa")


def test_a_ordem_sobrevive_a_troca_de_idioma(app):
    """`_refresh_language` remonta a aba inteira."""
    app._refresh_language()
    app.update()
    app.update_idletasks()

    assert _y(app._research_chat_input_main) > _y(app._research_chat_history_main)


# ── Alinhamento: a coluna começa no mesmo x ─────────────────────────────────────

def test_a_coluna_do_chat_comeca_toda_no_mesmo_x(app):
    """Medido: o CTkScrollableFrame do histórico insere 6px próprios, e sem compensar nas
    outras linhas a borda esquerda da coluna quebrava entre 260 e 266."""
    alinhados = {
        "barra_contexto": app._research_context_bar,
        "historico": app._research_chat_history_main,
        "entrada": app._research_chat_input_main,
        "sugestoes": app._blink_sug_frame,
    }
    xs = {nome: _x(w) for nome, w in alinhados.items()}

    assert max(xs.values()) - min(xs.values()) == 0, f"a coluna desalinhou: {xs}"


def test_o_x_nao_muda_entre_conversa_vazia_e_conversa_com_mensagens(app):
    antes = {n: _x(w) for n, w in (("historico", app._research_chat_history_main),
                                   ("entrada", app._research_chat_input_main))}

    app._add_blink_message("assistant", "uma resposta qualquer", gerado_por_ia=False)
    app.update()
    app.update_idletasks()

    depois = {n: _x(w) for n, w in (("historico", app._research_chat_history_main),
                                    ("entrada", app._research_chat_input_main))}
    assert antes == depois, f"o x mudou com o conteúdo: {antes} -> {depois}"


# ── As sugestões somem na primeira mensagem ─────────────────────────────────────

def test_as_sugestoes_aparecem_na_conversa_vazia(app):
    assert app._blink_sug_frame.winfo_manager(), (
        "sem sugestões, quem não sabe o que perguntar fica sem convite")


def test_as_sugestoes_somem_depois_da_primeira_mensagem(app):
    app._research_chat_input_main.insert(0, "primeira pergunta")
    app._ocultar_sugestoes()
    app.update()

    assert not app._blink_sug_frame.winfo_manager(), (
        "as sugestões continuaram ocupando altura depois da primeira mensagem")


def test_esconder_as_sugestoes_duas_vezes_nao_quebra(app):
    """Adversarial: `_ocultar_sugestoes` roda a cada envio, não só no primeiro."""
    app._ocultar_sugestoes()
    app._ocultar_sugestoes()
    app.update()

    assert not app._blink_sug_frame.winfo_manager()


def test_esconder_as_sugestoes_nao_mexe_na_entrada(app):
    """O campo não pode subir nem sumir junto."""
    y_antes = _y(app._research_chat_input_main)

    app._ocultar_sugestoes()
    app.update()
    app.update_idletasks()

    assert app._research_chat_input_main.winfo_manager(), "a entrada sumiu junto"
    assert _y(app._research_chat_input_main) >= y_antes - 4


# ── Contexto de pesquisa recolhível ─────────────────────────────────────────────

def test_a_barra_de_contexto_recolhe_e_reabre(app):
    barra = app._research_context_bar
    altura_aberta = barra.winfo_reqheight()

    barra.definir_recolhido(True)
    app.update()
    app.update_idletasks()
    altura_recolhida = barra.winfo_reqheight()

    assert altura_recolhida < altura_aberta, (
        f"recolher não economizou altura: {altura_aberta} -> {altura_recolhida}")

    barra.definir_recolhido(False)
    app.update()
    app.update_idletasks()
    assert barra.winfo_reqheight() >= altura_aberta - 4, "reabrir não devolveu o campo"


def test_recolhida_a_barra_mostra_um_resumo_de_uma_linha(app):
    barra = app._research_context_bar
    barra.definir("Estudo cooperativas de catadores no Sul do Brasil, com foco em "
                  "informalidade como categoria da sociologia do trabalho.")
    barra.definir_recolhido(True)
    app.update()

    resumo = barra.resumo.cget("text")
    assert resumo, "recolheu e não mostra nada do que está indo junto"
    assert "\n" not in resumo, "o resumo tem mais de uma linha"
    assert "cooperativas" in resumo


def test_o_resumo_avisa_quando_nao_ha_contexto(app):
    """Adversarial: recolhido e vazio não pode virar uma linha em branco sem sentido."""
    from core.i18n import t

    barra = app._research_context_bar
    barra.definir("")
    barra.definir_recolhido(True)
    app.update()

    assert barra.resumo.cget("text") == t("ai.contexto_vazio_resumo")


def test_contexto_longo_e_truncado_no_resumo(app):
    barra = app._research_context_bar
    barra.definir("palavra " * 200)
    barra.definir_recolhido(True)
    app.update()

    resumo = barra.resumo.cget("text")
    assert len(resumo) <= 91, f"o resumo tem {len(resumo)} caracteres"
    assert resumo.endswith("…")


def test_projeto_com_contexto_ja_abre_recolhido(app):
    """Escrito uma vez, relido sempre: manter aberto custa altura em toda conversa."""
    barra = app._research_context_bar

    barra.definir("Um contexto de pesquisa qualquer, já preenchido.")
    app.update()

    assert barra.esta_recolhido(), "projeto com contexto abriu com o campo inteiro aberto"


def test_projeto_sem_contexto_abre_aberto(app):
    """O oposto: é quando há o que escrever."""
    barra = app._research_context_bar

    barra.definir("")
    app.update()

    assert not barra.esta_recolhido(), "sem contexto, a barra abriu recolhida"


def test_recolher_nao_apaga_o_contexto(app):
    """Adversarial sobre o invariante do módulo: o valor não pode se perder no caminho."""
    barra = app._research_context_bar
    texto = "Contexto que precisa sobreviver ao recolhimento."
    barra.definir(texto)

    barra.definir_recolhido(True)
    app.update()
    barra.definir_recolhido(False)
    app.update()

    assert barra.valor() == texto


def test_o_exemplo_continua_sem_viajar_para_o_modelo(app):
    """O invariante que o módulo do contexto já protegia, agora com o recolhimento no meio:
    um exemplo pré-preenchido faria o Blink responder sobre catadores para quem estuda
    semicondutores."""
    barra = app._research_context_bar
    barra.definir("")
    barra.definir_recolhido(True)
    barra.definir_recolhido(False)
    app.update()

    assert barra.valor() == "", "o texto de exemplo virou contexto real"


# ── O espaço vazio no fim da conversa ───────────────────────────────────────────

@pytest.fixture
def enviar(app, monkeypatch):
    """Envio real do Blink, com a rede dublada e as threads em linha.

    Pelo caminho real de propósito. A primeira versão destes testes chamava
    `_add_blink_message` direto e ficava VERDE com o defeito reinjetado: o defeito só
    aparece quando o `update_height`, agendado com `after(50)`, redimensiona a bolha e
    manda rolar — e é justamente essa sequência que produz a região obsoleta.
    """
    import json
    import time
    import urllib.request

    import main as blicsa

    class Resposta:
        def __init__(self, texto):
            self._linhas = [b'data: ' + json.dumps(
                {"choices": [{"delta": {"content": texto}}]}).encode(), b'data: [DONE]']

        def __iter__(self): return iter(self._linhas)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: Resposta("Resposta do modelo. " * 6))

    class ThreadSincrona:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._alvo, self._args, self._kw = target, args, kwargs or {}

        def start(self): self._alvo(*self._args, **self._kw)

    monkeypatch.setattr(blicsa.threading, "Thread", ThreadSincrona)

    def _enviar(texto):
        app._research_chat_input_main.insert(0, texto)
        app._blink_enviar()
        # Passa dos 50ms do `after` que redimensiona a bolha e dispara a rolagem.
        fim = time.time() + 0.4
        while time.time() < fim:
            app.update()
            time.sleep(0.01)

    return _enviar


def _regiao_e_conteudo(app):
    """(altura da região de rolagem, altura real do conteúdo), COMO ESTÃO no quadro.

    Sem `update_idletasks` aqui de propósito: forçar a passada de geometria antes de ler faz
    o Tk recalcular o `scrollregion` sozinho, e o teste passa a medir um estado que se
    auto-cura. O que o usuário vê é o quadro tal como o app o deixou.
    """
    hist = app._research_chat_history_main
    regiao = hist._parent_canvas.cget("scrollregion").split()
    return int(float(regiao[3])) if len(regiao) == 4 else 0, hist.winfo_reqheight()


def test_a_regiao_de_rolagem_acompanha_o_conteudo(app, enviar):
    """O defeito medido no app: 770px de região para 308px de conversa, e 2.324 para 938.

    `yview_moveto(1.0)` rolava até o fim de uma região calculada ANTES de a bolha ser
    redimensionada. O usuário ia parar nos 60% vazios, com as mensagens acima da vista.
    """
    for i in range(4):
        enviar(f"pergunta numero {i} sobre bibliometria")

    regiao, conteudo = _regiao_e_conteudo(app)

    assert regiao == conteudo, (
        f"a região de rolagem ({regiao}px) não bate com o conteúdo ({conteudo}px): "
        f"a diferença é espaço vazio que o usuário vê ao rolar até o fim")


def test_conversa_curta_nao_precisa_rolar(app, enviar):
    """Com uma troca só o conteúdo cabe na tela: a barra não pode oferecer região extra."""
    enviar("oi")

    regiao, conteudo = _regiao_e_conteudo(app)
    assert regiao == conteudo


def test_rolar_com_a_conversa_vazia_nao_quebra(app):
    """Adversarial: o método roda a cada mensagem, inclusive na primeira."""
    app._rolar_conversa_para_o_fim()

    regiao, conteudo = _regiao_e_conteudo(app)
    assert regiao == conteudo


def test_rolar_depois_do_historico_destruido_nao_quebra(app):
    """Adversarial: `_refresh_language` destrói o histórico, e callbacks agendados com
    `after(50, ...)` ainda podem chamar a rolagem depois disso."""
    app._research_chat_history_main.destroy()

    app._rolar_conversa_para_o_fim()   # não pode levantar
