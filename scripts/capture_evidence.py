#!/usr/bin/env python3
"""Sobe o app numa tela específica e captura a JANELA.

Histórico desta correção: a versão anterior usava `ImageGrab.grab(bbox=...)`, ou seja,
capturava um **retângulo de coordenadas da tela**. Isso grava o que estiver naquela área — se
outra janela estiver por cima, é ela que entra na imagem. Foi assim que uma captura deste
repositório registrou o navegador do autor, e outra a tela inteira com o Dock. A captura por
`CGWindowID` (em `capture_window.py`) não tem esse modo de falha.

O fallback antigo para "despejo da árvore de widgets" também saiu: ele fazia a falha parecer
sucesso, gerando um `.txt` no lugar da evidência que ninguém conferia.

Uso:
    python3 scripts/capture_evidence.py <fase> <tela>      # tela: home|corpus|analises|mapa
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.capture_window import CapturaError, captura  # noqa: E402

ABAS = {"corpus": "corpus", "analises": "viz", "mapa": "viz", "home": None}


def agenda_captura(app, destino: Path, atraso: float = 2.5):
    """Captura fora da thread da UI e encerra o app — o mainloop precisa estar rodando."""
    def _tirar():
        time.sleep(atraso)
        try:
            caminho = captura(destino)
            print(f"OK: {caminho}")
        except CapturaError as e:
            # Falha ALTA: sem imagem é melhor do que com a imagem errada.
            print(f"FALHOU: {e}", file=sys.stderr)
            os._exit(1)
        finally:
            app.quit()

    threading.Thread(target=_tirar, daemon=True).start()


def main() -> int:
    if sys.platform.startswith("linux") and "DISPLAY" not in os.environ \
            and "XVFB_RUN_CALLED" not in os.environ:
        os.environ["XVFB_RUN_CALLED"] = "1"
        return subprocess.call(["xvfb-run", "-a", sys.executable] + sys.argv)

    fase = sys.argv[1] if len(sys.argv) > 1 else "fase"
    tela = sys.argv[2] if len(sys.argv) > 2 else "home"

    import importlib.util
    spec = importlib.util.spec_from_file_location("main", str(RAIZ / "main.py"))
    main_mod = importlib.util.module_from_spec(spec)
    sys.modules["main"] = main_mod
    spec.loader.exec_module(main_mod)

    app = main_mod.BlicsaApp()
    if ABAS.get(tela):
        app._switch_tab(ABAS[tela])

    agenda_captura(app, RAIZ / "docs" / "evidence" / f"{fase}_{tela}.png")
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
