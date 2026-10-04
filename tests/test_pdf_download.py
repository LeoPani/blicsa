"""Download de PDFs de acesso aberto — tudo offline, com a rede simulada."""
import io
import os
import threading

import pytest

from core import pdf_download as P

PDF = b"%PDF-1.7\n" + b"x" * 5000 + b"\n%%EOF"


class _Resp(io.BytesIO):
    def __init__(self, corpo, url):
        super().__init__(corpo)
        self.url = url
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _rede(paginas: dict, jsons: dict | None = None):
    """abrir_url/buscar_json falsos. `paginas[url]` é bytes ou uma exceção."""
    pedidos = []

    def abrir(url):
        pedidos.append(url)
        v = paginas.get(url)
        if v is None:
            raise OSError("HTTP Error 404")
        if isinstance(v, Exception):
            raise v
        return _Resp(v, url)

    def buscar(url):
        for chave, valor in (jsons or {}).items():
            if chave in url:
                return valor
        return None
    return abrir, buscar, pedidos


def _baixar(tmp_path, registros, paginas, jsons=None, **kw):
    abrir, buscar, pedidos = _rede(paginas, jsons)
    r = P.baixar_corpus(registros, str(tmp_path), abrir_url=abrir, buscar_json=buscar,
                        intervalo_por_host=0, **kw)
    return r, pedidos


def test_pdf_direto_e_baixado_e_conferido(tmp_path):
    reg = {"authors": "Silva, Ana; Souza, B.", "year": 2021, "title": "Mapas: uma revisão",
           "oa_url": "https://repo.org/a.pdf"}
    r, _ = _baixar(tmp_path, [reg], {"https://repo.org/a.pdf": PDF})
    assert r.contagem()[P.BAIXADO] == 1
    nome = r.resultados[0].arquivo
    assert nome == "Silva_2021_mapas-uma-revisao.pdf"
    assert (tmp_path / nome).read_bytes().startswith(b"%PDF-")


def test_pagina_html_nao_vira_pdf_falso(tmp_path):
    """O defeito do botão antigo: a página do editor era salva como .pdf e contada como sucesso."""
    reg = {"title": "T", "year": 2020, "authors": "A", "oa_url": "https://editor.com/artigo/1"}
    r, _ = _baixar(tmp_path, [reg], {"https://editor.com/artigo/1": b"<html><body>Artigo</body></html>"})
    assert r.resultados[0].situacao == P.SO_PAGINA
    assert r.resultados[0].link == "https://editor.com/artigo/1"
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".pdf")]


def test_segue_o_citation_pdf_url_da_pagina(tmp_path):
    pagina = (b'<html><head><meta name="citation_pdf_url" content="/content/1.full.pdf">'
              b'</head></html>')
    reg = {"title": "T", "year": 2020, "authors": "A", "oa_url": "https://editor.com/artigo/1"}
    r, pedidos = _baixar(tmp_path, [reg], {"https://editor.com/artigo/1": pagina,
                                           "https://editor.com/content/1.full.pdf": PDF})
    assert r.resultados[0].situacao == P.BAIXADO
    assert pedidos == ["https://editor.com/artigo/1", "https://editor.com/content/1.full.pdf"]


def test_corpus_do_scopus_sem_marcacao_de_acesso_aberto_usa_unpaywall(tmp_path):
    """Scopus/WoS não trazem is_oa: o botão antigo não baixava nada."""
    reg = {"title": "T", "year": 2019, "authors": "A", "doi": "10.1000/XYZ.1", "is_oa": False}
    uw = {"is_oa": True, "best_oa_location": {"url_for_pdf": "https://pmc.org/x.pdf",
                                              "url_for_landing_page": "https://pmc.org/x"}}
    r, _ = _baixar(tmp_path, [reg], {"https://pmc.org/x.pdf": PDF}, {"api.unpaywall.org": uw})
    assert r.resultados[0].situacao == P.BAIXADO


def test_arxiv_pelo_doi(tmp_path):
    reg = {"title": "Attention", "year": 2017, "authors": "Vaswani, A.",
           "doi": "https://doi.org/10.48550/arXiv.1706.03762"}
    r, pedidos = _baixar(tmp_path, [reg], {"https://arxiv.org/pdf/1706.03762": PDF})
    assert r.resultados[0].situacao == P.BAIXADO
    assert pedidos[0] == "https://arxiv.org/pdf/1706.03762"


def test_sem_acesso_aberto_e_sem_identificador_sao_separados(tmp_path):
    regs = [{"title": "Fechado", "year": 2020, "authors": "A", "doi": "10.1000/fechado"},
            {"title": "Nada", "year": 2020, "authors": "B"}]
    r, _ = _baixar(tmp_path, regs, {}, {"api.unpaywall.org": {"is_oa": False}})
    c = r.contagem()
    assert c[P.SEM_ACESSO_ABERTO] == 1 and c[P.SEM_IDENTIFICADOR] == 1
    assert r.resultados[0].link == "https://doi.org/10.1000/fechado"


def test_erro_de_rede_vira_falhou_e_nao_derruba_o_resto(tmp_path):
    regs = [{"title": "Ruim", "year": 2020, "authors": "A", "oa_url": "https://x.org/a.pdf"},
            {"title": "Bom", "year": 2021, "authors": "B", "oa_url": "https://y.org/b.pdf"}]
    r, _ = _baixar(tmp_path, regs, {"https://x.org/a.pdf": TimeoutError("timed out"),
                                    "https://y.org/b.pdf": PDF})
    assert [x.situacao for x in r.resultados] == [P.FALHOU, P.BAIXADO]
    assert "timed out" in r.resultados[0].detalhe


def test_segunda_rodada_nao_baixa_de_novo(tmp_path):
    reg = {"title": "T", "year": 2020, "authors": "A", "oa_url": "https://x.org/a.pdf"}
    _baixar(tmp_path, [reg], {"https://x.org/a.pdf": PDF})
    r, pedidos = _baixar(tmp_path, [reg], {"https://x.org/a.pdf": PDF})
    assert r.resultados[0].situacao == P.JA_EXISTIA and pedidos == []


def test_nomes_repetidos_nao_se_sobrescrevem(tmp_path):
    regs = [{"title": "Mesmo título", "year": 2020, "authors": "Silva, A.",
             "oa_url": f"https://x.org/{i}.pdf"} for i in range(3)]
    r, _ = _baixar(tmp_path, regs, {f"https://x.org/{i}.pdf": PDF for i in range(3)})
    nomes = sorted(x.arquivo for x in r.resultados)
    assert len(set(nomes)) == 3


def test_cancelar_para_e_nao_deixa_arquivo_pela_metade(tmp_path):
    cancelar = threading.Event()
    regs = [{"title": f"T{i}", "year": 2020, "authors": "A", "oa_url": f"https://x.org/{i}.pdf"}
            for i in range(20)]

    def progresso(n, total, resumo):
        if n >= 2:
            cancelar.set()
    r, _ = _baixar(tmp_path, regs, {f"https://x.org/{i}.pdf": PDF for i in range(20)},
                   cancelar=cancelar, ao_progresso=progresso, concorrencia=1)
    assert r.contagem()[P.CANCELADO] >= 15
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".part")]


def test_relatorio_csv_abre_no_excel_brasileiro(tmp_path):
    regs = [{"title": "Título; com ponto e vírgula", "year": 2020, "authors": "A",
             "doi": "10.1/x"}]
    r, _ = _baixar(tmp_path, regs, {}, {"api.unpaywall.org": {"is_oa": False}})
    texto = open(r.relatorio, encoding="utf-8-sig").read()
    assert texto.splitlines()[0].startswith("situacao;arquivo")
    assert '"Título; com ponto e vírgula"' in texto


def test_nome_de_arquivo_seguro_em_qualquer_sistema():
    usados = set()
    n = P.nome_arquivo({"authors": "Müller, Jörg", "year": "2019.0",
                        "title": 'A/B: "teste" <ação>?*|'}, usados)
    assert n == "Muller_2019_ab-teste-acao.pdf"
    assert P.nome_arquivo({}, usados) == "Sem-autor_sd_sem-titulo.pdf"


# ── Janela no app ───────────────────────────────────────────────────────────────────
@pytest.fixture
def app(monkeypatch, tmp_path):
    import main as M
    for nome in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(M.messagebox, nome, lambda *a, **k: None)
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


def _textos(widget):
    import customtkinter as ctk
    pilha, out = [widget], []
    while pilha:
        w = pilha.pop()
        if isinstance(w, (ctk.CTkLabel, ctk.CTkButton)):
            out.append(w.cget("text"))
        pilha.extend(w.winfo_children())
    return out


def test_janela_baixa_em_segundo_plano_e_mostra_a_trilha(app, monkeypatch, tmp_path):
    import pandas as pd
    import time as _t
    app._dataframe = pd.DataFrame([
        {"title": "A", "year": 2020, "authors": "Silva, A.", "oa_url": "https://x.org/a.pdf",
         "doi": ""},
        {"title": "B", "year": 2021, "authors": "Souza, B.", "oa_url": "", "doi": "10.1000/b"},
    ])
    threads_tk = []

    def falso(registros, pasta, *, cancelar, ao_progresso, **kw):
        import threading as th
        threads_tk.append(th.current_thread() is th.main_thread())
        resumo = P.Resumo(pasta=pasta, total=len(registros))
        resumo.resultados = [P.ResultadoRegistro(0, "A", "2020", "", P.BAIXADO, "a.pdf"),
                             P.ResultadoRegistro(1, "B", "2021", "10.1000/b",
                                                 P.SEM_ACESSO_ABERTO)]
        ao_progresso(2, 2, resumo)
        resumo.relatorio = P.escrever_relatorio(resumo)
        return resumo
    monkeypatch.setattr(P, "baixar_corpus", falso)
    app._download_oa_pdfs()
    app.update()
    dlg = app._pdf_janela
    assert "2 artigos" in " ".join(_textos(dlg))
    import os as _os
    destino = str(tmp_path / "pasta com espaço")
    # troca a pasta como o usuário faria pelo botão
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **k: destino)
    # escolhe a pasta clicando no botão
    import customtkinter as ctk
    pilha = [dlg]
    while pilha:
        w = pilha.pop()
        if isinstance(w, ctk.CTkButton) and w.cget("text").startswith("Escolher"):
            w._command()
        pilha.extend(w.winfo_children())
    app.after(20, app._pdf_iniciar)
    app.after(800, app.quit)
    app.mainloop()
    texto = " ".join(_textos(dlg))
    assert threads_tk == [False], "o download rodou na thread da interface"
    assert "Baixados: 1" in texto and "Sem versão aberta: 1" in texto
    assert "Abrir pasta" in texto and "Abrir relatório" in texto
    assert _os.path.exists(_os.path.join(destino, P.NOME_RELATORIO))


def test_corpus_vazio_avisa(app, monkeypatch):
    import main as M
    avisos = []
    monkeypatch.setattr(M.messagebox, "showinfo", lambda t, m, *a, **k: avisos.append(m))
    app._dataframe = None
    app._download_oa_pdfs()
    assert avisos and "corpus" in avisos[0]
