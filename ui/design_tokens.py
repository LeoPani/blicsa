PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
RED_HOVER = "#B82812"
BLUE = "#1E4DA0"
YELLOW = "#F5BE00"
MUTED = "#8A877F"
WHITE_CARD = "#FFFFFF"

# Semantic mappings
CONTENT_BG = PAPER
SIDEBAR_BG = INK
CARD_BG = WHITE_CARD
CARD2_BG = "#F9F9F9" # Light gray for alternating
ACCENT = RED
ACCENT_HOV = RED_HOVER

CORNER_RADIUS = 0
SPACING_GRID = 8

FONT_FAMILY = "Archivo"
FONT_FALLBACK = ("Segoe UI", "Helvetica", "Arial", "sans-serif")

def get_font(size, weight="normal"):
    import customtkinter as ctk
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
