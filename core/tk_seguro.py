"""Finalizadores do Tk que não chamam o Tk fora da thread da tela.

Fontes, variáveis e imagens do tkinter apagam o seu objeto no Tcl em `__del__`. O `__del__`
roda onde a coleta de lixo do Python roda — e ela pode disparar em QUALQUER thread que
esteja alocando memória (uma busca lendo JSON, um cálculo de mapa). Chamar o Tk fora da
thread da tela:

* trava a thread esperando a fila da interface (visto na suíte: uma página da busca em
  paralelo parada em `tkinter/font.py __del__`), ou
* aborta o programa inteiro ("Tcl_AsyncDelete: async handler deleted by the wrong thread",
  visto na medição de travadas, 1 vez em 4).

Fora da thread da tela, o finalizador agora não faz nada: o nome do objeto fica esquecido no
interpretador Tcl (alguns bytes), em vez de travar ou derrubar o app. Na thread da tela, o
comportamento é o original.
"""

from __future__ import annotations

import threading

_instalado = False


def _so_na_thread_da_tela(original):
    def __del__(self):
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            original(self)
        except Exception:
            pass
    __del__.__wrapped__ = original
    return __del__


def instalar() -> None:
    global _instalado
    if _instalado:
        return
    import tkinter
    import tkinter.font
    for cls in (tkinter.Variable, tkinter.Image, tkinter.font.Font):
        original = cls.__dict__.get("__del__")
        if original is not None and not hasattr(original, "__wrapped__"):
            cls.__del__ = _so_na_thread_da_tela(original)
    _instalado = True
