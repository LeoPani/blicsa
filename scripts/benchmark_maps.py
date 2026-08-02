#!/usr/bin/env python3
"""Benchmark da geração de mapas (Fase 5) — tempo por etapa e pico de memória.

Roda o pipeline COMPLETO como o app roda: extração de termos → matriz de coocorrência →
clusters → layout ForceAtlas2 → payload do Sigma. Mede cada etapa em separado, para que um
número ruim aponte o gargalo em vez de virar "está lento".

Uso:
    python3 scripts/benchmark_maps.py                 # 1k, 5k e 10k documentos
    python3 scripts/benchmark_maps.py --docs 1000     # só um tamanho
"""

from __future__ import annotations

import argparse
import gc
import random
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

VOCAB_BASE = [
    "innovation", "policy", "regional development", "technology transfer", "patent",
    "entrepreneurship", "knowledge management", "university", "industry", "cluster",
    "network analysis", "bibliometrics", "citation", "research funding", "startup",
    "incubator", "venture capital", "intellectual property", "collaboration", "spillover",
    "absorptive capacity", "open innovation", "triple helix", "ecosystem", "productivity",
    "digital transformation", "artificial intelligence", "machine learning", "data science",
    "sustainability", "circular economy", "green technology", "public policy", "governance",
]


def corpus_sintetico(n_docs: int, seed: int = 42, vocab_por_tema: int = 400) -> pd.DataFrame:
    """Corpus com estrutura temática plantada — não é ruído uniforme.

    Ruído puro geraria um grafo sem comunidades e o benchmark mediria um caso que não
    existe na prática. Aqui há 5 temas, cada documento sorteia de um deles com vazamento.

    O vocabulário é grande e com cauda longa (Zipf), como um corpus de verdade: uns poucos
    termos muito frequentes e uma multidão de raros. Um vocabulário pequeno faria o grafo
    saturar em poucas dezenas de nós e o benchmark mediria um caso irreal.
    """
    rnd = random.Random(seed)
    temas = []
    for t in range(5):
        base = VOCAB_BASE[t::5]
        # Cauda longa: termos derivados, cada vez mais raros.
        vocab = list(base) + [f"{rnd.choice(base)} {t}{j}" for j in range(vocab_por_tema)]
        temas.append(vocab)

    def sorteia(vocab: list[str], k: int) -> list[str]:
        # Zipf: índice baixo (termo comum) sai muito mais que índice alto.
        escolhidos = set()
        while len(escolhidos) < k:
            idx = min(int(rnd.paretovariate(1.2)) - 1, len(vocab) - 1)
            escolhidos.add(vocab[idx])
        return list(escolhidos)

    linhas = []
    for i in range(n_docs):
        tema = temas[i % 5]
        kws = sorteia(tema, rnd.randint(4, 7))
        if rnd.random() < 0.3:                     # vazamento entre temas
            kws.append(rnd.choice(VOCAB_BASE))
        linhas.append({
            "title": f"Study {i} on " + " and ".join(kws[:2]),
            "abstract": ("This paper analyses " + ", ".join(kws)
                         + " in the context of regional innovation systems."),
            "keywords": "; ".join(kws),
            "year": 2005 + (i % 20),
            "citations": rnd.randint(0, 200),
            "authors": f"Author {i % 500}; Coauthor {i % 300}",
            "source": f"Journal {i % 40}",
            "language": "en",
        })
    return pd.DataFrame(linhas)


def bench(n_docs: int, min_occ: int, fa2_iter: int = 200) -> dict:
    from core.matrix_builders import NetworkGenerator
    from core.sigma_exporter import build_sigma_payload
    from core.term_extraction import extract_terms

    gc.collect()
    df = corpus_sintetico(n_docs)
    resultado: dict = {"docs": n_docs, "min_occ": min_occ}

    tracemalloc.start()
    t0 = time.perf_counter()

    t = time.perf_counter()
    termos = extract_terms(df, fields="both", min_occurrences=min_occ)
    resultado["t_extracao"] = time.perf_counter() - t
    resultado["termos"] = len(termos)

    t = time.perf_counter()
    gen = NetworkGenerator(df)
    G = gen.build_keyword_cooccurrence(min_occurrence=min_occ, field="keywords")
    resultado["t_matriz_clusters"] = time.perf_counter() - t
    resultado["nos"] = G.number_of_nodes()
    resultado["arestas"] = G.number_of_edges()
    resultado["clusters"] = len({g for _, g in G.nodes(data="group")})

    t = time.perf_counter()
    if G.number_of_nodes():
        from fa2_modified import ForceAtlas2
        pos = ForceAtlas2(scalingRatio=2.0, gravity=1.0, verbose=False
                          ).forceatlas2_networkx_layout(G, pos=None, iterations=fa2_iter)
    else:
        pos = {}
    resultado["t_layout"] = time.perf_counter() - t

    t = time.perf_counter()
    payload = build_sigma_payload(G, pos, max_edges=2000)
    resultado["t_payload"] = time.perf_counter() - t
    resultado["arestas_render"] = payload["meta"]["edges_rendered"]

    resultado["t_total"] = time.perf_counter() - t0
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    resultado["pico_mb"] = pico / (1024 * 1024)
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", type=int, nargs="*", default=[1000, 5000, 10000])
    ap.add_argument("--fa2", type=int, default=200)
    args = ap.parse_args()

    print(f"{'docs':>7} {'termos':>7} {'nós':>6} {'arestas':>8} {'extrai':>8} "
          f"{'matriz':>8} {'layout':>8} {'payload':>8} {'TOTAL':>8} {'pico MB':>9}")
    print("-" * 92)
    linhas = []
    for n in args.docs:
        # Limiar cresce com o corpus, como na prática (o guia mira 1.000–2.000 termos).
        min_occ = {1000: 5, 5000: 15, 10000: 25}.get(n, max(3, n // 400))
        r = bench(n, min_occ, args.fa2)
        linhas.append(r)
        print(f"{r['docs']:>7} {r['termos']:>7} {r['nos']:>6} {r['arestas']:>8} "
              f"{r['t_extracao']:>7.2f}s {r['t_matriz_clusters']:>7.2f}s "
              f"{r['t_layout']:>7.2f}s {r['t_payload']:>7.2f}s {r['t_total']:>7.2f}s "
              f"{r['pico_mb']:>8.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
