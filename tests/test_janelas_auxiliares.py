"""Ajustes e Sobre têm de deixar o usuário voltar para outra janela.

As duas eram `overrideredirect(True)` + `attributes("-topmost", True)`. Juntas, isso é uma
janela sem barra de título — que não dá para arrastar nem fechar pelo botão do sistema — e
que fica acima de TODOS os aplicativos, não só do Blicsa: quem abrisse os Ajustes e fosse
para o navegador continuava com a caixa flutuando por cima. O único jeito de sair dela era
achar o botão OK.

`-topmost` é para alerta que não pode ser perdido. Um diálogo de preferências não é isso, e
o de Sobre muito menos.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "gsk_" + "T3st3Fals4" * 5)
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.withdraw()
    janela._dispensa_boas_vindas()
    janela.update()
    yield janela
    janela.destroy()


def _dialogos(app):
    """Os `Toplevel` abertos, fora a raiz e a janela de boas-vindas já dispensada."""
    import tkinter as tk

    return [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]


def _abrir(app, metodo):
    antes = set(_dialogos(app))
    getattr(app, metodo)()
    app.update()
    novos = [d for d in _dialogos(app) if d not in antes]
    assert novos, f"{metodo} não abriu janela nenhuma"
    return novos[-1]


@pytest.mark.parametrize("metodo", ["_show_settings", "_show_about"])
def test_a_janela_nao_flutua_acima_dos_outros_aplicativos(app, metodo):
    dlg = _abrir(app, metodo)
    try:
        assert not dlg.attributes("-topmost"), (
            "a janela voltou a ficar acima de todos os aplicativos")
    finally:
        dlg.destroy()


@pytest.mark.parametrize("metodo", ["_show_settings", "_show_about"])
def test_a_janela_tem_barra_de_titulo(app, metodo):
    """Sem ela não há como arrastar a janela para o lado nem fechá-la pelo sistema."""
    dlg = _abrir(app, metodo)
    try:
        assert not dlg.overrideredirect(), "a janela voltou a ser sem moldura"
        assert dlg.title(), "janela com moldura e sem título"
    finally:
        dlg.destroy()


@pytest.mark.parametrize("metodo", ["_show_settings", "_show_about"])
def test_a_janela_acompanha_a_principal(app, metodo):
    """`transient`: sobe e some junto com o Blicsa, e fica acima DELE — de mais nada."""
    dlg = _abrir(app, metodo)
    try:
        assert dlg.transient() == str(app)
    finally:
        dlg.destroy()


@pytest.mark.parametrize("metodo", ["_show_settings", "_show_about"])
def test_escape_fecha(app, metodo):
    """O OK existe, mas Escape é o que a mão faz — e era o que não tinha saída."""
    dlg = _abrir(app, metodo)
    dlg.event_generate("<Escape>")
    app.update()

    assert not dlg.winfo_exists(), "Escape não fechou a janela"
