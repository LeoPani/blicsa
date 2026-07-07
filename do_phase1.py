import os
import re
from PIL import Image, ImageDraw

os.makedirs("assets/icons", exist_ok=True)
icons = ["house", "magnet", "stack", "chart-network", "export-arrow", "gear", "sparkle"]
for icon in icons:
    for state in ["normal", "active"]:
        img = Image.new("RGBA", (24, 24), (0,0,0,0))
        d = ImageDraw.Draw(img)
        color = "#141414" if state == "normal" else "#DF3117"
        d.ellipse([4,4, 20,20], outline=color, width=2)
        img.save(f"assets/icons/{icon}_{state}.png")

with open("ui/design_tokens.py", "w") as f:
    f.write("""PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
RED_HOVER = "#B82812"
BLUE = "#1E4DA0"
YELLOW = "#F5BE00"
MUTED = "#8A877F"
WHITE_CARD = "#FFFFFF"

CONTENT_BG = PAPER
SIDEBAR_BG = WHITE_CARD
CARD_BG = WHITE_CARD
TEXT_MAIN = INK
TEXT_MUTED = MUTED

CORNER_RADIUS = 0
SPACING_GRID = 8
CLUSTER_PALETTE = ["#DF3117", "#1E4DA0", "#F5BE00", "#141414", "#7A9E7E", "#B65CA2", "#5CB0B8", "#C97B2D"]
FONT_FAMILY = "Segoe UI"
""")

with open("main.py", "r") as f:
    main_code = f.read()

# Remove set_appearance_mode and theme
main_code = re.sub(r'ctk\.set_appearance_mode\(.*?\)[\r\n]+', '', main_code)
main_code = re.sub(r'ctk\.set_default_color_theme\(.*?\)[\r\n]+', '', main_code)

# Replace navigation building
nav_code = """
        self._build_sidebar_button("Início", "house", self._build_tab_home)
        self._build_sidebar_button("Coletar", "magnet", self._build_tab_import)
        self._build_sidebar_button("Corpus", "stack", self._build_tab_corpus)
        self._build_sidebar_button("Análises", "chart-network", self._build_tab_analises)
        self._build_sidebar_button("Exportar", "export-arrow", self._build_tab_export)
        
        self.corpus_badge = ctk.CTkLabel(self._sidebar, text="Nenhum corpus", text_color=MUTED, font=(FONT_FAMILY, 11))
        self.corpus_badge.pack(side="bottom", pady=20)
"""
# Very basic replacement, we'll need a robust parser or manual fixes to apply all changes.
