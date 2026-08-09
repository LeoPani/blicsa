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


    font_bold = ctk.CTkFont(family=base_font.cget("family"), size=base_font.cget("size"), weight="bold")
    font_italic = ctk.CTkFont(family=base_font.cget("family"), size=base_font.cget("size"), slant="italic")
    font_bold_italic = ctk.CTkFont(family=base_font.cget("family"), size=base_font.cget("size"), weight="bold", slant="italic")
    font_h1 = ctk.CTkFont(family=base_font.cget("family"), size=base_font.cget("size") + 6, weight="bold")
    font_h2 = ctk.CTkFont(family=base_font.cget("family"), size=base_font.cget("size") + 4, weight="bold")
    font_h3 = ctk.CTkFont(family=base_font.cget("family"), size=base_font.cget("size") + 2, weight="bold")
    font_code = ctk.CTkFont(family="Courier", size=base_font.cget("size"))
    
    textbox._textbox.tag_config("bold", font=font_bold)
    textbox._textbox.tag_config("italic", font=font_italic)
    textbox._textbox.tag_config("bold_italic", font=font_bold_italic)
    textbox._textbox.tag_config("h1", font=font_h1)
    textbox._textbox.tag_config("h2", font=font_h2)
    textbox._textbox.tag_config("h3", font=font_h3)
    textbox._textbox.tag_config("code", font=font_code, background="#e0e0e0")

#: Estilos inline, na ordem em que precisam ser tentados.
#:
#: `***` **antes** de `**`, senão `***os dois***` casa como negrito de `*os dois` e sobra um
#: asterisco solto no texto — era o que acontecia, com a tag `bold_italic` configurada e
#: nunca aplicada.
#:
#: O `(?=\S)` do itálico é o que impede `2 * 3 * 4` de virar `2  3  4` com " 3 " em itálico.
#: Não era só estilo errado: **os asteriscos sumiam do texto**, e quem perguntasse ao Blink
#: sobre uma fórmula recebia a fórmula mutilada.
ESTILOS_INLINE = re.compile(
    r"(\*\*\*(?=\S)(?:.*?\S)?\*\*\*"      # ***negrito e itálico***
    r"|\*\*(?=\S)(?:.*?\S)?\*\*"          # **negrito**
    r"|\*(?=\S)(?:[^*]*?\S)?\*"           # *itálico*, sem espaço colado ao asterisco
    r"|`[^`]+?`)"                         # `código`
)

#: Cerca de bloco de código. O modelo devolve ```python ... ``` o tempo todo, e sem tratar a
#: cerca o texto saía com uma crase solta e a linha de fechamento engolida.
CERCA = "```"


def insert_markdown(textbox: ctk.CTkTextbox, text: str):
    """Insere Markdown básico num `CTkTextbox`, aplicando as tags de `configure_markdown_tags`.

    Cobre: `#`/`##`/`###`, `- ` (vira `•`), `**negrito**`, `*itálico*`, `***os dois***`,
    `` `código` `` e blocos cercados por ```` ``` ````.

    **Não** cobre: `__negrito__`, `[texto](url)`, lista aninhada e tabela. São conhecidos e
    ficam registrados em `docs/AUDITORIA-ARQUITETURA.md`; o parser é deliberadamente pequeno
    porque a saída que ele renderiza é conversa, não documento.
    """
    dentro_do_bloco = False

    for line in text.split("\n"):
        if line.lstrip().startswith(CERCA):
            # A cerca é delimitador, não conteúdo — inclusive a que abre com `​```python`.
            dentro_do_bloco = not dentro_do_bloco
            continue

        if dentro_do_bloco:
            # Dentro do bloco nada é interpretado: `*` é `*`, `#` é `#`.
            textbox.insert("end", line + "\n", ("code",))
            continue

        tags = []
        if line.startswith("# "):
            tags.append("h1")
            line = line[2:]
        elif line.startswith("## "):
            tags.append("h2")
            line = line[3:]
        elif line.startswith("### "):
            tags.append("h3")
            line = line[4:]
        elif line.startswith("- "):
            line = "• " + line[2:]

        for part in ESTILOS_INLINE.split(line):
            if not part:
                continue
            if part.startswith("***") and part.endswith("***"):
                textbox.insert("end", part[3:-3], tuple(tags + ["bold_italic"]))
            elif part.startswith("**") and part.endswith("**"):
                textbox.insert("end", part[2:-2], tuple(tags + ["bold"]))
            elif part.startswith("*") and part.endswith("*"):
                textbox.insert("end", part[1:-1], tuple(tags + ["italic"]))
            elif part.startswith("`") and part.endswith("`"):
                textbox.insert("end", part[1:-1], tuple(tags + ["code"]))
            elif tags:
                textbox.insert("end", part, tuple(tags))
            else:
                textbox.insert("end", part)
        textbox.insert("end", "\n")
