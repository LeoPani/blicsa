#!/usr/bin/env python3
"""Captura o chat da IA em streaming — pela JANELA do app.

A versão anterior terminava em `screencapture -x -m`, que grava o **display inteiro**. Foi
essa linha que produziu a captura com o Dock e a barra de menu do autor, commitada e depois
removida do histórico do repositório. `-m` e `-R` não aparecem mais aqui: a captura é por
`CGWindowID` (`capture_window.py`), que grava a janela e nada além dela.

Uso:
    python3 scripts/capture_chat.py ["pergunta a digitar"]
"""

import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.capture_window import CapturaError, ativa_app, captura  # noqa: E402

PERGUNTA_PADRAO = "Qual a tendência de publicações sobre IA?"
DESTINO = RAIZ / "docs" / "evidence" / "chat_streaming_full.png"


def main() -> int:
    pergunta = sys.argv[1] if len(sys.argv) > 1 else PERGUNTA_PADRAO

    proc = subprocess.Popen([sys.executable, "main.py"], cwd=str(RAIZ), env=os.environ.copy())
    try:
        time.sleep(6)
        ativa_app()
        subprocess.run(["osascript", "-e",
                        f'tell application "System Events" to keystroke "{pergunta}"'],
                       capture_output=True)
        time.sleep(1)
        subprocess.run(["osascript", "-e",
                        'tell application "System Events" to keystroke return'],
                       capture_output=True)
        time.sleep(15)          # streaming da resposta

        try:
            caminho = captura(DESTINO)
        except CapturaError as e:
            print(f"FALHOU: {e}", file=sys.stderr)
            return 1
        print(f"OK: {caminho}")
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
