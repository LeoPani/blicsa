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


def test_multi_year_builds_slider():
    root, fv = _make_view()
    try:
        recs = [_rec(i, 2015 + i) for i in range(5)]  # anos variados
        fv.load_results(recs, "Encontrados 5")
        root.update()
        assert hasattr(fv, "year_slider"), "slider deveria existir com anos variados"
    finally:
        root.destroy()
