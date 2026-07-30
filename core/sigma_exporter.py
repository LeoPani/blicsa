"""Exporta o grafo para o payload que o `map.js` consome (Sigma v3 / graphology).

O JSON carrega, por nó, TODAS as métricas dos três modos de visualização (network, overlay,
densidade) — porque alternar entre eles é troca de camada visual, nunca recálculo de layout:
as posições saem daqui uma única vez e não mudam mais.

Duas regras que valem contrato (e têm teste):

1. **Nada de `NaN`/`Infinity`.** Já causou o bug do mapa abrindo em branco: `JSON.parse` morre
   em silêncio no navegador. `allow_nan=False` faz o `json.dump` levantar em vez de gravar um
   arquivo que só quebra depois, longe da causa.
2. **Métrica ausente é `null`, não `0`.** No overlay, `0` seria pintado como "o valor mais
   baixo da escala" — um nó sem ano apareceria como o mais antigo do mapa. `null` vira o cinza
   neutro de "sem dado", e a legenda diz quantos são.
"""

import json
import math

import networkx as nx

from core.map_render import density_grid, overlay_scale

# Métricas que o seletor do overlay oferece. A chave é o que vai no JSON.
OVERLAY_METRICS = ("avg_year", "avg_citations", "occurrences")


def _finite(value, default=None):
    """Número finito ou `default`. É o filtro que impede NaN/Infinity de vazar pro JSON."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def _metric(attr: dict, *nomes, zero_is_missing: bool = False):
    """Primeira métrica presente entre `nomes`, como número finito ou None.

    `zero_is_missing=True` para ano e citações médias: o grafo antigo gravava 0.0 quando não
    achava o dado (ver `NetworkGenerator.compute_overlay_scores`), e 0 ali significa "não sei",
    não "ano zero". Traduzir isso para None é o que faz o overlay ficar honesto.
    """
    for nome in nomes:
        if nome in attr:
            v = _finite(attr.get(nome))
            if v is None:
                continue
            if zero_is_missing and v == 0:
                continue
            return v
    return None


def build_sigma_payload(
    G: nx.Graph,
    positions: dict,
    max_edges: int = 0,
    density_cols: int = 32,
    density_rows: int = 32,
    density_radius: float = 0.15,
) -> dict:
    """Monta o dicionário do payload (sem gravar em disco) — é o que os testes inspecionam.

    Args:
        G: grafo já com clusters e métricas.
        positions: {nó: (x, y)} — as posições definitivas, compartilhadas pelos três modos.
        max_edges: teto de arestas renderizadas (0 = sem teto). Corta pelas mais fracas,
            para não emaranhar o mapa; o total real fica em `meta.edges_total`.
    """
    raw_sizes = nx.get_node_attributes(G, "size")
    if raw_sizes:
        valores = [v for v in (_finite(s) for s in raw_sizes.values()) if v is not None]
        min_sz = min(valores) if valores else 0.0
        max_sz = max(valores) if valores else 0.0
        span = (max_sz - min_sz) or 1.0
    else:
        min_sz, span = 0.0, 1.0

    nodes = []
    for node in G.nodes():
        attr = G.nodes[node]
        px, py = positions.get(node, (0.0, 0.0))
        x = _finite(px, 0.0)
        y = _finite(py, 0.0)

        raw_sz = _finite(raw_sizes.get(node), 10.0)
        sigma_size = _finite(3 + 15 * (raw_sz - min_sz) / span, 3.0)

        ocorrencias = _metric(attr, "occurrence", "occurrences")
        nodes.append({
            "key": str(node),
            "attributes": {
                "x": x,
                "y": y,
                "size": float(sigma_size),
                "color": attr.get("color", "#1E4DA0"),
                "label": str(attr.get("label", node)),
                "cluster": int(_finite(attr.get("group"), 0) or 0),
                # ── métricas dos três modos (None = sem dado, nunca 0) ──
                "occurrences": ocorrencias,
                "occurrence": ocorrencias,          # nome legado, mantido por compatibilidade
                "doc_freq": _metric(attr, "doc_freq"),
                "relevance": _metric(attr, "relevance"),
                "avg_year": _metric(attr, "year_mean", "avg_year", zero_is_missing=True),
                "avg_citations": _metric(attr, "citations_mean", "avg_citations",
                                         zero_is_missing=True),
                "citations_sum": _metric(attr, "citations_sum"),
                # Força de ligação = grau ponderado; alimenta o seletor de tamanho do nó.
                "strength": _finite(G.degree(node, weight="weight"), 0.0),
            },
        })

    todas = []
    for u, v, data in G.edges(data=True):
        peso = _finite(data.get("weight"), 1.0)
        todas.append((peso, u, v, data))
    edges_total = len(todas)

    # Teto de arestas: mantém as mais FORTES (as fracas é que viram emaranhado).
    if max_edges and edges_total > max_edges:
        todas.sort(key=lambda t: t[0], reverse=True)
        todas = todas[:max_edges]

    # Espessura em PIXELS, normalizada. O `weight` cru é força de associação e chega a
    # centenas; usá-lo direto como `size` pintava arestas gigantes que viravam um borrão
    # cinza cobrindo o mapa. A espessura fica proporcional à força, dentro de uma faixa
    # legível — é o que o prompt pede ("espessura proporcional à força de associação").
    if todas:
        pesos = [t[0] for t in todas]
        w_min, w_max = min(pesos), max(pesos)
        w_span = (w_max - w_min) or 1.0
    else:
        w_min, w_span = 0.0, 1.0
    EDGE_MIN, EDGE_MAX = 0.15, 2.0

    edges = []
    for idx, (peso, u, v, data) in enumerate(todas):
        espessura = EDGE_MIN + (EDGE_MAX - EDGE_MIN) * ((peso - w_min) / w_span)
        edges.append({
            "key": f"e{idx}",
            "source": str(u),
            "target": str(v),
            "attributes": {
                "size": float(_finite(espessura, EDGE_MIN)),
                "weight": float(peso),
                "weight_raw": float(_finite(data.get("weight_raw"), peso)),
                # Alpha baixo: com milhares de arestas, 0.15 já satura o canvas inteiro.
                "color": "rgba(20,20,20,0.05)",
            },
        })

    # Escalas do overlay, já resolvidas em Python: JS e Python usam a MESMA rampa e a mesma
    # faixa, então a barra de gradiente nunca discorda das cores dos nós.
    escalas = {
        m: overlay_scale([n["attributes"].get(m) for n in nodes])
        for m in OVERLAY_METRICS
    }

    grade = density_grid(
        [(n["attributes"]["x"], n["attributes"]["y"]) for n in nodes],
        [(n["attributes"].get("occurrences") or 1.0) for n in nodes],
        cols=density_cols, rows=density_rows, radius=density_radius,
    )

    return {
        "options": {"type": "undirected", "multi": False, "allowSelfLoops": False},
        "nodes": nodes,
        "edges": edges,
        "overlay": escalas,
        "density": {"cols": grade["cols"], "rows": grade["rows"],
                    "radius": density_radius, "grid": grade["grid"],
                    "bounds": list(grade["bounds"])},
        "meta": {
            "nodes_total": len(nodes),
            "edges_total": edges_total,
            "edges_rendered": len(edges),
            "edges_capped": bool(max_edges and edges_total > max_edges),
            "clusters": sorted({n["attributes"]["cluster"] for n in nodes}),
            "metrics": list(OVERLAY_METRICS),
        },
    }


def export_sigma_json(G: nx.Graph, positions: dict, filepath: str, **kwargs):
    """Grava o payload. `allow_nan=False` de propósito: melhor levantar aqui do que gerar um
    JSON que o navegador rejeita depois, com o mapa abrindo em branco e sem pista da causa."""
    payload = build_sigma_payload(G, positions, **kwargs)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False)
    return payload
