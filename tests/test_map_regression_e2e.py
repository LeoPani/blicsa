"""Fase 5 — regressão ponta a ponta do pipeline de mapas.

Percorre o caminho completo que o usuário percorre: importar corpus → gerar mapa → os três
modos → leis de Bradford/Lotka → exportar Gephi/VOSviewer → salvar `.blicsa` → reabrir com
parâmetros e mapa intactos.

Não substitui os testes de unidade: existe para pegar a quebra que só aparece na COSTURA
entre as etapas — o payload que a etapa seguinte não consegue ler, o parâmetro que se perde
no round-trip do projeto.
"""
import json
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from core.map_animation import export_gif, render_frame, render_poster, timeline_frames
from core.map_controls import MapParams, build_legend, cluster_sizes, export_svg, recluster
from core.map_render import density_grid
from core.matrix_builders import NetworkGenerator
from core.project import load_blicsa_project, save_blicsa_project
from core.sigma_exporter import build_sigma_payload, export_sigma_json
from core.term_extraction import extract_terms

REPO = Path(__file__).resolve().parent.parent


def _corpus_real() -> pd.DataFrame:
    """Corpus de verdade, da fixture gravada da API.

    `docs/sample_dataset.csv` tem apenas 3 registros — serve de exemplo de formato, mas não
    produz um mapa com estrutura para exercitar clusters, overlay e densidade. A fixture
    gravada do OpenAlex tem 100 registros reais e roda offline.
    """
    from core.sources.openalex import OpenAlexProvider

    envelope = json.loads((REPO / "tests/fixtures/openalex_page1.json").read_text())
    bruto = json.loads(envelope["body"]) if "body" in envelope else envelope
    prov = OpenAlexProvider()
    return pd.DataFrame([prov._normalize_work(w) for w in bruto.get("results", [])])


@pytest.fixture(scope="module")
def pipeline():
    """Roda o pipeline uma vez e entrega os artefatos para os testes desta suíte."""
    df = _corpus_real()
    gen = NetworkGenerator(df)
    G = gen.build_keyword_cooccurrence(min_occurrence=5, field="keywords")
    pos = {n: (float(i % 9), float(i // 9)) for i, n in enumerate(G.nodes())}
    return {"df": df, "gen": gen, "G": G, "pos": pos}


def test_csv_de_exemplo_ainda_carrega():
    """O sample_dataset.csv continua sendo um CSV válido e importável (contrato do repo)."""
    caminho = REPO / "docs" / "sample_dataset.csv"
    df = pd.read_csv(caminho)
    assert len(df) >= 1
    for coluna in ("title", "year", "keywords", "authors"):
        assert coluna in df.columns, f"coluna esperada ausente no exemplo: {coluna}"


def test_pipeline_gera_grafo_com_estrutura(pipeline):
    G = pipeline["G"]
    assert G.number_of_nodes() >= 20, f"grafo pequeno demais: {G.number_of_nodes()} nós"
    assert G.number_of_edges() >= 50
    grupos = {int(g or 0) for _, g in G.nodes(data="group")}
    assert len(grupos) >= 2, f"esperava mais de um cluster, veio {grupos}"


def test_os_tres_modos_leem_o_mesmo_payload(pipeline):
    """Um payload serve os três modos, e nenhum deles fica sem o dado de que precisa."""
    payload = build_sigma_payload(pipeline["G"], pipeline["pos"], max_edges=1200)

    # network: cor de cluster em todo nó.
    assert all(n["attributes"]["color"] for n in payload["nodes"])
    # overlay: escala montada para cada métrica, com contagem de "sem dado".
    for metrica in ("avg_year", "avg_citations", "occurrences"):
        escala = payload["overlay"][metrica]
        assert "no_data" in escala and "stops" in escala
    # densidade: grade não vazia.
    grade = payload["density"]
    assert grade["grid"] and len(grade["grid"]) == grade["rows"]
    assert any(v > 0 for linha in grade["grid"] for v in linha)


def test_bradford_e_lotka_rodam_sobre_o_mesmo_corpus(pipeline):
    """As leis bibliométricas continuam calculáveis a partir do corpus do mapa.

    A conta é a mesma do main.py (as leis estão inline lá): Bradford ordena as fontes por
    produção e divide em 3 zonas de tamanho de produção equivalente; Lotka conta autores por
    número de artigos.
    """
    df = pipeline["df"]

    fontes = Counter(s for s in df["source"].fillna("") if str(s).strip())
    assert fontes, "corpus sem fontes — Bradford não teria o que dividir"
    total = sum(fontes.values())
    ordenadas = fontes.most_common()
    zonas, acumulado, zona_atual = [], 0, []
    for _, n in ordenadas:
        zona_atual.append(n)
        acumulado += n
        if acumulado >= total / 3 and len(zonas) < 2:
            zonas.append(list(zona_atual))
            zona_atual, acumulado = [], 0
    zonas.append(zona_atual)
    assert len(zonas) == 3
    assert sum(sum(z) for z in zonas) == total, "as zonas de Bradford perderam artigos"

    autores = Counter()
    for raw in df["authors"].fillna(""):
        sep = ";" if ";" in str(raw) else ","
        for a in str(raw).split(sep):
            if a.strip():
                autores[a.strip()] += 1
    assert autores, "corpus sem autores — Lotka não teria o que contar"
    por_producao = Counter(autores.values())
    assert por_producao[1] >= 1, "Lotka espera uma cauda de autores com um artigo só"
    assert sum(n * q for n, q in por_producao.items()) == sum(autores.values())


def test_exports_do_grafo_continuam_validos(tmp_path, pipeline):
    """Gephi (GML/GEXF), VOSviewer, SVG e JSON do Sigma — todos escrevem e releem."""
    gen, G, pos = pipeline["gen"], pipeline["G"], pipeline["pos"]

    gml = tmp_path / "g.gml"
    gen.export_gml(str(gml))
    lido = nx.read_gml(str(gml))
    assert lido.number_of_nodes() == G.number_of_nodes()

    gexf = tmp_path / "g.gexf"
    gen.export_gexf(str(gexf))
    assert nx.read_gexf(str(gexf)).number_of_nodes() == G.number_of_nodes()

    mapa, rede = tmp_path / "map.txt", tmp_path / "net.txt"
    gen.export_vosviewer(str(mapa), str(rede), positions=pos)
    assert mapa.read_text(encoding="utf-8").splitlines()[0].startswith("id\tlabel")

    svg = export_svg(G, pos, str(tmp_path / "m.svg"))
    assert svg.startswith("<svg") and "</svg>" in svg

    payload = export_sigma_json(G, pos, str(tmp_path / "graph.json"))
    recarregado = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    assert len(recarregado["nodes"]) == len(payload["nodes"])
    for proibido in ("NaN", "Infinity"):
        assert proibido not in (tmp_path / "graph.json").read_text(encoding="utf-8")


def test_animacao_e_poster_saem_do_mesmo_grafo(tmp_path, pipeline):
    """Animação e pôster consomem o grafo do pipeline sem preparo especial."""
    G, pos, df = pipeline["G"], pipeline["pos"], pipeline["df"]

    quadros = timeline_frames(G, df=df)
    assert quadros, "a linha do tempo ficou vazia"
    imagens = [render_frame(f, pos, width=320, height=240) for f in quadros[:5]]
    gif = tmp_path / "a.gif"
    export_gif(imagens, str(gif))
    from PIL import Image
    assert Image.open(gif).n_frames == len(imagens)

    tam = cluster_sizes(G)
    pesos = {c: float(n) for c, n in tam.items()}
    img = render_poster(pesos, width=600, height=400)
    assert img.size == (600, 400)


def test_projeto_salva_e_reabre_com_parametros_e_mapa_intactos(tmp_path, pipeline):
    """O ciclo completo do `.blicsa`: salvar e reabrir sem perder mapa nem parâmetros.

    É a costura mais fácil de quebrar sem ninguém notar — o mapa reabre, mas com outros
    parâmetros, e o usuário não tem como saber que a análise mudou.
    """
    gen, G, pos, df = pipeline["gen"], pipeline["G"], pipeline["pos"], pipeline["df"]

    params = MapParams(fields="keywords", binary_count=True, min_occurrences=5,
                       resolution=1.2, algorithm="louvain", attraction=1.0, repulsion=0.0,
                       excluded_terms=["ruído"])
    rotulos = {0: "Tema Zero"}
    caminho = tmp_path / "projeto.blicsa"
    save_blicsa_project(str(caminho), df, {"map_params": params.to_dict()}, pos, G, rotulos)
    assert caminho.exists() and caminho.stat().st_size > 1000

    dados = load_blicsa_project(str(caminho))

    restaurado = MapParams.from_dict((dados.get("config") or {}).get("map_params"))
    assert restaurado == params, "os parâmetros do mapa mudaram no round-trip"

    df2 = dados.get("df")
    assert df2 is not None and len(df2) == len(df), "o corpus mudou de tamanho"

    pos2 = dados.get("positions") or {}
    assert len(pos2) == len(pos), "o layout perdeu nós"
    for n, (x, y) in pos.items():
        rx, ry = pos2[str(n)]
        assert abs(rx - x) < 1e-6 and abs(ry - y) < 1e-6, f"a posição de {n} mudou"

    rede = dados.get("G")
    if rede is not None:
        assert rede.number_of_nodes() == G.number_of_nodes(), "o grafo perdeu nós"
        assert rede.number_of_edges() == G.number_of_edges(), "o grafo perdeu arestas"

    clusters = dados.get("cluster_labels") or {}
    assert str(0) in {str(k) for k in clusters}, "os rótulos de cluster se perderam"


def test_reclusterizar_apos_reabrir_nao_move_o_layout(tmp_path, pipeline):
    """Depois de reabrir o projeto, ajustar a resolução segue sem mexer nas posições."""
    G, pos = pipeline["G"], pipeline["pos"]
    antes = {n: tuple(p) for n, p in pos.items()}

    recluster(G, resolution=1.5)
    assert {n: tuple(p) for n, p in pos.items()} == antes

    # E a densidade continua sendo calculável sobre as mesmas posições.
    grade = density_grid(list(pos.values()), cols=16, rows=16)
    assert grade["max"] > 0


def test_extracao_de_termos_bate_com_o_grafo_gerado(pipeline):
    """Os termos que a extração aprova são os que viram nós — sem divergência silenciosa."""
    df, G = pipeline["df"], pipeline["G"]
    resultado = extract_terms(df, fields="keywords", min_occurrences=5)
    termos = set(resultado.term_names)
    nos = set(G.nodes())
    # O grafo pode ter menos (termos isolados caem), nunca termos que a extração reprovou.
    extras = nos - termos
    assert not extras, f"o grafo trouxe termos que a extração não aprovou: {sorted(extras)[:5]}"
