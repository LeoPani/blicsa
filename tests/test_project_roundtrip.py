"""Ida e volta de um projeto `.blicsa` completo: nada pode se perder no caminho.

Um projeto é o trabalho do usuário. Perder uma coluna, um rótulo de cluster ou um parâmetro
na gravação é pior do que um crash: o crash aparece, a perda silenciosa só é descoberta
quando alguém vai usar o dado e ele não está lá.

O teste grava um projeto com **tudo** preenchido — dataset com as 13 colunas do schema, grafo
com atributos em nós e arestas, posições do layout, rótulos de cluster, histórico de buscas e
os parâmetros de configuração — reabre e compara valor a valor.
"""

import gzip
import json
import zipfile
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from core.project import (CURRENT_MANIFEST_VERSION, SCHEMA_REGISTRO,
                          load_blicsa_project, save_blicsa_project)


@pytest.fixture
def projeto_completo():
    """Um projeto com todos os campos preenchidos e valores distinguíveis entre si.

    Valores escolhidos para pegar erro de serialização: acentos, ponto e vírgula, DOI com
    barra, booleano nos dois estados, zero e número grande, string vazia legítima.
    """
    df = pd.DataFrame([
        {"authors": "Silva A; Costa B", "title": "Mapeamento bibliométrico da inovação",
         "year": 2019, "source": "Revista de Inovação", "keywords": "inovação; patentes",
         "abstract": "Resumo com acentuação e ponto e vírgula; segunda parte.",
         "citations": 142, "doi": "10.1234/abc.2019/xyz", "references": "W1; W2; W3",
         "origin": "OpenAlex", "language": "pt", "is_oa": True,
         "oa_url": "https://exemplo.org/a.pdf"},
        {"authors": "Pereira C", "title": "Co-word analysis in regional studies",
         "year": 2021, "source": "Journal of Scientometrics", "keywords": "co-word; clusters",
         "abstract": "", "citations": 0, "doi": "10.5678/def",
         "references": "", "origin": "Crossref", "language": "en", "is_oa": False,
         "oa_url": ""},
        {"authors": "Nakamura T; Öztürk M", "title": "Bibliometrics of emerging fields",
         "year": 2024, "source": "Scientometrics", "keywords": "bibliometrics",
         "abstract": "Third abstract.", "citations": 7, "doi": "10.9999/ghi",
         "references": "W9", "origin": "PubMed", "language": "en", "is_oa": True,
         "oa_url": "https://exemplo.org/c.pdf"},
    ])

    G = nx.Graph()
    G.add_node("inovação", weight=12, cluster=0, color="#DF3117", relevance=0.83)
    G.add_node("patentes", weight=8, cluster=0, color="#DF3117", relevance=0.61)
    G.add_node("clusters", weight=5, cluster=1, color="#1E4DA0", relevance=0.44)
    G.add_edge("inovação", "patentes", weight=4, association=0.72)
    G.add_edge("inovação", "clusters", weight=1, association=0.15)

    positions = {"inovação": (0.12, -0.45), "patentes": (0.33, -0.21), "clusters": (-0.8, 0.6)}
    # Chaves INTEIRAS: é o que o app produz (`main.py:121` declara `dict[int, str]`, e os ids
    # vêm da partição do Louvain). A gravação serializa com `str(k)` e a carga desfaz com
    # `int(k)` — a volta só é identidade para este tipo, então o teste tem que usá-lo.
    cluster_labels = {0: "Inovação e propriedade industrial", 1: "Métodos bibliométricos"}
    searches = [
        {"query": "inovação regional", "provider": "openalex", "total": 54440,
         "downloaded": 3, "when": "2026-08-04 09:00:00"},
        {"query": "bibliometrics", "provider": "pubmed", "total": 5673431,
         "downloaded": 0, "when": "2026-08-04 09:05:00"},
    ]
    config = {
        "name": "Projeto de Ida e Volta", "slug": "ida-e-volta",
        "map_type": "rede", "field": "keywords", "min_occurrence": 5,
        "relevance_threshold": 0.4, "clustering_resolution": 1.2,
        "attraction": 0.8, "repulsion": 12.0,
        "thesaurus": {"inovacao": "inovação", "innovation": "inovação"},
        "extra_stop_words": ["estudo", "análise"],
        "year_min": 2019, "year_max": 2024,
    }
    return df, config, positions, G, cluster_labels, searches


def _salva_e_recarrega(tmp_path: Path, projeto):
    df, config, positions, G, cluster_labels, searches = projeto
    destino = tmp_path / "projeto.blicsa"
    save_blicsa_project(str(destino), df, config, positions, G, cluster_labels, searches)
    return destino, load_blicsa_project(str(destino))


# ── O dataset volta idêntico ──────────────────────────────────────────────────────

def test_dataset_volta_coluna_a_coluna_valor_a_valor(tmp_path, projeto_completo):
    df_original = projeto_completo[0]
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    df_lido = lido["df"]

    assert list(df_lido.columns) == list(df_original.columns), "ordem/conjunto de colunas mudou"
    assert len(df_lido) == len(df_original)

    for coluna in df_original.columns:
        esperado = list(df_original[coluna])
        obtido = list(df_lido[coluna])
        assert obtido == esperado, f"coluna {coluna!r}: {obtido} ≠ {esperado}"


def test_todas_as_colunas_do_schema_sobrevivem(tmp_path, projeto_completo):
    """Guarda explícita contra perda de coluna na gravação — a hipótese de corrupção ativa
    levantada pelos projetos anômalos de 30/07."""
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    faltando = [c for c in SCHEMA_REGISTRO if c not in lido["df"].columns]
    assert not faltando, f"a gravação perdeu colunas: {faltando}"


def test_tipos_nao_degradam(tmp_path, projeto_completo):
    """`is_oa` tem que voltar booleano, não a string "True"; ano e citações, inteiros."""
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    df = lido["df"]
    assert df["is_oa"].dtype == bool, df["is_oa"].dtype
    assert str(df["year"].dtype).startswith("int"), df["year"].dtype
    assert str(df["citations"].dtype).startswith("int"), df["citations"].dtype
    assert list(df["is_oa"]) == [True, False, True]


def test_acentos_e_separadores_sobrevivem(tmp_path, projeto_completo):
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    df = lido["df"]
    assert df.loc[0, "title"] == "Mapeamento bibliométrico da inovação"
    assert df.loc[0, "keywords"] == "inovação; patentes"
    assert df.loc[2, "authors"] == "Nakamura T; Öztürk M"
    assert df.loc[0, "doi"] == "10.1234/abc.2019/xyz", "a barra do DOI não pode ser escapada"


def test_vazio_legitimo_continua_vazio(tmp_path, projeto_completo):
    """Abstract vazio de verdade não pode virar None, NaN nem a palavra "nan"."""
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    assert lido["df"].loc[1, "abstract"] == ""
    assert lido["df"].loc[1, "oa_url"] == ""
    assert lido["df"].loc[1, "citations"] == 0, "zero não pode virar vazio"


# ── Mapa, clusters e parâmetros ───────────────────────────────────────────────────

def test_grafo_volta_com_nos_arestas_e_atributos(tmp_path, projeto_completo):
    G_original = projeto_completo[3]
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    G = lido["G"]

    assert set(G.nodes()) == set(G_original.nodes())
    assert set(map(frozenset, G.edges())) == set(map(frozenset, G_original.edges()))

    for no, dados in G_original.nodes(data=True):
        assert G.nodes[no] == dados, f"atributos do nó {no!r} mudaram"
    for u, v, dados in G_original.edges(data=True):
        assert G.edges[u, v] == dados, f"atributos da aresta {u}–{v} mudaram"


def test_posicoes_do_layout_voltam(tmp_path, projeto_completo):
    posicoes = projeto_completo[2]
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    assert set(lido["positions"]) == set(posicoes)
    for no, (x, y) in posicoes.items():
        gx, gy = lido["positions"][no]
        assert (gx, gy) == pytest.approx((x, y)), f"posição de {no!r} mudou"


def test_rotulos_de_cluster_voltam(tmp_path, projeto_completo):
    rotulos = projeto_completo[4]
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    assert lido["cluster_labels"] == rotulos
    assert all(isinstance(k, int) for k in lido["cluster_labels"]), (
        "as chaves têm que voltar inteiras: main.py faz `self._cluster_labels.get(cid)` "
        "com `cid` inteiro, e chave de texto silenciaria o rótulo no mapa")


def test_rotulo_de_cluster_nao_numerico_nao_impede_abrir_o_projeto(tmp_path, projeto_completo):
    """Robustez: `int(k)` levantava `ValueError` e derrubava a carga INTEIRA do projeto.

    Nenhum caminho do app produz chave não numérica hoje — os ids vêm do Louvain. Mas o custo
    de estar errado é o pior possível para um arquivo de trabalho: o projeto não abre mais, e
    nada além do rótulo de um cluster estava em jogo. A chave estranha é preservada como veio.
    """
    df, config, positions, G, _, searches = projeto_completo
    destino = tmp_path / "rotulo_estranho.blicsa"
    save_blicsa_project(str(destino), df, config, positions, G,
                        {0: "Numérico", "principal": "Nomeado à mão"}, searches)

    lido = load_blicsa_project(str(destino))
    assert lido["cluster_labels"] == {0: "Numérico", "principal": "Nomeado à mão"}
    assert lido["df"] is not None, "o dataset foi perdido junto com o rótulo"


def test_parametros_e_thesaurus_voltam(tmp_path, projeto_completo):
    config = projeto_completo[1]
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    assert lido["config"] == config, "algum parâmetro do mapa se perdeu"
    assert lido["config"]["thesaurus"] == {"inovacao": "inovação", "innovation": "inovação"}
    assert lido["config"]["extra_stop_words"] == ["estudo", "análise"]


def test_historico_de_buscas_volta(tmp_path, projeto_completo):
    buscas = projeto_completo[5]
    _, lido = _salva_e_recarrega(tmp_path, projeto_completo)
    assert lido["searches"] == buscas


# ── Formato do arquivo ────────────────────────────────────────────────────────────

def test_manifesto_declara_a_versao_corrente(tmp_path, projeto_completo):
    """A anomalia de 30/07 (`version: 3`, `app: "Blicsa"`) NÃO veio deste caminho — nenhum
    código do repositório escreve esses valores. Este teste trava o que o app escreve."""
    destino, _ = _salva_e_recarrega(tmp_path, projeto_completo)
    with zipfile.ZipFile(destino) as z:
        manifesto = json.loads(z.read("manifest.json"))
    assert manifesto["version"] == CURRENT_MANIFEST_VERSION
    assert manifesto["app"] == "PyBibliomics Blicsa"
    assert manifesto["saved_at"], "sem carimbo de gravação"


def test_arquivo_contem_todas_as_entradas_esperadas(tmp_path, projeto_completo):
    destino, _ = _salva_e_recarrega(tmp_path, projeto_completo)
    with zipfile.ZipFile(destino) as z:
        entradas = set(z.namelist())
    assert {"manifest.json", "config.json", "dataset.json.gz", "layout.json",
            "network.json", "clusters.json", "searches.json"} <= entradas, entradas


def test_dataset_gravado_tem_as_13_colunas_no_disco(tmp_path, projeto_completo):
    """Olha o BYTE gravado, não o objeto recarregado: se a normalização da carga estivesse
    mascarando uma perda na gravação, este é o teste que veria."""
    destino, _ = _salva_e_recarrega(tmp_path, projeto_completo)
    with zipfile.ZipFile(destino) as z:
        registros = json.loads(gzip.decompress(z.read("dataset.json.gz")))
    colunas = set().union(*[set(r) for r in registros])
    assert set(SCHEMA_REGISTRO) <= colunas, f"faltam no disco: {set(SCHEMA_REGISTRO) - colunas}"


# ── Ida e volta repetida ──────────────────────────────────────────────────────────

def test_duas_voltas_seguidas_nao_degradam(tmp_path, projeto_completo):
    """Salvar → abrir → salvar → abrir. Degradação por acúmulo só aparece na segunda volta."""
    destino1, primeira = _salva_e_recarrega(tmp_path, projeto_completo)

    destino2 = tmp_path / "segunda.blicsa"
    save_blicsa_project(str(destino2), primeira["df"], primeira["config"],
                        primeira["positions"], primeira["G"], primeira["cluster_labels"],
                        primeira["searches"])
    segunda = load_blicsa_project(str(destino2))

    pd.testing.assert_frame_equal(segunda["df"], primeira["df"])
    assert segunda["config"] == primeira["config"]
    assert segunda["cluster_labels"] == primeira["cluster_labels"]
    assert segunda["searches"] == primeira["searches"]
    assert set(segunda["G"].nodes()) == set(primeira["G"].nodes())
    for no, dados in primeira["G"].nodes(data=True):
        assert segunda["G"].nodes[no] == dados
