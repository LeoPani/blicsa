import re
import customtkinter as ctk

def configure_markdown_tags(textbox: ctk.CTkTextbox):
    """Configures text tags in a CTkTextbox to support basic Markdown styles."""
    # Base font is assumed to be the textbox's font, we just change weight/slant
    base_font = textbox.cget("font")
    if isinstance(base_font, str):
        # We need CTkFont objects
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

def insert_markdown(textbox: ctk.CTkTextbox, text: str):
    """Parses basic markdown and inserts it into a CTkTextbox."""
    # A very naive markdown parser for basic chat formatting
    
    lines = text.split("\n")
    for line in lines:
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
            
        # Parse inline styles using regex splitting
        # We look for **bold**, *italic*, `code`
        # This regex splits keeping the delimiters
        parts = re.split(r'(\*\*.*?\*\*|\*.*?\*|`.*?`)', line)
        for part in parts:
            if not part: continue
            if part.startswith("**") and part.endswith("**"):
                textbox.insert("end", part[2:-2], tuple(tags + ["bold"]))
            elif part.startswith("*") and part.endswith("*"):
                textbox.insert("end", part[1:-1], tuple(tags + ["italic"]))
            elif part.startswith("`") and part.endswith("`"):
                textbox.insert("end", part[1:-1], tuple(tags + ["code"]))
            else:
                if tags:
                    textbox.insert("end", part, tuple(tags))
                else:
                    textbox.insert("end", part)
        textbox.insert("end", "\n")
