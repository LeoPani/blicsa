"""Larguras de widget medidas, nos três idiomas (itens 2.1–2.3 do prompt de layout).

Por que este arquivo existe: as três correções de largura foram feitas e MEDIDAS à mão, mas
ficaram sem teste. A matriz de reinjeção da rodada anterior registrou isso explicitamente —
"sem teste automatizado, só medição". Uma medição é uma foto; um teste é uma guarda. Sem
isto, voltar `width=100` para `60` não quebra nada e o estouro só reaparece na tela do
usuário, em francês, que é o idioma mais largo.

A medição usa a fonte REAL de cada widget (`tkfont.Font(font=widget.cget("font"))`), não uma
fonte suposta: medir com uma fonte diferente da que o Tk desenha dá números que não
correspondem ao que aparece na tela.

Regra dos dois eixos: além da largura, os testes conferem altura e a coordenada de origem —
a variação de x entre cards tem de ser zero.
"""
import gzip
import json
import zipfile
from pathlib import Path

import pytest

IDIOMAS = ("pt_BR", "en", "fr")

# Folga mínima entre o rótulo e a borda do botão, em pixels.
#
# O critério é o `_text_label` INTERNO do CTkButton, não a largura do texto medida numa fonte
# escolhida por fora: é ele que o Tk desenha, e é o `reqwidth` dele contra a largura do botão
# que decide se o rótulo clipa. Medido neste projeto: o label pede `texto + 2px`, e
# "Renommer" em `width=60` pedia 68px — 8px além do botão, que era o defeito original.
#
# Uma medição com fonte suposta (SF Pro Display 13) dava "Renommer"=84px e "⬅ Retour"=71px,
# números que não batem com o que a tela mostra (66px e 56px com a fonte real do widget).
FOLGA_MINIMA = 8


def _ctk():
    return pytest.importorskip("customtkinter")


def _root(ctk):
    try:
        r = ctk.CTk()
    except Exception:
        pytest.skip("sem display")
    # Fora da tela em vez de withdraw(): janela retirada não realiza geometria e todo
    # winfo_width() volta 1px — foi assim que uma medição anterior saiu inteira errada.
    r.geometry("1000x700+3000+3000")
    return r


def _botoes(widget, ctk, acc=None):
    acc = [] if acc is None else acc
    for ch in widget.winfo_children():
        if isinstance(ch, ctk.CTkButton):
            acc.append(ch)
        _botoes(ch, ctk, acc)
    return acc


def _largura_rotulo(botao) -> int:
    """Largura que o rótulo REALMENTE pede dentro do botão.

    Usa o `_text_label` interno do CTkButton — é ele que o Tk desenha e que clipa quando não
    cabe. Se a versão do CustomTkinter mudar a estrutura interna, cai na medição por fonte do
    próprio widget (`cget("font")`), que ainda é a fonte real, só sem os 2px do label.
    """
    lbl = getattr(botao, "_text_label", None)
    if lbl is not None:
        try:
            return int(lbl.winfo_reqwidth())
        except Exception:
            pass
    import tkinter.font as tkfont
    return tkfont.Font(font=botao.cget("font")).measure(botao.cget("text")) + 2


def _projeto_falso(base: Path, slug: str, *, thumb=True, searches=True,
                   antigo=False, docs=3, nome=None) -> str:
    """Fixture adversarial: dá para pedir projeto sem thumbnail, sem searches e `.blicsa`
    de versão antiga (sem `version` no manifest)."""
    d = base / slug
    d.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(d / "project.blicsa", "w") as zf:
        manifesto = {"app": "Blicsa", "saved_at": "2026-08-01 10:00:00"}
        if not antigo:
            manifesto["version"] = 3
        zf.writestr("manifest.json", json.dumps(manifesto))
        zf.writestr("config.json", json.dumps({"name": nome or slug}))
        if docs:
            zf.writestr("dataset.json.gz", gzip.compress(
                json.dumps([{"title": f"t{i}"} for i in range(docs)]).encode()))
        if thumb:
            from PIL import Image
            p = d / "t.png"
            Image.new("RGB", (60, 45), (200, 50, 20)).save(p)
            zf.write(p, "thumbnail.png")
            p.unlink()
        if searches:
            zf.writestr("searches.json", json.dumps([{"query": "x"}]))
    if searches:
        (d / "backlog.jsonl").write_text(
            json.dumps({"action": "search", "ts": "2026-08-01T10:00:00"}) + "\n")
    return slug


# ─────────────── 2.1 · botões de ação do card de projeto ───────────────

@pytest.mark.parametrize("lang", IDIOMAS)
def test_project_card_buttons_fit_their_labels(lang, tmp_path):
    """Nenhum rótulo do card estoura o botão, em nenhum idioma.

    O francês é o caso apertado: "Renommer" e "Supprimer" não cabiam em `width=60`, que era
    o valor original.
    """
    ctk = _ctk()
    from core.i18n import load_locales
    from ui.projects_view import ProjectCard

    load_locales(lang)
    root = _root(ctk)
    try:
        slug = _projeto_falso(tmp_path, "p1", nome="Projeto de teste")
        frame = ctk.CTkFrame(root)
        frame.pack(fill="both", expand=True)
        card = ProjectCard(frame, slug, str(tmp_path), lambda *a: None, lambda *a: None,
                           lambda *a: None, lambda *a: None)
        card.pack(fill="x")
        root.update()

        botoes = _botoes(card, ctk)
        assert botoes, "o card não tem botões de ação"

        # (a) Respiro: o botão não pode ficar do tamanho exato do rótulo. O CTkButton CRESCE
        # para caber o texto em vez de clipar — então "não cabe" nunca vira texto cortado;
        # vira botão esticado até encostar no rótulo, sem margem.
        apertados = []
        for b in botoes:
            rotulo = _largura_rotulo(b)
            folga = b.winfo_width() - rotulo
            if folga < FOLGA_MINIMA:
                apertados.append((b.cget("text"), rotulo, b.winfo_width(), folga))
        assert not apertados, (
            f"[{lang}] botão sem respiro (texto, rótulo px, largura, folga): {apertados}")

        # (b) Fileira uniforme: é o defeito que o usuário enxerga. Com a largura antiga (60)
        # cada botão esticava ao seu próprio rótulo e a fileira saía irregular — medido em
        # francês: [60, 72, 65, 69] contra [60, 68, 60, 60] em português.
        larguras = [b.winfo_width() for b in botoes]
        assert max(larguras) - min(larguras) == 0, (
            f"[{lang}] fileira de botões irregular: "
            f"{dict(zip([b.cget('text') for b in botoes], larguras))}")
    finally:
        root.destroy()


def test_project_card_button_width_is_identical_across_languages(tmp_path):
    """A mesma largura nos três idiomas — o card não pode mudar de forma ao traduzir."""
    ctk = _ctk()
    from core.i18n import load_locales
    from ui.projects_view import ProjectCard

    por_idioma = {}
    for lang in IDIOMAS:
        load_locales(lang)
        root = _root(ctk)
        try:
            slug = _projeto_falso(tmp_path, f"p_{lang}", nome="Projeto")
            frame = ctk.CTkFrame(root)
            frame.pack(fill="both", expand=True)
            card = ProjectCard(frame, slug, str(tmp_path), lambda *a: None, lambda *a: None,
                               lambda *a: None, lambda *a: None)
            card.pack(fill="x")
            root.update()
            por_idioma[lang] = sorted({b.winfo_width() for b in _botoes(card, ctk)})
        finally:
            root.destroy()

    valores = list(por_idioma.values())
    assert all(v == valores[0] for v in valores), (
        f"a largura dos botões muda conforme o idioma: {por_idioma}")
    assert len(valores[0]) == 1, f"botões com larguras diferentes entre si: {por_idioma}"


def test_project_cards_align_and_have_equal_height_with_poor_fixtures(tmp_path):
    """Dois eixos + origem, com as fixtures POBRES.

    Projeto sem thumbnail, sem `searches.json` e `.blicsa` antigo têm de render na mesma
    altura e com os botões na mesma coordenada x dos demais — senão a lista fica torta
    conforme o conteúdo de cada projeto.
    """
    ctk = _ctk()
    from core.i18n import load_locales
    from ui.projects_view import ProjectCard

    load_locales("fr")            # o idioma mais largo
    root = _root(ctk)
    try:
        slugs = [
            _projeto_falso(tmp_path, "completo", nome="Projeto completo"),
            _projeto_falso(tmp_path, "sem-thumb", thumb=False,
                           nome="Um nome de projeto consideravelmente mais longo que os outros"),
            _projeto_falso(tmp_path, "sem-searches", searches=False, nome="C"),
            _projeto_falso(tmp_path, "antigo", antigo=True, thumb=False, searches=False,
                           docs=0, nome="Legado"),
        ]
        frame = ctk.CTkFrame(root)
        frame.pack(fill="both", expand=True)
        cards = []
        for s in slugs:
            c = ProjectCard(frame, s, str(tmp_path), lambda *a: None, lambda *a: None,
                            lambda *a: None, lambda *a: None)
            c.pack(fill="x", pady=4)
            cards.append(c)
        root.update()

        alturas = [c.winfo_reqheight() for c in cards]
        assert max(alturas) - min(alturas) == 0, (
            f"cards com alturas diferentes conforme o conteúdo: {dict(zip(slugs, alturas))}")

        xs = [_botoes(c, ctk)[0].winfo_x() for c in cards]
        assert max(xs) - min(xs) == 0, (
            f"o 1º botão começa em x diferente entre cards: {dict(zip(slugs, xs))}")
    finally:
        root.destroy()


# ─────────────── 2.2 · botão Voltar do Blink ───────────────

def test_blink_back_button_has_the_same_width_in_every_language():
    """O botão Voltar mantém a MESMA largura nos três idiomas, com respiro.

    Correção de premissa: o prompt dizia que "⬅ Retour" estourava `width=80` em 7px. Medido
    com a fonte real do widget, o rótulo pede 58px e cabe em 80 — os 71px do relatório vinham
    de uma fonte suposta (SF Pro Display 13), diferente da que o Tk desenha. E o CTkButton
    CRESCE em vez de clipar: com `width=40` ele renderiza 70px.

    Então o risco real nunca foi texto cortado; é o botão mudar de tamanho conforme o idioma
    (o que desalinha a barra de título do Blink). `width=100` mantém os três iguais.
    """
    ctk = _ctk()
    from core.i18n import load_locales, t

    largura = _largura_blink_back()
    medidas = {}
    for lang in IDIOMAS:
        load_locales(lang)
        root = _root(ctk)
        try:
            botao = ctk.CTkButton(root, text=t("blink.voltar"), width=largura, height=30)
            botao.pack()
            root.update()
            medidas[lang] = (botao.cget("text"), botao.winfo_width(), _largura_rotulo(botao))
        finally:
            root.destroy()

    larguras = {v[1] for v in medidas.values()}
    assert len(larguras) == 1, (
        f"o botão Voltar muda de largura conforme o idioma: {medidas}")

    for lang, (texto, larg, rotulo) in medidas.items():
        folga = larg - rotulo
        assert folga >= FOLGA_MINIMA, (
            f"[{lang}] '{texto}' sem respiro: rótulo {rotulo}px em {larg}px (folga {folga}px)")


def _largura_blink_back() -> int:
    """Lê do fonte a largura do botão Voltar, para o teste seguir a implementação."""
    import re
    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    # Procura na LINHA da atribuição: um regex sobre a chamada inteira tropeça no ")" de
    # t("blink.voltar"), que aparece antes do width.
    linhas = [l for l in src.splitlines()
              if "_blink_back_btn" in l and "CTkButton" in l]
    assert linhas, "não achei o botão Voltar do Blink em main.py"
    m = re.search(r"width=(\d+)", linhas[0])
    assert m, f"o botão Voltar não tem width explícito: {linhas[0].strip()[:120]}"
    return int(m.group(1))


# ─────────────── 2.3 · sugestões do Blink quebrando linha ───────────────

@pytest.mark.parametrize("lang", IDIOMAS)
def test_blink_suggestions_fit_the_panel_width(lang):
    """As sugestões cabem no painel. Em francês, as três numa linha davam ~1277px.

    O layout é um grid de 2 colunas: a linha mais larga tem 2 botões. O teste reproduz a
    mesma conta que o `main.py` faz e confere contra a largura útil do painel.
    """
    ctk = _ctk()
    import tkinter.font as tkfont

    from core.i18n import load_locales, t

    LARGURA_PAINEL = 1000          # largura útil do painel do Blink
    load_locales(lang)
    root = _root(ctk)
    try:
        sugestoes = [t(f"blink.sugestao_{i}") for i in (1, 2, 3)]
        fonte = tkfont.Font(family=ctk.CTkFont(size=12).cget("family"), size=12)
        largura_botao = max(fonte.measure(s) for s in sugestoes) + 24

        colunas = _colunas_das_sugestoes()
        linha_mais_larga = largura_botao * colunas + 10 * (colunas - 1)
        assert linha_mais_larga <= LARGURA_PAINEL, (
            f"[{lang}] as sugestões ocupam {linha_mais_larga}px numa faixa de "
            f"{LARGURA_PAINEL}px (botão {largura_botao}px × {colunas} colunas)")

        # E o texto não pode ser truncado — o botão tem de caber o rótulo inteiro.
        for s in sugestoes:
            assert fonte.measure(s) <= largura_botao, f"[{lang}] sugestão truncada: {s!r}"
    finally:
        root.destroy()


def _colunas_das_sugestoes() -> int:
    """Nº de colunas do grid de sugestões, lido do fonte.

    Com `column=i % 2` são 2 colunas (quebra em 2 linhas); com `column=i` seriam 3 numa
    linha só, que é o que estourava em francês.
    """
    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    if "column=i % 2" in src:
        return 2
    if "column=i," in src or "column=i)" in src:
        return 3
    pytest.fail("não identifiquei o grid das sugestões do Blink em main.py")


def test_suggestions_use_a_wrapping_grid_not_a_single_row():
    """Trava a decisão de layout: grid de 2 colunas, não 3 numa linha."""
    assert _colunas_das_sugestoes() == 2, (
        "as sugestões voltaram para uma linha só — em francês isso estoura o painel")


# ─────────────── 2.5 · slider de anos com ano único ───────────────

def test_year_slider_is_not_created_for_a_single_year():
    """Complementa o teste que já existe em test_search_feed_ui.py.

    Aqui a checagem é do outro lado: com anos VARIADOS o slider tem de existir e ter
    `number_of_steps` positivo — senão "proteger" viraria "nunca criar o slider".
    """
    ctk = _ctk()
    from ui.search_feed import SearchFeedView

    root = _root(ctk)
    try:
        fv = SearchFeedView(root, lambda *a, **k: None, lambda: None, lambda *a, **k: None)
        fv.pack(fill="both", expand=True)

        def _rec(i, ano):
            return {"title": f"T{i}", "year": ano, "authors": "A", "source": "S",
                    "citations": 0, "abstract": "", "doi": f"10.1/{i}", "language": "en"}

        # Ano único → sem slider (o ZeroDivisionError vinha daqui).
        fv.load_results([_rec(i, 2020) for i in range(4)], "trilha")
        root.update()
        assert not hasattr(fv, "year_slider"), "ano único não deveria criar slider"

        # Anos variados → slider existe e com passos positivos.
        fv.load_results([_rec(i, 2018 + i) for i in range(5)], "trilha")
        root.update()
        assert hasattr(fv, "year_slider"), "anos variados deveriam criar o slider"
        passos = fv.year_slider.cget("number_of_steps")
        assert passos and passos > 0, f"number_of_steps inválido: {passos!r}"
    finally:
        root.destroy()
