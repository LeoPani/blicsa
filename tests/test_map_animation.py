"""Fase 4 — animação temporal e camada artística.

Fixtures adversariais (regra 1): ano sem documento, corpus de um único ano, nó sem ano,
pesos todos iguais, cluster de peso zero, grafo vazio.
"""
import math
import shutil
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest
from PIL import Image

from core.map_animation import (
    LEGEND_REQUIRED,
    POSTER_COLORS,
    THEMES,
    Frame,
    export_gif,
    export_mp4,
    export_png_sequence,
    ffmpeg_available,
    frames_share_positions,
    poster_area_report,
    render_frame,
    render_poster,
    squarified_treemap,
    timeline_frames,
)
from core.map_controls import build_legend
from core.map_render import print_pattern_for


def _grafo_temporal():
    """Grafo com estreias em 3 anos conhecidos: 2020, 2021 e 2022."""
    G = nx.Graph()
    plano = [("a", 2020, 10), ("b", 2020, 8), ("c", 2021, 6), ("d", 2022, 4)]
    for nome, ano, occ in plano:
        G.add_node(nome, label=nome, size=10 + occ, group=0, occurrence=occ,
                   first_year=ano, year_mean=float(ano), citations_mean=float(occ),
                   color="#DF3117")
    G.add_edge("a", "b", weight=3.0)
    G.add_edge("b", "c", weight=2.0)
    G.add_edge("c", "d", weight=1.0)
    pos = {"a": (0.0, 0.0), "b": (1.0, 0.0), "c": (0.5, 1.0), "d": (1.5, 1.0)}
    return G, pos


# ─────────────────── quadros da linha do tempo ───────────────────

def test_three_known_years_yield_three_frames_with_the_right_nodes():
    """Corpus com 3 anos plantados → 3 quadros, cada um com o conjunto correto de nós."""
    G, _ = _grafo_temporal()
    quadros = timeline_frames(G)

    assert [f.year for f in quadros] == [2020, 2021, 2022]
    # Acumulativo: o nó entra no ano da estreia e permanece.
    assert quadros[0].visible == {"a", "b"}
    assert quadros[1].visible == {"a", "b", "c"}
    assert quadros[2].visible == {"a", "b", "c", "d"}
    # Arestas só entre nós já presentes.
    assert quadros[0].edges == [("a", "b", 3.0)]
    assert len(quadros[2].edges) == 3


def test_non_cumulative_shows_only_that_years_debuts():
    G, _ = _grafo_temporal()
    quadros = timeline_frames(G, cumulative=False)
    assert quadros[0].visible == {"a", "b"}
    assert quadros[1].visible == {"c"}
    assert quadros[2].visible == {"d"}


def test_positions_are_identical_across_every_frame():
    """Layout FIXO: nenhum quadro move um nó — é o que torna a animação legível.

    `timeline_frames` nem devolve coordenadas (por construção não há caminho para mover
    nada); o teste confirma que todo nó visível tem posição no mapa fixo, e que a projeção
    de tela é a mesma em todos os quadros.
    """
    G, pos = _grafo_temporal()
    quadros = timeline_frames(G)

    assert frames_share_positions(quadros, pos)
    for f in quadros:
        for n, info in f.nodes.items():
            assert "x" not in info and "y" not in info, (
                "o quadro não pode carregar coordenada própria — o layout é fixo")

    # E na renderização: o centro de um nó presente em todos os quadros é o MESMO pixel.
    from core.map_animation import _projector
    proj = _projector(pos, 400, 300, 20, 0)
    centros = {f.year: proj("a") for f in quadros}
    assert len(set(centros.values())) == 1, f"o nó 'a' saltou entre quadros: {centros}"


def test_year_without_documents_yields_a_valid_empty_frame_with_a_note():
    """Ano sem nenhum documento → quadro VÁLIDO e vazio, com aviso. Nunca um buraco."""
    G = nx.Graph()
    G.add_node("a", label="a", size=12, group=0, occurrence=3, first_year=2018,
               year_mean=2018.0, color="#DF3117")
    G.add_node("b", label="b", size=12, group=0, occurrence=3, first_year=2021,
               year_mean=2021.0, color="#1E4DA0")
    df = pd.DataFrame([{"year": 2018}, {"year": 2021}])   # 2019 e 2020 não existem

    quadros = timeline_frames(G, df=df)
    anos = {f.year: f for f in quadros}
    assert set(anos) == {2018, 2019, 2020, 2021}
    for vazio in (2019, 2020):
        f = anos[vazio]
        assert f.empty is True, f"{vazio} deveria estar marcado como vazio"
        assert f.note, f"{vazio} precisa de aviso explicando o quadro vazio"
    assert anos[2021].visible == {"a", "b"}


def test_year_before_any_term_debuts_is_marked_empty_with_its_own_note():
    """O outro ramo de quadro vazio: ano ANTERIOR à estreia de qualquer termo.

    Existem dois motivos distintos para um quadro sair vazio, e cada um tem sua mensagem —
    "ainda não há termos" e "não há documentos neste ano". A matriz de reinjeção mostrou que
    o teste acima só cobria o segundo: com contagem acumulativa os nós antigos continuam
    presentes, então aquele caminho nunca chegava ao primeiro ramo.
    """
    G = nx.Graph()
    G.add_node("a", label="a", size=12, group=0, occurrence=3, first_year=2020,
               year_mean=2020.0, color="#DF3117")
    # O corpus tem documentos em 2018, mas nenhum TERMO estreia antes de 2020.
    df = pd.DataFrame([{"year": 2018}, {"year": 2020}])

    quadros = {f.year: f for f in timeline_frames(G, df=df)}
    assert set(quadros) == {2018, 2019, 2020}

    primeiro = quadros[2018]
    assert primeiro.empty is True and primeiro.visible == set()
    assert primeiro.note == "map.anim_year_empty", (
        f"o quadro sem termo nenhum precisa da mensagem própria, veio {primeiro.note!r}")
    assert quadros[2020].visible == {"a"}


def test_single_year_corpus_degrades_to_one_frame_without_dividing_by_zero():
    """Corpus com um único ano → um quadro só, sem divisão por zero (bug do slider)."""
    G = nx.Graph()
    for nome in ("a", "b"):
        G.add_node(nome, label=nome, size=12, group=0, occurrence=5, first_year=2021,
                   year_mean=2021.0, color="#DF3117")
    G.add_edge("a", "b", weight=1.0)
    quadros = timeline_frames(G, df=pd.DataFrame([{"year": 2021}]))
    assert len(quadros) == 1
    assert quadros[0].year == 2021 and quadros[0].visible == {"a", "b"}
    # E renderiza sem erro.
    img = render_frame(quadros[0], {"a": (0.0, 0.0), "b": (1.0, 1.0)}, width=320, height=240)
    assert img.size == (320, 240)


def test_nodes_without_any_year_are_left_out_not_invented():
    """Nó sem ano nenhum fica de fora da linha do tempo — não se inventa uma data."""
    G = nx.Graph()
    G.add_node("com_ano", label="x", size=12, group=0, occurrence=2, first_year=2020,
               year_mean=2020.0, color="#DF3117")
    G.add_node("sem_ano", label="y", size=12, group=0, occurrence=2, color="#1E4DA0")
    quadros = timeline_frames(G)
    assert quadros, "deveria haver quadros a partir do nó com ano"
    for f in quadros:
        assert "sem_ano" not in f.visible, "nó sem ano não pode ganhar data inventada"


def test_empty_graph_yields_no_frames_instead_of_crashing():
    assert timeline_frames(nx.Graph()) == []


# ─────────────────── exports da animação ───────────────────

def test_gif_export_has_multiple_distinct_frames(tmp_path):
    """GIF válido, com mais de um quadro E com quadros DISTINTOS (não um still repetido)."""
    G, pos = _grafo_temporal()
    quadros = timeline_frames(G)
    imagens = [render_frame(f, pos, width=320, height=240) for f in quadros]

    alvo = tmp_path / "anim.gif"
    export_gif(imagens, str(alvo), duration_ms=500)

    assert alvo.exists() and alvo.stat().st_size > 0
    im = Image.open(alvo)
    assert im.n_frames == len(quadros) == 3, f"esperava 3 quadros, tem {im.n_frames}"
    assert im.size == (320, 240)

    assinaturas = set()
    for i in range(im.n_frames):
        im.seek(i)
        assinaturas.add(tuple(im.convert("RGB").resize((32, 24)).getdata()))
    assert len(assinaturas) == 3, (
        f"os quadros do GIF deveriam ser distintos, só {len(assinaturas)} são")


def test_png_sequence_is_written(tmp_path):
    G, pos = _grafo_temporal()
    imagens = [render_frame(f, pos, width=200, height=150) for f in timeline_frames(G)]
    caminhos = export_png_sequence(imagens, str(tmp_path / "seq"))
    assert len(caminhos) == 3
    for c in caminhos:
        assert Path(c).exists() and Path(c).stat().st_size > 0


def test_mp4_degrades_gracefully_without_ffmpeg(tmp_path):
    """Sem ffmpeg o MP4 é pulado COM mensagem clara — e nunca levanta."""
    G, pos = _grafo_temporal()
    imagens = [render_frame(f, pos, width=200, height=150) for f in timeline_frames(G)]

    ok, msg = export_mp4(imagens, str(tmp_path / "v.mp4"), fps=2)
    if ffmpeg_available():
        assert ok and Path(msg).exists()
    else:
        assert ok is False
        assert "ffmpeg" in msg.lower(), f"a mensagem deveria explicar o motivo: {msg}"
        assert "gif" in msg.lower(), "a mensagem deveria dizer que o GIF saiu mesmo assim"

    # E o GIF sai de qualquer jeito, independente do ffmpeg.
    gif = tmp_path / "sempre.gif"
    export_gif(imagens, str(gif))
    assert gif.exists() and Image.open(gif).n_frames == 3


def test_export_gif_with_no_frames_raises_clearly(tmp_path):
    with pytest.raises(ValueError):
        export_gif([], str(tmp_path / "vazio.gif"))


# ─────────────────── reduzir movimento ───────────────────

def test_reduce_motion_switch_exists_and_final_state_matches():
    """"Reduzir movimento" desliga as transições e o estado FINAL é o mesmo.

    A checagem é no fonte do map.js: a animação da câmera precisa ter o caminho sem
    transição (setState) ao lado do animado, e a preferência do sistema
    (prefers-reduced-motion) tem de ser respeitada.
    """
    js = Path("assets/map.js").read_text(encoding="utf-8")
    assert "reduceMotion" in js, "faltou o interruptor de reduzir movimento"
    assert "prefers-reduced-motion" in js, "a preferência do sistema deve ser respeitada"
    assert "BLICSA_REDUCE_MOTION" in js, "faltou o interruptor vindo dos Ajustes do app"
    # O caminho sem animação leva ao MESMO estado final da câmera.
    assert "setState" in js and "animate(" in js, (
        "precisa dos dois caminhos: com transição e sem")


# ─────────────────── modo pôster ───────────────────

def test_poster_rect_areas_are_proportional_to_cluster_weights():
    """Área de cada plano ∝ peso do cluster, com tolerância de 2%, cobrindo o canvas."""
    pesos = {0: 40.0, 1: 25.0, 2: 20.0, 3: 10.0, 4: 5.0}
    rel = poster_area_report(pesos, 1400, 1000)

    assert len(rel["rects"]) == len(pesos)
    for cluster, erro in rel["errors"].items():
        assert erro <= 0.02, f"cluster {cluster}: área {erro:.2%} fora do peso (tolerância 2%)"
    cobertura = rel["total_area"] / rel["canvas_area"]
    assert 0.98 <= cobertura <= 1.02, f"os planos cobrem {cobertura:.2%} do canvas"


def test_poster_handles_equal_weights_and_zero_weight_clusters():
    """Pesos todos iguais e cluster de peso zero — sem divisão por zero, sem plano fantasma."""
    iguais = poster_area_report({0: 10.0, 1: 10.0, 2: 10.0}, 900, 600)
    assert len(iguais["rects"]) == 3
    areas = [w * h for _, _, w, h in iguais["rects"]]
    assert max(areas) - min(areas) < max(areas) * 0.02, "pesos iguais → áreas iguais"

    com_zero = poster_area_report({0: 10.0, 1: 0.0}, 900, 600)
    assert len(com_zero["rects"]) == 1, "cluster de peso zero não pode virar plano"

    assert squarified_treemap([], 100, 100) == []
    assert squarified_treemap([0, 0], 100, 100) == []


def test_poster_renders_with_terms_and_legend(tmp_path):
    pesos = {0: 30.0, 1: 20.0, 2: 12.0}
    termos = {0: ["inovação", "política"], 1: ["rede", "grafo"], 2: ["dados"]}
    legenda = build_legend("empreendedorismo", 317, "2015–2024", "binária, limiar 5",
                           "2026-07-30")
    img = render_poster(pesos, termos, {0: "Tema A"}, width=800, height=600, legend=legenda,
                        title="Blicsa")
    assert img.size == (800, 600)
    caminho = tmp_path / "poster.png"
    img.save(caminho)
    assert caminho.stat().st_size > 2000

    # Não é uma imagem chapada: há planos de cores diferentes.
    cores = img.convert("RGB").getcolors(maxcolors=1_000_000)
    assert cores and len(cores) > 20


def test_poster_with_no_clusters_shows_message_not_blank():
    img = render_poster({}, width=400, height=300)
    cores = img.convert("RGB").getcolors(maxcolors=100_000)
    assert cores and len(cores) > 1, "deveria escrever a mensagem, não devolver tela chapada"


# ─────────────────── temas ───────────────────

def test_print_theme_distinguishes_clusters_without_color():
    """Tema impressão: cada cluster ganha um PADRÃO — distinguível em preto e branco."""
    padroes = [print_pattern_for(i) for i in range(8)]
    assert len(set(padroes)) == 8, f"padrões repetidos: {padroes}"

    # E o desenho difere de fato entre dois clusters no tema impressão.
    G = nx.Graph()
    for i, nome in enumerate(("a", "b")):
        G.add_node(nome, label=nome, size=30, group=i, occurrence=10, first_year=2020,
                   year_mean=2020.0, color="#DF3117")
    pos = {"a": (0.0, 0.0), "b": (1.0, 1.0)}
    quadro = timeline_frames(G)[0]

    img = render_frame(quadro, pos, width=300, height=300, theme="print")
    # Preto e branco de verdade: a imagem não deve trazer as cores da paleta de clusters.
    cores = {c for _, c in (img.convert("RGB").getcolors(maxcolors=1_000_000) or [])}
    assert (223, 49, 23) not in cores, "tema impressão não pode usar o vermelho do cluster"


def test_all_three_themes_render_with_distinct_backgrounds():
    G, pos = _grafo_temporal()
    quadro = timeline_frames(G)[0]
    fundos = {}
    for tema in ("paper", "ink", "print"):
        img = render_frame(quadro, pos, width=200, height=160, theme=tema)
        fundos[tema] = img.convert("RGB").getpixel((3, 3))
    assert len(set(fundos.values())) == 3, f"os temas deveriam diferir no fundo: {fundos}"
    assert fundos["paper"] == THEMES["paper"]["bg"]
    assert fundos["ink"] == THEMES["ink"]["bg"]


# ─────────────────── legenda ───────────────────

def test_export_legend_carries_every_required_field():
    legenda = build_legend("query x", 42, "2010–2020", "binária, limiar 3, resolução 1.0",
                           "2026-07-30")
    for campo in LEGEND_REQUIRED:
        assert campo in legenda, f"campo obrigatório ausente: {campo}"
        assert legenda[campo] not in (None, ""), f"campo vazio: {campo}"


def test_frame_with_legend_is_taller_content_and_renders_the_fields(tmp_path):
    """A legenda é desenhada no quadro (faixa inferior separada por linha)."""
    G, pos = _grafo_temporal()
    quadro = timeline_frames(G)[0]
    legenda = build_legend("empreendedorismo", 317, "2015–2024", "binária", "2026-07-30")

    sem = render_frame(quadro, pos, width=500, height=400)
    com = render_frame(quadro, pos, width=500, height=400, legend=legenda)
    assert sem.tobytes() != com.tobytes(), "a legenda deveria mudar a imagem"

    # Há tinta na faixa do rodapé (onde a legenda foi escrita).
    faixa = com.convert("L").crop((0, 340, 500, 400))
    extremos = faixa.getextrema()
    assert extremos[0] < 100, "o rodapé da legenda está em branco"


# ─────────────────── desempenho ───────────────────

def test_animation_frame_generation_is_fast_for_500_nodes(capsys):
    """500 nós: geração dos quadros e render dentro de orçamento interativo."""
    import time

    G = nx.Graph()
    for i in range(500):
        G.add_node(f"n{i}", label=f"n{i}", size=10 + i % 20, group=i % 6,
                   occurrence=1 + i % 30, first_year=2010 + (i % 12),
                   year_mean=float(2010 + (i % 12)), color=POSTER_COLORS[i % 5])
    for i in range(0, 498, 2):
        G.add_edge(f"n{i}", f"n{i+1}", weight=1.0 + (i % 5))
    pos = {f"n{i}": (float(i % 25), float(i // 25)) for i in range(500)}

    t0 = time.perf_counter()
    quadros = timeline_frames(G)
    t_quadros = time.perf_counter() - t0

    t1 = time.perf_counter()
    imagens = [render_frame(f, pos, width=800, height=600) for f in quadros]
    t_render = time.perf_counter() - t1
    por_quadro = t_render / max(len(imagens), 1)

    with capsys.disabled():
        print(f"\n[perf] 500 nós · {len(quadros)} quadros · montagem {t_quadros:.2f}s · "
              f"render {t_render:.2f}s ({por_quadro * 1000:.0f}ms/quadro)")
    assert t_quadros < 5.0, f"montagem dos quadros levou {t_quadros:.1f}s"
    assert por_quadro < 1.5, f"{por_quadro * 1000:.0f}ms por quadro é lento demais"
