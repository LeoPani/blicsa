"""Explorar a partir de um artigo — OpenAlex simulado, offline."""
import json
import re
import urllib.parse

import pytest

from core import artigos_conectados as AC


def _w(i, ano, cit, refs=(), autor="Autor", related=()):
    return {"id": f"https://openalex.org/W{i}", "doi": f"https://doi.org/10.1000/{i}",
            "title": f"Artigo {i}", "publication_year": ano, "cited_by_count": cit,
            "authorships": [{"author": {"display_name": f"Ana {autor}{i}"}}],
            "referenced_works": [f"https://openalex.org/W{r}" for r in refs],
            "related_works": [f"https://openalex.org/W{r}" for r in related],
            "type": "article", "open_access": {"is_oa": False}}


def _mundo():
    """Semente 1 cita 10..19. Os artigos 100..129 citam a semente; os pares 100-114 também
    citam 10..19 (mesmo assunto), os 115-129 citam 50..59 (outro assunto)."""
    obras = {1: _w(1, 2015, 500, refs=range(10, 20), related=[300])}
    for r in range(10, 20):
        obras[r] = _w(r, 2005, 300, refs=[5, 6])
    for r in range(50, 60):
        obras[r] = _w(r, 2003, 50)
    for c in range(100, 115):
        obras[c] = _w(c, 2018 + c % 5, 40 + c, refs=[1, *range(10, 20)])
    for c in range(115, 130):
        obras[c] = _w(c, 2019, 10, refs=[1, *range(50, 60)])
    obras[300] = _w(300, 2016, 80, refs=range(10, 15))
    obras[5] = _w(5, 1990, 2000)
    obras[6] = _w(6, 1992, 1500)
    # Uma revisão posterior que cita 8 artigos do grupo
    obras[900] = _w(900, 2024, 5, refs=[1, 100, 101, 102, 103, 10, 11, 12])
    return obras


def _obter(obras, pedidos):
    def obter(url):
        pedidos.append(url)
        u = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(u.query)
        caminho = u.path.replace("/works", "", 1).lstrip("/")
        if caminho:
            m = re.search(r"W(\d+)$", caminho) or re.search(r"10\.1000/(\d+)$", caminho)
            return obras.get(int(m.group(1))) if m else None
        filtro = q["filter"][0]
        if filtro.startswith("openalex_id:"):
            ids = [int(x[1:]) for x in filtro.split(":", 1)[1].split("|")]
            return {"results": [obras[i] for i in ids if i in obras]}
        if filtro.startswith("cites:"):
            alvo = {f"https://openalex.org/{x}" for x in filtro.split(":", 1)[1].split("|")}
            res = [w for w in obras.values() if alvo & set(w["referenced_works"])]
            res.sort(key=lambda w: -w["cited_by_count"])
            pp, pg = int(q["per_page"][0]), int(q.get("page", ["1"])[0])
            return {"results": res[(pg - 1) * pp: pg * pp]}
        raise AssertionError(url)
    return obter


def test_interpreta_dois_ids_e_links():
    refs = AC.interpretar_entrada("10.1000/abc; https://doi.org/10.2000/X.Y\nW123 "
                                  "https://openalex.org/W456 lixo")
    assert refs == ["https://doi.org/10.1000/abc", "https://doi.org/10.2000/X.Y", "W123", "W456"]


def test_grafo_agrupa_os_parecidos_com_a_semente():
    obras, pedidos = _mundo(), []
    ex = AC.explorar("10.1000/1", _obter(obras, pedidos), n=20)
    assert ex.sementes == ["W1"]
    G = ex.grafo
    assert "W1" in G and G.nodes["W1"]["semente"]
    nos = set(G) - {"W1"}
    # os que citam a semente E as mesmas obras dela vêm antes dos de outro assunto
    mesmos = {f"W{c}" for c in range(100, 115)}
    assert len(nos & mesmos) >= 12
    assert sum(ex.semelhanca[f"W{c}"] for c in range(100, 105)) > \
           sum(ex.semelhanca.get(f"W{c}", 0) for c in range(115, 120))
    assert all(G.degree(n) > 0 for n in G), "nó solto no mapa"
    assert G.nodes["W1"]["label"] == "Autor1 (2015)"
    assert ex.pedidos <= 12, f"pedidos demais à API: {ex.pedidos}"


def test_obras_anteriores_e_derivadas():
    obras, pedidos = _mundo(), []
    ex = AC.explorar("W1", _obter(obras, pedidos), n=20)
    anteriores = dict(ex.anteriores)
    assert "W5" in anteriores and "W6" in anteriores        # os clássicos citados pelo grupo
    assert all(r not in ex.grafo for r in anteriores)
    assert ex.derivadas and ex.derivadas[0][0] == "W900"    # a revisão que cita o grupo


def test_varias_sementes_e_doi_inexistente_avisam():
    obras, pedidos = _mundo(), []
    ex = AC.explorar("W1 W300 10.1000/999999", _obter(obras, pedidos), n=10)
    assert ex.sementes == ["W1", "W300"]
    assert any("10.1000/999999" in a for a in ex.avisos)


def test_nada_encontrado_e_entrada_vazia():
    with pytest.raises(AC.ErroExplorar, match="sem_entrada"):
        AC.explorar("   ", lambda u: None)
    with pytest.raises(AC.ErroExplorar, match="nao_achado"):
        AC.explorar("10.1000/1", lambda u: None)


def test_cancelar_interrompe():
    import threading
    ev = threading.Event()
    ev.set()
    with pytest.raises(InterruptedError):
        AC.explorar("W1", _obter(_mundo(), []), cancelar=ev)


def test_vira_registro_do_corpus():
    obras = _mundo()
    ex = AC.explorar("W1", _obter(obras, []), n=10)
    regs = AC.para_registros(ex, list(ex.grafo)[:3])
    assert len(regs) == 3
    assert regs[0]["openalex_id"].startswith("https://openalex.org/W")
    assert regs[0]["references"].count("openalex.org/W") >= 1
    assert {"title", "authors", "year", "doi", "citations"} <= set(regs[0])


def test_semente_real_gravada_do_openalex():
    """Uma obra REAL gravada (fixture) como semente: os campos que o módulo lê existem."""
    corpo = json.load(open("tests/fixtures/openalex_page1.json"))["body"]
    corpo = json.loads(corpo) if isinstance(corpo, str) else corpo
    w = corpo["results"][0]
    assert AC.rotulo(w).endswith(f"({w['publication_year']})")
    assert AC._refs(w)
    assert all(AC.id_curto(r) for r in w["related_works"])


# ── Janela no app ───────────────────────────────────────────────────────────────────
@pytest.fixture
def app(monkeypatch, tmp_path):
    import main as M
    for nome in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(M.messagebox, nome, lambda *a, **k: None)
    monkeypatch.setattr(M, "REPORTS_DIR", tmp_path / "reports")
    try:
        a = M.BlicsaApp()
    except Exception as exc:
        pytest.skip(f"Tk indisponível: {exc}")
    a._demo_no_browser = True
    a.withdraw()
    yield a
    try:
        a.destroy()
    except Exception:
        pass


def test_janela_explora_adiciona_ao_corpus_e_gera_mapa(app, monkeypatch, tmp_path):
    import threading
    import pandas as pd
    import main as M
    obras = _mundo()
    na_thread_da_tela = []

    def obter_falso():
        def obter(url):
            na_thread_da_tela.append(threading.current_thread() is threading.main_thread())
            return _obter(obras, [])(url)
        return obter, "teste@example.com"
    monkeypatch.setattr(AC, "obter_padrao", obter_falso)
    infos = []
    monkeypatch.setattr(M.messagebox, "showinfo", lambda t, m, *a, **k: infos.append(m))
    # corpus já tem a semente: ela não pode entrar duplicada
    app._dataframe = pd.DataFrame([{"title": "Artigo 1", "doi": "https://doi.org/10.1000/1",
                                    "authors": "Ana Autor1", "year": 2015}])
    app._abrir_explorar()
    api = app._explorar_api
    api["entrada"].insert("1.0", "https://doi.org/10.1000/1")
    app.after(20, api["explorar"])
    app.after(1500, app.quit)
    app.mainloop()
    assert na_thread_da_tela and not any(na_thread_da_tela), "consulta na thread da interface"
    ex = api["estado"]["ex"]
    assert ex is not None and len(ex.grafo) > 10
    assert "Pronto" in api["status"].cget("text")
    # marca a primeira lista inteira (grafo, inclui a semente) e adiciona
    for i in ex.grafo.nodes:
        api["estado"]["marcas"][i].set(True)
    api["adicionar"]()
    assert any("1 já estavam" in m or "(1 já" in m for m in infos), infos
    assert len(app._dataframe) == len(ex.grafo)            # semente não duplicou
    assert app._dataframe["openalex_id"].str.contains("openalex.org/W").sum() >= len(ex.grafo) - 1
    api["abrir_mapa"]()
    html = list((tmp_path / "reports").glob("blicsa_explorar_*.html"))
    assert html and "Autor1 (2015)" in html[0].read_text(encoding="utf-8")


def test_janela_sem_entrada_avisa_e_nao_consulta(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr(AC, "obter_padrao", lambda: chamadas.append(1))
    app._abrir_explorar()
    app._explorar_api["explorar"]()
    assert "DOI" in app._explorar_api["status"].cget("text") and not chamadas


def test_grafo_conexo_e_colorido_por_cluster():
    import networkx as nx
    ex = AC.explorar("W1", _obter(_mundo(), []), n=40)
    assert nx.is_connected(ex.grafo), "grupos soltos viram ilhas no mapa"
    cores = {ex.grafo.nodes[n]["color"] for n in ex.grafo}
    assert len(cores) >= 2 and all(c.startswith("#") for c in cores)


def test_completar_ids_pelo_doi():
    import pandas as pd
    obras = _mundo()
    df = pd.DataFrame([{"doi": "https://doi.org/10.1000/100", "title": "a"},
                       {"doi": "10.1000/101", "title": "b", "openalex_id": ""},
                       {"doi": "", "title": "sem doi"},
                       {"doi": "10.1000/888888", "title": "não existe"}])
    pedidos = []

    def obter(url):
        pedidos.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        dois = q["filter"][0].split(":", 1)[1].split("|")
        return {"results": [w for w in obras.values()
                            if w["doi"].lower().replace("https://doi.org/", "") in dois]}
    assert AC.completar_ids(df, obter) == 2
    assert list(df["openalex_id"][:2]) == ["https://openalex.org/W100", "https://openalex.org/W101"]
    assert len(pedidos) == 1


def test_botao_completar_ids_aparece_e_destrava_citacao_direta(app, monkeypatch):
    import pandas as pd
    import main as M
    obras = _mundo()
    linhas = [{"title": f"T{i}", "authors": "A", "year": 2020, "doi": f"10.1000/{i}",
               "references": "; ".join(obras[i]["referenced_works"]), "openalex_id": ""}
              for i in range(100, 110)]
    app._dataframe = M.normalize_dataframe(pd.DataFrame(linhas)) if hasattr(M, "normalize_dataframe") \
        else pd.DataFrame(linhas)
    app._map_type_var.set(M.MAP_TYPES[4])
    app._atualizar_tipo_de_mapa()
    app.update()
    assert app._btn_completar_ids.winfo_ismapped()

    def obter(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        dois = q["filter"][0].split(":", 1)[1].split("|")
        return {"results": [w for w in obras.values()
                            if w["doi"].lower().replace("https://doi.org/", "") in dois]}
    monkeypatch.setattr(AC, "obter_padrao", lambda: (obter, "x@y.z"))
    app.after(20, app._completar_ids_openalex)
    app.after(1200, app.quit)
    app.mainloop()
    assert app._dataframe["openalex_id"].str.startswith("https://openalex.org/W").all()
    assert not app._btn_completar_ids.winfo_ismapped()     # aviso some: agora dá


def test_doi_inexistente_404_vira_nao_encontrado(monkeypatch):
    import urllib.error
    from core.sources import openalex as O

    def fetch(self, url, *a, **k):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(O.OpenAlexProvider, "fetch_url", fetch)
    obter, _ = AC.obter_padrao(api_key="")
    with pytest.raises(AC.ErroExplorar, match="nao_achado"):
        AC.explorar("10.1000/naoexiste", obter)
