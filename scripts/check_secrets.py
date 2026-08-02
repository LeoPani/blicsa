#!/usr/bin/env python3
"""Varredura de segredos nos arquivos rastreados — quebra o build se achar algo.

Deliberadamente simples e sem dependência: procura padrões de chave com **formato real**
(comprimento típico de credencial), não a palavra "api_key". Fixture de teste com
`gsk_plaintext_123` é legítima e não pode reprovar o build; uma chave de 56 caracteres, sim.

Uso:
    python3 scripts/check_secrets.py            # arquivos rastreados
    python3 scripts/check_secrets.py --historico
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# (nome, regex, comprimento mínimo do segredo). O comprimento é o que separa credencial de
# placeholder: chaves reais são longas, exemplos de teste são curtos e falam por si.
PADROES = [
    ("Groq / OpenAI-style", re.compile(r"\b(gsk_|sk-)[A-Za-z0-9_\-]{32,}\b")),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{32,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Chave genérica longa em atribuição",
     re.compile(r"""(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['"][A-Za-z0-9_\-]{32,}['"]""")),
]

# Caminhos onde credencial de exemplo é esperada e legítima.
ISENTOS = ("tests/", "docs/AUDITORIA-PRIVACIDADE.md", "scripts/check_secrets.py")

BINARIOS = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".mp4", ".zip", ".ttf", ".ico")


def arquivos_rastreados(raiz: Path) -> list[str]:
    r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=raiz)
    return [l for l in r.stdout.splitlines()
            if l and not l.lower().endswith(BINARIOS)]


def varre_texto(nome: str, texto: str) -> list[tuple[str, int, str, str]]:
    achados = []
    for i, linha in enumerate(texto.splitlines(), 1):
        for rotulo, rx in PADROES:
            m = rx.search(linha)
            if m:
                trecho = m.group(0)
                # Não imprime o segredo inteiro: se for real, o log do CI é público.
                mascarado = trecho[:8] + "…" + trecho[-4:] if len(trecho) > 16 else "…"
                achados.append((nome, i, rotulo, mascarado))
    return achados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--historico", action="store_true")
    args = ap.parse_args()

    raiz = Path(__file__).resolve().parent.parent
    achados: list[tuple[str, int, str, str]] = []

    for nome in arquivos_rastreados(raiz):
        if any(nome.startswith(p) for p in ISENTOS):
            continue
        caminho = raiz / nome
        try:
            texto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        achados += varre_texto(nome, texto)

    if args.historico:
        r = subprocess.run(["git", "log", "--all", "-p"], capture_output=True, text=True,
                           errors="replace", cwd=raiz)
        for i, linha in enumerate(r.stdout.splitlines(), 1):
            if not linha.startswith("+"):
                continue
            for rotulo, rx in PADROES:
                m = rx.search(linha)
                if m and "test" not in linha.lower():
                    t = m.group(0)
                    achados.append(("<histórico>", i, rotulo,
                                    t[:8] + "…" + t[-4:] if len(t) > 16 else "…"))

    if not achados:
        print("Nenhum segredo com formato de credencial real encontrado.")
        return 0

    print(f"{len(achados)} possível(is) segredo(s):")
    for nome, linha, rotulo, mascarado in achados:
        print(f"  {nome}:{linha} · {rotulo} · {mascarado}")
    print("\nSe for credencial real: REVOGUE e gere outra. Chave que já esteve num arquivo "
          "deve ser considerada comprometida, mesmo depois de removida.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
