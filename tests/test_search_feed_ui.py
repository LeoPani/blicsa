"""
Teste de UI do SearchFeedView: regressão do slider de anos.
Requer Tk/CustomTkinter com display; se indisponível (CI headless), é pulado.
"""
import pytest


def _make_view():
    ctk = pytest.importorskip("customtkinter")
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    root.withdraw()
    from ui.search_feed import SearchFeedView
    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None)
    fv.pack()
    return root, fv


def _rec(i, year):
    return {"title": f"Artigo {i}", "year": year, "authors": "Autor", "source": "Rev",
            "citations": 0, "abstract": "resumo", "doi": f"10.1/{i}", "language": "en"}


def test_single_year_does_not_crash_and_hides_slider():
    """BUG (RELATORIO-BUGS-E-PERCEPCAO): todos os resultados com o MESMO ano
    causava ZeroDivisionError no CTkSlider (number_of_steps=0)."""
    root, fv = _make_view()
    try:
        recs = [_rec(i, 2020) for i in range(5)]  # ano único
        fv.load_results(recs, "Encontrados 5")     # não deve levantar
        root.update()
        assert not hasattr(fv, "year_slider"), "slider deveria estar oculto para ano único"
    finally:
        root.destroy()


def test_blink_drawer_preserves_feed_state():
    """BUG-B: abrir/fechar o drawer do Blink não pode destruir o feed nem o estado."""
    root, fv = _make_view()
    try:
        recs = [_rec(i, 2015 + (i % 5)) for i in range(50)]
        fv.load_results(recs, "Encontrados 50")
        root.update()
        cards_before = len(fv.cards)
        sel_before = set(fv.selected_indices)
        trail_before = fv.trail_lbl.cget("text")
        records_before = list(fv.records)

        out = fv.open_blink_drawer(); root.update()
        assert fv.blink_drawer_open(), "drawer deveria estar aberto"
        assert out is not None
        # feed intacto com o drawer aberto
        assert len(fv.cards) == cards_before
        assert set(fv.selected_indices) == sel_before
        assert fv.trail_lbl.cget("text") == trail_before
        assert list(fv.records) == records_before

        fv.close_blink_drawer(); root.update()
        assert not fv.blink_drawer_open(), "drawer deveria estar fechado"
        # feed continua intacto após fechar
        assert len(fv.cards) == cards_before
        assert set(fv.selected_indices) == sel_before
        assert fv.trail_lbl.cget("text") == trail_before
        assert list(fv.records) == records_before
    finally:
        root.destroy()


def test_multi_year_builds_slider():
    root, fv = _make_view()
    try:
        recs = [_rec(i, 2015 + i) for i in range(5)]  # anos variados
        fv.load_results(recs, "Encontrados 5")
        root.update()
        assert hasattr(fv, "year_slider"), "slider deveria existir com anos variados"
    finally:
        root.destroy()
