"""O layout da aba Blink: rodapé embaixo, sugestões que ficam, contexto que recolhe.

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


# ── As sugestões ficam a conversa inteira ───────────────────────────────────────

def test_as_sugestoes_aparecem_na_conversa_vazia(app):
    assert app._blink_sug_frame.winfo_manager(), (
        "sem sugestões, quem não sabe o que perguntar fica sem convite")


def test_as_sugestoes_continuam_depois_da_primeira_mensagem(app):
    """Elas sumiam na primeira mensagem, para devolver altura à conversa.

    O clique numa sugestão é a única forma de mandar uma pergunta pronta sem digitá-la:
    sumindo, o atalho deixava de existir a partir da segunda pergunta — o usuário relatou
    exatamente isso, como "não tem mais a opção".
    """
    app._add_blink_message("user", "primeira pergunta")
    app.update()
    app.update_idletasks()

    assert app._blink_sug_frame.winfo_manager(), (
        "as sugestões sumiram depois da primeira mensagem")
    assert all(b.winfo_manager() for b in app._blink_sug_btns), (
        "o rodapé ficou, mas os botões saíram dele")


def test_as_sugestoes_continuam_depois_de_varias_mensagens(app):
    """Adversarial: o defeito aparecia na SEGUNDA pergunta, não na primeira."""
    for i in range(4):
        app._add_blink_message("user", f"pergunta {i}")
        app._add_blink_message("assistant", f"resposta {i}")
    app.update()
    app.update_idletasks()

    assert app._blink_sug_frame.winfo_manager()


def test_a_entrada_continua_abaixo_das_sugestoes(app):
    """O rodapé não pode se reordenar com o conteúdo da conversa."""
    y_sug = _y(app._blink_sug_frame)

    app._add_blink_message("assistant", "resposta longa\n" * 20)
    app.update()
    app.update_idletasks()

    assert app._research_chat_input_main.winfo_manager(), "a entrada sumiu"
    assert _y(app._research_chat_input_main) > y_sug, (
        "a entrada subiu para cima das sugestões")


# ── A string proposta pelo Blink vai para a busca num clique ────────────────────

def _botoes_por_base(app):
    """Os botões do cartão de sugestão, indexados pela base. `{}` quando não há cartão.

    Procurados pelo RÓTULO, que é o que o usuário lê — um teste que descesse pela árvore de
    widgets passaria com o botão presente e ilegível.
    """
    import customtkinter as ctk
    from core.i18n import t
    from core.strings_por_base import BASES, ROTULOS

    esperados = {t("blink.usar_na_base", base=ROTULOS[b]): b for b in BASES}
    achados = {}

    def _varrer(widget):
        for filho in widget.winfo_children():
            if isinstance(filho, ctk.CTkButton):
                base = esperados.get(filho.cget("text"))
                if base:
                    achados[base] = filho
            _varrer(filho)

    _varrer(app._research_chat_history_main)
    return achados


def _botao_usar_string(app, base="openalex"):
    return _botoes_por_base(app).get(base)


def test_a_string_proposta_vai_para_o_campo_de_busca(app):
    """Sem o botão, a string "pronta para copiar e colar" exigia copiar e colar À MÃO.

    E de dentro de um `CTkTextbox` desabilitado, atravessando para outra aba.
    """
    string = '("machine learning" OR "deep learning") AND bibliometrics'
    app._oferecer_string_de_busca(f"Sugiro:\n```\n{string}\n```")
    app.update()
    app.update_idletasks()

    botao = _botao_usar_string(app)
    assert botao is not None, "a string proposta ficou só para copiar e colar"

    botao.invoke()
    app.update()
    app.update_idletasks()

    assert app._search_query_entry.get() == string


def test_ha_um_botao_para_cada_uma_das_tres_bases(app):
    """Um botão só mandava a MESMA string para qualquer base — a origem do "não dá resultado".

    O que cada base entende está medido em `core/strings_por_base.py`; aqui o que se guarda
    é que as três chegam à tela, cada uma com o seu botão.
    """
    from core.strings_por_base import BASES

    app._oferecer_string_de_busca('```\n("machine learning" OR "deep learning") AND bibliometrics\n```')
    app.update()

    assert set(_botoes_por_base(app)) == set(BASES)


def test_o_botao_troca_a_base_junto_com_a_string(app):
    """Preencher o campo sem trocar a base mandaria a string do PubMed para o OpenAlex.

    E a tela continuaria mostrando "OpenAlex" no seletor — mentindo sobre onde a busca vai
    sair, que é pior do que não trocar nada.
    """
    app._oferecer_string_de_busca('```\n(bibliometric* OR scientometric*) AND "machine learning"\n```')
    app.update()

    _botoes_por_base(app)["pubmed"].invoke()
    app.update()

    assert app._search_provider_var.get() == "pubmed"
    assert app._provider_seg.get() == "PubMed"
    # O PubMed é a única das três que entende curinga: a dele sai intacta.
    assert "*" in app._search_query_entry.get()


def test_a_string_do_openalex_perde_o_curinga_que_derruba_a_busca(app):
    """`bibliometric*` no `filter=default.search:` do OpenAlex devolve HTTP 400 — zero.

    É o caso literal do relato "a string sugerida não dá resultado": não é que a busca
    devolva pouco, é que ela FALHA. O botão do OpenAlex entrega a string já sem o curinga.
    """
    app._oferecer_string_de_busca('```\n(bibliometric* OR scientometric*) AND "machine learning"\n```')
    app.update()

    _botoes_por_base(app)["openalex"].invoke()
    app.update()

    assert "*" not in app._search_query_entry.get()
    assert app._search_provider_var.get() == "openalex"


def test_a_string_nova_substitui_a_antiga_em_vez_de_concatenar(app):
    """Adversarial: o campo quase nunca está vazio — é a string que o Blink acabou de analisar."""
    app._search_query_entry.insert(0, "string antiga AND obsoleta")
    app._oferecer_string_de_busca('```\n("a" OR "b") AND c\n```')
    app.update()

    _botao_usar_string(app).invoke()
    app.update()

    assert app._search_query_entry.get() == '("a" OR "b") AND c'


def test_resposta_sem_string_nao_deixa_botao_inerte(app):
    """O Blink também responde pergunta que não é sobre busca."""
    app._oferecer_string_de_busca("Os clusters temáticos indicam três frentes.")
    app.update()

    assert _botoes_por_base(app) == {}, "cartão inerte sob uma resposta sem string"


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


# ── O streaming da resposta, contra um CTkTextbox de verdade ────────────────────

def _bombear(app, fluxo, quadros=4):
    """Deixa o fluxo desenhar alguns quadros.

    Dois detalhes que um `app.update()` solto não cobre: o quadro é agendado com
    `after(70, ...)` e só vence depois desse tempo, e enquanto o stream está ABERTO o fluxo
    se reagenda de propósito (é o batimento que faz o texto aparecer). Ou seja, esperar
    `_agendado` virar falso no meio do stream esperaria para sempre — só depois de
    `concluir()` é que ele para.
    """
    import time

    for _ in range(quadros):
        app.update()
        app.update_idletasks()
        time.sleep(fluxo._intervalo / 1000 + 0.01)
    app.update()
    app.update_idletasks()


def test_o_streaming_monta_a_resposta_inteira_no_balao(app):
    """O duble de `tests/test_streaming_blink.py` não conhece os índices do Tk de verdade.

    `index("end-1c")`, `delete(indice, "end")` e o `\\n` que o `Text` acrescenta sozinho no
    fim são exatamente onde um desenho incremental erra — e o erro apareceria na tela como
    texto duplicado ou comido, não como exceção.
    """
    fluxo = app._fluxo_de_resposta()
    for pedaco in ("# Análise\n\n", "Três frentes ", "aparecem no corpus.\n",
                   "\n- primeira\n- segunda\n"):
        fluxo.escrever(pedaco)
        _bombear(app, fluxo)
    fluxo.concluir()
    _bombear(app, fluxo)

    escrito = fluxo._caixa.get("1.0", "end")
    assert "Análise" in escrito
    assert "Três frentes aparecem no corpus." in escrito
    assert escrito.count("Três frentes") == 1, "trecho já desenhado foi escrito de novo"
    assert "primeira" in escrito and "segunda" in escrito


def test_o_streaming_nao_deixa_a_marcacao_crua_na_tela(app):
    """A cauda provisória entra como texto simples; ao virar definitiva tem de ser reparsada.

    Sem isso o `#` e os `**` do último trecho ficariam à mostra — o "formatação estranha"
    que o parser de Markdown existe para não deixar acontecer.
    """
    fluxo = app._fluxo_de_resposta()
    fluxo.escrever("**negrito** e `codigo` sem quebra no fim")
    _bombear(app, fluxo)
    fluxo.concluir()
    _bombear(app, fluxo)

    escrito = fluxo._caixa.get("1.0", "end")
    assert "**" not in escrito and "`" not in escrito
    assert "negrito" in escrito and "codigo" in escrito


def test_um_stream_longo_nao_enche_a_fila_de_eventos_do_tk(app):
    """A causa da janela que parava de responder: um `after(0, ...)` por token.

    Contado no `after` do app real, porque é a fila dele que saturava.
    """
    original = app.after
    contador = {"n": 0}

    def contando(ms, *a, **kw):
        if a:
            contador["n"] += 1
        return original(ms, *a, **kw)

    app.after = contando
    try:
        fluxo = app._fluxo_de_resposta()
        for i in range(300):
            fluxo.escrever(f"token{i} ")
        fluxo.concluir()
        _bombear(app, fluxo)
    finally:
        app.after = original

    assert contador["n"] < 30, (
        f"{contador['n']} agendamentos para 300 tokens — voltou a ser um por token")


def test_o_fluxo_para_de_bater_depois_de_concluir(app):
    """O batimento existe enquanto o stream está aberto; depois dele é vazamento.

    Uma resposta por pergunta, um temporizador vivo por resposta: em meia hora de conversa
    seriam dezenas repintando um balão que ninguém mais alimenta.
    """
    import time

    fluxo = app._fluxo_de_resposta()
    fluxo.escrever("resposta curta\n")
    _bombear(app, fluxo)
    fluxo.concluir()

    for _ in range(20):
        app.update()
        app.update_idletasks()
        if not fluxo._agendado:
            break
        time.sleep(0.02)

    assert not fluxo._agendado, "o fluxo continuou agendando quadros depois de concluir"


# ── O pedido ao modelo não é o que a conversa mostra ────────────────────────────

def test_a_bolha_mostra_a_pergunta_e_nao_o_paredao_de_instrucoes(app):
    """A bolha do usuário exibia o pedido inteiro, regras de sintaxe inclusive.

    Apresentado como se fosse a frase que a pessoa acabou de escrever — e ela não escreveu
    nada, clicou num botão. O modelo continua recebendo tudo; a conversa mostra a pergunta.
    """
    app._search_query_entry.insert(0, '"machine learning" AND bibliometrics')

    pedido, bolha, _ = app._pedido_de_analise_de_busca()

    assert '"machine learning" AND bibliometrics' in bolha
    assert len(bolha) < 120, f"a bolha voltou a ser um paredão: {len(bolha)} caracteres"
    assert "PROIBIDO" not in bolha and "INTERDIT" not in bolha and "FORBIDDEN" not in bolha
    assert len(pedido) > len(bolha), "o pedido ao modelo encolheu junto com a bolha"


def test_o_pedido_proibe_o_que_derruba_cada_base(app):
    """Cada proibição corresponde a uma falha medida, não a preferência de estilo.

    O tradutor conserta de qualquer forma; a proibição existe para o usuário LER uma string
    que já é a boa, em vez de ver o aviso de conserto embaixo de toda sugestão.
    """
    pedido, _, _ = app._pedido_de_analise_de_busca()

    for proibido in ("TITLE-ABS-KEY", "[tiab]", "TS="):
        assert proibido in pedido, f"o pedido deixou de proibir {proibido}"
    assert "OpenAlex" in pedido and "Crossref" in pedido and "PubMed" in pedido


def test_o_contexto_carrega_a_busca_configurada(app):
    """O modelo precisa ver os filtros da tela para não repeti-los dentro da string."""
    app._search_query_entry.insert(0, "bibliometria")
    app._search_year_start.insert(0, "2018")

    _, _, contexto = app._pedido_de_analise_de_busca()

    assert "bibliometria" in contexto
    assert "2018" in contexto
