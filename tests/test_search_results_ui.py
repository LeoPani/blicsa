"""Fase 3 — tela de resultados no modelo Web of Science.

Cobre o que a paginação trouxe de novo para a UI: seleção que atravessa páginas, estados
vazio e de erro desenhados, chips de filtro, e as medições de layout nos três idiomas.

Fixtures adversariais: registro sem DOI, sem título, sem ano, sem abstract; página vazia;
página com erro; dois registros com o mesmo título e anos diferentes.
"""
import pytest

from core.browse import BrowseSession, Page
from core.sources import OpenAlexProvider


def _ctk():
    return pytest.importorskip("customtkinter")


def _view(ctk):
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    # Fora da tela em vez de withdraw(): janela retirada não realiza geometria.
    root.geometry("1200x800+3000+3000")
    from ui.search_feed import SearchFeedView
    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None)
    fv.pack(fill="both", expand=True)
    return root, fv


def _rec(i, *, ano=2020, doi=True, titulo=None, abstract="resumo", cit=3):
    return {"title": titulo or f"Artigo {i}", "year": ano, "authors": "Silva, J",
            "source": "Revista X", "citations": cit, "abstract": abstract,
            "doi": f"10.1/{i}" if doi else "", "language": "en"}


def _page(recs, total=1000, page=1, per_page=25, error=""):
    return Page(records=recs, total=total, page=page, per_page=per_page, error=error)


# ─────────────────── identidade estável do registro ───────────────────

def test_record_key_is_stable_and_survives_doi_prefixes():
    from ui.search_feed import record_key

    assert record_key({"doi": "10.1/x"}) == record_key({"doi": "https://doi.org/10.1/X"})
    assert record_key({"doi": " 10.1/x/ "}) == record_key({"doi": "10.1/x"})


def test_record_key_falls_back_to_title_and_year_without_doi():
    from ui.search_feed import record_key

    a = {"title": "Um  Estudo ", "year": 2020, "doi": ""}
    b = {"title": "um estudo", "year": 2020}
    c = {"title": "um estudo", "year": 2021}
    assert record_key(a) == record_key(b), "título normalizado é a mesma identidade"
    assert record_key(b) != record_key(c), "ano diferente é outro registro"


# ─────────────────── seleção atravessa páginas ───────────────────

def test_selection_survives_paging_back_and_forth():
    """Marcar na página 1, passear pela 2 e voltar: continua marcado.

    A seleção era por ÍNDICE na lista em memória. Com paginação, "índice 3" é um registro na
    página 1 e outro na página 2 — a marcação do usuário migraria para registros que ele
    nunca escolheu.
    """
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        p1 = _page([_rec(i) for i in range(5)], total=10, page=1, per_page=5)
        fv.load_browse_page(p1)
        root.update()

        fv._on_card_toggle(True, 2)          # marca o terceiro da página 1
        marcado = fv.records[2]["doi"]
        assert fv.selected_count() == 1

        p2 = _page([_rec(i) for i in range(5, 10)], total=10, page=2, per_page=5)
        fv.load_browse_page(p2)
        root.update()
        assert fv.selected_indices == set(), "nenhum da página 2 estava marcado"
        assert fv.selected_count() == 1, "a seleção da página 1 não pode sumir"

        fv.load_browse_page(p1)
        root.update()
        assert 2 in fv.selected_indices, "voltando à página 1, o registro segue marcado"
        assert fv.records[2]["doi"] == marcado
    finally:
        root.destroy()


def test_select_all_on_page_does_not_touch_other_pages():
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        fv.load_browse_page(_page([_rec(i) for i in range(5)], total=10, page=1, per_page=5))
        root.update()
        fv.select_all_on_page(True)
        assert fv.selected_count() == 5

        fv.load_browse_page(_page([_rec(i) for i in range(5, 10)], total=10, page=2, per_page=5))
        root.update()
        assert fv.selected_indices == set(), "a página 2 não foi selecionada"
        assert fv.selected_count() == 5, "a seleção da página 1 continua contando"

        fv.select_all_on_page(True)
        assert fv.selected_count() == 10

        fv.select_all_on_page(False)          # o outro lado da guarda
        assert fv.selected_count() == 5, "desmarcar a página 2 preserva a página 1"
    finally:
        root.destroy()


def test_records_without_doi_still_select_independently():
    """Sem DOI a identidade cai no título+ano — dois registros distintos seguem distintos."""
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        recs = [_rec(0, doi=False, titulo="Mesmo Título", ano=2020),
                _rec(1, doi=False, titulo="Mesmo Título", ano=2021)]
        fv.load_browse_page(_page(recs, total=2, per_page=25))
        root.update()
        fv._on_card_toggle(True, 0)
        assert fv.selected_count() == 1, "marcar um não pode marcar o outro"
        assert fv.selected_indices == {0}
    finally:
        root.destroy()


# ─────────────────── estados vazio e de erro ───────────────────

def test_empty_page_renders_the_empty_state_with_a_hint():
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        fv.load_browse_page(_page([], total=0))
        root.update()
        assert fv.has_empty_state(), "página sem resultados deve desenhar o estado vazio"
        assert not fv.has_error_state()
        assert fv.records == [] and fv.selected_indices == set()
    finally:
        root.destroy()


def test_page_with_error_renders_the_error_state_with_retry():
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        chamou = {}
        fv.load_browse_page(_page([], total=0, error="rede caiu"))
        root.update()
        assert fv.has_error_state(), "erro deve desenhar o estado de erro"
        assert not fv.has_empty_state(), "erro não é o mesmo que vazio"

        fv.show_error_state("outro erro", on_retry=lambda: chamou.setdefault("sim", True))
        root.update()
        fv._retry_btn.invoke()
        assert chamou.get("sim"), "o botão de tentar de novo tem de chamar o callback"
    finally:
        root.destroy()


def test_a_page_with_results_renders_neither_empty_nor_error():
    """O outro lado da guarda: com resultados, nenhum dos dois estados aparece."""
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        fv.load_browse_page(_page([_rec(i) for i in range(3)], total=3))
        root.update()
        assert not fv.has_empty_state() and not fv.has_error_state()
        assert len(fv.records) == 3
    finally:
        root.destroy()


def test_error_after_results_replaces_the_list_and_back_again():
    """Alternar resultado → erro → resultado deixa a tela consistente nas duas direções."""
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        fv.load_browse_page(_page([_rec(i) for i in range(3)], total=3))
        root.update()
        fv.load_browse_page(_page([], total=0, error="timeout"))
        root.update()
        assert fv.has_error_state() and fv.records == []

        fv.load_browse_page(_page([_rec(i) for i in range(3)], total=3))
        root.update()
        assert len(fv.records) == 3
    finally:
        root.destroy()


# ─────────────────── chips de filtro ───────────────────

def test_chips_reflect_active_facets_and_removal_restores_the_query():
    from core.browse import FacetValue
    from core.browse import Facet

    s = BrowseSession(OpenAlexProvider(), "x")
    s.facets = {"type": Facet(field="type", values=[FacetValue("article", "Artigo", 10)])}
    assert s.chips() == []

    s.toggle_facet("type", "article")
    assert s.chips() == [{"field": "type", "key": "article", "label": "Artigo"}]

    s.clear_facet("type", "article")
    assert s.chips() == [], "remover o chip limpa a faceta"


def test_multiple_chips_from_the_same_category():
    s = BrowseSession(OpenAlexProvider(), "x")
    s.toggle_facet("type", "article")
    s.toggle_facet("type", "book")
    assert len(s.chips()) == 2
    s.clear_facet("type")                    # sem valor: limpa a categoria inteira
    assert s.chips() == []


# ─────────────────── layout dos cards ───────────────────

@pytest.mark.parametrize("variante", [
    {"abstract": "", "ano": 0, "cit": 0, "doi": False},       # o registro mais pobre
    {"abstract": "resumo curto"},
    {"abstract": "Resumo " * 40, "cit": 900},
])
def test_card_height_stays_within_one_and_a_half_of_its_content(variante):
    """Altura do card ≤ 1,5× a altura do conteúdo, com e sem abstract e badges."""
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        from ui.search_feed import ArticleCard

        card = ArticleCard(fv.feed, _rec(0, **variante), lambda *a, **k: None, 0)
        card.pack(fill="x")
        root.update()

        conteudo = sum(w.winfo_reqheight() for w in card.winfo_children()
                       if w.winfo_manager() == "grid" and w.grid_info().get("column") == 2)
        conteudo += 24                        # respiro de topo e base do card
        razao = card.winfo_reqheight() / max(conteudo, 1)
        assert razao <= 1.5, (
            f"card com {card.winfo_reqheight()}px para {conteudo}px de conteúdo "
            f"(razão {razao:.2f}, teto 1.5) — variante {variante}")
    finally:
        root.destroy()


def test_cards_share_the_same_origin_x_regardless_of_content():
    """Dois eixos + origem: conteúdos bem diferentes não podem desalinhar a coluna."""
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        recs = [_rec(0, titulo="Curto", abstract=""),
                _rec(1, titulo="Um título consideravelmente mais longo que o primeiro",
                     abstract="Resumo " * 30),
                _rec(2, titulo="Médio", abstract="curto", doi=False, ano=0)]
        fv.load_browse_page(_page(recs, total=3))
        root.update()

        xs = []
        for card in fv.cards:
            titulos = [w for w in card.winfo_children()
                       if isinstance(w, ctk.CTkLabel) and w.winfo_manager() == "grid"
                       and w.grid_info().get("row") == 1]
            assert titulos, "card sem label de título"
            xs.append(titulos[0].winfo_x())
        assert max(xs) - min(xs) == 0, f"títulos desalinhados entre cards: {xs}"
    finally:
        root.destroy()


def test_source_name_truncation_never_leaves_a_dangling_paren():
    from ui.search_feed import truncate_source_name as tr

    longo = tr("LA Referencia (Red Federal de Repositorios Institucionales)")
    assert longo.count("(") == longo.count(")"), f"parêntese pendurado: {longo!r}"
    assert longo.endswith("…")
    assert tr("Nature") == "Nature", "nome curto não é mexido"


# ─────────────────── Blink drawer preserva o estado ───────────────────

def test_blink_drawer_preserves_selection_page_and_scroll():
    """Abrir e fechar o Blink não pode custar seleção, página nem posição de rolagem."""
    ctk = _ctk()
    root, fv = _view(ctk)
    try:
        fv.load_browse_page(_page([_rec(i) for i in range(25)], total=1000, page=3))
        root.update()
        fv.select_all_on_page(True)

        canvas = getattr(fv.feed, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0.5)
            root.update()
        scroll_antes = canvas.yview() if canvas is not None else None
        cards_antes = list(fv.cards)
        pagina_antes = fv.browse_page
        sel_antes = fv.selected_count()

        fv.open_blink_drawer()
        root.update()
        assert fv.blink_drawer_open()
        assert fv.cards == cards_antes, "os cards foram reconstruídos"
        assert fv.selected_count() == sel_antes and fv.browse_page == pagina_antes
        if canvas is not None:
            assert canvas.yview() == scroll_antes, "a rolagem se moveu"

        fv.close_blink_drawer()
        root.update()
        assert not fv.blink_drawer_open()
        assert fv.cards == cards_antes and fv.selected_count() == sel_antes
        assert fv.browse_page == pagina_antes
        if canvas is not None:
            assert canvas.yview() == scroll_antes
    finally:
        root.destroy()


def test_blink_receives_the_records_on_screen_not_the_old_corpus():
    """O contexto RAG do Blink é montado com os resultados EM TELA."""
    ctk = _ctk()
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    root.geometry("1000x700+3000+3000")
    recebido = {}
    from ui.search_feed import SearchFeedView

    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None,
                        lambda recs, sel: recebido.update(records=recs, sel=set(sel)))
    fv.pack(fill="both", expand=True)
    try:
        pagina = [_rec(i, titulo=f"Na tela {i}") for i in range(4)]
        fv.load_browse_page(_page(pagina, total=1000, page=2))
        root.update()
        fv._trigger_ai()

        assert recebido.get("records"), "o Blink não recebeu registro nenhum"
        titulos = [r["title"] for r in recebido["records"]]
        assert titulos == [r["title"] for r in pagina], (
            f"o Blink recebeu outra coisa que não a página em tela: {titulos[:3]}")
    finally:
        root.destroy()


# ─────────────────── rótulos novos nos 3 idiomas ───────────────────

@pytest.mark.parametrize("lang", ["pt_BR", "en", "fr"])
def test_new_browse_labels_fit_their_widgets(lang):
    """Nenhum rótulo novo estoura o widget, em nenhum idioma.

    Método: `_text_label` interno do CTkButton (o que o Tk desenha e o que clipa), com a
    fonte real do widget. Reproduzível por `pytest tests/test_search_results_ui.py -k fit`.
    """
    ctk = _ctk()
    from core.i18n import load_locales, t

    load_locales(lang)
    root, fv = _view(ctk)
    try:
        LARGURA = 160
        apertados = []
        for chave in ("browse.retry", "browse.select_page", "browse.clear_selection"):
            # No `root`, não no feed: o SearchFeedView é gerenciado por grid.
            b = ctk.CTkButton(root, text=t(chave), width=LARGURA, height=30)
            b.place(x=0, y=0)
            root.update()
            lbl = getattr(b, "_text_label", None)
            pede = lbl.winfo_reqwidth() if lbl is not None else 0
            folga = b.winfo_width() - pede
            if folga < 8:
                apertados.append((chave, t(chave), pede, b.winfo_width(), folga))
        assert not apertados, f"[{lang}] rótulo sem respiro: {apertados}"
    finally:
        from core.i18n import load_locales as _ll
        _ll("pt_BR")
        root.destroy()
