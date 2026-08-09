"""Fase 2 — payload do Sigma e cálculos das três visualizações.

Fixtures adversariais obrigatórias (regra 1): nó sem ano, sem citações, sem cluster; corpus
de um único ano; valores todos iguais (divisão por zero); grafo vazio; e valores extremos
(NaN/Infinity), que é a regressão do mapa abrindo em branco.
"""
import json
import math

import networkx as nx
import pytest

from core.map_render import (
    NO_DATA_COLOR,
    OVERLAY_PALETTE,
    color_at,
    contrast_ratio,
    density_grid,
    density_peaks,
    normalize_metric,
    overlay_color,
    overlay_scale,
    palette_contrast_report,
    print_pattern_for,
)
from core.matrix_builders import CLUSTER_PALETTE
from core.sigma_exporter import OVERLAY_METRICS, build_sigma_payload, export_sigma_json


def _grafo_rico():
    """Grafo com as métricas completas — o caso feliz."""
    G = nx.Graph()
    G.add_node("a", size=20, label="alpha", group=0, occurrence=10,
               year_mean=2015.0, citations_mean=5.0, citations_sum=50, relevance=1.2)
    G.add_node("b", size=10, label="beta", group=1, occurrence=4,
               year_mean=2023.0, citations_mean=1.0, citations_sum=4, relevance=0.8)
    G.add_edge("a", "b", weight=3.0, weight_raw=7)
    return G, {"a": (0.0, 0.0), "b": (1.0, 1.0)}


def _grafo_pobre():
    """Grafo POBRE: nó sem ano, sem citações, sem cluster, sem occurrence."""
    G = nx.Graph()
    G.add_node("x", size=10, label="x")                       # nada além do rótulo
    G.add_node("y", size=10, label="y", group=0, occurrence=0,
               year_mean=0.0,          # ano zero não existe → sentinela de "não sei"
               citations_mean=None)    # "não sei" em citações é None, não 0 (ver abaixo)
    G.add_edge("x", "y", weight=1)
    return G, {"x": (0.0, 0.0), "y": (1.0, 0.0)}


# ─────────────────── payload: métricas dos três modos ───────────────────

def test_payload_carries_every_metric_the_three_modes_need():
    G, pos = _grafo_rico()
    p = build_sigma_payload(G, pos)
    for node in p["nodes"]:
        a = node["attributes"]
        for chave in ("x", "y", "size", "color", "label", "cluster",
                      "occurrences", "avg_year", "avg_citations", "strength"):
            assert chave in a, f"atributo ausente no nó {node['key']}: {chave}"
    assert set(p["meta"]["metrics"]) == set(OVERLAY_METRICS)
    assert p["meta"]["nodes_total"] == 2 and p["meta"]["edges_total"] == 1


def test_missing_metrics_are_null_never_zero():
    """Nó sem métrica → `null`. `0` mentiria no overlay (viraria "o mais antigo do mapa")."""
    G, pos = _grafo_pobre()
    p = build_sigma_payload(G, pos)
    por_chave = {n["key"]: n["attributes"] for n in p["nodes"]}

    assert por_chave["x"]["avg_year"] is None
    assert por_chave["x"]["avg_citations"] is None
    # E o 0.0 gravado como sentinela de ano também vira None ("não sei").
    assert por_chave["y"]["avg_year"] is None, "0.0 de ano deveria virar None"
    assert por_chave["y"]["avg_citations"] is None
    # Cluster ausente cai para 0 (é índice de grupo, não métrica de overlay).
    assert por_chave["x"]["cluster"] == 0


def test_zero_citacoes_e_zero_e_nao_ausencia_de_dado():
    """A assimetria entre ano e citações, que a Auditoria 1 encontrou medindo.

    Este teste já existiu ao contrário: afirmava que `citations_mean=0.0` virava `None`,
    e por isso a suíte inteira ficava verde sobre o defeito. **Zero citação é o valor mais
    comum de artigo recente** — tratá-lo como ausência apagava o overlay inteiro num corpus
    dos últimos dois anos, com a legenda anunciando "sem dado" sobre um dado que existia.
    O payload chegava a se contradizer: `citations_sum: 0` ao lado de `avg_citations: null`.

    Ano continua com 0 = "não sei", e a diferença é que **ano zero não existe**.
    """
    G = nx.Graph()
    G.add_node("recente", size=10, label="recente", group=0, occurrence=5,
               year_mean=2026.0, citations_mean=0.0, citations_sum=0)
    G.add_node("sem_info", size=10, label="sem_info", group=0, occurrence=5,
               year_mean=0.0, citations_mean=None, citations_sum=None)
    G.add_edge("recente", "sem_info", weight=1)
    p = build_sigma_payload(G, {"recente": (0.0, 0.0), "sem_info": (1.0, 0.0)})
    por_chave = {n["key"]: n["attributes"] for n in p["nodes"]}

    assert por_chave["recente"]["avg_citations"] == 0.0, "zero citações virou 'sem dado'"
    assert por_chave["sem_info"]["avg_citations"] is None
    # Contradição interna do payload: os dois campos falam do mesmo fato.
    assert por_chave["recente"]["citations_sum"] == 0.0
    # E a legenda não pode contar o nó com zero citações como "sem dado".
    assert p["overlay"]["avg_citations"]["no_data"] == 1


def test_no_nan_or_infinity_ever_reaches_the_json(tmp_path):
    """Regressão do mapa abrindo em branco: NaN quebra o JSON.parse do navegador em silêncio."""
    G = nx.Graph()
    G.add_node("n1", size=float("nan"), label="n1", group=0, occurrence=float("inf"),
               year_mean=float("nan"), citations_mean=float("-inf"))
    G.add_node("n2", size=10, label="n2", group=0, occurrence=2, year_mean=2020)
    G.add_edge("n1", "n2", weight=float("nan"))
    pos = {"n1": (float("nan"), float("inf")), "n2": (1.0, 1.0)}

    caminho = tmp_path / "graph.json"
    export_sigma_json(G, pos, str(caminho))          # allow_nan=False: levantaria se vazasse
    texto = caminho.read_text(encoding="utf-8")
    for proibido in ("NaN", "Infinity", "-Infinity"):
        assert proibido not in texto, f"{proibido} vazou para o JSON"

    dados = json.loads(texto)
    for node in dados["nodes"]:
        for chave in ("x", "y", "size"):
            v = node["attributes"][chave]
            assert v is not None and math.isfinite(v), f"{chave} não finito em {node['key']}"


def test_empty_graph_yields_valid_empty_payload(tmp_path):
    """Grafo vazio → payload válido e vazio (o JS mostra "Nenhum dado para exibir")."""
    caminho = tmp_path / "g.json"
    p = export_sigma_json(nx.Graph(), {}, str(caminho))
    assert p["nodes"] == [] and p["edges"] == []
    assert p["meta"]["nodes_total"] == 0
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["nodes"] == []
    # A grade de densidade existe e é toda zero — não é None, para o JS não quebrar.
    assert dados["density"]["grid"] and all(
        v == 0 for linha in dados["density"]["grid"] for v in linha)


def test_edge_cap_keeps_strongest_and_reports_honestly():
    """Teto de arestas corta as MAIS FRACAS e o meta informa o total real."""
    G = nx.Graph()
    for i in range(6):
        G.add_node(f"n{i}", size=10, label=f"n{i}", group=0, occurrence=1)
    pesos = [(0, 1, 9.0), (1, 2, 8.0), (2, 3, 1.0), (3, 4, 0.5), (4, 5, 7.0)]
    for u, v, w in pesos:
        G.add_edge(f"n{u}", f"n{v}", weight=w)
    pos = {f"n{i}": (float(i), 0.0) for i in range(6)}

    p = build_sigma_payload(G, pos, max_edges=3)
    assert p["meta"]["edges_total"] == 5
    assert p["meta"]["edges_rendered"] == 3
    assert p["meta"]["edges_capped"] is True
    mantidos = sorted(e["attributes"]["weight"] for e in p["edges"])
    assert mantidos == [7.0, 8.0, 9.0], f"deveria manter as mais fortes, manteve {mantidos}"


def test_positions_are_identical_across_modes():
    """Alternar de modo é troca de camada visual: as posições exportadas são as mesmas.

    O payload é gerado UMA vez e serve os três modos — não há caminho para recalcular
    layout por modo. Este teste trava o contrato: o array de posições não muda.
    """
    G, pos = _grafo_rico()
    p = build_sigma_payload(G, pos)
    esperado = [(n["key"], n["attributes"]["x"], n["attributes"]["y"]) for n in p["nodes"]]

    # Reexportar com parâmetros de OUTROS modos (densidade diferente) não move nada.
    for cols, rows, raio in ((8, 8, 0.05), (64, 64, 0.4)):
        p2 = build_sigma_payload(G, pos, density_cols=cols, density_rows=rows,
                                 density_radius=raio)
        obtido = [(n["key"], n["attributes"]["x"], n["attributes"]["y"]) for n in p2["nodes"]]
        assert obtido == esperado, "as posições mudaram entre configurações de modo"


# ─────────────────── escala do overlay ───────────────────

def test_overlay_color_at_extremes_and_middle():
    """valor→cor nos extremos e no meio, batendo com as paradas da paleta."""
    frio = "#%02X%02X%02X" % OVERLAY_PALETTE[0][1]
    meio = "#%02X%02X%02X" % OVERLAY_PALETTE[1][1]
    quente = "#%02X%02X%02X" % OVERLAY_PALETTE[-1][1]

    assert overlay_color(2010, 2010, 2020) == frio
    assert overlay_color(2015, 2010, 2020) == meio
    assert overlay_color(2020, 2010, 2020) == quente
    # Fora da faixa é preso nos extremos (nunca cor inválida).
    assert overlay_color(1900, 2010, 2020) == frio
    assert overlay_color(2100, 2010, 2020) == quente
    assert color_at(-5) == frio and color_at(99) == quente


def test_overlay_scale_with_all_values_equal_does_not_divide_by_zero():
    """Todos os valores iguais (corpus de um único ano) — o mesmo bug do slider de anos."""
    assert normalize_metric(2021, 2021, 2021) == 0.5, "faixa nula deve cair no meio da escala"
    cor = overlay_color(2021, 2021, 2021)
    assert cor != NO_DATA_COLOR and cor.startswith("#")

    escala = overlay_scale([2021, 2021, 2021])
    assert escala["uniform"] is True
    assert escala["min"] == escala["max"] == 2021
    assert len(escala["ticks"]) == 1, "escala uniforme mostra uma marca só"
    assert escala["no_data"] == 0


def test_overlay_scale_counts_missing_values_explicitly():
    """"Sem dado" é contado e exposto — a legenda diz quantos nós ficaram cinza."""
    escala = overlay_scale([2010, None, 2020, None, float("nan")])
    assert escala["no_data"] == 3, f"deveria contar 3 sem dado, contou {escala['no_data']}"
    assert escala["min"] == 2010 and escala["max"] == 2020
    assert overlay_color(None, 2010, 2020) == NO_DATA_COLOR

    # Nenhum valor válido: faixa nula, sem exceção.
    vazia = overlay_scale([None, None])
    assert vazia["min"] is None and vazia["ticks"] == [] and vazia["no_data"] == 2


def test_overlay_scale_ticks_span_the_range():
    escala = overlay_scale([2000, 2010, 2020], ticks=3)
    valores = [t["value"] for t in escala["ticks"]]
    assert valores[0] == 2000 and valores[-1] == 2020
    assert valores[1] == pytest.approx(2010)


# ─────────────────── densidade ───────────────────

def test_density_grid_finds_two_known_clusters():
    """Conjunto sintético com DOIS aglomerados conhecidos → dois picos, nos lugares certos."""
    pontos = ([(0.1 + i * 0.005, 0.1 + i * 0.005) for i in range(12)]      # canto inferior-esq
              + [(0.9 - i * 0.005, 0.9 - i * 0.005) for i in range(12)])   # canto superior-dir
    grade = density_grid(pontos, cols=24, rows=24, radius=0.08,
                         bounds=(0.0, 0.0, 1.0, 1.0))
    picos = density_peaks(grade, limiar=0.4)
    assert len(picos) == 2, f"esperava 2 aglomerados, achou {len(picos)}: {picos}"

    # Um perto do canto (0,0) e outro perto de (1,1) — em índices de grade.
    linhas = sorted(r for r, _ in picos)
    cols = sorted(c for _, c in picos)
    assert linhas[0] < 8 and linhas[1] > 15, f"picos nas linhas erradas: {picos}"
    assert cols[0] < 8 and cols[1] > 15, f"picos nas colunas erradas: {picos}"
    # A grade é normalizada: o máximo é 1.0.
    assert max(v for linha in grade["grid"] for v in linha) == pytest.approx(1.0)


def test_density_grid_weights_change_the_peak():
    """O peso (ocorrências) pesa: o aglomerado com nós maiores fica mais quente."""
    pontos = [(0.2, 0.2), (0.2, 0.21), (0.8, 0.8), (0.8, 0.81)]
    grade = density_grid(pontos, weights=[10, 10, 1, 1], cols=20, rows=20, radius=0.1,
                        bounds=(0.0, 0.0, 1.0, 1.0))
    g = grade["grid"]
    # Célula do aglomerado pesado deve superar a do leve.
    pesado = max(g[r][c] for r in range(0, 8) for c in range(0, 8))
    leve = max(g[r][c] for r in range(12, 20) for c in range(12, 20))
    assert pesado > leve, f"aglomerado com peso 10 deveria ser mais denso ({pesado} vs {leve})"


def test_density_grid_degenerate_inputs_do_not_crash():
    """Entradas degeneradas: vazio, ponto único, todos no mesmo lugar, NaN."""
    vazia = density_grid([], cols=4, rows=4)
    assert vazia["max"] == 0.0 and len(vazia["grid"]) == 4

    unico = density_grid([(5.0, 5.0)], cols=4, rows=4)
    assert unico["max"] > 0, "um ponto ainda gera densidade"

    iguais = density_grid([(1.0, 1.0)] * 5, cols=4, rows=4)   # bounds degenerado
    assert iguais["max"] > 0

    com_nan = density_grid([(float("nan"), 0.0), (1.0, 1.0)], cols=4, rows=4)
    assert all(math.isfinite(v) for linha in com_nan["grid"] for v in linha)


# ─────────────────── paleta e contraste ───────────────────

def test_cluster_palette_pairs_are_perceptually_distinguishable(capsys):
    """Clusters vizinhos precisam ser distinguíveis; o pior par é o que decide.

    A métrica é ΔE (CIE76), não a razão WCAG: WCAG mede luminância, para texto sobre fundo.
    Vermelho #DF3117 e roxo #B65CA2 dão razão WCAG 1.1 — e se distinguem à vista sem esforço,
    porque o matiz é muito diferente (ΔE > 59). Julgar a paleta de clusters por WCAG
    reprovaria uma paleta legível.
    """
    rel = palette_contrast_report(CLUSTER_PALETTE)
    with capsys.disabled():
        print(f"\n[paleta] pior par (ΔE) {rel['worst_pair']} = ΔE {rel['min_delta_e']} · "
              f"pior par (WCAG) {rel['worst_wcag_pair']} = {rel['min_ratio']}:1 · "
              f"{len(rel['pairs'])} pares")
    assert rel["min_delta_e"] >= 20.0, (
        f"par de clusters indistinguível: {rel['worst_pair']} ΔE={rel['min_delta_e']} "
        f"(ΔE ≳ 20 = claramente distinguíveis)")
    # Aqui WCAG é a métrica CERTA: cor de nó contra o fundo papel é figura sobre fundo.
    for cor in CLUSTER_PALETTE:
        assert contrast_ratio(cor, "#F6F4EE") >= 1.5, f"{cor} some no fundo papel"


def test_delta_e_and_wcag_measure_different_things():
    """Trava a distinção entre as duas métricas — foi o que fez o teste acima ser reescrito."""
    from core.map_render import delta_e
    vermelho, roxo = "#DF3117", "#B65CA2"
    # Luminância parecida (WCAG baixo) mas matiz muito diferente (ΔE alto).
    assert contrast_ratio(vermelho, roxo) < 1.3
    assert delta_e(vermelho, roxo) > 40
    # Cores idênticas: ΔE zero e razão 1.
    assert delta_e("#141414", "#141414") == pytest.approx(0.0)
    assert contrast_ratio("#141414", "#141414") == pytest.approx(1.0)
    # Preto e branco: os dois extremos concordam.
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)
    assert delta_e("#000000", "#FFFFFF") == pytest.approx(100.0, abs=1.0)


def test_print_theme_assigns_distinct_patterns_per_cluster():
    """Tema impressão: clusters distinguíveis por PADRÃO, não só por cor."""
    padroes = [print_pattern_for(i) for i in range(8)]
    assert len(set(padroes)) == 8, f"padrões repetidos entre clusters: {padroes}"
    assert print_pattern_for(0) == print_pattern_for(8), "deve ser cíclico e determinístico"


# ─────────────────── contrato do JS (sem navegador) ───────────────────

def test_map_js_handles_all_three_modes_and_null_metrics():
    """Garantias no fonte do map.js que o teste de Python consegue verificar:
    os três modos existem, nulo vira cinza, e a densidade some com as arestas."""
    from pathlib import Path
    js = Path("assets/map.js").read_text(encoding="utf-8")

    for modo in ('"network"', '"overlay"', '"density"'):
        assert modo in js, f"modo ausente no map.js: {modo}"
    assert "NO_DATA_COLOR" in js, "map.js precisa do cinza de sem-dado"
    assert "showEmpty" in js and "map_empty" in js, "mensagem de vazio ausente"
    # A rampa vem do Python (payload.overlay[...].stops) — fonte única da verdade.
    assert "scale.stops" in js or "stops" in js
    # Sombra é proibida pelo design system.
    assert "boxShadow" not in js and "box-shadow" not in js


def test_map_template_has_the_three_tabs_and_zero_radius():
    from pathlib import Path
    html = Path("assets/map_template.html").read_text(encoding="utf-8")
    for tab in ("tab-network", "tab-overlay", "tab-density"):
        assert f'id="{tab}"' in html, f"aba ausente no template: {tab}"
    assert 'id="legend"' in html, "barra de gradiente ausente"
    assert "border-radius: 0" in html
    # Nenhuma sombra em nenhum lugar do template.
    assert "box-shadow" not in html
    # O único gradiente permitido é o da barra do overlay, e ele é criado no JS.
    assert "linear-gradient" not in html


def test_graph_generation_is_deterministic_across_hash_seeds():
    """Mesmo corpus + mesmos parâmetros → MESMOS clusters, sempre.

    Bug real achado ao gerar as evidências visuais: os nós eram inseridos iterando um `set`,
    cuja ordem varia com PYTHONHASHSEED, e o Louvain depende da ordem de inserção. O mesmo
    corpus dava 4 clusters numa execução e 5 na seguinte — num programa científico isso é
    grave, porque o usuário regenera o mapa e recebe outra resposta.

    O teste roda em subprocessos com sementes de hash DIFERENTES: dentro de um mesmo processo
    a ordem do set é estável e o bug não apareceria.
    """
    import subprocess
    import sys
    from collections import Counter

    script = (
        "import sys, json; sys.path.insert(0, '.');"
        "import pandas as pd;"
        "from core.matrix_builders import NetworkGenerator;"
        "docs=[{'keywords': '; '.join(k), 'title': 't', 'abstract': '', 'year': 2020,"
        " 'citations': 1} for k in ["
        "  ['alpha','beta','gamma'],['alpha','beta'],['gamma','delta'],['delta','epsilon'],"
        "  ['epsilon','zeta'],['zeta','alpha'],['beta','gamma','delta'],['alpha','epsilon'],"
        "  ['eta','theta'],['eta','theta','iota'],['theta','iota'],['iota','eta'],"
        "]];"
        "G=NetworkGenerator(pd.DataFrame(docs)).build_keyword_cooccurrence(min_occurrence=2,"
        " field='keywords');"
        "import networkx as nx;"
        "print(sorted((n, d) for n, d in G.nodes(data='group')))"
    )
    saidas = []
    for semente in ("0", "1", "12345"):
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": semente, "PATH": "/usr/bin:/bin"})
        assert r.returncode == 0, f"subprocesso falhou (seed={semente}): {r.stderr[-400:]}"
        saidas.append(r.stdout.strip().splitlines()[-1])

    assert saidas[0] == saidas[1] == saidas[2], (
        "partição muda conforme PYTHONHASHSEED — os nós estão sendo inseridos a partir de "
        f"um set sem ordenar:\n" + "\n".join(saidas))
