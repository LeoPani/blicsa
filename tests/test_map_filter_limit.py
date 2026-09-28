"""Frequência e quantidade de nós são limites distintos na configuração do mapa."""

from types import SimpleNamespace


def test_map_filter_controls_reach_100_and_explain_which_limit_they_set(monkeypatch):
    import main

    class Widget:
        def pack(self, *args, **kwargs):
            return None

    class MaxNodesEntryCaptured(Exception):
        def __init__(self, options):
            self.options = options

    labels = []
    sliders = []
    tooltips = []

    def capture_label(*args, **kwargs):
        labels.append(kwargs.get("text"))
        return Widget()

    monkeypatch.setattr(main.ctk, "CTkLabel", capture_label)
    monkeypatch.setattr(main.ctk, "CTkComboBox", lambda *args, **kwargs: Widget())
    monkeypatch.setattr(main.ctk, "CTkCheckBox", lambda *args, **kwargs: Widget())
    monkeypatch.setattr(main.ctk, "CTkFrame", lambda *args, **kwargs: Widget())
    monkeypatch.setattr(main.ctk, "CTkFont", lambda *args, **kwargs: object())
    monkeypatch.setattr(main.ctk, "StringVar", lambda *args, **kwargs: object())
    monkeypatch.setattr(main, "HoverTooltip",
                        lambda widget, text: tooltips.append(text))

    def capture_slider(*args, **kwargs):
        sliders.append(kwargs)
        return Widget()

    def capture_entry(*args, **kwargs):
        raise MaxNodesEntryCaptured(kwargs)

    monkeypatch.setattr(main.ctk, "CTkSlider", capture_slider)
    monkeypatch.setattr(main.ctk, "CTkEntry", capture_entry)
    app = SimpleNamespace(
        _map_type_var=object(), _field_var=object(), _counting_var=object(),
        _assoc_var=object(), _min_occ_var=object(), _on_occ_change=lambda val: None,
        _binary_count_var=object(), _max_nodes_var=object(),
        _update_thresh_label=lambda: None, _open_term_review=lambda: None,
        _btn=lambda *args, **kwargs: Widget(),
    )

    try:
        main.BlicsaApp._build_config_widgets(app, Widget())
    except MaxNodesEntryCaptured as captured:
        entry = captured.options
    else:
        raise AssertionError("campo Máx. Nós não foi criado")

    slider = sliders[0]
    assert (slider["from_"], slider["to"], slider["number_of_steps"]) == (1, 100, 99)
    assert slider["variable"] is app._min_occ_var
    assert entry["textvariable"] is app._max_nodes_var
    assert main.t("map.filter_min_frequency_label") in labels
    assert main.t("map.filter_max_nodes_label") in labels
    assert main.t("map.filter_min_frequency_help") in tooltips
    assert main.t("map.filter_max_nodes_help") in tooltips


def test_new_map_starts_with_100_nodes_instead_of_unlimited(monkeypatch):
    import main

    class Variable:
        def __init__(self, value=None):
            self.value = value

        def get(self):
            return self.value

        def trace_add(self, *args):
            return None

    # Usa o construtor real e substitui somente as partes do Tk que exigem display.
    # Também evita abrir portas ou carregar dados do projeto.
    monkeypatch.setattr(main.ctk.CTk, "__init__", lambda self: None)
    for method in ("title", "geometry", "minsize", "resizable", "configure", "protocol"):
        monkeypatch.setattr(main.BlicsaApp, method, lambda *args, **kwargs: None)
    for variable in ("StringVar", "IntVar", "BooleanVar", "DoubleVar"):
        monkeypatch.setattr(main.ctk, variable, Variable)
    for method in ("_start_local_server", "_start_bridge", "_build_layout",
                   "_attach_log_handler", "_setup_dnd", "_setup_shortcuts"):
        monkeypatch.setattr(main.BlicsaApp, method, lambda self: None)

    app = main.BlicsaApp()
    assert app._max_nodes_var.get() == "100"
