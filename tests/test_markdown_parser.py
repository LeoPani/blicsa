"""`core/markdown_parser.py` — o renderizador da resposta do Blink.

Estava **sem cobertura própria** (Auditoria 1, Fase 3, §6) e é ele que transforma o Markdown
do modelo em tags do `CTkTextbox`. Um erro aqui aparece como resposta de IA malformada na
tela — a mesma superfície que três commits da fase de IA passaram protegendo.

A varredura com entrada adversarial encontrou três defeitos, todos visíveis:

1. `***os dois***` saía como negrito de `*os dois`, com um asterisco solto no texto e a tag
   `bold_italic` configurada e nunca aplicada;
2. bloco cercado por ``` saía com uma crase solta e a linha de fechamento engolida — e o
   modelo devolve bloco cercado o tempo todo;
3. `2 * 3 * 4` virava `2  3  4` com " 3 " em itálico. Não era só estilo errado: **os
   asteriscos sumiam do texto**, e quem perguntasse sobre uma fórmula recebia a fórmula
   mutilada.

Os testes de estilo passam por `configure_markdown_tags` + `insert_markdown` num widget de
verdade, porque é assim que o app usa; e há um teste que percorre o funil real do chat
(`_add_blink_message`), já que foi ele que configurou as tags.
"""

import customtkinter as ctk
import pytest

from core.markdown_parser import configure_markdown_tags, insert_markdown


@pytest.fixture
def caixa():
    try:
        raiz = ctk.CTk()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    raiz.withdraw()
    tb = ctk.CTkTextbox(raiz)
    configure_markdown_tags(tb)
    yield tb
    raiz.destroy()


def _render(caixa, markdown: str) -> tuple[str, dict[str, list[str]]]:
    """Devolve `(texto puro, {tag: [trechos marcados]})` — o que o usuário lê e como."""
    insert_markdown(caixa, markdown)
    interno = caixa._textbox
    marcas: dict[str, list[str]] = {}
    for tag in ("bold", "italic", "bold_italic", "code", "h1", "h2", "h3"):
        faixas = interno.tag_ranges(tag)
        if faixas:
            marcas[tag] = [interno.get(faixas[i], faixas[i + 1])
                           for i in range(0, len(faixas), 2)]
    return interno.get("1.0", "end-1c"), marcas


# ── Os três defeitos encontrados ─────────────────────────────────────────────────

def test_asterisco_de_multiplicacao_nao_some_do_texto(caixa):
    """O pior dos três: caractere **apagado** da resposta.

    `2 * 3 * 4 = 24` virava `2  3  4 = 24`. Um pesquisador perguntando ao Blink sobre uma
    fórmula recebia a fórmula errada, sem nada indicando que houve edição.
    """
    texto, marcas = _render(caixa, "2 * 3 * 4 = 24")

    assert texto.strip() == "2 * 3 * 4 = 24", "os asteriscos foram engolidos"
    assert "italic" not in marcas, "espaço colado ao asterisco não é itálico"


def test_negrito_e_italico_juntos(caixa):
    """`***x***` deixava um asterisco solto no texto e nunca usava a tag `bold_italic`."""
    texto, marcas = _render(caixa, "***os dois***")

    assert texto.strip() == "os dois", "sobrou asterisco no texto"
    assert marcas.get("bold_italic") == ["os dois"]
    assert "bold" not in marcas and "italic" not in marcas


def test_bloco_cercado_sai_inteiro_e_sem_a_cerca(caixa):
    """O modelo devolve ```python ... ``` o tempo todo. A cerca é delimitador, não conteúdo."""
    texto, marcas = _render(caixa, "```python\nprint(1)\n```")

    assert "`" not in texto, "a crase da cerca vazou para o texto"
    assert "print(1)" in texto
    assert "python" not in texto, "a linguagem da cerca virou conteúdo"
    assert marcas.get("code"), "o bloco não foi marcado como código"


def test_dentro_do_bloco_nada_e_interpretado(caixa):
    """Fórmula dentro de bloco de código não pode perder asterisco nem virar título."""
    texto, _ = _render(caixa, "```\na * b * c\n# não é título\n```")

    assert "a * b * c" in texto
    assert "# não é título" in texto, "o `#` dentro do bloco virou cabeçalho"


# ── O que já funcionava, e não pode regredir ─────────────────────────────────────

@pytest.mark.parametrize("markdown,esperado,tag", [
    ("**forte**", "forte", "bold"),
    ("*fraco*", "fraco", "italic"),
    ("`pip install`", "pip install", "code"),
    ("# Um", "Um", "h1"),
    ("## Dois", "Dois", "h2"),
    ("### Três", "Três", "h3"),
])
def test_estilos_basicos(caixa, markdown, esperado, tag):
    texto, marcas = _render(caixa, markdown)
    assert texto.strip() == esperado
    assert marcas.get(tag) == [esperado]


def test_lista_vira_marcador(caixa):
    texto, _ = _render(caixa, "- item um\n- item dois")
    assert texto.count("•") == 2
    assert "- item" not in texto


def test_varios_estilos_na_mesma_linha(caixa):
    texto, marcas = _render(caixa, "**a** e *b* e `c`")
    assert texto.strip() == "a e b e c"
    assert marcas == {"bold": ["a"], "italic": ["b"], "code": ["c"]}


def test_estilo_dentro_de_cabecalho_mantem_os_dois(caixa):
    """`## Título com **destaque**` — o trecho tem de ficar h2 E negrito."""
    _, marcas = _render(caixa, "## Título com **destaque**")
    assert "destaque" in marcas.get("bold", [])
    assert any("Título" in t for t in marcas.get("h2", []))


# ── Entrada adversarial: nada pode levantar ──────────────────────────────────────

@pytest.mark.parametrize("markdown", [
    "", "\n", "   ", "*", "**", "***", "`", "```", "```\n", "**sem fechar",
    "*", "* ", " *", "a*b*c", "###", "#sem espaço", "- ", "•", "\x00",
    "🌍 **emoji** e `código` com ação", "a" * 5000,
    "```\nbloco sem fechamento",
    "| tabela | não | suportada |",
    "[link](http://x)", "__underscore__",
])
def test_entrada_adversarial_nao_levanta(caixa, markdown):
    """O texto vem de um modelo: pode vir truncado no meio de um `**`, com cerca sem fechar
    ou com marcação que este parser não conhece. Nenhum caso pode derrubar a tela do chat."""
    insert_markdown(caixa, markdown)


def test_marcacao_desconhecida_sai_literal_em_vez_de_sumir(caixa):
    """`__x__` e `[texto](url)` não são suportados — e a resposta certa é mostrá-los como
    vieram. Apagar o que não se entende é o defeito nº 3 outra vez."""
    texto, _ = _render(caixa, "__forte__ e [texto](http://x)")
    assert "__forte__" in texto
    assert "[texto](http://x)" in texto


def test_bloco_sem_fechamento_nao_engole_o_resto(caixa):
    """Resposta truncada pelo limite de tokens deixa a cerca aberta. O que veio antes e
    depois tem de aparecer."""
    texto, _ = _render(caixa, "antes\n```\ncodigo truncado")
    assert "antes" in texto and "codigo truncado" in texto


# ── O funil real do chat ─────────────────────────────────────────────────────────

def test_o_chat_do_blink_configura_as_tags_antes_de_inserir():
    """Sem `configure_markdown_tags`, o Tk cria a tag vazia e o texto sai **sem estilo
    nenhum**, em silêncio. O funil `_add_blink_message` é quem configura — este teste
    percorre o caminho do app, não a função isolada."""
    import main as blicsa

    try:
        app = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        tb, _upd, _ = app._add_blink_message("assistant", "")
        tb.configure(state="normal")
        insert_markdown(tb, "## Achados\n\n**Freire** escreveu *Pedagogia*.")
        app.update_idletasks()

        interno = tb._textbox
        for tag in ("h2", "bold", "italic"):
            assert interno.tag_ranges(tag), f"a tag '{tag}' não chegou configurada ao chat"
        assert "Pedagogia" in interno.get("1.0", "end-1c")
    finally:
        app.destroy()


def test_configure_aceita_caixa_com_fonte_em_string():
    """`cget("font")` devolve string em alguns temas do CustomTkinter, e o módulo cai para
    uma fonte padrão. Se isso levantar, o chat não abre."""
    try:
        raiz = ctk.CTk()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    try:
        raiz.withdraw()
        tb = ctk.CTkTextbox(raiz, font=("Inter", 13))
        configure_markdown_tags(tb)
        insert_markdown(tb, "**ok**")
        assert tb._textbox.tag_ranges("bold")
    finally:
        raiz.destroy()
