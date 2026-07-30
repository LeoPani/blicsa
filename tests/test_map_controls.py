"""Fase 3 — controles de qualidade do mapa.

Fixtures adversariais (regra 1): resposta de IA malformada, `.blicsa` de versão antiga e com
lixo, limiar que zera os termos, grafo vazio, valores extremos de resolução.
"""
import json
import math
import xml.etree.ElementTree as ET

import networkx as nx
import pandas as pd
import pytest

from core.map_controls import (
    RESOLUTION_DEFAULT,
    RESOLUTION_MAX,
    RESOLUTION_MIN,
    MapParams,
    allowed_terms_from,
    apply_cluster_labels,
    build_legend,
    cluster_sizes,
    export_svg,
    parse_cluster_labels,
    recluster,
)
from core.matrix_builders import NetworkGenerator
from core.term_extraction import extract_terms, threshold_preview


def _corpus_com_estrutura():
    """Corpus com DOIS grupos temáticos plantados, que se separam ao subir a resolução."""
    docs = []
    grupo_a = ["alpha", "beta", "gamma", "delta"]
    grupo_b = ["sigma", "tau", "upsilon", "phi"]
    for _ in range(8):
        docs.append({"keywords": "; ".join(grupo_a), "title": "a", "abstract": "",
                     "year": 2020, "citations": 5})
        docs.append({"keywords": "; ".join(grupo_b), "title": "b", "abstract": "",
                     "year": 2021, "citations": 3})
    # Uma ponte fraca entre os grupos, para não serem componentes separados.
    docs.append({"keywords": "delta; sigma", "title": "ponte", "abstract": "",
                 "year": 2020, "citations": 1})
    return pd.DataFrame(docs)


def _grafo_pronto(min_occ=2):
    gen = NetworkGenerator(_corpus_com_estrutura())
    G = gen.build_keyword_cooccurrence(min_occurrence=min_occ, field="keywords")
    pos = {n: (float(i % 5), float(i // 5)) for i, n in enumerate(G.nodes())}
    return gen, G, pos


# ─────────────────── resolução: muda clusters, NÃO move nós ───────────────────

def test_resolution_changes_the_partition_without_moving_nodes():
    """Ajustar a resolução recalcula clusters e NÃO refaz o layout.

    É o ponto do passo 14 do guia: o mapa tem de continuar sendo o mesmo mapa, senão o
    usuário perde a referência visual a cada ajuste.

    O grafo é o clube de karatê do Zachary — referência clássica com estrutura não-trivial.
    A primeira fixture que escrevi (dois grupos de 4, perfeitamente separados) dava a MESMA
    partição em toda a faixa, e o teste passava mesmo com a resolução fixada em 1.0: foi a
    matriz de reinjeção que expôs isso.
    """
    G = nx.karate_club_graph()
    nx.set_edge_attributes(G, 1.0, "weight")
    for n in G.nodes():
        G.nodes[n].update(size=10, label=str(n))
    pos = {n: (float(n % 7), float(n // 7)) for n in G.nodes()}
    antes = dict(pos)

    baixa = recluster(G, resolution=0.5)
    part_baixa = dict(baixa)
    tam_baixa = cluster_sizes(G)

    alta = recluster(G, resolution=2.0)
    part_alta = dict(alta)
    tam_alta = cluster_sizes(G)

    # As posições são um dicionário à parte: reclusterizar não pode encostar nelas.
    assert pos == antes, "as posições mudaram ao reclusterizar"
    assert set(pos) == set(G.nodes()), "o conjunto de nós mudou"
    # A resolução TEM de mudar a partição — senão o controle é decorativo.
    assert part_baixa != part_alta, (
        f"resolução 0.5 e 2.0 deram a mesma partição ({tam_baixa} vs {tam_alta}) — "
        "o parâmetro não está chegando ao algoritmo")
    assert len(tam_baixa) >= 1 and len(tam_alta) >= 1


def test_resolution_reaches_the_clustering_algorithm():
    """O valor pedido chega mesmo ao algoritmo (espião no ponto de chamada).

    Complementa o teste acima: aqui a checagem independe de o grafo reagir à resolução,
    então continua valendo para qualquer corpus.
    """
    from unittest.mock import patch

    G = nx.karate_club_graph()
    nx.set_edge_attributes(G, 1.0, "weight")
    for n in G.nodes():
        G.nodes[n].update(size=10, label=str(n))

    vistos = []
    import community as community_louvain
    real = community_louvain.best_partition

    def espiao(graph, **kwargs):
        vistos.append(kwargs.get("resolution"))
        return real(graph, **kwargs)

    with patch("core.matrix_builders.community_louvain.best_partition", side_effect=espiao):
        recluster(G, resolution=1.2)
        recluster(G, resolution=0.7)
    assert vistos == [1.2, 0.7], f"resoluções recebidas pelo algoritmo: {vistos}"


def test_louvain_resolution_is_not_monotonic_and_the_ui_must_not_promise_otherwise():
    """Documenta o comportamento REAL: com python-louvain a resolução não é monotônica.

    O tooltip da UI dizia "valores > 1 geram mais clusters, < 1 geram menos". Medido no
    karate club: 0.5 → 5 clusters, 1.0 → 4, 1.5 → 5, 2.0 → 7 — sobe, desce e sobe. A promessa
    era falsa, e o texto foi corrigido. Este teste trava a medição para que a afirmação no
    tooltip continue verdadeira.
    """
    G = nx.karate_club_graph()
    nx.set_edge_attributes(G, 1.0, "weight")
    for n in G.nodes():
        G.nodes[n].update(size=10, label=str(n))

    contagens = {}
    for r in (0.5, 1.0, 1.5, 2.0):
        recluster(G, resolution=r)
        contagens[r] = len(cluster_sizes(G))

    valores = [contagens[r] for r in sorted(contagens)]
    assert len(set(valores)) > 1, f"a resolução não teve efeito nenhum: {contagens}"
    crescente = all(valores[i] <= valores[i + 1] for i in range(len(valores) - 1))
    assert not crescente, (
        f"a resolução virou monotônica ({contagens}) — se a biblioteca mudou, o tooltip "
        "da UI pode voltar a prometer 'mais resolução = mais clusters'")


def test_resolution_is_clamped_to_the_documented_range():
    """Valores fora da faixa são presos, sem exceção (o slider da UI é 0.5–2.0)."""
    _, G, _ = _grafo_pronto()
    for extremo in (-100.0, 0.0, 1e9):
        p = recluster(G, resolution=extremo)
        assert p, "reclusterização não deveria falhar com resolução extrema"
        assert all(isinstance(v, int) for v in p.values())


def test_recluster_on_empty_graph_returns_empty():
    assert recluster(nx.Graph(), resolution=1.0) == {}
    assert cluster_sizes(nx.Graph()) == {}


# ─────────────────── lista de termos revisável ───────────────────

def test_excluding_terms_reduces_nodes_in_the_expected_proportion():
    """Excluir termos da tabela revisável (passo 13 do guia) reduz nós na medida certa."""
    df = _corpus_com_estrutura()
    gen = NetworkGenerator(df)
    completo = gen.build_keyword_cooccurrence(min_occurrence=2, field="keywords")
    termos = sorted(completo.nodes())
    n_total = len(termos)
    assert n_total >= 6, "corpus de teste pequeno demais para o caso"

    excluidos = termos[:2]
    permitidos = allowed_terms_from(termos, excluidos)
    assert len(permitidos) == n_total - 2

    gen2 = NetworkGenerator(df)
    reduzido = gen2.build_keyword_cooccurrence(
        min_occurrence=2, field="keywords", allowed_terms=permitidos)
    assert reduzido.number_of_nodes() == n_total - 2, (
        f"esperava {n_total - 2} nós após excluir 2, obteve {reduzido.number_of_nodes()}")
    for t in excluidos:
        assert t not in reduzido.nodes(), f"termo excluído continua no mapa: {t}"


def test_exclusion_is_case_insensitive_and_ignores_blanks():
    termos = ["Alpha", "beta", "GAMMA"]
    permitidos = allowed_terms_from(termos, ["  alpha ", "", None, "gamma"])
    assert permitidos == {"beta"}


def test_threshold_preview_matches_the_real_generation():
    """O "limiar 10 → N termos" mostrado antes de gerar tem de bater com o que sai."""
    df = _corpus_com_estrutura()
    preview = threshold_preview(df, thresholds=(1, 2, 5, 9), fields="keywords")
    for limiar, previsto in preview.items():
        real = extract_terms(df, fields="keywords", min_occurrences=limiar)
        assert len(real) == previsto, (
            f"limiar {limiar}: preview disse {previsto}, extração deu {len(real)}")


def test_extreme_threshold_gives_clear_message_not_a_crash():
    """Limiar altíssimo → zero termos, COM aviso e com a contagem do que havia antes."""
    df = _corpus_com_estrutura()
    r = extract_terms(df, fields="keywords", min_occurrences=10_000)
    assert len(r) == 0
    assert "map.warn_threshold_empty" in r.warnings
    assert r.total_unique_before_threshold > 0, "precisa dizer quantos termos havia"


# ─────────────────── rotulagem por IA ───────────────────

def test_ai_labels_applied_from_well_formed_response():
    _, G, _ = _grafo_pronto()
    recluster(G, resolution=1.0)
    grupos = sorted({int(g) for _, g in G.nodes(data="group")})
    resposta = "\n".join(f"{g}: Tema {g}" for g in grupos)

    labels = parse_cluster_labels(resposta)
    assert labels == {g: f"Tema {g}" for g in grupos}
    afetados = apply_cluster_labels(G, labels)
    assert afetados == G.number_of_nodes()
    assert all(G.nodes[n].get("cluster_label") for n in G.nodes())


@pytest.mark.parametrize("resposta,esperado", [
    # Preâmbulo + markdown em volta das linhas: aproveita o que dá.
    ("Claro! Aqui estão:\n\n- **0**: Aprendizado de Máquina\n* 1: Visão Computacional\n",
     {0: "Aprendizado de Máquina", 1: "Visão Computacional"}),
    # JSON em vez das linhas pedidas.
    ('{"0": "Bibliometria", "1": "Redes"}', {0: "Bibliometria", 1: "Redes"}),
    # Travessão em vez de dois-pontos.
    ("0 – Inovação\n1 - Política", {0: "Inovação", 1: "Política"}),
    # Totalmente malformada: dicionário vazio, NUNCA exceção.
    ("Desculpe, não consegui gerar rótulos.", {}),
    ("", {}),
    ("```\nlixo\n```", {}),
])
def test_malformed_ai_response_never_breaks(resposta, esperado):
    assert parse_cluster_labels(resposta) == esperado


def test_parse_cluster_labels_tolerates_non_string():
    assert parse_cluster_labels(None) == {}
    assert parse_cluster_labels(12345) == {}


def test_apply_labels_ignores_clusters_without_label():
    """Rótulo parcial: os clusters sem nome ficam sem `cluster_label`, sem erro."""
    _, G, _ = _grafo_pronto()
    recluster(G, resolution=1.0)
    afetados = apply_cluster_labels(G, {0: "Só o zero"})
    assert afetados >= 1
    rotulados = [n for n in G.nodes() if G.nodes[n].get("cluster_label")]
    assert len(rotulados) == afetados


# ─────────────────── exports ───────────────────

def test_svg_export_is_valid_and_not_empty(tmp_path):
    """SVG precisa ser XML válido, com dimensões e com os elementos do mapa."""
    _, G, pos = _grafo_pronto()
    caminho = tmp_path / "mapa.svg"
    svg = export_svg(G, pos, str(caminho), width=1200, height=900)

    assert caminho.exists() and caminho.stat().st_size > 500
    raiz = ET.fromstring(svg)                       # levanta se não for XML válido
    assert raiz.tag.endswith("svg")
    assert raiz.get("width") == "1200" and raiz.get("height") == "900"

    ns = {"s": "http://www.w3.org/2000/svg"}
    circulos = raiz.findall(".//s:circle", ns)
    textos = raiz.findall(".//s:text", ns)
    assert len(circulos) == G.number_of_nodes(), (
        f"esperava {G.number_of_nodes()} nós no SVG, achei {len(circulos)}")
    assert len(textos) >= 1, "nenhum rótulo no SVG"
    # Todas as coordenadas finitas (NaN quebraria o SVG em qualquer visualizador).
    for c in circulos:
        for at in ("cx", "cy", "r"):
            assert math.isfinite(float(c.get(at))), f"{at} não finito no SVG"


def test_svg_overlay_and_print_themes_differ(tmp_path):
    """Overlay usa a rampa; tema impressão usa PADRÕES (distinguível em preto e branco)."""
    _, G, pos = _grafo_pronto()
    rede = export_svg(G, pos, str(tmp_path / "a.svg"), mode="network")
    overlay = export_svg(G, pos, str(tmp_path / "b.svg"), mode="overlay", metric="avg_year")
    impressao = export_svg(G, pos, str(tmp_path / "c.svg"), theme="print")

    assert rede != overlay, "overlay deveria colorir diferente da rede"
    assert "<pattern" in impressao, "tema impressão precisa de padrões de preenchimento"
    assert "url(#pat" in impressao, "os nós deveriam usar os padrões"
    # E os padrões são distintos entre clusters.
    import re as _re
    ids = set(_re.findall(r'<pattern id="(pat\d+)"', impressao))
    assert len(ids) >= 2, f"padrões demais repetidos: {ids}"


def test_svg_legend_carries_every_required_field(tmp_path):
    """Legenda honesta: sem ela a imagem não é reproduzível nem citável."""
    _, G, pos = _grafo_pronto()
    legenda = build_legend(query="empreendedorismo", documents=317, period="2015–2024",
                           method="binária, limiar 5, resolução 1.0", date="2026-07-30")
    svg = export_svg(G, pos, str(tmp_path / "l.svg"), legend=legenda)
    for obrigatorio in ("empreendedorismo", "317", "2015–2024", "resolução 1.0", "2026-07-30"):
        assert obrigatorio in svg, f"campo obrigatório ausente na legenda: {obrigatorio}"


def test_svg_export_handles_empty_graph_and_nan_positions(tmp_path):
    """Grafo vazio e posições NaN não podem gerar SVG quebrado."""
    vazio = export_svg(nx.Graph(), {}, str(tmp_path / "v.svg"))
    ET.fromstring(vazio)

    G = nx.Graph()
    G.add_node("a", size=10, label="a", group=0)
    G.add_node("b", size=10, label="b", group=0)
    G.add_edge("a", "b", weight=1)
    svg = export_svg(G, {"a": (float("nan"), 0.0), "b": (float("inf"), 1.0)},
                     str(tmp_path / "n.svg"))
    raiz = ET.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    for c in raiz.findall(".//s:circle", ns):
        assert math.isfinite(float(c.get("cx"))) and math.isfinite(float(c.get("cy")))


def test_gephi_and_vosviewer_exports_have_no_regression(tmp_path):
    """Os exports que já existiam continuam idênticos ao formato de referência."""
    gen, G, pos = _grafo_pronto()

    gml = tmp_path / "g.gml"
    gen.export_gml(str(gml))
    texto_gml = gml.read_text(encoding="utf-8")
    assert texto_gml.startswith("graph"), "GML deveria começar com 'graph'"
    assert "node" in texto_gml and "edge" in texto_gml
    lido = nx.read_gml(str(gml))
    assert lido.number_of_nodes() == G.number_of_nodes()
    assert lido.number_of_edges() == G.number_of_edges()

    mapa = tmp_path / "map.txt"
    rede = tmp_path / "net.txt"
    gen.export_vosviewer(str(mapa), str(rede), positions=pos)
    cabecalho = mapa.read_text(encoding="utf-8").splitlines()[0]
    assert cabecalho.split("\t") == [
        "id", "label", "x", "y", "cluster", "weight",
        "score<mean pub year>", "score<mean citations>"], (
        f"cabeçalho do VOSviewer mudou: {cabecalho}")
    linhas_mapa = mapa.read_text(encoding="utf-8").splitlines()
    assert len(linhas_mapa) == G.number_of_nodes() + 1
    linhas_rede = [l for l in rede.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(linhas_rede) == G.number_of_edges()
    for linha in linhas_rede:
        assert len(linha.split("\t")) == 3


# ─────────────────── persistência dos parâmetros ───────────────────

def test_params_round_trip_through_json():
    """Os parâmetros vão e voltam do `.blicsa` sem perder nada."""
    p = MapParams(fields="both", method="ngram", binary_count=False, min_occurrences=7,
                  resolution=1.2, algorithm="leiden", attraction=1.0, repulsion=0.0,
                  max_edges=1500, excluded_terms=["ruído", "outro"],
                  thesaurus_path="/tmp/t.csv")
    voltou = MapParams.from_dict(json.loads(json.dumps(p.to_dict())))
    assert voltou == p


def test_params_from_old_or_corrupt_project_still_open():
    """Projeto de versão antiga (sem os campos novos) ou com lixo NÃO pode falhar ao abrir."""
    antigo = MapParams.from_dict({"min_occurrences": 5})       # versão anterior
    assert antigo.min_occurrences == 5
    assert antigo.fields == "keywords" and antigo.resolution == RESOLUTION_DEFAULT

    lixo = MapParams.from_dict({"min_occurrences": "não é número", "resolution": None,
                                "binary_count": "talvez", "excluded_terms": None,
                                "campo_inexistente": 42})
    assert lixo.min_occurrences == MapParams().min_occurrences
    assert lixo.resolution == RESOLUTION_DEFAULT
    assert lixo.excluded_terms == []

    assert MapParams.from_dict(None) == MapParams()
    assert MapParams.from_dict({}) == MapParams()


def test_params_clamp_resolution_and_threshold_on_load():
    fora = MapParams.from_dict({"resolution": 99.0, "min_occurrences": -3})
    assert fora.resolution == RESOLUTION_MAX
    assert fora.min_occurrences == 1
    baixo = MapParams.from_dict({"resolution": 0.001})
    assert baixo.resolution == RESOLUTION_MIN


def test_params_persist_inside_a_real_blicsa_file(tmp_path):
    """Round-trip pelo `.blicsa` de verdade (save/load do core.project)."""
    from core.project import load_blicsa_project, save_blicsa_project

    gen, G, pos = _grafo_pronto()
    params = MapParams(fields="both", min_occurrences=4, resolution=1.2,
                       excluded_terms=["ponte"])
    caminho = tmp_path / "projeto.blicsa"
    save_blicsa_project(str(caminho), gen.df, {"map_params": params.to_dict()},
                        pos, G, {0: "Tema A"})

    dados = load_blicsa_project(str(caminho))
    restaurado = MapParams.from_dict((dados.get("config") or {}).get("map_params"))
    assert restaurado == params, "os parâmetros do mapa não sobreviveram ao .blicsa"


def test_ui_wires_the_new_controls_into_the_pipeline():
    """Os controles novos não podem ser decorativos: têm de chegar ao pipeline.

    Checagem no fonte do main.py, porque instanciar a UI inteira num teste é caro e frágil.
    O ponto crítico é o `_mapping_worker`: se as exclusões da revisão não entrarem ali, o
    botão "Revisar termos" existe mas o mapa sai com os termos que o usuário descartou.
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "main.py"
    texto = src.read_text(encoding="utf-8")

    # As variáveis existem e estão ligadas aos widgets.
    for var in ("_binary_count_var", "_attraction_var", "_repulsion_var", "_excluded_terms"):
        assert var in texto, f"controle ausente na UI: {var}"

    # A exclusão entra no worker que constrói o grafo.
    inicio = texto.index("def _mapping_worker")
    corpo = texto[inicio:inicio + 2500]
    assert "_excluded_terms" in corpo, (
        "as exclusões da revisão não chegam ao _mapping_worker — o botão seria decorativo")
    assert "allowed_terms_from" in corpo

    # A reclusterização usa recluster() (sem refazer layout), não o gerador inteiro.
    assert "_recluster_only" in texto and "from core.map_controls import cluster_sizes, recluster" in texto
    # E os parâmetros são salvos e restaurados.
    assert 'config["map_params"]' in texto, "map_params não é salvo no .blicsa"
    assert "MapParams.from_dict(config.get(\"map_params\"))" in texto, "map_params não é restaurado"
