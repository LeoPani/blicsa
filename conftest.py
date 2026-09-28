"""Coloca a raiz do repositório no `sys.path` para a suíte de testes.

Sem isto, `pytest tests/` falha com `ModuleNotFoundError: No module named 'core'`, enquanto
`python -m pytest tests/` funciona — a diferença é que `python -m` insere o diretório atual no
`sys.path` e o executável `pytest` não. O projeto não é instalado como pacote (roda de dentro
do diretório, via `python3 main.py`), então nada mais coloca a raiz lá.

O custo dessa diferença foi concreto: o CI chamava `pytest tests/` e quebrava na coleção dos
32 módulos de teste, mas isso ficou **escondido atrás de outra falha** — o build já morria
antes, em `Install dependencies`, por causa da matriz com Python 3.10. Corrigida a primeira
camada, a segunda apareceu.

Um `conftest.py` na raiz resolve para as duas formas de invocar, inclusive a de quem clona o
repositório e digita `pytest` por hábito.
"""

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


# ── A suíte não toma a tela de quem a roda ──────────────────────────────────────

#: Escotilha para depurar layout: `BLICSA_TESTES_VISIVEIS=1 pytest tests/test_layout_blink.py`
#: devolve o comportamento antigo, com as janelas à mostra. Sem ela não há como VER o que um
#: teste de geometria está medindo quando ele falha.
VISIVEIS = os.environ.get("BLICSA_TESTES_VISIVEIS", "").strip() not in ("", "0")


def _processo_acessorio_no_macos():
    """Registra o processo como ACESSÓRIO: sem ícone no Dock, sem virar o app ativo.

    Esconder a janela não basta. Ao inicializar, o Tk registra o processo como aplicação
    normal do macOS e o sistema o traz para a FRENTE: o ícone pula no Dock e o foco sai da
    janela em que a pessoa estava. Dezenove módulos de teste abrem janela, então isso
    acontecia dezenas de vezes por execução — e a suíte leva dezoito minutos, durante os
    quais não dava para usar o computador.

    `NSApplicationActivationPolicyAccessory` (1) é a política de app sem interface de
    primeiro plano.

    **Depois do primeiro root, nunca antes.** O Tk 9 instala uma subclasse própria de
    `NSApplication` (`TKApplication`) e manda `macOSVersion` para ela durante a inicialização.
    Adiantar o `sharedApplication` cria um `NSApplication` puro, o Tk o reaproveita, o
    seletor não existe e o processo ABORTA com `NSInvalidArgumentException` — testado. Com
    o Tk já inicializado, `sharedApplication` devolve a `TKApplication` que ele criou, e
    `setActivationPolicy:` é método legítimo dela.
    """
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        app = objc.objc_msgSend(objc.objc_getClass(b"NSApplication"),
                                objc.sel_registerName(b"sharedApplication"))
        if not app:
            return
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        objc.objc_msgSend(app, objc.sel_registerName(b"setActivationPolicy:"), 1)
    except Exception:
        # Sem AppKit o pior caso é o de antes: a janela aparece. Não é motivo para a suíte
        # inteira não rodar.
        pass


@pytest.fixture(autouse=True, scope="session")
def janelas_fora_da_frente():
    """Toda janela da suíte nasce escondida.

    Os fixtures já chamavam `withdraw()` logo depois de construir a janela, e isso não era
    suficiente por dois motivos.

    O primeiro é `test_search_stress.py`, que cria duas raízes e não esconde nenhuma. Pôr
    `withdraw()` lá resolveria só até o próximo teste que esquecesse — e esquecer é o
    padrão, porque quem escreve o teste não vê o efeito no CI.

    O segundo é mais sutil: `CTk.update()` chama `deiconify()` sozinho quando a janela ainda
    não foi mostrada e `withdraw()` não veio ANTES. Um `withdraw()` tardio, depois de
    qualquer `update()`, não segura mais a janela. Escondendo na construção, a ordem deixa
    de depender de quem escreveu o fixture.

    Os testes de geometria continuam válidos: janela escondida ainda calcula `winfo_x` e
    `winfo_rooty` depois de `update_idletasks()`, que é como eles já rodavam — todos os
    fixtures de layout já chamavam `withdraw()`.
    """
    if VISIVEIS:
        yield
        return

    import tkinter

    originais = []
    #: Lista de um elemento em vez de `nonlocal`: o closure só precisa marcar que já rodou.
    politica_aplicada = []

    def _esconder_ao_nascer(classe):
        original = classe.__init__

        def __init__(self, *args, **kwargs):
            original(self, *args, **kwargs)
            if not politica_aplicada:
                # Aqui, e não antes: o NSApplication do Tk só existe depois do primeiro root.
                politica_aplicada.append(True)
                _processo_acessorio_no_macos()
            try:
                # Transparente ANTES de esconder, e não em vez de: `tests/test_layout_widths.py`
                # precisa da janela MAPEADA — janela retirada não realiza geometria e todo
                # `winfo_width()` volta 1px, o que faria a asserção passar medindo nada. O
                # alfa deixa aquele módulo reexibir a dele sem que ela apareça.
                self.wm_attributes("-alpha", 0.0)
            except Exception:
                pass
            try:
                self.withdraw()
            except Exception:
                # `CTk.withdraw` lê atributos que só existem depois do `__init__` da
                # própria CTk. Quando esta chamada cai aqui é porque veio de dentro do
                # `tkinter.Tk.__init__` da classe-mãe — e o patch da classe filha esconde
                # a janela logo em seguida, já com tudo montado.
                pass

        originais.append((classe, original))
        classe.__init__ = __init__

    alvos = [tkinter.Tk, tkinter.Toplevel]
    try:
        import customtkinter as ctk
        alvos += [ctk.CTk, ctk.CTkToplevel]
    except Exception:
        pass
    for classe in alvos:
        _esconder_ao_nascer(classe)

    yield

    for classe, original in originais:
        classe.__init__ = original


class _KeyringDeMentira:
    """Cofre em memória com a interface que `core.settings` usa do keyring."""

    def __init__(self):
        self._cofre: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._cofre.get((service, username))

    def set_password(self, service, username, value):
        self._cofre[(service, username)] = value

    def delete_password(self, service, username):
        if (service, username) not in self._cofre:
            raise KeyError("nada a apagar")
        del self._cofre[(service, username)]


@pytest.fixture(autouse=True)
def configuracao_isolada(tmp_path, monkeypatch):
    """Nenhum teste toca o settings.json nem o keyring REAIS da máquina.

    Isto não é zelo preventivo, é conserto. `tests/test_ai_onboarding.py` tentava se isolar
    com

        monkeypatch.setattr(cs, "SETTINGS_PATH", tmp_path / "settings.json", raising=False)
        monkeypatch.setattr(cs, "_settings_cache", None, raising=False)

    e `core/settings.py` nunca teve nenhum dos dois nomes — tem `settings_path()` e
    `_OVERRIDE_PATH`. Com `raising=False` o monkeypatch cria atributos novos, ninguém lê, e
    o isolamento é decorativo: os testes gravavam a `CHAVE_FALSA` no
    `~/Library/Application Support/blicsa/settings.json` de verdade. No start seguinte,
    `migrate_api_key_from_json()` a promovia ao keyring do SO e **sobrescrevia a chave real
    do usuário**. Rodar a suíte desconfigurava o app, e o sintoma aparecia longe da causa:
    o Blink dizia estar configurado e devolvia 401.

    Autouse de propósito. Isolar só os módulos que hoje escrevem deixaria a próxima
    escrita — a de um teste que ainda não existe — livre para repetir o estrago.
    """
    import core.settings as cs

    monkeypatch.setattr(cs, "_OVERRIDE_PATH", tmp_path / "settings.json")
    cofre = _KeyringDeMentira()
    monkeypatch.setattr(cs, "_keyring", lambda: cofre)
    # `get_api_key()` lê o ambiente ANTES do keyring. Sem limpar, a chave real da máquina
    # de quem roda a suíte vaza para dentro dos testes — e para as mensagens de falha.
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    return cofre
