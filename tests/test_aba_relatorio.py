"""A aba de Relatório: o que ela mostra, e o que ela se recusa a mostrar.

Ela não é a aba de Histórico com outro nome. O Histórico lista uma linha por evento, crua;
esta SOMA — declaração de uso de IA, cadeia de busca, fluxo de registros, consumo e
cobertura — e é a única que exporta.

Dois riscos que estes testes cobrem:

* **Sem projeto, o relatório seria um formulário em branco com cara de documento pronto.**
  Zeros em toda parte e uma declaração dizendo que não houve IA — quando na verdade não há
  onde ter havido. A aba tem de dizer que falta o projeto.
* **A declaração precisa ser copiável.** Ela existe para ir colada num artigo, e de um
  `CTkLabel` não se seleciona texto.
"""

from __future__ import annotations

import pytest

from core.uso_de_ia import ACAO, evento


@pytest.fixture
def projetos(tmp_path, monkeypatch):
    """Pasta de projetos isolada: a suíte não pode escrever em `~/Blicsa/projects`."""
    from core import project

    monkeypatch.setattr(project, "PROJECTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def app(monkeypatch, projetos):
    monkeypatch.setenv("AI_API_KEY", "gsk_" + "T3st3Fals4" * 5)
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.geometry("1380x840")
    janela.withdraw()
    janela._dispensa_boas_vindas()
    janela.update()
    # `update_idletasks` além do `update`: sem ele a passada de geometria não terminou, e
    # os `winfo_rooty` do teste da barra lateral saem todos iguais — dois widgets em linhas
    # diferentes pareceriam empilhados um sobre o outro.
    janela.update_idletasks()
    yield janela
    janela.destroy()


@pytest.fixture
def com_projeto(app, projetos):
    """App com um projeto que já viveu: uma busca, uma importação e quatro usos de IA."""
    from core import project

    slug = project.create_project("Bibliometria de ML", projects_dir=projetos)
    project.append_backlog(slug, "search", {
        "provider": "openalex", "query": 'TITLE-ABS-KEY("ml")',
        "query_interpretada": '("machine learning" OR "deep learning") AND bibliometric',
        "filters": {"year_start": 2018}, "encontrados": 4722, "baixados": 1000,
        "stop_reason": "limite do usuário"}, projects_dir=projetos)
    project.append_backlog(slug, "import", {"registros": 1000, "total_corpus": 1000},
                           projects_dir=projetos)
    for ponto, uso in (("assistente_de_busca", {"prompt_tokens": 820,
                                                "completion_tokens": 410,
                                                "total_tokens": 1230}),
                       ("rotulos_de_cluster", None),
                       ("blink_chat", None),
                       ("insights_do_corpus", None)):
        project.append_backlog(slug, ACAO,
                               evento(ponto, "openai/gpt-oss-120b", "Groq", uso=uso),
                               projects_dir=projetos)

    app._active_project = slug
    app._active_project_name = "Bibliometria de ML"
    app._switch_tab("relatorio")
    app.update()
    app.update_idletasks()
    return app


def _textos(widget) -> list:
    """Todo texto visível abaixo de um widget, achatado. É o que o usuário lê."""
    import customtkinter as ctk

    achados = []
    for filho in widget.winfo_children():
        if isinstance(filho, ctk.CTkTextbox):
            achados.append(filho.get("1.0", "end").strip())
        elif isinstance(filho, ctk.CTkLabel):
            texto = filho.cget("text")
            if texto:
                achados.append(str(texto))
        achados += _textos(filho)
    return achados


# ── Sem projeto ─────────────────────────────────────────────────────────────────

def test_sem_projeto_a_aba_pede_o_projeto_em_vez_de_mostrar_zeros(app):
    """Um relatório todo zerado tem cara de documento pronto — e seria mentira."""
    from core.i18n import t

    app._switch_tab("relatorio")
    app.update()

    textos = _textos(app._relatorio_frame)
    assert t("project.none_warning") in textos
    assert t("relatorio.sec_declaracao") not in textos
    assert app._relatorio_sub_lbl.cget("text") == ""


def test_sem_projeto_exportar_avisa_em_vez_de_gravar_arquivo_vazio(app, monkeypatch):
    avisos = []
    monkeypatch.setattr("main.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr("main.filedialog.asksaveasfilename",
                        lambda **k: pytest.fail("não podia chegar ao seletor de arquivo"))

    app._exportar_relatorio("md")

    assert avisos, "exportou sem projeto e sem avisar"


# ── Com projeto ─────────────────────────────────────────────────────────────────

def test_a_declaracao_aparece_na_tela(com_projeto):
    textos = " ".join(_textos(com_projeto._relatorio_frame))
    assert "openai/gpt-oss-120b" in textos
    assert "incorporada ao resultado" in textos


def test_a_declaracao_fica_numa_caixa_de_onde_da_para_selecionar(com_projeto):
    """De um `CTkLabel` não se copia nada, e a declaração existe para ser colada."""
    import customtkinter as ctk

    caixa = com_projeto._relatorio_caixa_declaracao
    assert isinstance(caixa, ctk.CTkTextbox)
    assert "Blicsa" in caixa.get("1.0", "end")


def test_o_botao_copiar_poe_a_declaracao_na_area_de_transferencia(com_projeto):
    com_projeto._copiar_declaracao_de_ia()
    com_projeto.update()

    assert "openai/gpt-oss-120b" in com_projeto.clipboard_get()


def test_os_pontos_de_ia_aparecem_do_mais_grave_para_o_menos(com_projeto):
    """Ordenar por número de chamadas poria o chat acima da nomeação de clusters, que vai
    para a figura publicada. Numa tabela de declaração de uso, a ordem é a informação."""
    textos = _textos(com_projeto._relatorio_frame)
    posicao = {nome: textos.index(nome) for nome in
               ("Nomeação de clusters", "Insights do corpus", "Chat do Blink")}
    assert posicao["Nomeação de clusters"] < posicao["Insights do corpus"]
    assert posicao["Insights do corpus"] < posicao["Chat do Blink"]


def test_a_string_que_foi_para_a_api_aparece_na_cadeia_de_busca(com_projeto):
    textos = _textos(com_projeto._relatorio_frame)
    assert '("machine learning" OR "deep learning") AND bibliometric' in textos


def test_o_subtitulo_conta_ia_buscas_e_corpus(com_projeto):
    assert "4" in com_projeto._relatorio_sub_lbl.cget("text")


def test_o_relatorio_e_remontado_a_cada_abertura(com_projeto, projetos):
    """Guardado em cache, mostraria um número que o projeto já não tem — e num documento de
    método isso é pior do que não ter o documento."""
    from core import project

    project.append_backlog(com_projeto._active_project, ACAO,
                           evento("blink_chat", "m", "Groq"), projects_dir=projetos)

    com_projeto._switch_tab("hist")
    com_projeto._switch_tab("relatorio")
    com_projeto.update()

    assert com_projeto._relatorio_atual()["ia"]["resumo"]["chamadas"] == 5


# ── Exportação ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("formato", ["md", "json"])
def test_exporta_e_registra_no_backlog(com_projeto, tmp_path, monkeypatch, formato,
                                       projetos):
    from core.project import load_backlog

    destino = tmp_path / f"relatorio.{formato}"
    monkeypatch.setattr("main.filedialog.asksaveasfilename", lambda **k: str(destino))

    com_projeto._exportar_relatorio(formato)

    assert destino.exists() and destino.stat().st_size > 200
    acoes = [e for e in load_backlog(com_projeto._active_project, projects_dir=projetos)
             if e["action"] == "export"]
    assert acoes and acoes[-1]["detail"]["formato"] == f"relatorio_{formato}"


def test_cancelar_o_seletor_nao_grava_nada(com_projeto, monkeypatch, projetos):
    from core.project import load_backlog

    monkeypatch.setattr("main.filedialog.asksaveasfilename", lambda **k: "")
    antes = len(load_backlog(com_projeto._active_project, projects_dir=projetos))

    com_projeto._exportar_relatorio("md")

    assert len(load_backlog(com_projeto._active_project, projects_dir=projetos)) == antes


def test_sem_o_extra_de_pdf_o_aviso_vem_ANTES_do_seletor(com_projeto, monkeypatch):
    """Pedir pasta e nome para só então dizer que não dá é fazer o usuário escolher à toa."""
    import core.relatorio_pdf as pdf

    monkeypatch.setattr(pdf, "disponivel", lambda: False)
    monkeypatch.setattr("main.filedialog.asksaveasfilename",
                        lambda **k: pytest.fail("chegou ao seletor sem o extra instalado"))
    avisos = []
    monkeypatch.setattr("main.messagebox.showwarning", lambda *a, **k: avisos.append(a))

    com_projeto._exportar_relatorio("pdf")

    assert avisos and "requirements-pdf.txt" in " ".join(str(a) for a in avisos[0])


# ── A aba nova não pode desarrumar a barra lateral ──────────────────────────────

def test_a_aba_de_relatorio_esta_na_navegacao(app):
    from core.i18n import t

    assert "relatorio" in app._nav_btns
    assert t("nav.relatorio") in app._nav_btns["relatorio"].cget("text")


def test_o_rodape_da_barra_nao_divide_linha_com_nenhum_botao(app):
    """As linhas do rodapé eram números FIXOS, escolhidos quando havia dez abas.

    Duas consequências: o badge do corpus já dividia a linha 10 com o último botão, e a aba
    de Relatório poria o décimo primeiro botão exatamente na linha que estica. Agora as
    linhas do rodapé são derivadas de `len(itens_de_navegacao)`.

    Medido em LINHA DO GRID, e não em pixels como os testes de `test_layout_blink.py`: o
    defeito aqui é estrutural (dois widgets no mesmo endereço), a barra lateral não é
    mapeada numa janela retirada da tela, e `winfo_rooty` devolveria o mesmo valor para
    todo mundo — o teste passaria ou falharia por motivo nenhum.
    """
    linhas_de_botao = {b.grid_info()["row"] for b in app._nav_btns.values()}
    rodape = {"badge": app._corpus_badge, "ajustes": app._settings_btn,
              "status": app._status_square, "sobre": app._about_btn}

    for nome, widget in rodape.items():
        linha = widget.grid_info()["row"]
        assert linha not in linhas_de_botao, f"{nome} divide a linha {linha} com um botão"
        assert linha > max(linhas_de_botao), f"{nome} está acima do último botão"

    assert app._corpus_badge.grid_info()["row"] < app._settings_btn.grid_info()["row"]
    assert app._settings_btn.grid_info()["row"] < app._about_btn.grid_info()["row"]


def test_uma_aba_nova_empurra_o_rodape_sozinha(app):
    """A guarda de verdade: o rodapé tem de acompanhar a contagem, não um número escrito.

    Se alguém acrescentar a décima segunda aba e o rodapé continuar onde estava, este teste
    cai — que é o que faltou quando a décima primeira entrou.
    """
    linha_do_ultimo_botao = max(b.grid_info()["row"] for b in app._nav_btns.values())

    assert linha_do_ultimo_botao == len(app._nav_btns), (
        "os botões deixaram de ocupar uma linha cada, a partir da 1")
    assert app._corpus_badge.grid_info()["row"] == linha_do_ultimo_botao + 2, (
        "o rodapé descolou da contagem de abas")
