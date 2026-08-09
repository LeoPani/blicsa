#!/usr/bin/env python3
"""Matriz de corpus adversariais × três modos de visualização — Auditoria 1, Fase 1, item 1.

Roda cada corpus de `tests/corpus_adversarial.py` pelo caminho real (NetworkGenerator →
ForceAtlas2 → build_sigma_payload) e imprime a tabela do relatório em Markdown.

Auditoria, não demonstração: **qualquer** anomalia vira linha na tabela, inclusive as que não
levantam exceção. Payload que serializa com NaN, escala de overlay com faixa degenerada e
grade de densidade toda zerada são exatamente os defeitos que não aparecem no caso feliz.

    python3 scripts/audit_mapas.py            # tabela em Markdown
    python3 scripts/audit_mapas.py --json     # dados crus
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time
import traceback

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import networkx as nx  # noqa: E402

from corpus_adversarial import CASOS, monta  # noqa: E402
from core.sigma_exporter import build_sigma_payload  # noqa: E402


def _tem_nao_finito(obj) -> list[str]:
    """Caminhos até qualquer NaN/Infinity dentro do payload.

    `export_sigma_json` grava com `allow_nan=False`, então um não-finito aqui vira exceção na
    hora de salvar — com o mapa abrindo em branco e sem pista da causa, que foi o bug da
    Fase 0 do megaprompt.
    """
    achados: list[str] = []

    def anda(o, caminho: str):
        if isinstance(o, float):
            if math.isnan(o) or math.isinf(o):
                achados.append(caminho)
        elif isinstance(o, dict):
            for k, v in o.items():
                anda(v, f"{caminho}.{k}")
        elif isinstance(o, (list, tuple)):
            for i, v in enumerate(o):
                anda(v, f"{caminho}[{i}]")

    anda(obj, "payload")
    return achados


def roda_caso(caso) -> dict:
    r: dict = {"nome": caso.nome, "descricao": caso.descricao, "alvo": caso.alvo,
               "anomalias": [], "erro": None}
    t0 = time.perf_counter()
    try:
        G, pos = monta(caso)
        r["nos"] = G.number_of_nodes()
        r["arestas"] = G.number_of_edges()
        r["componentes"] = nx.number_connected_components(G) if G.number_of_nodes() else 0

        # ── MODO 1: rede ──
        payload = build_sigma_payload(G, pos)
        r["payload_nos"] = payload["meta"]["nodes_total"]
        r["clusters"] = len(payload["meta"]["clusters"])

        nao_finitos = _tem_nao_finito(payload)
        if nao_finitos:
            r["anomalias"].append(f"NaN/Inf no payload: {nao_finitos[:3]}")

        # Serialização com o MESMO rigor do disco.
        try:
            json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError) as e:
            r["anomalias"].append(f"payload não serializa: {e}")

        # Posição perdida = nó empilhado na origem, invisível sob os outros.
        sem_pos = [n for n in G.nodes() if n not in pos]
        if sem_pos:
            r["anomalias"].append(f"{len(sem_pos)} nó(s) sem posição do layout")
        coincidentes = len({(round(p["attributes"]["x"], 6), round(p["attributes"]["y"], 6))
                            for p in payload["nodes"]})
        if payload["nodes"] and coincidentes == 1 and len(payload["nodes"]) > 1:
            r["anomalias"].append(f"todos os {len(payload['nodes'])} nós na mesma coordenada")

        # ── MODO 2: overlay ──
        escalas = payload["overlay"]
        r["overlay"] = {}
        for metrica, esc in escalas.items():
            com_dado = sum(1 for n in payload["nodes"]
                           if n["attributes"].get(metrica) is not None)
            r["overlay"][metrica] = {"com_dado": com_dado,
                                     "min": esc.get("min"), "max": esc.get("max")}
            ticks = esc.get("ticks") or []
            if com_dado and not ticks:
                r["anomalias"].append(f"overlay[{metrica}]: {com_dado} nós com dado e 0 ticks")
            if any(t is None or (isinstance(t, float) and not math.isfinite(t))
                   for t in ticks):
                r["anomalias"].append(f"overlay[{metrica}]: tick não finito {ticks}")

        # ── MODO 3: densidade ──
        d = payload["density"]
        grade = d["grid"]
        r["densidade_soma"] = round(sum(sum(linha) for linha in grade), 4)
        r["densidade_dim"] = f"{d['cols']}×{d['rows']}"
        if payload["nodes"] and r["densidade_soma"] == 0:
            r["anomalias"].append("grade de densidade inteiramente zerada com nós presentes")
        if any(not math.isfinite(v) for linha in grade for v in linha):
            r["anomalias"].append("densidade com valor não finito")
        b = d["bounds"]
        if any(not math.isfinite(v) for v in b):
            r["anomalias"].append(f"bounds da densidade não finitos: {b}")

    except Exception as e:
        r["erro"] = f"{type(e).__name__}: {e}"
        r["traceback"] = traceback.format_exc()
    r["segundos"] = round(time.perf_counter() - t0, 2)
    return r


def veredito(r: dict) -> str:
    if r["erro"]:
        return "**QUEBRA**"
    if r["anomalias"]:
        return "**ANOMALIA**"
    return "OK"


def hashes(nome_caso: str) -> dict:
    """Impressões digitais de ordem, clusters, cores e posições de um caso.

    Existe para ser chamado em **subprocesso**, com `PYTHONHASHSEED` distinto: a ordem de
    iteração de `set`/`dict` de strings só muda entre processos, então determinismo de grafo
    não é verificável dentro de um pytest só. Ver `tests/test_mapas_adversariais.py`.
    """
    import hashlib

    from corpus_adversarial import POR_NOME

    G, pos = monta(POR_NOME[nome_caso], iteracoes=50)

    def h(o) -> str:
        crua = json.dumps(o, sort_keys=True, default=str).encode()
        return hashlib.sha256(crua).hexdigest()[:16]

    return {
        "ordem_nos": h(list(map(str, G.nodes()))),
        "clusters": h({str(n): G.nodes[n].get("group") for n in sorted(G.nodes(), key=str)}),
        "cores": h({str(n): G.nodes[n].get("color") for n in sorted(G.nodes(), key=str)}),
        "posicoes": h({str(n): [round(float(v), 4) for v in pos[n]]
                       for n in sorted(pos, key=str)}),
    }


def main() -> int:
    if "--hash" in sys.argv:
        print(json.dumps(hashes(sys.argv[sys.argv.index("--hash") + 1])))
        return 0

    resultados = [roda_caso(c) for c in CASOS]

    if "--json" in sys.argv:
        print(json.dumps(resultados, ensure_ascii=False, indent=2, default=str))
        return 0

    print("| caso | o que testa | nós | arestas | comp. | clusters | densidade Σ | s | veredito |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for r in resultados:
        if r["erro"]:
            print(f"| `{r['nome']}` | {r['alvo']} | — | — | — | — | — | "
                  f"{r['segundos']} | {veredito(r)} |")
            continue
        print(f"| `{r['nome']}` | {r['alvo']} | {r['nos']} | {r['arestas']} | "
              f"{r['componentes']} | {r['clusters']} | {r['densidade_soma']} | "
              f"{r['segundos']} | {veredito(r)} |")

    print()
    problemas = [r for r in resultados if r["erro"] or r["anomalias"]]
    if not problemas:
        print("Nenhuma anomalia. (Numa auditoria isto é para ser conferido, não comemorado.)")
        return 0

    print(f"### {len(problemas)} caso(s) com achado\n")
    for r in problemas:
        print(f"**`{r['nome']}`** — {r['descricao']}")
        if r["erro"]:
            print(f"- QUEBRA: `{r['erro']}`")
            print("```\n" + r["traceback"].strip()[-900:] + "\n```")
        for a in r["anomalias"]:
            print(f"- {a}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
