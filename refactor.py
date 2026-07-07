import re

with open('main.py', 'r') as f:
    content = f.read()

# Replace window init to remove borders/corners (actually ctk handles corners, but we set them to 0 earlier)

# Add splash screen and build tab home
HOME_TAB = """
    def _build_tab_home(self) -> ctk.CTkFrame:
        from PIL import Image
        frame = self._tab()
        
        # Slogan & Logo strip
        top_strip = ctk.CTkFrame(frame, fg_color="transparent")
        top_strip.grid(row=0, column=0, padx=24, pady=(24, 16), sticky="ew")
        top_strip.grid_columnconfigure(1, weight=1)
        
        try:
            logo_img = ctk.CTkImage(light_image=Image.open("assets/branding/blicsa-logo-horizontal.png"), size=(180, 48))
            ctk.CTkLabel(top_strip, image=logo_img, text="").grid(row=0, column=0, sticky="w")
        except:
            ctk.CTkLabel(top_strip, text="Blicsa", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
            
        ctk.CTkLabel(top_strip, text="just blink", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).grid(row=1, column=0, sticky="w", padx=4)
        
        # Flags
        flag_f = ctk.CTkFrame(top_strip, fg_color="transparent")
        flag_f.grid(row=0, column=2, rowspan=2, sticky="e")
        
        def set_l(l):
            from core.i18n import set_lang
            set_lang(l)
            from tkinter import messagebox
            messagebox.showinfo("Blicsa", "Language changed. Please restart the app for full changes.")
            
        try:
            for i, (l, f_name) in enumerate([("pt_BR", "flag-pt-br.png"), ("en", "flag-en.png"), ("fr", "flag-fr.png")]):
                img = ctk.CTkImage(light_image=Image.open(f"assets/branding/{f_name}"), size=(32, 22))
                btn = ctk.CTkButton(flag_f, image=img, text="", width=32, height=22, fg_color="transparent", corner_radius=0, border_width=2, border_color=INK, hover_color="#e0e0e0", command=lambda x=l: set_l(x))
                btn.grid(row=0, column=i, padx=4)
        except:
            pass

        # Tiles Grid
        grid_f = ctk.CTkFrame(frame, fg_color="transparent")
        grid_f.grid(row=1, column=0, padx=24, pady=16, sticky="nsew")
        
        # Tile 1: New analysis (Red)
        t1 = ctk.CTkButton(grid_f, text=t("home_new_analysis"), font=ctk.CTkFont(size=18, weight="bold"), fg_color=RED, text_color="white", width=250, height=120, corner_radius=0, border_width=3, border_color=INK, hover_color="#B82813", command=lambda: self._switch_tab("import"))
        t1.grid(row=0, column=0, padx=8, pady=8)
        
        # Tile 2: Search databases (Blue)
        t2 = ctk.CTkButton(grid_f, text=t("home_search_db"), font=ctk.CTkFont(size=18, weight="bold"), fg_color=BLUE, text_color="white", width=250, height=120, corner_radius=0, border_width=3, border_color=INK, hover_color="#153a60", command=lambda: self._switch_tab("import"))
        t2.grid(row=0, column=1, padx=8, pady=8)
        
        # Tile 3: Open project (Paper + ink border)
        t3 = ctk.CTkButton(grid_f, text=t("home_open_project"), font=ctk.CTkFont(size=18, weight="bold"), fg_color=PAPER, text_color=INK, width=250, height=120, corner_radius=0, border_width=3, border_color=INK, hover_color="#e0e0e0", command=self._load_project_gui)
        t3.grid(row=0, column=2, padx=8, pady=8)
        
        # Tile 4: Recent files
        t4 = ctk.CTkButton(grid_f, text=t("home_recent_files"), font=ctk.CTkFont(size=16), fg_color=PAPER, text_color=INK, width=250, height=80, corner_radius=0, border_width=3, border_color=INK, hover_color="#e0e0e0")
        t4.grid(row=1, column=0, padx=8, pady=8)
        
        # Tile 5: Sample dataset (Yellow, small)
        t5 = ctk.CTkButton(grid_f, text=t("home_sample_dataset"), font=ctk.CTkFont(size=14, weight="bold"), fg_color=YELLOW, text_color="black", width=150, height=80, corner_radius=0, border_width=3, border_color=INK, hover_color="#d4a017")
        t5.grid(row=1, column=1, padx=8, pady=8, sticky="w")
        
        # Micro-motion stagger 2
        tiles = [t1, t2, t3, t4, t5]
        for idx, t_btn in enumerate(tiles):
            t_btn.grid_remove()
            self.after(100 + (idx * 60), t_btn.grid)

        return frame
"""

if "_build_tab_home" not in content:
    content = content.replace(
        "def _build_tab_import(self) -> ctk.CTkFrame:",
        HOME_TAB + "\n    def _build_tab_import(self) -> ctk.CTkFrame:"
    )

# The blink - status square 
BLINK = """
    def blink_status(self):
        try:
            settings_path = os.path.join(os.path.dirname(__file__), ".blicsa_settings.json")
            if os.path.exists(settings_path):
                import json
                s = json.load(open(settings_path))
                if s.get("reduce_animations"): return
        except: pass
        if hasattr(self, '_status_square'):
            orig_h = self._status_square.winfo_height()
            self._status_square.configure(height=2)
            self.after(250, lambda: self._status_square.configure(height=10))
"""
if "def blink_status" not in content:
    content = content.replace("def _set_idle(self, msg: str = \"\"):", BLINK + "\n    def _set_idle(self, msg: str = \"\"):")
    content = content.replace("self._status_lbl.configure(text=msg)", "self._status_lbl.configure(text=msg)\n        if msg == 'Concluído' or 'Sucesso' in msg: self.blink_status()")

# Status square in sidebar
SQUARE = """
        self._status_square = ctk.CTkFrame(sb, width=10, height=10, fg_color=BLUE, corner_radius=0)
        self._status_square.grid(row=10, column=0, padx=(16, 0), pady=(0, 2), sticky="sw")
        self._status_lbl.grid(row=10, column=0, padx=(32, 16), pady=(0, 2), sticky="sew")
"""
if "_status_square" not in content:
    content = content.replace('self._status_lbl.grid(row=10, column=0, padx=16, pady=(0, 2), sticky="sew")', SQUARE)

with open('main.py', 'w') as f:
    f.write(content)
