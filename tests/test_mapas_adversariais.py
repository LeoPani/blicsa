"""Bateria dos mapas com corpus adversariais — Auditoria 1, Fase 1.

O caso feliz do mapa já tinha teste. O que não tinha era **grafo com uma componente por
documento, corpus sem nenhum ano, termo de 600 caracteres e artigo recente sem citação** —
e foi aí que estavam os dois defeitos que esta bateria fixa:

1. **posições não reprodutíveis** — `fa2_modified` sorteia a posição inicial com o `random`
   global do processo, que ninguém semeava. Clusters e cores saíam idênticos entre execuções
   (a semente da v2.0.0 funciona) e as coordenadas nunca. Figura publicada não podia ser
   refeita.
2. **zero citação lido como "sem dado"** — sentinela `0` herdada do tratamento do ano. Ano
   zero não existe; artigo com zero citação é o caso mais comum de corpus recente.

Os corpus vivem em `tests/corpus_adversarial.py`, compartilhados com `scripts/audit_mapas.py`
para que o relatório da auditoria e esta bateria nunca auditem coisas diferentes.
"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from corpus_adversarial import CASOS, POR_NOME, _df, monta
from core.map_render import overlay_scale
from core.matrix_builders import NetworkGenerator
from core.sigma_exporter import build_sigma_payload, export_sigma_json
from core.visualizer import compute_fa2_layout, posicoes_iniciais

RAIZ = Path(__file__).resolve().parent.parent

NOMES = [c.nome for c in CASOS]


@pytest.fixture(scope="module")
def montados():
    """Monta cada caso uma vez só. São 11 corpus e um deles tem 5.000 documentos."""
    return {c.nome: monta(c) for c in CASOS}


def _payload(montados, nome):
    G, pos = montados[nome]
    return G, pos, build_sigma_payload(G, pos)


def _nao_finitos(obj, caminho="payload"):
    if isinstance(obj, float):
        return [caminho] if (math.isnan(obj) or math.isinf(obj)) else []
    if isinstance(obj, dict):
        return [p for k, v in obj.items() for p in _nao_finitos(v, f"{caminho}.{k}")]
    if isinstance(obj, (list, tuple)):
        return [p for i, v in enumerate(obj) for p in _nao_finitos(v, f"{caminho}[{i}]")]
    return []


# ── Os três modos, caso a caso ───────────────────────────────────────────────────

@pytest.mark.parametrize("nome", NOMES)
def test_payload_dos_tres_modos_serializa(nome, montados, tmp_path):
    """`export_sigma_json` grava com `allow_nan=False`: um não-finito aqui vira exceção na
    hora de salvar, e o sintoma para o usuário é o mapa abrindo em branco sem pista da causa
    (regressão da Fase 0 do megaprompt)."""
    G, pos, p = _payload(montados, nome)

    assert not _nao_finitos(p), f"{nome}: não-finito em {_nao_finitos(p)[:3]}"
    export_sigma_json(G, pos, str(tmp_path / "graph.json"))

    assert p["meta"]["nodes_total"] == G.number_of_nodes()
    assert p["meta"]["edges_total"] == G.number_of_edges()
    # Os três modos leem do MESMO payload: nós (rede), overlay (escalas), density (grade).
    assert {"nodes", "overlay", "density"} <= set(p)


@pytest.mark.parametrize("nome", NOMES)
def test_todo_no_tem_posicao_propria(nome, montados):
    """Nó sem posição cai em (0,0) e some sob os outros — invisível, sem erro nenhum."""
    G, pos, p = _payload(montados, nome)
    faltando = [n for n in G.nodes() if n not in pos]
    assert not faltando, f"{nome}: {len(faltando)} nó(s) sem posição"

    if G.number_of_nodes() > 1:
        coords = {(round(n["attributes"]["x"], 6), round(n["attributes"]["y"], 6))
                  for n in p["nodes"]}
        assert len(coords) > 1, f"{nome}: todos os nós na mesma coordenada"


@pytest.mark.parametrize("nome", NOMES)
def test_densidade_cobre_os_nos(nome, montados):
    G, pos, p = _payload(montados, nome)
    grade = p["density"]["grid"]
    assert all(math.isfinite(v) for linha in grade for v in linha), f"{nome}: densidade não finita"
    assert all(math.isfinite(v) for v in p["density"]["bounds"]), f"{nome}: bounds não finitos"

    soma = sum(sum(linha) for linha in grade)
    if G.number_of_nodes():
        assert soma > 0, f"{nome}: grade zerada com {G.number_of_nodes()} nós"
    else:
        assert soma == 0


def test_grafo_vazio_nao_vira_tela_branca(montados):
    """`abstracts_vazios` é o corpus que produz grafo vazio. O payload precisa sair válido e
    declarar zero nós, para o JS mostrar 'sem dados' em vez de um canvas em branco."""
    G, pos, p = _payload(montados, "abstracts_vazios")
    assert G.number_of_nodes() == 0
    assert p["nodes"] == [] and p["edges"] == []
    assert p["meta"]["nodes_total"] == 0
    json.dumps(p, allow_nan=False)


@pytest.mark.parametrize("nome,componentes", [("dois_desconexos", 2), ("dez_desconexos", 10)])
def test_componentes_isoladas_sobrevivem_ao_layout(nome, componentes, montados):
    """Componentes isoladas quebram layout por força: sem aresta entre elas, nada as separa,
    e implementações ingênuas empilham tudo ou explodem em coordenada infinita."""
    G, pos, p = _payload(montados, nome)
    assert nx.number_connected_components(G) == componentes
    assert len(p["meta"]["clusters"]) == componentes, "Louvain não separou as componentes"
    assert all(math.isfinite(v) for n in p["nodes"]
               for v in (n["attributes"]["x"], n["attributes"]["y"]))


def test_rotulos_dificeis_chegam_intactos(montados):
    """Acento, emoji, aspas, barra invertida e 600 caracteres atravessam JSON, rótulo de
    canvas e nome de export pelo mesmo caminho."""
    G, pos, p = _payload(montados, "caracteres_dificeis")
    rotulos = {n["attributes"]["label"] for n in p["nodes"]}

    assert any("🌍" in r for r in rotulos), "emoji não sobreviveu"
    assert any("ção" in r for r in rotulos), "acentuação não sobreviveu"
    assert any('"' in r for r in rotulos), "aspas não sobreviveram"
    assert any(len(r) > 500 for r in rotulos), "termo longo foi truncado em silêncio"

    # Ida e volta pelo JSON, que é como o rótulo chega ao navegador.
    devolta = json.loads(json.dumps(p, ensure_ascii=False, allow_nan=False))
    assert {n["attributes"]["label"] for n in devolta["nodes"]} == rotulos


# ── Determinismo (item 3): só verificável entre processos ────────────────────────

CASOS_DETERMINISMO = ["um_documento", "dez_desconexos", "termo_dominante"]


def _hashes_com_seed(caso: str, seed: str) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    r = subprocess.run(
        [sys.executable, str(RAIZ / "scripts/audit_mapas.py"), "--hash", caso],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, f"probe falhou (seed={seed}): {r.stderr[-400:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("caso", CASOS_DETERMINISMO)
def test_mapa_e_reproduzivel_entre_processos(caso):
    """Mesma entrada, `PYTHONHASHSEED` distinto: clusters, cores **e posições** idênticos.

    O `PYTHONHASHSEED` importa porque a ordem de iteração de um `set` de strings muda entre
    processos, e é dela que sai a ordem de inserção dos nós. Rodar isto dentro de um pytest
    só não provaria nada — o processo tem uma semente de hash só.

    Posições entraram nesta lista depois de a auditoria medir que **só elas** variavam: o
    ForceAtlas2 sorteava o ponto de partida com o `random` global, sem semente. Variavam
    inclusive entre duas execuções com o mesmo `PYTHONHASHSEED`.
    """
    referencia = _hashes_com_seed(caso, "0")
    for seed in ("1", "2"):
        atual = _hashes_com_seed(caso, seed)
        for campo in ("ordem_nos", "clusters", "cores", "posicoes"):
            assert atual[campo] == referencia[campo], (
                f"{caso}: '{campo}' mudou com PYTHONHASHSEED={seed}")


def test_posicoes_iniciais_sao_a_fonte_da_reprodutibilidade():
    """Guarda da causa, não do sintoma: se alguém voltar a passar `pos=None` ao ForceAtlas2,
    o teste acima ficaria vermelho sem dizer por quê. Este aponta o dedo."""
    G = nx.path_graph(["a", "b", "c", "d"])
    assert posicoes_iniciais(G) == posicoes_iniciais(G)
    assert posicoes_iniciais(G, seed=1) != posicoes_iniciais(G, seed=2)
    assert set(posicoes_iniciais(G)) == set(G.nodes())

    # Pelo argumento REAL da chamada, não pelo texto do trecho: a primeira versão deste
    # guarda procurava a string "pos=None" no código e ficava vermelha por causa do
    # *comentário* que explica o defeito. Asserção sobre a forma do texto não protege.
    import ast
    fonte = (RAIZ / "core/visualizer.py").read_text(encoding="utf-8")
    metodo = next(n for n in ast.walk(ast.parse(fonte))
                  if isinstance(n, ast.FunctionDef) and n.name == "compute_fa2_layout")
    chamadas = [n for n in ast.walk(metodo)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "forceatlas2_networkx_layout"]
    assert chamadas, "compute_fa2_layout não chama mais o ForceAtlas2"
    for chamada in chamadas:
        pos_kw = next((k for k in chamada.keywords if k.arg == "pos"), None)
        assert pos_kw is not None, "`pos` omitido — a biblioteca volta a sortear"
        assert not (isinstance(pos_kw.value, ast.Constant) and pos_kw.value.value is None), \
            "layout voltou a sortear sem semente (pos=None)"


def test_layout_repetido_no_mesmo_processo_tambem_bate():
    """O defeito também aparecia sem trocar de processo — era RNG puro, não ordem de hash."""
    G, _ = monta(POR_NOME["termo_dominante"])
    a = compute_fa2_layout(G, iterations=30)
    b = compute_fa2_layout(G, iterations=30)
    assert {k: tuple(map(float, v)) for k, v in a.items()} == \
           {k: tuple(map(float, v)) for k, v in b.items()}


# ── Overlay com extremos (item 4) ────────────────────────────────────────────────

def test_overlay_uniforme_declara_que_e_uniforme(montados):
    """Todos os valores iguais → `vmax - vmin == 0`. A barra não pode inventar uma faixa,
    e o JS precisa saber que é uniforme para escrever 'todos = X' em vez de um gradiente."""
    _, _, p = _payload(montados, "mesmo_ano")
    esc = p["overlay"]["avg_year"]
    assert esc["uniform"] is True
    assert esc["min"] == esc["max"]
    assert len(esc["ticks"]) == 1, "faixa degenerada não pode virar três marcas distintas"


def test_overlay_ausente_nao_inventa_escala(montados):
    """Métrica inteiramente ausente: sem ticks, sem min/max, e todos os nós contados em
    `no_data` para o JS pintá-los de cinza."""
    G, _, p = _payload(montados, "sem_ano")
    esc = p["overlay"]["avg_year"]
    assert esc["min"] is None and esc["max"] is None
    assert esc["ticks"] == []
    assert esc["no_data"] == G.number_of_nodes()


def test_overlay_com_outlier_unico_mantem_a_faixa_real():
    valores = [1.0] * 20 + [1000.0]
    esc = overlay_scale(valores)
    assert (esc["min"], esc["max"]) == (1.0, 1000.0)
    assert esc["uniform"] is False
    assert [t["value"] for t in esc["ticks"]] == [1.0, 500.5, 1000.0]


def test_overlay_aceita_valores_negativos():
    """Nenhuma métrica do Blicsa é negativa hoje, mas a rampa é genérica e um `min` negativo
    já bastou para produzir `t` fora de [0,1] em implementações que assumem positivo."""
    esc = overlay_scale([-50.0, 0.0, 50.0])
    assert (esc["min"], esc["max"]) == (-50.0, 50.0)
    assert all(0.0 <= t["t"] <= 1.0 for t in esc["ticks"])
    assert [t["value"] for t in esc["ticks"]] == [-50.0, 0.0, 50.0]


def test_overlay_sem_nenhum_valor_nao_quebra():
    esc = overlay_scale([None, None])
    assert esc["ticks"] == [] and esc["no_data"] == 2
    assert esc["stops"], "a rampa some e a legenda fica sem barra nenhuma"


# ── Zero citação (item 4, encontrado medindo) ────────────────────────────────────

def test_corpus_recente_sem_citacoes_mantem_o_overlay_utilizavel():
    """O defeito, pelo caminho real e não por atributo forjado: 10 artigos de 2026, todos
    com zero citação. Antes, o overlay inteiro saía cinza e a legenda dizia 'sem dado'."""
    linhas = [{"title": f"Artigo {i}", "keywords": "clima;adaptacao;cidade",
               "authors": f"A{i}, X.", "year": 2026, "citations": 0} for i in range(10)]
    gen = NetworkGenerator(_df(linhas))
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    p = build_sigma_payload(G, compute_fa2_layout(G, iterations=20))

    for no in p["nodes"]:
        assert no["attributes"]["avg_citations"] == 0.0, "zero citações virou 'sem dado'"
    assert p["overlay"]["avg_citations"]["no_data"] == 0
    assert p["overlay"]["avg_citations"]["uniform"] is True


def test_ausencia_real_de_citacao_continua_sendo_ausencia():
    """O outro lado: sem a coluna, tem de continuar `None`. A correção não pode ter virado
    'zero para tudo', que trocaria um erro por outro."""
    import numpy as np

    linhas = [{"title": f"Artigo {i}", "keywords": "clima;cidade", "year": 2015,
               "citations": np.nan} for i in range(6)]
    gen = NetworkGenerator(_df(linhas))
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    p = build_sigma_payload(G, compute_fa2_layout(G, iterations=20))

    assert all(n["attributes"]["avg_citations"] is None for n in p["nodes"])
    assert p["overlay"]["avg_citations"]["no_data"] == G.number_of_nodes()


def test_ano_continua_usando_zero_como_ausencia():
    """A assimetria é deliberada e precisa de guarda: ano zero não existe, citação zero sim."""
    G = nx.Graph()
    G.add_node("t", size=10, label="t", group=0, occurrence=3,
               year_mean=0.0, citations_mean=0.0, citations_sum=0)
    p = build_sigma_payload(G, {"t": (0.0, 0.0)})
    attrs = p["nodes"][0]["attributes"]
    assert attrs["avg_year"] is None, "ano 0 deveria continuar significando 'não sei'"
    assert attrs["avg_citations"] == 0.0, "citação 0 deveria significar zero"


# ── Animação temporal (item 6) pelo caminho REAL ─────────────────────────────────

def _grafo_com_anos(anos_por_doc: list[int]):
    linhas = [{"title": f"A{i}", "keywords": "alfa;beta;gama", "year": y, "citations": i}
              for i, y in enumerate(anos_por_doc)]
    gen = NetworkGenerator(_df(linhas))
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    return G, gen.df


def test_termo_estreia_no_primeiro_ano_e_nao_no_ano_medio():
    """O defeito que só um corpus adversarial revela.

    Todos os testes de `tests/test_map_animation.py` **passam `first_year` na mão** ao montar
    o grafo. Nenhum builder do `NetworkGenerator` escrevia esse atributo, então o app real
    caía sempre no fallback `int(year_mean)`: um termo usado de 2010 a 2020 estreava em 2013,
    e os quadros de 2010 a 2012 saíam vazios com o corpus tendo documentos ali.

    A suíte inteira da animação exercitava um caminho que a aplicação nunca tomava.
    """
    from core.map_animation import timeline_frames

    G, df = _grafo_com_anos([2010] * 4 + [2011] * 4 + [2020] * 4)

    assert all(G.nodes[n]["first_year"] == 2010 for n in G.nodes()), \
        "o builder não gravou o ano de estreia"
    assert all(G.nodes[n]["year_mean"] != 2010 for n in G.nodes()), \
        "fixture fraca: com estreia igual à média o teste não distinguiria os dois"

    quadros = {q.year: len(q.visible) for q in timeline_frames(G, df)}
    assert quadros[2010] == G.number_of_nodes(), "termo de 2010 não aparece no quadro de 2010"
    assert quadros[2011] == G.number_of_nodes()


def test_ano_faltando_no_meio_vira_quadro_vazio_e_nao_buraco():
    """2010, 2011 e 2020 no corpus: os anos sem documento precisam existir como quadro."""
    from core.map_animation import timeline_frames

    G, df = _grafo_com_anos([2010] * 4 + [2011] * 4 + [2020] * 4)
    anos = [q.year for q in timeline_frames(G, df)]
    assert anos == list(range(2010, 2021)), f"linha do tempo com buraco: {anos}"


def test_corpus_de_um_ano_so_da_um_quadro():
    from core.map_animation import timeline_frames

    G, df = _grafo_com_anos([2020] * 8)
    quadros = timeline_frames(G, df)
    assert [q.year for q in quadros] == [2020]
    assert len(quadros[0].visible) == G.number_of_nodes()


def test_corpus_sem_nenhum_ano_nao_inventa_linha_do_tempo():
    """Sem data nenhuma, a resposta honesta é lista vazia — não um ano inventado."""
    from core.map_animation import timeline_frames

    G, df = _grafo_com_anos([0] * 6)
    assert timeline_frames(G, df) == []


def test_posicoes_nao_se_mexem_entre_quadros():
    from core.map_animation import frames_share_positions, timeline_frames

    G, df = _grafo_com_anos([2015] * 3 + [2016] * 3 + [2017] * 3)
    pos = compute_fa2_layout(G, iterations=25)
    assert frames_share_positions(timeline_frames(G, df), pos)


# ── Exports que o próprio networkx não conseguia reler (item 7) ──────────────────

def _gen_com_termo(termo: str):
    linhas = [{"title": f"D{i}", "keywords": f"{termo};comum", "year": 2020, "citations": i}
              for i in range(4)]
    gen = NetworkGenerator(_df(linhas))
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    return gen, G, compute_fa2_layout(G, iterations=15)


@pytest.mark.parametrize("termo", ["quebra\nlinha", "tab\tinterno", "retorno\r\ncarro"])
def test_termo_com_quebra_nao_corrompe_export_de_linha(termo, tmp_path):
    """Pajek e VOSviewer são formatos de UM registro por linha.

    Um termo com `\\n` partia o registro em vários e o arquivo saía ilegível — medido com
    `nx.read_pajek` levantando `ValueError: No closing quotation` sobre o arquivo que o
    próprio `export_pajek` tinha acabado de escrever. O usuário só descobriria ao abrir no
    Gephi. A correção é na origem: termo de vocabulário não tem quebra de linha no meio.
    """
    gen, G, pos = _gen_com_termo(termo)

    assert not any(c in str(n) for n in G.nodes() for c in "\n\r\t"), \
        "quebra de linha sobreviveu até o nome do nó"

    caminho = tmp_path / "rede.net"
    gen.export_pajek(str(caminho))
    relido = nx.read_pajek(str(caminho))
    assert relido.number_of_nodes() == G.number_of_nodes()

    mapa, rede = tmp_path / "vos_map.txt", tmp_path / "vos_net.txt"
    gen.export_vosviewer(str(mapa), str(rede), pos)
    linhas = [l for l in mapa.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(linhas) - 1 == G.number_of_nodes(), "VOSviewer com linha a mais/a menos"


def test_aspas_no_termo_sobrevivem_ao_pajek(tmp_path):
    """O contraponto: aspas **não** eram o problema, e o teste acima não pode virar desculpa
    para começar a apagar caractere legítimo do vocabulário."""
    gen, G, _ = _gen_com_termo('aspas "duplas"')
    assert any('"' in str(n) for n in G.nodes()), "as aspas foram removidas do termo"

    caminho = tmp_path / "rede.net"
    gen.export_pajek(str(caminho))
    assert nx.read_pajek(str(caminho)).number_of_nodes() == G.number_of_nodes()


def test_normalizar_termo_preserva_o_que_e_conteudo():
    from core.nlp import normalizar_termo

    assert normalizar_termo("gestão\nde resíduos") == "gestão de resíduos"
    assert normalizar_termo("  espaço  nas  pontas  ") == "espaço nas pontas"
    assert normalizar_termo("tab\tinterno") == "tab interno"
    # Acento, emoji e aspas são conteúdo do termo, não sujeira de importação.
    assert normalizar_termo("ação 🌍 \"x\"") == "ação 🌍 \"x\""
    assert normalizar_termo("") == "" and normalizar_termo(None) == ""


@pytest.mark.parametrize("nome", ["caracteres_dificeis", "dez_desconexos", "cinco_mil"])
def test_export_bate_com_o_mapa_em_tela(nome, montados, tmp_path):
    """Item 7: número de nós e arestas conferidos programaticamente em cada formato."""
    from core.matrix_builders import NetworkGenerator as NG

    G, pos, _ = _payload(montados, nome)
    gen = NG(POR_NOME[nome].df)
    gen.G = G

    gen.export_gml(str(tmp_path / "r.gml"))
    lido = nx.read_gml(str(tmp_path / "r.gml"))
    assert (lido.number_of_nodes(), lido.number_of_edges()) == \
           (G.number_of_nodes(), G.number_of_edges())

    gen.export_gexf(str(tmp_path / "r.gexf"))
    lido = nx.read_gexf(str(tmp_path / "r.gexf"))
    assert (lido.number_of_nodes(), lido.number_of_edges()) == \
           (G.number_of_nodes(), G.number_of_edges())

    gen.export_pajek(str(tmp_path / "r.net"))
    lido = nx.read_pajek(str(tmp_path / "r.net"))
    assert lido.number_of_nodes() == G.number_of_nodes()


# ── Ida e volta do .blicsa (item 9) ──────────────────────────────────────────────

@pytest.mark.parametrize("nome", ["caracteres_dificeis", "dez_desconexos"])
def test_ida_e_volta_preserva_mapa_clusters_rotulos_e_parametros(nome, montados, tmp_path):
    from core.project import load_blicsa_project, save_blicsa_project

    G, pos, _ = _payload(montados, nome)
    config = {"name": nome, "field": "keywords", "min_occurrence": 7,
              "clustering_resolution": 1.7, "max_nodes": 123,
              "counting_method": "fractional", "research_context": "catadores"}
    grupos = sorted({G.nodes[n].get("group", 0) for n in G.nodes()})
    rotulos = {i: f"Rótulo {i} — ção 🌍" for i in grupos}
    origens = {i: ("ia" if i % 2 == 0 else "humano") for i in grupos}

    alvo = tmp_path / f"{nome}.blicsa"
    save_blicsa_project(str(alvo), POR_NOME[nome].df, config, pos, G, rotulos,
                        cluster_label_origins=origens)
    devolta = load_blicsa_project(str(alvo))

    G2 = devolta["G"]
    assert (G2.number_of_nodes(), G2.number_of_edges()) == \
           (G.number_of_nodes(), G.number_of_edges())
    for n in G.nodes():
        assert G2.nodes[str(n)].get("group") == G.nodes[n].get("group")
        assert G2.nodes[str(n)].get("color") == G.nodes[n].get("color")
        assert G2.nodes[str(n)].get("first_year") == G.nodes[n].get("first_year")
        x, y = devolta["positions"][str(n)]
        assert abs(float(x) - float(pos[n][0])) < 1e-6
        assert abs(float(y) - float(pos[n][1])) < 1e-6

    for chave, valor in config.items():
        assert devolta["config"].get(chave) == valor, f"parâmetro '{chave}' não voltou"
    assert {str(k): v for k, v in devolta["cluster_labels"].items()} == \
           {str(k): v for k, v in rotulos.items()}
    assert {str(k): v for k, v in devolta["cluster_label_origins"].items()} == \
           {str(k): v for k, v in origens.items()}, "a ORIGEM do rótulo (IA/humano) se perdeu"


def test_export_nao_grava_zero_no_lugar_de_ausencia(tmp_path):
    """A correção das citações não pode reaparecer como mentira no arquivo exportado.

    GML e GEXF não têm nulo e o TSV do VOSviewer não tem tipo: a tentação é gravar `0`. Mas
    `0` no arquivo que o usuário abre no Gephi é exatamente o que foi tirado da tela — o nó
    vira "o menos citado do mapa". Ausência se representa **omitindo** o atributo (GML/GEXF)
    ou deixando o campo **vazio** (TSV), nunca com um número inventado.

    Este teste nasceu de a bateria quebrar depois da correção: `float(None)` derrubava o
    export inteiro, e o conserto preguiçoso teria sido `.get(chave, 0.0)`.
    """
    import numpy as np

    linhas = [{"title": f"D{i}", "keywords": "alfa;beta", "year": 2020, "citations": np.nan}
              for i in range(4)]
    gen = NetworkGenerator(_df(linhas))
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    pos = compute_fa2_layout(G, iterations=15)

    assert all(G.nodes[n].get("citations_mean") is None for n in G.nodes()), "fixture fraca"

    gml = tmp_path / "r.gml"
    gen.export_gml(str(gml))
    lido = nx.read_gml(str(gml))
    assert lido.number_of_nodes() == G.number_of_nodes()
    for _, data in lido.nodes(data=True):
        assert data.get("citations_mean") is None, "GML gravou um valor onde não havia dado"

    gexf = tmp_path / "r.gexf"
    gen.export_gexf(str(gexf))
    lido = nx.read_gexf(str(gexf))
    assert lido.number_of_nodes() == G.number_of_nodes()
    for _, data in lido.nodes(data=True):
        assert data.get("citations_mean") is None, "GEXF gravou um valor onde não havia dado"

    mapa, rede = tmp_path / "m.txt", tmp_path / "n.txt"
    gen.export_vosviewer(str(mapa), str(rede), pos)
    linhas_tsv = [l for l in mapa.read_text(encoding="utf-8").splitlines() if l.strip()]
    for linha in linhas_tsv[1:]:
        campo = linha.split("\t")[-1]
        assert campo == "", f"VOSviewer gravou {campo!r} no lugar de campo vazio"
        assert "None" not in linha


def test_ano_de_estreia_chega_ao_payload_do_mapa():
    """O `map.js` monta a linha do tempo com `a.first_year || Math.round(a.avg_year)`
    (linhas 423 e 502) — e `first_year` **nunca esteve no payload**.

    A animação que o usuário vê na tela caía sempre no fallback: um termo usado de 2010 a
    2020 estreava em 2015, e a barra do tempo começava três anos depois do primeiro
    documento do corpus. Foi a captura da janela real que expôs isso; o módulo Python de
    animação (`core/map_animation.py`, sem chamador) tinha mascarado o problema, porque os
    testes dele passam `first_year` na mão.
    """
    linhas = []
    for ano in (2010, 2011, 2020):
        linhas += [{"title": f"A{ano}{i}", "keywords": "alfa;beta;gama", "year": ano,
                    "citations": i} for i in range(4)]
    gen = NetworkGenerator(_df(linhas))
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    p = build_sigma_payload(G, compute_fa2_layout(G, iterations=20))

    for no in p["nodes"]:
        attrs = no["attributes"]
        assert attrs["first_year"] == 2010, "estreia não chegou ao mapa"
        assert attrs["avg_year"] != attrs["first_year"], \
            "fixture fraca: com média igual à estreia o fallback do JS passaria despercebido"


def test_o_js_do_mapa_realmente_consome_first_year():
    """Guarda do guarda: se o `map.js` parar de ler `first_year`, o teste acima continuaria
    verde exportando um campo que ninguém usa."""
    js = (RAIZ / "assets/map.js").read_text(encoding="utf-8")
    assert "first_year" in js, "o mapa não lê mais o ano de estreia"


def test_payload_sem_ano_nao_inventa_estreia():
    G = nx.Graph()
    G.add_node("t", size=10, label="t", group=0, occurrence=3, year_mean=0.0, first_year=0)
    p = build_sigma_payload(G, {"t": (0.0, 0.0)})
    assert p["nodes"][0]["attributes"]["first_year"] is None
