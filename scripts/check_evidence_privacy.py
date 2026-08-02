#!/usr/bin/env python3
"""Auditoria de privacidade das imagens de evidência — working tree e histórico do git.

Por que existe: durante o desenvolvimento, uma captura automatizada pegou a **tela inteira**
em vez da janela do app, gravando o navegador do usuário com conteúdo pessoal. O arquivo foi
descartado antes do commit, mas o modo de falha é real e silencioso: `screencapture -R` grava
o que estiver naquelas coordenadas, e o resultado passa em qualquer teste de "a imagem não
está em branco".

O que este script decide, por imagem:

* **dimensões** — igual à da tela inteira levanta suspeita (captura de desktop, não de janela);
* **fração de fundo papel `#F6F4EE`** — captura legítima do Blicsa é dominada por ele. As
  exceções conhecidas (tema tinta, tema impressão, ícones, bandeiras) são declaradas;
* **fração de pixels escuros** — terminal e navegador em modo escuro dominam a imagem; a UI
  do app tem preto só em bordas finas e texto.

OCR entra quando `tesseract` estiver instalado; sem ele, o script **diz que pulou** em vez de
fingir que verificou.

Uso:
    python3 scripts/check_evidence_privacy.py              # working tree (sai 1 se reprovar)
    python3 scripts/check_evidence_privacy.py --historico  # inclui os blobs antigos do git
    python3 scripts/check_evidence_privacy.py --json       # saída para o relatório
"""

from __future__ import annotations

import argparse
import io
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

PAPER = (246, 244, 238)
INK = (20, 20, 20)

# Resoluções de tela cheia conhecidas. Uma captura com exatamente estas dimensões quase
# certamente é do desktop inteiro, não de uma janela.
TELAS_CHEIAS = {
    (2940, 1912), (2560, 1664), (3024, 1964), (1920, 1080), (2880, 1800),
    (3456, 2234), (5120, 2880), (1440, 900), (2560, 1600),
}

# Fração mínima de fundo papel para uma captura de tela do app ser considerada legítima.
LIMIAR_PAPEL = 0.25

# Arquivos que legitimamente NÃO são dominados pelo papel — cada um com o motivo.
EXCECOES = {
    "docs/evidence/mapa_tema_tinta.png": "tema tinta: fundo INK por design",
    "docs/evidence/mapa_poster.png": "modo pôster: planos chapados cobrindo o canvas",
    "docs/evidence/mapa_animacao.gif": "animação: quadros com fundo papel, verificados à parte",
}

# Diretórios cujas imagens são arte do produto, não capturas de tela.
ARTE = ("assets/", "extension/icons/", "dist/")


def _frac_cor(pixels, alvo, tol=26.0) -> float:
    if not pixels:
        return 0.0
    n = sum(1 for p in pixels
            if math.dist(p, alvo) <= tol)
    return n / len(pixels)


def analisa(dados: bytes, nome: str) -> dict:
    """Analisa uma imagem em memória. Não escreve nada em disco."""
    im = Image.open(io.BytesIO(dados))
    quadros = getattr(im, "n_frames", 1)
    im = im.convert("RGB")
    largura, altura = im.size
    amostra = list(im.resize((120, 80)).convert('RGB').getdata())

    papel = _frac_cor(amostra, PAPER)
    escuro = sum(1 for p in amostra if sum(p) / 3 < 60) / len(amostra)

    rel = {
        "arquivo": nome,
        "dimensoes": f"{largura}x{altura}",
        "quadros": quadros,
        "papel": round(papel, 4),
        "escuro": round(escuro, 4),
        "tela_cheia": (largura, altura) in TELAS_CHEIAS,
    }

    arte = any(nome.startswith(p) for p in ARTE)
    excecao = EXCECOES.get(nome)

    motivos = []
    if arte:
        rel["veredito"] = "OK"
        rel["motivo"] = "arte do produto (ícone/logo/bandeira), não é captura de tela"
        return rel

    if rel["tela_cheia"]:
        motivos.append(f"dimensões de TELA CHEIA ({rel['dimensoes']})")
    if excecao:
        rel["veredito"] = "SUSPEITA" if motivos else "OK"
        rel["motivo"] = "; ".join(motivos + [excecao])
        return rel
    if papel < LIMIAR_PAPEL:
        motivos.append(f"fundo papel em só {papel:.1%} (mínimo {LIMIAR_PAPEL:.0%})")
    if escuro > 0.45:
        motivos.append(f"{escuro:.0%} de pixels escuros — terminal/navegador?")

    rel["veredito"] = "REPROVADA" if papel < 0.05 else ("SUSPEITA" if motivos else "OK")
    rel["motivo"] = "; ".join(motivos) if motivos else "fundo papel dominante, janela do app"
    return rel


def ocr(dados: bytes) -> str | None:
    """Texto da imagem, se `tesseract` estiver instalado. `None` = não verificado."""
    if not shutil.which("tesseract"):
        return None
    try:
        r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "por+eng"],
                           input=dados, capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None


TERMOS_ALHEIOS = [
    "gmail", "whatsapp", "youtube", "chrome", "safari", "firefox", "gemini",
    "chatgpt", "instagram", "facebook", "twitter", "linkedin", "slack",
    "outlook", "icloud", "@gmail", "@hotmail", "@outlook", "netflix", "spotify",
]


def termos_suspeitos(texto: str | None) -> list[str]:
    if not texto:
        return []
    baixo = texto.lower()
    return sorted({t for t in TERMOS_ALHEIOS if t in baixo})


def imagens_working_tree(raiz: Path) -> list[tuple[str, bytes]]:
    saida = []
    r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=raiz)
    for linha in r.stdout.splitlines():
        if linha.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            caminho = raiz / linha
            if caminho.exists():
                saida.append((linha, caminho.read_bytes()))
    return saida


def imagens_historico(raiz: Path) -> list[tuple[str, bytes]]:
    """Todos os blobs de imagem que já existiram, inclusive versões sobrescritas.

    É o ponto do exercício: apagar o arquivo agora não tira o conteúdo do histórico, e uma
    versão ruim commitada e depois substituída continua acessível a quem clonar.
    """
    saida = []
    vistos = set()
    r = subprocess.run(
        ["git", "log", "--all", "--pretty=format:%H", "--name-only", "--diff-filter=AM"],
        capture_output=True, text=True, cwd=raiz)
    commit = None
    for linha in r.stdout.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if len(linha) == 40 and all(c in "0123456789abcdef" for c in linha):
            commit = linha
            continue
        if not linha.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            continue
        blob = subprocess.run(["git", "rev-parse", f"{commit}:{linha}"],
                              capture_output=True, text=True, cwd=raiz).stdout.strip()
        if not blob or blob in vistos:
            continue
        vistos.add(blob)
        dados = subprocess.run(["git", "cat-file", "blob", blob],
                               capture_output=True, cwd=raiz).stdout
        if dados:
            saida.append((f"{linha}  @{commit[:8]}", dados))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--historico", action="store_true", help="incluir blobs antigos do git")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ocr", action="store_true", help="rodar OCR (exige tesseract)")
    args = ap.parse_args()

    raiz = Path(__file__).resolve().parent.parent
    alvos = imagens_working_tree(raiz)
    if args.historico:
        alvos += imagens_historico(raiz)

    tem_ocr = bool(shutil.which("tesseract"))
    relatorios = []
    for nome, dados in alvos:
        try:
            rel = analisa(dados, nome.split("  @")[0])
        except Exception as e:
            # Blob que o PIL não abre (arquivo corrompido, truncado ou não-imagem com
            # extensão de imagem) é ele próprio um achado — não pode ser engolido.
            relatorios.append({"arquivo": nome, "dimensoes": "?", "quadros": 0,
                               "papel": 0.0, "escuro": 0.0, "tela_cheia": False,
                               "veredito": "SUSPEITA", "ocr_termos": None,
                               "motivo": f"não foi possível abrir como imagem: {e}"})
            continue
        rel["arquivo"] = nome
        if args.ocr and tem_ocr:
            achados = termos_suspeitos(ocr(dados))
            rel["ocr_termos"] = achados
            if achados:
                rel["veredito"] = "REPROVADA"
                rel["motivo"] += f"; OCR achou {achados}"
        else:
            rel["ocr_termos"] = None
        relatorios.append(rel)

    if args.json:
        print(json.dumps({"ocr_disponivel": tem_ocr, "itens": relatorios},
                         ensure_ascii=False, indent=2))
    else:
        ruins = [r for r in relatorios if r["veredito"] != "OK"]
        print(f"{len(relatorios)} imagens analisadas · OCR "
              f"{'ativo' if (args.ocr and tem_ocr) else 'NÃO verificado (tesseract ausente)'}")
        for r in sorted(relatorios, key=lambda x: (x["veredito"] == "OK", x["arquivo"])):
            if r["veredito"] == "OK":
                continue
            print(f"  [{r['veredito']}] {r['arquivo']} · {r['dimensoes']} · "
                  f"papel {r['papel']:.1%} · {r['motivo']}")
        print(f"\n{len(relatorios) - len(ruins)} OK · {len(ruins)} para inspeção humana")

    return 1 if any(r["veredito"] == "REPROVADA" for r in relatorios) else 0


if __name__ == "__main__":
    sys.exit(main())
