"""Passo 7 — filtro do DedupPreviewDialog.

Checkbox por par: marcado = remove. Pares "autor+ano" são baixa confiança e
começam DESMARCADOS. "Aplicar" entrega só os marcados + a contagem de
desmarcados. Requer Tk/CustomTkinter com display; pulado em CI headless.
"""
import pandas as pd
import pytest


def _make_dialog(dupes):
    ctk = pytest.importorskip("customtkinter")
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    root.withdraw()
    from ui.components import DedupPreviewDialog

    df = pd.DataFrame({"title": [f"Artigo {i}" for i in range(6)]})
    captured = {}

    def on_apply(applied, desmarcados):
        captured["applied"] = applied
        captured["desmarcados"] = desmarcados

    dlg = DedupPreviewDialog(root, df, dupes, on_apply)
    return root, dlg, captured


# Pares: DOI (alta conf.), Autor+Ano (baixa conf.), Título (alta conf.)
DUPES = [
    (0, 1, "DOI exato"),
    (2, 3, "Autor+Ano (fuzzy)"),
    (4, 5, "Título 0.95"),
]


def test_low_confidence_pairs_start_unchecked():
    root, dlg, _ = _make_dialog(DUPES)
    try:
        selected = dlg.selected_pairs()
        reasons = {r for _, _, r in selected}
        # o par autor+ano NÃO entra por padrão; os outros dois sim
        assert (2, 3, "Autor+Ano (fuzzy)") not in selected
        assert (0, 1, "DOI exato") in selected
        assert (4, 5, "Título 0.95") in selected
        assert len(selected) == 2
    finally:
        root.destroy()


def test_apply_returns_only_checked_and_desmarcados_count():
    root, dlg, captured = _make_dialog(DUPES)
    try:
        dlg._apply()  # aplica com os defaults
        assert len(captured["applied"]) == 2
        assert captured["desmarcados"] == 1  # o par autor+ano ficou de fora
    finally:
        root.destroy()


def test_checking_low_confidence_includes_it():
    root, dlg, captured = _make_dialog(DUPES)
    try:
        # marca manualmente o par de baixa confiança
        for var, pair in dlg._pair_vars:
            if pair == (2, 3, "Autor+Ano (fuzzy)"):
                var.set(True)
        dlg._apply()
        assert len(captured["applied"]) == 3
        assert captured["desmarcados"] == 0
    finally:
        root.destroy()
