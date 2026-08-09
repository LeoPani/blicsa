#!/usr/bin/env python3
"""Métricas de arquitetura por AST — Auditoria 1, Fase 3 (itens 15, 17, 18, 19).

Sem dependência nova: o Python do sistema é gerenciado externamente e instalar `radon` para
uma auditoria seria trocar um número por uma alteração no ambiente do usuário. Complexidade
ciclomática é contagem de pontos de decisão + 1, e isso o `ast` dá.

    python3 scripts/audit_arquitetura.py            # relatório em Markdown
    python3 scripts/audit_arquitetura.py --json     # dados crus
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Nós que criam um caminho de execução alternativo. `BoolOp` conta os operandos extras
#: (`a and b and c` são dois desvios), que é como o McCabe clássico trata curto-circuito.
DESVIOS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
           ast.With, ast.AsyncWith, ast.Assert, ast.IfExp, ast.comprehension)

ANINHAVEIS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
              ast.Try, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def arquivos() -> list[Path]:
    saida = subprocess.run(["git", "ls-files", "*.py"], cwd=RAIZ,
                           capture_output=True, text=True).stdout
    return [RAIZ / linha for linha in saida.split() if linha]


def complexidade(no: ast.AST) -> int:
    total = 1
    for filho in ast.walk(no):
        if isinstance(filho, DESVIOS):
            total += 1
        elif isinstance(filho, ast.BoolOp):
            total += len(filho.values) - 1
        elif isinstance(filho, ast.Match):
            total += len(filho.cases)
    return total


def profundidade(no: ast.AST, nivel: int = 0) -> int:
    maior = nivel
    for filho in ast.iter_child_nodes(no):
        passo = 1 if isinstance(filho, ANINHAVEIS) else 0
        maior = max(maior, profundidade(filho, nivel + passo))
    return maior


def _modulo(caminho: Path) -> str:
    rel = caminho.relative_to(RAIZ).with_suffix("")
    partes = list(rel.parts)
    if partes[-1] == "__init__":
        partes.pop()
    return ".".join(partes)


def analisa() -> dict:
    dados: dict = {"arquivos": [], "funcoes": [], "importa": defaultdict(set),
                   "marcadores": [], "imports_nao_usados": [], "definidas": {},
                   "chamadas": set()}

    for caminho in arquivos():
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        linhas = texto.splitlines()
        rel = str(caminho.relative_to(RAIZ))
        try:
            arvore = ast.parse(texto)
        except SyntaxError:
            continue

        dados["arquivos"].append({"arquivo": rel, "linhas": len(linhas)})

        for i, linha in enumerate(linhas, 1):
            for marca in ("TODO", "FIXME", "XXX", "HACK"):
                if marca in linha and ("#" in linha or '"""' in linha):
                    dados["marcadores"].append({"arquivo": rel, "linha": i,
                                                "marca": marca, "texto": linha.strip()[:90]})

        # ── imports: grafo e não usados ──
        mod = _modulo(caminho)
        importados: dict[str, int] = {}
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for a in no.names:
                    dados["importa"][mod].add(a.name.split(".")[0])
                    importados[(a.asname or a.name).split(".")[0]] = no.lineno
            elif isinstance(no, ast.ImportFrom):
                alvo = no.module or ""
                if no.level:                      # from .x import y
                    base = mod.rsplit(".", no.level)[0] if "." in mod else ""
                    alvo = f"{base}.{alvo}".strip(".")
                dados["importa"][mod].add(alvo.split(".")[0] if alvo else "")
                for a in no.names:
                    if a.name != "*":
                        importados[a.asname or a.name] = no.lineno

        usados = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
        usados |= {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
        # Nome dentro de anotação escrita como string (`def f() -> "Grafo":`).
        usados |= {n.value for n in ast.walk(arvore)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for nome, linha in importados.items():
            # `from __future__ import annotations` é diretiva de compilação: não tem uso por
            # nome, e apagá-la muda a semântica das anotações do módulo inteiro.
            if nome == "annotations":
                continue
            if nome in usados:
                continue
            if any(f"{nome}." in l or f"{nome}(" in l or f"[{nome}]" in l for l in linhas):
                continue
            dados["imports_nao_usados"].append(
                {"arquivo": rel, "linha": linha, "nome": nome})

        # ── funções ──
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fim = getattr(no, "end_lineno", no.lineno)
            dados["funcoes"].append({
                "arquivo": rel, "nome": no.name, "linha": no.lineno,
                "linhas": fim - no.lineno + 1,
                "complexidade": complexidade(no),
                "aninhamento": profundidade(no),
            })
            dados["definidas"].setdefault(no.name, []).append(f"{rel}:{no.lineno}")

        for no in ast.walk(arvore):
            if isinstance(no, ast.Call):
                f = no.func
                if isinstance(f, ast.Name):
                    dados["chamadas"].add(f.id)
                elif isinstance(f, ast.Attribute):
                    dados["chamadas"].add(f.attr)
            elif isinstance(no, ast.Name):
                dados["chamadas"].add(no.id)     # referência sem chamar (callback, decorator)
            elif isinstance(no, ast.Constant) and isinstance(no.value, str):
                # Despacho por STRING conta como referência. Sem isto, os oito loaders de
                # `core/parsers.py` apareciam como código morto — e são chamados por
                # `getattr(parser, loaders_map[fmt])()` no `main.py`. Reportar aquilo como
                # "função sem referência" teria mandado apagar o import de BibTeX e RIS.
                dados["chamadas"].add(no.value)

    dados["importa"] = {k: sorted(v - {""}) for k, v in dados["importa"].items()}
    return dados


def ciclos(grafo: dict[str, list[str]]) -> list[list[str]]:
    """Ciclos entre os pacotes do próprio projeto (ignora biblioteca de terceiros)."""
    internos = {"core", "ui", "ai", "main", "scripts", "tests"}
    adj = {m: [d for d in deps if d in internos] for m, deps in grafo.items()}
    achados, visitando, feito = [], set(), set()

    def anda(no, caminho):
        if no in visitando:
            achados.append(caminho[caminho.index(no):] + [no])
            return
        if no in feito:
            return
        visitando.add(no)
        for viz in adj.get(no, []):
            for m in list(adj):
                if m == viz or m.startswith(viz + "."):
                    anda(m, caminho + [no])
        visitando.discard(no)
        feito.add(no)

    for m in list(adj):
        anda(m, [])
    return achados


def main() -> int:
    d = analisa()

    if "--json" in sys.argv:
        d["chamadas"] = sorted(d["chamadas"])
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        return 0

    print("## Linhas por arquivo (top 12)\n")
    print("| arquivo | linhas |\n|---|---:|")
    for a in sorted(d["arquivos"], key=lambda x: -x["linhas"])[:12]:
        print(f"| `{a['arquivo']}` | {a['linhas']:,} |")

    print("\n## Complexidade ciclomática (top 15)\n")
    print("| função | arquivo:linha | CC | linhas | aninhamento |\n|---|---|---:|---:|---:|")
    for f in sorted(d["funcoes"], key=lambda x: -x["complexidade"])[:15]:
        print(f"| `{f['nome']}` | `{f['arquivo']}:{f['linha']}` | **{f['complexidade']}** | "
              f"{f['linhas']} | {f['aninhamento']} |")

    longas = [f for f in d["funcoes"] if f["linhas"] > 50]
    prod = [f for f in longas if not f["arquivo"].startswith(("tests/", "scripts/"))]
    print(f"\n## Funções com mais de 50 linhas: **{len(longas)}** "
          f"({len(prod)} fora de testes/scripts)\n")
    print("| função | arquivo:linha | linhas |\n|---|---|---:|")
    for f in sorted(prod, key=lambda x: -x["linhas"])[:12]:
        print(f"| `{f['nome']}` | `{f['arquivo']}:{f['linha']}` | {f['linhas']} |")

    print("\n## Aninhamento profundo (>= 5)\n")
    fundas = [f for f in d["funcoes"] if f["aninhamento"] >= 5
              and not f["arquivo"].startswith("tests/")]
    print("| função | arquivo:linha | aninhamento |\n|---|---|---:|")
    for f in sorted(fundas, key=lambda x: -x["aninhamento"])[:10]:
        print(f"| `{f['nome']}` | `{f['arquivo']}:{f['linha']}` | {f['aninhamento']} |")

    print("\n## Dependências indevidas\n")
    ruins = [(m, deps) for m, deps in d["importa"].items()
             if m.startswith("core") and "ui" in deps]
    print(f"- `core/` importando de `ui/`: **{len(ruins)}**"
          + (f" → {ruins}" if ruins else " (nenhuma)"))
    ai_ui = [(m, deps) for m, deps in d["importa"].items()
             if m.startswith("ai") and ("ui" in deps or "main" in deps)]
    print(f"- `ai/` importando de `ui/` ou `main`: **{len(ai_ui)}**"
          + (f" → {ai_ui}" if ai_ui else " (nenhuma)"))
    cic = ciclos(d["importa"])
    print(f"- ciclos entre pacotes internos: **{len(cic)}**"
          + (f" → {cic[:3]}" if cic else " (nenhum)"))

    print(f"\n## Marcadores de dívida: **{len(d['marcadores'])}**\n")
    if d["marcadores"]:
        print("| arquivo:linha | marca | texto |\n|---|---|---|")
        for m in d["marcadores"][:15]:
            print(f"| `{m['arquivo']}:{m['linha']}` | {m['marca']} | {m['texto']} |")

    nao_usados = [i for i in d["imports_nao_usados"]
                  if not i["arquivo"].startswith("tests/")]
    print(f"\n## Imports possivelmente não usados: **{len(nao_usados)}**\n")
    if nao_usados:
        print("| arquivo:linha | nome |\n|---|---|")
        for i in nao_usados[:20]:
            print(f"| `{i['arquivo']}:{i['linha']}` | `{i['nome']}` |")

    # Funções definidas em core/ui/ai e nunca referenciadas em lugar nenhum do repo.
    # Sobrescritas de framework: quem chama é a classe-base, nunca o nosso código.
    SOBRESCRITAS = {"do_GET", "do_POST", "do_OPTIONS", "emit", "log_message", "format",
                    "run", "handle", "write", "flush", "close"}
    orfas = []
    for nome, locais in d["definidas"].items():
        if nome.startswith("_") or nome.startswith("test_") or nome in SOBRESCRITAS:
            continue
        if any(l.startswith(("core/", "ui/", "ai/")) for l in locais) \
                and nome not in d["chamadas"]:
            orfas.append((nome, locais))
    print(f"\n## Funções públicas sem nenhuma referência: **{len(orfas)}**\n")
    if orfas:
        print("| função | definida em |\n|---|---|")
        for nome, locais in sorted(orfas)[:20]:
            print(f"| `{nome}` | `{', '.join(locais)}` |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
