#!/usr/bin/env python3
"""Medições LIVE do modo navegação (Fase 4) — contra a API de verdade.

Método declarado, para os números serem reproduzíveis:
* busca ampla `empreendedorismo`, sem filtros, base OpenAlex;
* 3 repetições por medida, **mediana** reportada (a média seria puxada por um outlier de rede);
* cada repetição usa um `BrowseSession` NOVO e um provider NOVO — sem cache carregado de
  medição anterior, que faria a segunda rodada parecer instantânea;
* relógio: `time.perf_counter()`, em segundos.

Uso:
    python3 scripts/benchmark_search.py
    python3 scripts/benchmark_search.py --repeticoes 5
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUERY = "empreendedorismo"
METAS = {
    "contagem": 1.5,
    "primeiros_25": 2.5,
    "troca_pagina": 1.5,
    "aplicar_faceta": 1.5,
    "remover_faceta": 1.5,
}


def _sessao():
    from core.browse import BrowseSession
    from core.sources import OpenAlexProvider
    return BrowseSession(OpenAlexProvider(), QUERY)


def mede_uma_rodada() -> dict:
    r: dict = {}

    # Contagem + primeiros 25 vêm da MESMA requisição: o tempo até a contagem é o tempo até a
    # resposta chegar; o tempo até os cards inclui a normalização dos 25 registros.
    s = _sessao()
    t0 = time.perf_counter()
    pagina = s.fetch_page(1)
    t_resposta = time.perf_counter() - t0
    r["contagem"] = t_resposta
    r["primeiros_25"] = t_resposta
    r["total"] = pagina.total
    r["erro"] = pagina.error

    if pagina.error:
        return r

    # Troca de página: página nova, sem cache.
    t0 = time.perf_counter()
    s.fetch_page(4)
    r["troca_pagina"] = time.perf_counter() - t0

    # Facetas (as 6 em sequência, para saber o custo de montar a sidebar inteira).
    s2 = _sessao()
    s2.fetch_page(1)
    t0 = time.perf_counter()
    facetas = s2.fetch_facets()
    r["facetas_todas"] = time.perf_counter() - t0
    r["facetas_ok"] = sum(1 for f in facetas.values() if f.ok)

    # Aplicar faceta = nova query de 25.
    campo, valor = None, None
    for c, f in facetas.items():
        if f.ok and f.values:
            campo, valor = c, f.values[0].key
            break
    if campo:
        s2.toggle_facet(campo, valor)
        t0 = time.perf_counter()
        s2.fetch_page(1)
        r["aplicar_faceta"] = time.perf_counter() - t0
        r["total_filtrado"] = s2.total

        s2.clear_facet(campo, valor)
        t0 = time.perf_counter()
        s2.fetch_page(1, use_cache=False)
        r["remover_faceta"] = time.perf_counter() - t0
    return r


def mede_importacao(n: int = 1000) -> dict:
    """Tempo até baixar N registros no modo importação."""
    from core.import_job import ImportJob
    from core.sources import OpenAlexProvider

    prov = OpenAlexProvider()
    t0 = time.perf_counter()
    total = prov.count(QUERY)
    job = ImportJob(total_encontrado=total, limite=n)
    registros = []
    for rec in prov.search(QUERY, max_results=n):
        registros.append(rec)
        job.advance(1)
    dt = time.perf_counter() - t0
    return {"segundos": dt, "baixados": len(registros), "total": total,
            "taxa": len(registros) / dt if dt > 0 else 0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--sem-importacao", action="store_true")
    args = ap.parse_args()

    print(f"Query: {QUERY!r} · base OpenAlex · {args.repeticoes} repetições · mediana\n")
    rodadas = []
    for i in range(args.repeticoes):
        r = mede_uma_rodada()
        rodadas.append(r)
        if r.get("erro"):
            print(f"  rodada {i+1}: ERRO — {r['erro'][:90]}")
        else:
            print(f"  rodada {i+1}: contagem {r['contagem']:.2f}s · "
                  f"página {r.get('troca_pagina', 0):.2f}s · "
                  f"faceta {r.get('aplicar_faceta', 0):.2f}s · total {r['total']}")
        time.sleep(1.0)

    validas = [r for r in rodadas if not r.get("erro")]
    if not validas:
        print("\nTodas as rodadas falharam — sem rede ou API indisponível.")
        return 2

    print(f"\n{'medida':<18} {'mediana':>9} {'meta':>7}  status")
    print("-" * 50)
    for chave, meta in METAS.items():
        vals = [r[chave] for r in validas if chave in r]
        if not vals:
            print(f"{chave:<18} {'—':>9} {meta:>6.1f}s  sem amostra")
            continue
        med = statistics.median(vals)
        print(f"{chave:<18} {med:>8.2f}s {meta:>6.1f}s  {'OK' if med <= meta else 'ACIMA'}")

    facetas = [r["facetas_todas"] for r in validas if "facetas_todas" in r]
    if facetas:
        print(f"{'facetas (6, seq.)':<18} {statistics.median(facetas):>8.2f}s {'—':>7}  "
              f"({validas[0].get('facetas_ok', 0)}/6 ok)")

    # Reprodutibilidade: mesma busca, mesma contagem?
    totais = [r["total"] for r in validas]
    print(f"\nReprodutibilidade — contagem por rodada: {totais}")
    print("  idênticas:", "SIM" if len(set(totais)) == 1 else
          f"NÃO (variação {max(totais) - min(totais)})")

    if not args.sem_importacao:
        print("\nModo importação (1.000 registros)…")
        imp = mede_importacao(1000)
        print(f"  {imp['baixados']} baixados em {imp['segundos']:.1f}s "
              f"({imp['taxa']:.0f} reg/s) · universo {imp['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
