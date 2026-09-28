"""Markdown do modelo → tags do `CTkTextbox`. É o que o usuário lê como resposta do Blink.

O parser é pequeno de propósito — a saída que ele renderiza é conversa, não documento —
mas precisa cobrir o que o modelo DE FATO devolve. O `blink.system_prompt` pede "use
markdown para formatar a resposta", e o que voltava sem tratamento saía cru na tela: tabela
como um amontoado de canos, `[texto](url)` com colchetes e parênteses à mostra, `__negrito__`
com os underscores. Era o "formatação estranha" relatado.

Regra que atravessa o módulo: **nada é apagado**. Marcação que o parser não entende sai
literal, e link mostra o texto E a URL — a URL é a referência, some-la seria perder o dado.
"""

import re

import customtkinter as ctk


def configure_markdown_tags(textbox: ctk.CTkTextbox):
    """Configures text tags in a CTkTextbox to support basic Markdown styles."""
    # Base font is assumed to be the textbox's font, we just change weight/slant
    base_font = textbox.cget("font")
    if not hasattr(base_font, "cget"):
        # `cget("font")` devolve `CTkFont`, **string** ou **tupla** conforme como o widget foi
        # criado: `CTkTextbox(font=("Inter", 13))` devolve a tupla. A checagem era só contra
        # `str`, e a tupla levantava `AttributeError: 'tuple' object has no attribute 'cget'`
        # — dentro da configuração das tags, ou seja, a tela do chat não abria.
        #
        # Por presença de `.cget` em vez de lista de tipos: o que importa é a interface que
        # as linhas abaixo usam, e uma lista de tipos envelhece a cada versão do CustomTkinter.
        base_font = ctk.CTkFont(family="Inter", size=14)

    familia = base_font.cget("family")
    corpo = base_font.cget("size")

    font_bold = ctk.CTkFont(family=familia, size=corpo, weight="bold")
    font_italic = ctk.CTkFont(family=familia, size=corpo, slant="italic")
    font_bold_italic = ctk.CTkFont(family=familia, size=corpo, weight="bold", slant="italic")
    font_h1 = ctk.CTkFont(family=familia, size=corpo + 6, weight="bold")
    font_h2 = ctk.CTkFont(family=familia, size=corpo + 4, weight="bold")
    font_h3 = ctk.CTkFont(family=familia, size=corpo + 2, weight="bold")
    font_h4 = ctk.CTkFont(family=familia, size=corpo, weight="bold")
    font_code = ctk.CTkFont(family="Courier", size=corpo)
    font_tabela = ctk.CTkFont(family="Courier", size=max(corpo - 2, 9))
    font_tabela_cab = ctk.CTkFont(family="Courier", size=max(corpo - 2, 9), weight="bold")

    interno = textbox._textbox
    interno.tag_config("bold", font=font_bold)
    interno.tag_config("italic", font=font_italic)
    interno.tag_config("bold_italic", font=font_bold_italic)
    interno.tag_config("h1", font=font_h1)
    interno.tag_config("h2", font=font_h2)
    interno.tag_config("h3", font=font_h3)
    interno.tag_config("h4", font=font_h4)
    interno.tag_config("code", font=font_code, background="#e0e0e0")
    # O link precisa se distinguir SEM cor própria: o texto do balão é preto no claro e
    # branco no do usuário, e uma cor fixa some num dos dois. O sublinhado sobrevive aos dois.
    interno.tag_config("link", underline=True)
    interno.tag_config("url", font=font_code)
    # `lmargin2` é o que faz a segunda linha de um item longo alinhar sob o texto e não sob
    # o marcador — sem ele a lista embaralha assim que um item quebra de linha.
    interno.tag_config("lista", lmargin1=12, lmargin2=26)
    interno.tag_config("lista_aninhada", lmargin1=32, lmargin2=46)
    interno.tag_config("citacao", lmargin1=16, lmargin2=16, font=font_italic)
    interno.tag_config("tabela", font=font_tabela)
    interno.tag_config("tabela_cabecalho", font=font_tabela_cab)


#: Estilos inline, na ordem em que precisam ser tentados.
#:
#: `***` **antes** de `**`, senão `***os dois***` casa como negrito de `*os dois` e sobra um
#: asterisco solto no texto — era o que acontecia, com a tag `bold_italic` configurada e
#: nunca aplicada.
#:
#: O `(?=\S)` do itálico é o que impede `2 * 3 * 4` de virar `2  3  4` com " 3 " em itálico.
#: Não era só estilo errado: **os asteriscos sumiam do texto**, e quem perguntasse ao Blink
#: sobre uma fórmula recebia a fórmula mutilada.
#:
#: `__negrito__` e `[texto](url)` entraram porque o modelo os produz o tempo todo e eles
#: saíam com a pontuação à mostra. `_itálico_` de underscore único ficou DE FORA de
#: propósito: casaria `nome_de_variavel` e `campo_x`, que aparecem em toda conversa sobre
#: dados bibliométricos.
ESTILOS_INLINE = re.compile(
    r"(\*\*\*(?=\S)(?:.*?\S)?\*\*\*"      # ***negrito e itálico***
    r"|\*\*(?=\S)(?:.*?\S)?\*\*"          # **negrito**
    r"|__(?=\S)(?:.*?\S)?__"              # __negrito__
    r"|\*(?=\S)(?:[^*]*?\S)?\*"           # *itálico*, sem espaço colado ao asterisco
    r"|`[^`]+?`"                          # `código`
    r"|\[[^\[\]]+\]\([^()\s]+\))"         # [texto](url)
)

LINK = re.compile(r"^\[([^\[\]]+)\]\(([^()\s]+)\)$")

#: Cerca de bloco de código. O modelo devolve ```python ... ``` o tempo todo, e sem tratar a
#: cerca o texto saía com uma crase solta e a linha de fechamento engolida.
CERCA = "```"

#: Régua horizontal. `***` ficou de fora: colide com `***negrito e itálico***`, e o modelo
#: escreve `---` quando quer uma régua.
REGRA = re.compile(r"^(?:-{3,}|_{3,})$")

#: Célula só de traços: é a linha `|---|---|` que separa cabeçalho de corpo, não conteúdo.
CELULA_SEPARADORA = re.compile(r"^:?-{2,}:?$")

MARCADORES = ("- ", "* ", "+ ")


def _e_linha_de_tabela(linha: str) -> bool:
    """`| a | b |` — precisa de pelo menos dois canos para não casar um `|` solto no texto."""
    t = linha.strip()
    return t.startswith("|") and t.count("|") >= 2


def _celulas(linha: str) -> list[str]:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def _e_separadora(celulas: list[str]) -> bool:
    return bool(celulas) and all(CELULA_SEPARADORA.match(c) for c in celulas)


def _inserir_tabela(textbox: ctk.CTkTextbox, linhas: list[str]):
    """Alinha a tabela em colunas monoespaçadas, com o cabeçalho destacado.

    Um `CTkTextbox` não tem célula: a alternativa a alinhar por espaço em fonte de largura
    fixa seria deixar os canos crus na tela, que é como estava. Tabela é justamente o
    formato em que o modelo devolve comparação de métricas, então sai muito.
    """
    grade = [_celulas(l) for l in linhas]
    cabecalho = None
    corpo = []
    for i, celulas in enumerate(grade):
        if _e_separadora(celulas):
            # A separadora promove a linha ANTERIOR a cabeçalho, e só a primeira vez.
            if i == 1 and corpo and cabecalho is None:
                cabecalho = corpo.pop(0)
            continue
        corpo.append(celulas)

    todas = ([cabecalho] if cabecalho else []) + corpo
    if not todas:
        return
    n_colunas = max(len(l) for l in todas)
    todas = [l + [""] * (n_colunas - len(l)) for l in todas]
    larguras = [max(len(l[c]) for l in todas) for c in range(n_colunas)]

    def _formatar(celulas):
        return "  ".join(c.ljust(larguras[i]) for i, c in enumerate(celulas)).rstrip()

    if cabecalho:
        linha_cab = todas[0]
        textbox.insert("end", _formatar(linha_cab) + "\n", ("tabela_cabecalho",))
        textbox.insert("end", "─" * len(_formatar([("─" * w) for w in larguras])) + "\n",
                       ("tabela",))
        restantes = todas[1:]
    else:
        restantes = todas
    for celulas in restantes:
        textbox.insert("end", _formatar(celulas) + "\n", ("tabela",))


def _inserir_com_estilos(textbox: ctk.CTkTextbox, linha: str, tags: list[str]):
    """Aplica os estilos inline de uma linha já sem o prefixo de bloco."""
    for part in ESTILOS_INLINE.split(linha):
        if not part:
            continue
        if part.startswith("***") and part.endswith("***"):
            textbox.insert("end", part[3:-3], tuple(tags + ["bold_italic"]))
        elif part.startswith("**") and part.endswith("**"):
            textbox.insert("end", part[2:-2], tuple(tags + ["bold"]))
        elif part.startswith("__") and part.endswith("__"):
            textbox.insert("end", part[2:-2], tuple(tags + ["bold"]))
        elif part.startswith("*") and part.endswith("*"):
            textbox.insert("end", part[1:-1], tuple(tags + ["italic"]))
        elif part.startswith("`") and part.endswith("`"):
            textbox.insert("end", part[1:-1], tuple(tags + ["code"]))
        elif LINK.match(part):
            # Texto sublinhado E a URL: num Textbox desabilitado o link não é clicável, e
            # esconder a URL apagaria a referência — que costuma ser um DOI.
            texto, url = LINK.match(part).groups()
            textbox.insert("end", texto, tuple(tags + ["link"]))
            textbox.insert("end", f" ({url})", tuple(tags + ["url"]))
        elif tags:
            textbox.insert("end", part, tuple(tags))
        else:
            textbox.insert("end", part)


def insert_markdown(textbox: ctk.CTkTextbox, text: str):
    """Insere Markdown básico num `CTkTextbox`, aplicando as tags de `configure_markdown_tags`.

    Cobre: `#` a `####`, `- `/`* `/`+ ` (viram `•`, com um nível de aninhamento), lista
    numerada, `> ` de citação, régua `---`, tabela `| a | b |`, `**negrito**`,
    `__negrito__`, `*itálico*`, `***os dois***`, `` `código` ``, `[texto](url)` e blocos
    cercados por ```` ``` ````.

    **Não** cobre, de propósito: `_itálico_` de underscore único (casaria
    `nome_de_variavel`, que aparece em toda conversa sobre dados), `~~riscado~~`, imagem e
    lista aninhada além de um nível. O parser é pequeno porque a saída que ele renderiza é
    conversa, não documento — e o que ele não entende sai LITERAL em vez de sumir, que é a
    regra que `tests/test_markdown_parser.py` guarda.
    """
    dentro_do_bloco = False
    linhas = text.split("\n")
    i = 0

    while i < len(linhas):
        line = linhas[i]

        if line.lstrip().startswith(CERCA):
            # A cerca é delimitador, não conteúdo — inclusive a que abre com ```python.
            dentro_do_bloco = not dentro_do_bloco
            i += 1
            continue

        if dentro_do_bloco:
            # Dentro do bloco nada é interpretado: `*` é `*`, `#` é `#`.
            textbox.insert("end", line + "\n", ("code",))
            i += 1
            continue

        # Tabela: um bloco de linhas consecutivas, consumido de uma vez porque a largura
        # das colunas só se conhece depois de ver todas.
        if _e_linha_de_tabela(line):
            bloco = []
            while i < len(linhas) and _e_linha_de_tabela(linhas[i]):
                bloco.append(linhas[i])
                i += 1
            _inserir_tabela(textbox, bloco)
            continue

        i += 1

        if REGRA.match(line.strip()):
            textbox.insert("end", "─" * 40 + "\n", ("tabela",))
            continue

        tags = []
        recuo = len(line) - len(line.lstrip(" "))
        nu = line.lstrip(" ")

        if line.startswith("# "):
            tags.append("h1")
            line = line[2:]
        elif line.startswith("## "):
            tags.append("h2")
            line = line[3:]
        elif line.startswith("### "):
            tags.append("h3")
            line = line[4:]
        elif line.startswith("#### "):
            tags.append("h4")
            line = line[5:]
        elif nu.startswith("> "):
            tags.append("citacao")
            line = nu[2:]
        elif any(nu.startswith(m) for m in MARCADORES):
            # Dois níveis: o modelo aninha para separar critério de subcritério, e sem o
            # recuo os dois níveis viravam uma lista chapada só.
            aninhado = recuo >= 2
            tags.append("lista_aninhada" if aninhado else "lista")
            line = ("◦ " if aninhado else "• ") + nu[2:]
        elif re.match(r"^\d+\.\s", nu):
            tags.append("lista_aninhada" if recuo >= 2 else "lista")
            line = nu

        _inserir_com_estilos(textbox, line, tags)
        textbox.insert("end", "\n")
