"""A análise de obras seminais ligada à interface — Etapa 3.

`generate_seminal_insights` existia no cliente, testada nos três idiomas; `_seminal_box` e
`_show_seminal_insights` existiam na tela, com marcação de IA. **Nada ligava os dois**, e o
texto de espera da aba prometia *"aparecerá aqui após gerar o mapa"* — o app anunciava uma
entrega que nenhum caminho disparava.

Estes testes exercitam o **método do botão**, não a função do cliente. A distinção não é
formalidade: existiam trinta testes de animação passando `first_year` por um caminho que o
app nunca tomava, e a suíte inteira ficava verde sobre um defeito visível na tela.
"""

from pathlib import Path

import pandas as pd
import pytest

CORPUS = pd.DataFrame([
    {"title": f"Artigo {i}", "keywords": "residuos;politica", "authors": "Silva, J",
     "year": 2020, "citations": i,
     "references": "Freire P, 1968, PEDAGOGIA DO OPRIMIDO; Ostrom E, 1990, GOVERNING COMMONS"}
    for i in range(6)
])

SEM_REFERENCIAS = pd.DataFrame([
    {"title": f"Artigo {i}", "keywords": "residuos", "authors": "Silva, J",
     "year": 2020, "citations": i} for i in range(4)
])


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


def _texto_do_painel(app) -> str:
    return app._seminal_box.get("1.0", "end").strip()


@pytest.fixture
def sem_thread(monkeypatch):
    """Faz `threading.Thread(...).start()` rodar o alvo na hora, na thread principal.

    O gatilho é o mesmo, o worker é o mesmo, o renderizador é o mesmo — só o paralelismo
    sai. E sai por necessidade, não por comodidade: os workers devolvem resultado por
    `self.after(0, ...)`, que exige o `mainloop` rodando. Num teste, que bombeia `update()`
    em vez de entrar no loop, chamar `after` de outra thread levanta
    `RuntimeError: main thread is not in main loop` — o app real não tem esse problema.

    Assim o teste continua percorrendo o caminho do usuário do começo ao fim, em vez de
    pular direto para o worker e deixar o gatilho sem cobertura.
    """
    import main as blicsa

    class ThreadSincrona:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._alvo, self._args = target, args
            self._kwargs = kwargs or {}

        def start(self):
            self._alvo(*self._args, **self._kwargs)

    monkeypatch.setattr(blicsa.threading, "Thread", ThreadSincrona)
    return ThreadSincrona


# ── O fio que faltava ────────────────────────────────────────────────────────────

def test_o_botao_leva_a_resposta_do_modelo_ate_o_painel(app, monkeypatch, sem_thread):
    """O caminho inteiro: botão → worker → cliente → renderizador → widget."""
    from ai import client as mod

    visto = {}

    def _falso(base_url, api_key, model, system_prompt, user_prompt, **kw):
        visto["user"] = user_prompt
        return "## Autores e Obras Seminais\n\n**Paulo Freire** — Pedagogia do Oprimido (1968)"

    monkeypatch.setattr(mod, "call_openai_chat", _falso)
    monkeypatch.setattr(app, "_get_ai_analyst", lambda: mod.AIAnalyst(api_key="k"))
    app._dataframe = CORPUS

    app._trigger_seminal_insights()
    app.update()

    texto = _texto_do_painel(app)
    assert "Paulo Freire" in texto, "a resposta do modelo não chegou ao painel"
    assert "Freire P, 1968" in visto["user"], "as referências do corpus não foram enviadas"


def test_o_texto_entregue_carrega_a_marcacao_de_ia(app, monkeypatch, sem_thread):
    """A marcação é o que o usuário vê. `_show_seminal_insights` já a fazia — o que faltava
    era alguém chamá-lo, e é por isso que este teste vai pelo botão."""
    from ai import client as mod

    monkeypatch.setattr(mod, "call_openai_chat",
                        lambda **kw: "Freire fundou a pedagogia crítica.")
    monkeypatch.setattr(app, "_get_ai_analyst", lambda: mod.AIAnalyst(api_key="k"))
    app._dataframe = CORPUS

    app._trigger_seminal_insights()
    app.update()

    assert "[IA]" in _texto_do_painel(app), "texto gerado por IA entregue sem marcação"


def test_o_painel_nao_promete_mais_o_que_nao_entrega(app):
    """O texto de espera dizia 'após gerar o mapa' e nada acontecia ao gerar o mapa."""
    assert "após gerar o mapa" not in _texto_do_painel(app)
    assert _texto_do_painel(app), "o painel ficou sem texto de espera"


def test_o_botao_esta_na_tela_e_aponta_para_o_gatilho(app):
    """Guarda contra o método existir e o botão não — que era exatamente o estado anterior."""
    encontrados = []

    def varre(widget):
        for filho in widget.winfo_children():
            comando = getattr(filho, "_command", None)
            if comando is not None and getattr(comando, "__name__", "") == \
                    app._trigger_seminal_insights.__name__:
                encontrados.append(filho)
            varre(filho)

    varre(app)
    assert encontrados, "nenhum botão dispara `_trigger_seminal_insights`"


# ── Estados em que o usuário chega ───────────────────────────────────────────────

def test_sem_corpus_avisa_e_nao_chama_o_modelo(app, monkeypatch):
    chamou = []
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: chamou.append("aviso"))
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: chamou.append("erro"))
    app._dataframe = None

    app._trigger_seminal_insights()

    assert chamou == ["aviso"], "corpus ausente devia avisar, e só avisar"


def test_corpus_sem_referencias_explica_o_que_falta(app, monkeypatch):
    """A análise depende das referências citadas. Um corpus sem elas não é erro do usuário —
    é característica do export, e a mensagem tem de dizer isso."""
    mensagens = []
    monkeypatch.setattr("tkinter.messagebox.showerror",
                        lambda titulo, msg, *a, **k: mensagens.append(msg))
    app._dataframe = SEM_REFERENCIAS

    app._trigger_seminal_insights()

    assert mensagens, "corpus sem referências passou em silêncio"
    assert "Web of Science" in mensagens[0] or "Scopus" in mensagens[0], \
        "a mensagem não diz onde conseguir um corpus com referências"


def test_sem_chave_de_ia_recusa_sem_traceback(app, monkeypatch, sem_thread):
    """O estado do usuário novo. Recusa clara, nunca traceback."""
    import os

    from ai import client as mod

    for var in ("AI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(app, "_get_ai_analyst", lambda: mod.AIAnalyst(api_key=None))
    erros = []
    monkeypatch.setattr("tkinter.messagebox.showerror",
                        lambda titulo, msg, *a, **k: erros.append(str(msg)))
    app._dataframe = CORPUS

    app._trigger_seminal_insights()
    app.update()
    app.update()          # o tratador enfileira duas chamadas: _set_idle e o showerror

    assert erros, "sem chave, o usuário não recebeu aviso nenhum"
    assert "Traceback" not in erros[0]
    assert "API Key" in erros[0] or "chave" in erros[0].lower()


# ── A contagem de referências é a mesma dos dois lados ───────────────────────────

def test_top_referencias_conta_certo(app):
    app._dataframe = CORPUS
    top = app._top_referencias()

    assert [ref for ref, _ in top] == ["Freire P, 1968, PEDAGOGIA DO OPRIMIDO",
                                       "Ostrom E, 1990, GOVERNING COMMONS"]
    assert all(n == len(CORPUS) for _, n in top)


def test_analise_e_biblioteca_partem_da_mesma_lista():
    """A pasta de PDFs e o relatório têm de falar das MESMAS obras. Duas contagens
    independentes fariam o relatório citar o que a pasta não baixou.

    Por AST, e com os **mesmos argumentos**: a primeira versão deste teste só chamava
    `_top_referencias` e afirmava a contagem — passava a verde com um dos dois lados pedindo
    `_top_referencias(5)`. Quem apontou foi `scripts/reinject_ia_ux.py`.
    """
    import ast

    fonte = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    chamadas = {}
    for nome in ("_trigger_seminal_insights", "_create_seminal_library"):
        metodo = next(n for n in ast.walk(arvore)
                      if isinstance(n, ast.FunctionDef) and n.name == nome)
        achadas = [c for c in ast.walk(metodo)
                   if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                   and c.func.attr == "_top_referencias"]
        assert achadas, f"{nome} não usa `_top_referencias` — voltou a contar por conta"
        chamadas[nome] = [ast.dump(a) for a in achadas]

    assert chamadas["_trigger_seminal_insights"] == chamadas["_create_seminal_library"], \
        "os dois lados chamam `_top_referencias` com argumentos diferentes"


def test_corpus_sem_coluna_de_referencias_devolve_lista_vazia(app):
    app._dataframe = SEM_REFERENCIAS
    assert app._coluna_de_referencias() is None
    assert app._top_referencias() == []


# ── A função superada saiu ───────────────────────────────────────────────────────

def test_generate_insights_foi_removida():
    """Superada por `_trigger_corpus_ai_insights`, que faz o mesmo com streaming e **tem**
    botão. Manter duas rotas para análise de corpus, uma morta, é a pergunta que um revisor
    faria. Registrado em `docs/CODIGO-SEM-CHAMADOR.md`."""
    from ai.client import AIAnalyst

    assert not hasattr(AIAnalyst, "generate_insights"), \
        "a rota morta de análise de corpus voltou"
