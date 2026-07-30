#!/usr/bin/env python3
"""Verifica que um PNG/GIF de evidência não é vazio — E que mostra o que deveria mostrar.

Por que existe: a primeira captura das evidências do mapa pegou a tela inteira em vez da
janela do app, e **passou** no teste de histograma (desvio de brilho 41, muito acima de
qualquer limiar de "imagem em branco"), porque um desktop cheio de janelas é tudo menos
uniforme. Variância prova que a imagem não é chapada; não prova que é a imagem certa.

Então aqui a verificação é de CONTEÚDO: a captura tem de conter as cores do próprio mapa
(fundo papel do design system, paleta de clusters ou a rampa do overlay) em proporção
significativa. Uma captura do desktop errado reprova.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image

PAPER = (246, 244, 238)          # #F6F4EE — fundo do mapa
INK = (20, 20, 20)               # #141414
CLUSTER_PALETTE = [
    (223, 49, 23), (30, 77, 160), (245, 190, 0), (20, 20, 20),
    (122, 158, 126), (182, 92, 162), (92, 176, 184), (201, 123, 45),
]
OVERLAY_RAMP = [(30, 77, 160), (122, 158, 126), (245, 190, 0)]


def _dist(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _fraction_near(pixels, alvo, tol=26.0) -> float:
    """Fração de pixels a menos de `tol` de distância RGB de `alvo`."""
    if not pixels:
        return 0.0
    return sum(1 for p in pixels if _dist(p, alvo) <= tol) / len(pixels)


def check_png(caminho: Path, expect: str = "map", verbose: bool = True) -> tuple[bool, dict]:
    im = Image.open(caminho).convert("RGB")
    amostra = im.resize((160, 100))
    pixels = list(amostra.getdata())

    brilhos = [sum(p) / 3 for p in pixels]
    media = sum(brilhos) / len(brilhos)
    desvio = math.sqrt(sum((b - media) ** 2 for b in brilhos) / len(brilhos))
    cores_distintas = len(im.getcolors(maxcolors=5_000_000) or [])

    rel = {
        "arquivo": caminho.name,
        "dimensoes": im.size,
        "cores_distintas": cores_distintas,
        "desvio_brilho": round(desvio, 1),
        "fracao_papel": round(_fraction_near(pixels, PAPER), 3),
        "fracao_tinta": round(_fraction_near(pixels, INK, tol=40), 3),
        "fracao_clusters": round(max(_fraction_near(pixels, c) for c in CLUSTER_PALETTE), 4),
        "fracao_rampa": round(max(_fraction_near(pixels, c, tol=40) for c in OVERLAY_RAMP), 4),
    }

    problemas = []
    if im.size[0] < 400 or im.size[1] < 300:
        problemas.append(f"dimensões pequenas demais: {im.size}")
    if cores_distintas < 200:
        problemas.append(f"poucas cores distintas ({cores_distintas}) — imagem chapada?")
    if desvio < 3.0:
        problemas.append(f"desvio de brilho {desvio:.1f} — imagem praticamente uniforme")

    if expect == "map":
        # O fundo papel tem de dominar boa parte da imagem: é o que garante que a captura é
        # do MAPA e não de um desktop/navegador qualquer.
        if rel["fracao_papel"] < 0.12:
            problemas.append(
                f"fundo papel #F6F4EE em só {rel['fracao_papel']:.1%} da imagem — "
                "a captura provavelmente não é do mapa")
        # E tem de haver cor de dado: cluster (network) ou rampa (overlay/densidade).
        if max(rel["fracao_clusters"], rel["fracao_rampa"]) < 0.0015:
            problemas.append(
                "nenhuma cor da paleta de clusters nem da rampa do overlay encontrada — "
                "o mapa não desenhou nós")

    ok = not problemas
    if verbose:
        estado = "OK " if ok else "FALHOU"
        print(f"[{estado}] {caminho.name} {im.size} · cores={cores_distintas} · "
              f"desvio={desvio:.1f} · papel={rel['fracao_papel']:.1%} · "
              f"dados={max(rel['fracao_clusters'], rel['fracao_rampa']):.2%}")
        for p in problemas:
            print(f"         ! {p}")
    rel["problemas"] = problemas
    return ok, rel


def check_gif(caminho: Path, min_frames: int = 2, verbose: bool = True) -> tuple[bool, dict]:
    """GIF precisa de múltiplos quadros DISTINTOS — um still repetido não é animação."""
    im = Image.open(caminho)
    n = getattr(im, "n_frames", 1)
    assinaturas = []
    for i in range(n):
        im.seek(i)
        q = im.convert("RGB").resize((48, 32))
        assinaturas.append(tuple(q.getdata()))
    distintos = len(set(assinaturas))

    rel = {"arquivo": caminho.name, "dimensoes": im.size,
           "quadros": n, "quadros_distintos": distintos}
    problemas = []
    if n < min_frames:
        problemas.append(f"só {n} quadro(s), esperado >= {min_frames}")
    if distintos < 2:
        problemas.append(f"{n} quadros mas todos IGUAIS — é um still repetido, não animação")

    ok = not problemas
    if verbose:
        print(f"[{'OK ' if ok else 'FALHOU'}] {caminho.name} {im.size} · "
              f"quadros={n} · distintos={distintos}")
        for p in problemas:
            print(f"         ! {p}")
    rel["problemas"] = problemas
    return ok, rel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arquivos", nargs="+", type=Path)
    ap.add_argument("--expect", default="map", choices=["map", "any"],
                    help="'map' exige as cores do mapa; 'any' só checa que não é vazio")
    args = ap.parse_args()

    todos_ok = True
    for f in args.arquivos:
        if not f.exists():
            print(f"[FALHOU] {f} não existe")
            todos_ok = False
            continue
        if f.suffix.lower() == ".gif":
            ok, _ = check_gif(f)
        else:
            ok, _ = check_png(f, expect=args.expect)
        todos_ok = todos_ok and ok
    return 0 if todos_ok else 1


if __name__ == "__main__":
    sys.exit(main())
