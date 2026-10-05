"""Rótulos "Sobrenome (ano)" para referências do OpenAlex — offline."""
import threading
import time

import networkx as nx

from core import rotulos_referencias as R


def _obra(i, nome, ano):
    return {"id": f"https://openalex.org/W{i}", "publication_year": ano, "title": f"Título {i}",
            "authorships": [{"author": {"display_name": nome}}, {"author": {"display_name": "B"}},
                            {"author": {"display_name": "C"}}]}


def _obter(obras, pedidos):
    def obter(url):
        pedidos.append(url)
        if "openalex_id:" not in url:                 # consulta direta /works/W…
            return obras.get(url.split("?")[0].rsplit("/", 1)[-1])
        ids = url.split("openalex_id:")[1].split("&")[0].split("|")
        return {"results": [obras[i] for i in ids if i in obras]}
    return obter


def test_rotula_cacheia_e_nao_pergunta_de_novo(tmp_path):
    obras = {"W1": _obra(1, "Ana Silva", 2020), "W2": _obra(2, "Rui Costa", 2018)}
    pedidos = []
    cache = tmp_path / "c.json"
    r = R.rotulos(["https://openalex.org/W1", "W2", "W3"], _obter(obras, pedidos), cache=cache)
    assert r == {"W1": "Silva et al. (2020)", "W2": "Costa et al. (2018)"}
    assert len(pedidos) == 2                       # um lote + W3, que não veio nele
    r2 = R.rotulos(["W1", "W2", "W3"], _obter(obras, pedidos), cache=cache)
    assert r2 == r and len(pedidos) == 2           # tudo do cache, inclusive "W3 não existe"


def test_homonimos_viram_a_e_b(tmp_path):
    obras = {"W5": _obra(5, "Ana Silva", 2020), "W9": _obra(9, "Bia Silva", 2020)}
    r = R.rotulos(["W9", "W5"], _obter(obras, []), cache=tmp_path / "c.json")
    assert r == {"W5": "Silva et al. (2020a)", "W9": "Silva et al. (2020b)"}


def test_sem_internet_mapa_fica_com_rotulo_curto(tmp_path):
    def quebrado(url):
        raise OSError("sem rede")
    G = nx.Graph()
    G.add_node("https://openalex.org/W1", label="W1")
    assert R.aplicar_no_grafo(G, quebrado, cache=tmp_path / "c.json") == 0
    assert G.nodes["https://openalex.org/W1"]["label"] == "W1"


def test_openalex_lento_nao_segura_o_mapa(tmp_path):
    def lento(url):
        time.sleep(3)
        return {"results": []}
    G = nx.Graph()
    G.add_node("W1", label="W1")
    t0 = time.perf_counter()
    assert R.aplicar_no_grafo(G, lento, tempo_max=0.3, cache=tmp_path / "c.json") == 0
    assert time.perf_counter() - t0 < 1.5


def test_aplica_no_grafo_de_cocitacao(tmp_path):
    from core.matrix_builders import NetworkGenerator
    import pandas as pd
    linhas = [{"authors": "X", "title": f"T{i}", "year": 2020, "keywords": "a",
               "references": "https://openalex.org/W1; https://openalex.org/W2",
               "doi": f"10.1000/{i}", "citations": 0, "source": "", "abstract": ""}
              for i in range(5)]
    G = NetworkGenerator(pd.DataFrame(linhas)).build_cocitation_network(min_cocitations=1)
    obras = {"W1": _obra(1, "Ana Silva", 2020), "W2": _obra(2, "Rui Costa", 2018)}
    assert R.aplicar_no_grafo(G, _obter(obras, []), cache=tmp_path / "c.json") == 2
    assert sorted(G.nodes[n]["label"] for n in G) == ["Costa et al. (2018)", "Silva et al. (2020)"]
    assert "Título 1" in G.nodes["https://openalex.org/W1"]["title"]


def test_dois_autores_e_obra_fundida(tmp_path):
    """Dois autores: "Gregor e Hevner (2013)". Obra fundida no OpenAlex: o lote não a
    devolve, a consulta direta segue o redirecionamento (visto ao vivo em 04/10)."""
    from core.artigos_conectados import rotulo
    w2 = {"id": "https://openalex.org/W2", "publication_year": 2013,
          "authorships": [{"author": {"display_name": "Shirley Gregor"}},
                          {"author": {"display_name": "Alan R. Hevner"}}]}
    assert rotulo(w2) == "Gregor e Hevner (2013)"
    fundida = {"id": "https://openalex.org/W99", "publication_year": 2019,
               "authorships": [{"author": {"display_name": "Jacob Devlin"}}]}
    pedidos = []

    def obter(url):
        pedidos.append(url)
        if "openalex_id:" in url:
            return {"results": [w2]}                 # W7 não vem no lote
        if url.split("?")[0].endswith("/W7"):
            return fundida                           # redirecionada para W99
        return None
    r = R.rotulos(["W2", "W7"], obter, cache=tmp_path / "c.json")
    assert r == {"W2": "Gregor e Hevner (2013)", "W7": "Devlin (2019)"}


def test_cache_de_formato_antigo_e_refeito(tmp_path):
    import json
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"W2": {"rotulo": "Gregor e outro (2013)"}}))
    w2 = {"id": "https://openalex.org/W2", "publication_year": 2013,
          "authorships": [{"author": {"display_name": "Shirley Gregor"}},
                          {"author": {"display_name": "Alan Hevner"}}]}
    r = R.rotulos(["W2"], lambda url: {"results": [w2]}, cache=cache)
    assert r == {"W2": "Gregor e Hevner (2013)"}
