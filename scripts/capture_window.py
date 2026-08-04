#!/usr/bin/env python3
"""Captura APENAS a janela do app, nunca a tela — e recusa em vez de improvisar.

Por que existe: uma captura automatizada deste repositório já gravou a tela inteira, com o
Dock e a barra de menu do autor, e o arquivo foi commitado. Outra gravou a janela de um
navegador com uma conversa pessoal. Nos dois casos a causa foi a mesma: o script pedia um
retângulo de coordenadas (`screencapture -R`) ou o display inteiro (`-m`), e o que estivesse
ali era gravado sem ninguém perceber.

A regra deste módulo, e do `CONTRIBUTING.md`:

* captura-se pelo **CGWindowID** da janela (`screencapture -l`), que grava aquela janela e
  mais nada — o que estiver atrás ou na frente não entra;
* **não há fallback para coordenadas.** Se o ID não for encontrado, o script falha e diz por
  quê. Fallback silencioso é como as duas capturas erradas aconteceram;
* toda captura passa pela validação de `check_evidence_privacy` antes de ser considerada boa.

Uso:
    python3 scripts/capture_window.py --listar
    python3 scripts/capture_window.py --titulo Blicsa --saida docs/evidence/tela.png
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


class CapturaError(RuntimeError):
    """Falha na captura. Sempre explícita — nunca vira uma imagem errada."""


def janelas_visiveis() -> list[dict]:
    """Janelas na tela, via Quartz. Só macOS."""
    try:
        from Quartz import (CGWindowListCopyWindowInfo, kCGNullWindowID,
                            kCGWindowListExcludeDesktopElements,
                            kCGWindowListOptionOnScreenOnly)
    except ImportError as e:  # pragma: no cover - depende do SO
        raise CapturaError(
            "Quartz indisponível (pyobjc-framework-Quartz). Sem ele não dá para descobrir o "
            "ID da janela, e capturar por coordenadas é justamente o que este módulo proíbe."
        ) from e

    opcoes = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    saida = []
    for w in CGWindowListCopyWindowInfo(opcoes, kCGNullWindowID) or []:
        limites = w.get("kCGWindowBounds") or {}
        saida.append({
            "id": int(w.get("kCGWindowNumber", 0)),
            "titulo": str(w.get("kCGWindowName") or ""),
            "app": str(w.get("kCGWindowOwnerName") or ""),
            "largura": int(limites.get("Width", 0)),
            "altura": int(limites.get("Height", 0)),
        })
    return saida


def encontra_janela(titulo: str, minimo: tuple[int, int] = (400, 300)) -> dict:
    """Janela cujo título OU app casa com `titulo`, ignorando as pequenas demais.

    O filtro de tamanho evita pegar um tooltip ou uma janela auxiliar de 1×1 que o Tk cria.
    """
    alvo = titulo.lower()
    candidatas = [j for j in janelas_visiveis()
                  if (alvo in j["titulo"].lower() or alvo in j["app"].lower())
                  and j["largura"] >= minimo[0] and j["altura"] >= minimo[1]]
    if not candidatas:
        visiveis = ", ".join(sorted({f"{j['app']}:{j['titulo']}" for j in janelas_visiveis()
                                     if j["largura"] >= minimo[0]})) or "(nenhuma)"
        raise CapturaError(
            f"nenhuma janela casa com {titulo!r} e pelo menos {minimo[0]}x{minimo[1]}.\n"
            f"Janelas visíveis: {visiveis}\n"
            "A janela do Tk só aparece na lista do Quartz depois que o processo é ativado — "
            "veja `ativa_app()`. NÃO há captura por coordenadas como alternativa.")
    # A maior: a principal do app, não uma auxiliar.
    return max(candidatas, key=lambda j: j["largura"] * j["altura"])


def ativa_app(nome_processo: str = "Python") -> None:
    """Traz o processo para a frente — sem isso a janela do Tk não é listada pelo Quartz."""
    subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to set frontmost of '
                            f'(first process whose name contains "{nome_processo}") to true'],
        capture_output=True)
    time.sleep(1.0)


def captura(destino: Path, titulo: str = "Blicsa", ativar: bool = True) -> Path:
    """Captura a janela em `destino` e valida o resultado. Levanta em qualquer falha."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Apaga antes: `screencapture` pode falhar em silêncio, e um arquivo antigo no lugar
    # certo já fez uma captura "bem-sucedida" ser reportada sem nada ter sido gravado.
    if destino.exists():
        destino.unlink()

    if ativar:
        ativa_app()
    janela = encontra_janela(titulo)

    r = subprocess.run(["screencapture", "-x", "-o", "-l", str(janela["id"]), str(destino)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not destino.exists() or destino.stat().st_size == 0:
        raise CapturaError(
            f"screencapture falhou para a janela {janela['id']} ({janela['app']!r}): "
            f"{r.stderr.strip() or 'sem stderr'}")

    valida(destino)
    return destino


def valida(caminho: Path) -> dict:
    """Roda a MESMA análise do `check_evidence_privacy` usado no CI."""
    from scripts.check_evidence_privacy import analisa

    rel = analisa(Path(caminho).read_bytes(), str(caminho))
    if rel["veredito"] == "REPROVADA":
        Path(caminho).unlink(missing_ok=True)
        raise CapturaError(f"captura REPROVADA e descartada: {rel['motivo']}")
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true", help="lista as janelas visíveis")
    ap.add_argument("--titulo", default="Blicsa")
    ap.add_argument("--saida")
    ap.add_argument("--sem-ativar", action="store_true")
    args = ap.parse_args()

    if args.listar:
        for j in sorted(janelas_visiveis(), key=lambda x: -x["largura"] * x["altura"])[:20]:
            print(f"  {j['id']:>7}  {j['largura']:>5}x{j['altura']:<5}  "
                  f"{j['app']:<22} {j['titulo']}")
        return 0

    if not args.saida:
        ap.error("--saida é obrigatório fora do modo --listar")

    try:
        destino = captura(Path(args.saida), args.titulo, ativar=not args.sem_ativar)
    except CapturaError as e:
        print(f"FALHOU: {e}", file=sys.stderr)
        return 1
    rel = valida(destino)
    print(f"{destino} · {rel['dimensoes']} · papel {rel['papel']:.1%} · {rel['veredito']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
