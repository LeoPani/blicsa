"""Migração do `citations_mean: 0.0` ambíguo de projeto antigo.

Até 09/08/2026 o escritor gravava `0.0` em duas situações diferentes — termo em documentos
com **zero citação** (valor verdadeiro) e termo em documentos **sem dado de citação** (valor
desconhecido). O leitor tratava os dois como "não sei", e um corpus recente saía com o
overlay inteiro cinza sobre um dado que existia.

A correção mudou o escritor para gravar `None` no segundo caso. Mas **o arquivo já salvo não
tinha como ser lido**: `0.0` sozinho não diz qual dos dois casos era.

O que torna a migração possível é o `.blicsa` guardar o **dataset inteiro**, com a coluna
`citations`. A ambiguidade só existe no grafo derivado; a fonte está do lado.
"""

import gzip
import json
import zipfile
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from core.project import load_blicsa_project, migrar_citacoes_ambiguas

#: 'clima' só aparece em artigos de 2026 sem citação → zero VERDADEIRO.
#: 'velho' aparece em artigos citados → o 0.0 no grafo é MENTIRA do escritor antigo.
CORPUS = pd.DataFrame(
    [{"title": f"Recente {i}", "keywords": "clima", "authors": "A, X",
      "year": 2026, "citations": 0} for i in range(4)]
    + [{"title": f"Antigo {i}", "keywords": "velho", "authors": "B, Y",
        "year": 2010, "citations": 30 + i} for i in range(4)]
)


def _grafo_antigo() -> nx.Graph:
    """Como o escritor de antes de 09/08 gravava: 0.0 para os dois significados."""
    G = nx.Graph()
    for termo, ano in (("clima", 2026.0), ("velho", 2010.0)):
        G.add_node(termo, size=10, label=termo, group=0, occurrence=4,
                   year_mean=ano, citations_mean=0.0, citations_sum=0)
    G.add_edge("clima", "velho")
    return G


def _blicsa_antigo(destino: Path, df: pd.DataFrame | None = CORPUS,
                   G: nx.Graph | None = None) -> Path:
    G = _grafo_antigo() if G is None else G
    with zipfile.ZipFile(destino, "w") as z:
        z.writestr("manifest.json", json.dumps({"version": "1.0"}))
        z.writestr("config.json", json.dumps({"name": "antigo"}))
        if df is not None:
            z.writestr("dataset.json.gz",
                       gzip.compress(df.to_json(orient="records").encode()))
        z.writestr("network.json", json.dumps({
            "nodes": [{"id": n, "attributes": dict(G.nodes[n])} for n in G.nodes()],
            "edges": [{"source": u, "target": v, "attributes": {}} for u, v in G.edges()],
        }))
    return destino


# ── O que a migração recupera ────────────────────────────────────────────────────

def test_projeto_antigo_recupera_a_citacao_que_o_grafo_perdeu(tmp_path):
    """O caso que justifica a migração: `velho` valia 0.0 no arquivo e 31,5 na fonte."""
    d = load_blicsa_project(str(_blicsa_antigo(tmp_path / "p.blicsa")))
    G = d["G"]

    assert G.nodes["velho"]["citations_mean"] == 31.5, \
        "o 0.0 mentiroso não foi corrigido a partir do dataset"
    assert G.nodes["velho"]["citations_sum"] == 126


def test_zero_verdadeiro_continua_zero(tmp_path):
    """O outro lado: a migração não pode inventar citação onde de fato não há nenhuma.
    Trocar um erro por outro seria pior — 'zero citações' é informação, não ausência."""
    d = load_blicsa_project(str(_blicsa_antigo(tmp_path / "p.blicsa")))

    assert d["G"].nodes["clima"]["citations_mean"] == 0.0
    assert d["G"].nodes["clima"]["citations_sum"] == 0


def test_migracao_e_idempotente(tmp_path):
    """Projeto já migrado (ou salvo pelo escritor novo) não muda ao ser reaberto."""
    caminho = _blicsa_antigo(tmp_path / "p.blicsa")
    primeiro = load_blicsa_project(str(caminho))["G"]
    valores = {n: primeiro.nodes[n]["citations_mean"] for n in primeiro.nodes()}

    segundo = load_blicsa_project(str(caminho))["G"]
    assert {n: segundo.nodes[n]["citations_mean"] for n in segundo.nodes()} == valores


def test_so_os_nos_ambiguos_sao_recalculados(tmp_path):
    """`compute_overlay_scores` é O(nós × documentos) — 36 s para 5.000 nós. Recalcular o
    grafo inteiro faria toda abertura pagar por uma ambiguidade que atinge poucos nós."""
    G = _grafo_antigo()
    G.add_node("intacto", size=10, label="intacto", group=0, occurrence=4,
               year_mean=2015.0, citations_mean=99.0, citations_sum=396)
    G.add_edge("clima", "intacto")

    recalculados = migrar_citacoes_ambiguas(G, CORPUS)

    assert recalculados == 2, "recalculou nós que não eram ambíguos"
    assert G.nodes["intacto"]["citations_mean"] == 99.0, "nó não ambíguo foi tocado"


def test_projeto_sem_dataset_nao_quebra(tmp_path):
    """Projeto salvo sem corpus não tem de onde recalcular. Tem de abrir mesmo assim, com o
    valor antigo — é o único caso que a migração não resolve, e está no CHANGELOG."""
    d = load_blicsa_project(str(_blicsa_antigo(tmp_path / "p.blicsa", df=None)))

    assert d["G"].number_of_nodes() == 2
    assert d["G"].nodes["velho"]["citations_mean"] == 0.0


def test_grafo_ou_corpus_ausente_nao_levanta():
    assert migrar_citacoes_ambiguas(None, CORPUS) == 0
    assert migrar_citacoes_ambiguas(_grafo_antigo(), None) == 0
    assert migrar_citacoes_ambiguas(_grafo_antigo(), pd.DataFrame()) == 0


def test_falha_da_migracao_nao_impede_o_projeto_de_abrir(tmp_path, monkeypatch):
    """Projeto que abre com métrica velha é melhor do que projeto que não abre. A carga já
    foi perdida uma vez inteira por causa do rótulo de um cluster (`_id_cluster`)."""
    import core.matrix_builders as mb

    def explode(self, apenas=None):
        raise RuntimeError("falha proposital")

    monkeypatch.setattr(mb.NetworkGenerator, "compute_overlay_scores", explode)
    d = load_blicsa_project(str(_blicsa_antigo(tmp_path / "p.blicsa")))

    assert d["G"].number_of_nodes() == 2, "o projeto deixou de abrir por causa da migração"
    assert d["G"].nodes["velho"]["citations_mean"] == 0.0


# ── O efeito no que o usuário vê ─────────────────────────────────────────────────

def test_overlay_do_projeto_antigo_deixa_de_ser_cinza(tmp_path):
    """O sintoma que originou tudo, medido no payload que alimenta o mapa."""
    from core.sigma_exporter import build_sigma_payload

    d = load_blicsa_project(str(_blicsa_antigo(tmp_path / "p.blicsa")))
    G = d["G"]
    payload = build_sigma_payload(G, {n: (i * 1.0, 0.0) for i, n in enumerate(G.nodes())})

    escala = payload["overlay"]["avg_citations"]
    assert escala["no_data"] == 0, "ainda há nó anunciado como 'sem dado'"
    assert escala["min"] == 0.0 and escala["max"] == 31.5, \
        "a faixa do overlay não reflete os valores recuperados"


@pytest.mark.parametrize("apenas", [None, {"velho"}])
def test_compute_overlay_scores_respeita_o_subconjunto(apenas):
    """A migração reusa `compute_overlay_scores` em vez de reescrever o casamento
    nó↔documento. Dois casadores para o mesmo campo é a inconsistência já catalogada em
    `docs/AUDITORIA-ARQUITETURA.md` §4.

    `clima` entra com um valor-sentinela impossível: recalculá-lo daria 0.0, que é igual ao
    que já estava lá, e o teste não distinguiria "foi recalculado" de "não foi tocado".
    """
    from core.matrix_builders import NetworkGenerator

    G = _grafo_antigo()
    G.nodes["clima"]["citations_mean"] = 777.0
    gen = NetworkGenerator(CORPUS)
    gen.G = G

    gen.compute_overlay_scores(apenas=apenas)

    assert G.nodes["velho"]["citations_mean"] == 31.5, "o nó pedido não foi recalculado"
    if apenas is None:
        assert G.nodes["clima"]["citations_mean"] == 0.0, "sem filtro, tudo é recalculado"
    else:
        assert G.nodes["clima"]["citations_mean"] == 777.0, \
            "nó fora do subconjunto foi recalculado — o filtro não vale nada"
