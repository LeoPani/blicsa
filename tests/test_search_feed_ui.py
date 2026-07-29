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


def test_article_card_no_fixed_whitespace():
    """BUG-C: card não pode ter altura fixa gigante. Qualquer CTkFrame criado sem `height`
    assume a default de 200px do CustomTkinter; um frame VAZIO (sem filhos) não encolhe e
    vira vão branco. São três no card: left_bar, a faixa de badges e a faixa de ações.

    O caso que escapou antes: o registro do teste tinha year/language (badges) e doi (botão),
    então as duas faixas tinham filhos e encolhiam. Um registro SEM badge e SEM botão —
    comum no feed real, p.ex. Open Access (não ganha "Abrir DOI") ou sem ano — somava
    200px + 200px de branco. Por isso o card mínimo cobre agora o registro PELADO."""
    ctk = pytest.importorskip("customtkinter")
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    root.withdraw()
    from ui.search_feed import ArticleCard
    frame = ctk.CTkFrame(root); frame.pack(fill="both", expand=True); frame.grid_columnconfigure(0, weight=1)

    def height(rec):
        c = ArticleCard(frame, rec, lambda *a, **k: None, 0)
        c.grid(row=0, column=0, sticky="ew"); root.update_idletasks()
        h = c.winfo_reqheight(); c.destroy(); return h

    # Registro PELADO: sem badge nenhum (sem ano/citações/OA/idioma) e sem botão (sem DOI).
    bare = {"title": "T", "year": 0, "authors": "", "source": "",
            "citations": 0, "abstract": "", "doi": "", "language": ""}
    h_bare = height(bare)
    # Com badges e botão — as faixas ganham filhos.
    h_badges = height({**bare, "year": 2024, "language": "en", "doi": "10/1", "citations": 9})
    # Open Access: tem badge, mas NÃO ganha o botão "Abrir DOI" (faixa de ações vazia).
    h_oa = height({**bare, "year": 2024, "is_oa": True, "oa_url": "u", "doi": "10/1"})
    h_abs = height({**bare, "authors": "Autor", "source": "Rev", "abstract": "Resumo " * 40})
    try:
        for nome, h in (("pelado", h_bare), ("com badges", h_badges), ("open access", h_oa)):
            assert h < 160, f"card {nome} alto demais ({h}px) — CTkFrame vazio reservando 200px?"
        assert h_abs > h_bare, "card com abstract deveria ser mais alto (altura segue conteúdo)"
        # As três variantes mínimas têm o MESMO conteúdo de uma linha: não podem divergir
        # em centenas de px (era 454 vs 254 conforme o registro tivesse badge/botão).
        assert max(h_bare, h_badges, h_oa) - min(h_bare, h_badges, h_oa) < 60, (
            f"alturas inconsistentes entre variantes: pelado={h_bare} "
            f"badges={h_badges} oa={h_oa}")
    finally:
        root.destroy()


def test_truncate_source_name_never_leaves_a_dangling_paren():
    """BUG-C (sidebar): "LA Referencia (Red F (305)" — o nome era cortado no meio e a
    contagem colava logo depois, parecendo parêntese partido. O corte agora usa
    reticências e não deixa parêntese aberto do nome pendurado antes da contagem."""
    from ui.search_feed import truncate_source_name as tr

    curto = tr("Nature")
    assert curto == "Nature", "nome curto não deve ser mexido"

    longo = tr("LA Referencia (Red Federal de Repositorios Institucionales)")
    assert longo.endswith("…"), f"deveria truncar com reticências: {longo!r}"
    assert longo.count("(") == longo.count(")"), (
        f"parêntese aberto pendurado antes da contagem: {longo!r}")
    assert "Red F" not in longo, f"cortou no meio do parêntese: {longo!r}"

    # Sem parênteses, trunca normalmente e continua dentro do limite da sidebar.
    simples = tr("Journal of Cleaner Production")
    assert simples.endswith("…") and len(simples) <= 22

    # Nome que é só um parêntese longo não pode virar string vazia.
    assert tr("(" + "x" * 40 + ")").strip("…") != ""


def test_refilter_maps_sidebar_to_server_filters():
    """Mudança 3: os filtros da sidebar (ano/OA/idioma/tipo) viram filtros server-side
    e disparam on_refilter (re-consulta na fonte, não só client-side)."""
    ctk = pytest.importorskip("customtkinter")
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    root.withdraw()
    from ui.search_feed import SearchFeedView
    captured = {}
    fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None,
                        on_refilter=lambda sf: captured.update(sf=sf))
    fv.pack()
    try:
        recs = [_rec(i, 2015 + (i % 6)) for i in range(20)]
        fv.load_results(recs, "Encontrados 20")
        root.update()
        btns = [w for w in fv.sidebar.winfo_children()
                if isinstance(w, ctk.CTkButton) and "Rebuscar" in (w.cget("text") or "")]
        assert len(btns) == 1, "botão 'Rebuscar na fonte' deveria existir"
        fv.year_slider.set(2018)
        fv.oa_var.set(True)
        fv.lang_var.set("pt")
        btns[0].invoke()
        root.update()
        assert captured["sf"] == {"year_start": 2018, "is_oa": True, "language": "pt"}
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
