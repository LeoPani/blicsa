import sys
import os

__version__ = "1.1.0-beta"

try:
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
except Exception:
    pass
import json
import threading
import webbrowser
import tempfile
from pathlib import Path
from collections import Counter
import networkx as nx
import pandas as pd

import customtkinter as ctk
from core.i18n import t
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD as _TkDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from core.parsers import BibliometricParser, find_duplicates
from core.matrix_builders import NetworkGenerator, CLUSTER_PALETTE
from core.visualizer import compute_fa2_layout, build_plotly_map, build_plotly_density, export_plotly_html, export_figure_image, build_thematic_map, build_historiograph
from core.nlp import load_thesaurus
from ai.client import GroqBibliometricAnalyst

from ui.design_tokens import SIDEBAR_BG, CONTENT_BG, CARD_BG, CARD2_BG, ACCENT, ACCENT_HOV, TEXT_MUTED, MUTED, BLUE, YELLOW, RED, INK, PAPER, RED_HOV, RED_HOVER, WHITE_CARD, INK_HOV, BLUE_HOV, YELLOW_HOV
from ui.styles import get_color, LogWriter
from ui.components import DeduplicationDialog, TrendChartWindow, VerificationDialog, MapCanvas, BurstDetectionWindow, HoverTooltip

# Force light mode globally since we use a custom light theme (Paper & Ink)
ctk.set_appearance_mode("Light")

OUTPUT_DIR  = Path(__file__).parent
MAP_PATH    = str(OUTPUT_DIR / "blicsa_mapa.html")
PLOTLY_PATH = str(OUTPUT_DIR / "blicsa_plotly.html")

MAP_TYPES = [
    "Coocorrência de Palavras-chave",
    "Coautoria",
    "Cocitação de Referências",
    "Acoplamento Bibliográfico",
    "Citação Direta (paper→paper)",
    "Co-classificação IPC (patentes)",
    "Agrupamento Semântico (Embeddings)",
]
VIZ_MODES  = [
    "Clusters", "Grau (Degree)", "Ano Médio",
    "Betweenness", "PageRank",
    "Densidade (matplotlib)", "Densidade (Plotly)",
]
FIELD_OPTS = [
    ("Palavras-chave (Author Keywords)", "keywords"),
    ("Títulos",                          "titles"),
    ("Resumos",                          "abstracts"),
    ("Títulos + Resumos",                "titles_abstracts"),
]

# ── Main App ───────────────────────────────────────────────────────────────────
class BlicsaApp(ctk.CTk):
    """
    Main application window and controller for the Blicsa UI.
    
    This class inherits from customtkinter.CTk and acts as the central hub
    managing all tabs (home, import, corpus, analyses, export), UI state,
    and background worker threads for data loading, search, and AI integration.
    """
    def __init__(self):
        super().__init__()
        self.title("Blicsa — Inteligência Bibliométrica")
        self.geometry("1380x880")
        self.minsize(1100, 700)
        self.resizable(True, True)
        self.configure(fg_color=CONTENT_BG)

        self._file_paths: list[str]              = []
        self._file_formats: list[str]            = []
        self._dataframe                          = None
        self._generator: NetworkGenerator | None = None
        self._positions: dict                    = {}
        
        self._start_local_server()
        
        self._map_canvas: MapCanvas | None       = None
        self._thesaurus: dict[str, str]          = {}
        self._thesaurus_path: str | None         = None
        self._candidate_counts: Counter          = Counter()
        self._candidate_scores: dict             = {}
        self._cluster_labels: dict[int, str]     = {}
        self._max_edge_weight: float             = 1.0

        # Configuration variables
        self._map_type_var = ctk.StringVar(value=MAP_TYPES[0])
        self._field_var = ctk.StringVar(value="keywords")
        self._counting_var = ctk.StringVar(value="full")
        self._assoc_var = ctk.BooleanVar(value=True)
        self._min_occ_var = ctk.IntVar(value=3)
        self._max_nodes_var = ctk.StringVar(value="0")
        self._max_pct_var = ctk.StringVar(value="")
        self._fa2_iter_var = ctk.IntVar(value=500)
        self._linlog_var = ctk.BooleanVar(value=False)
        self._viz_mode_var = ctk.StringVar(value=VIZ_MODES[0])
        self._year_min_var = ctk.StringVar(value="")
        self._year_max_var = ctk.StringVar(value="")
        self._extra_sw_var = ctk.StringVar(value="")
        self._plotly_mode_var = ctk.StringVar(value="cluster")
        self._api_key_var = ctk.StringVar(value=os.environ.get("AI_API_KEY", os.environ.get("GROQ_API_KEY", "")))
        self._ai_provider_var = ctk.StringVar(value=os.environ.get("AI_PROVIDER", "groq"))
        self._ai_base_url_var = ctk.StringVar(value=os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1"))
        self._ai_model_var = ctk.StringVar(value=os.environ.get("AI_MODEL", "llama-3.3-70b-versatile"))
        self._show_ai_modal = False
        self._prune_isolated_var = ctk.BooleanVar(value=True)
        self._prune_largest_var = ctk.BooleanVar(value=False)
        self._cluster_alg_var = ctk.StringVar(value="louvain")
        self._cluster_res_var = ctk.DoubleVar(value=1.0)

        self._build_layout()
        if hasattr(self, '_log_box'):
            sys.stdout = LogWriter(self._log_box)
        self._setup_dnd()
        self._setup_shortcuts()

    def _start_local_server(self):
        import http.server
        import socketserver
        import threading
        import socket
        
        if hasattr(self, '_local_server_port'): return
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        self._local_server_port = s.getsockname()[1]
        s.close()
        
        def serve():
            try:
                # Python 3.7+ SimpleHTTPRequestHandler directory argument
                class Handler(http.server.SimpleHTTPRequestHandler):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)
                with socketserver.TCPServer(("127.0.0.1", self._local_server_port), Handler) as httpd:
                    httpd.serve_forever()
            except Exception as e:
                print(f"[HTTP Server] Error: {e}")
                
        threading.Thread(target=serve, daemon=True).start()
        print(f"[HTTP Server] Started at http://127.0.0.1:{self._local_server_port} serving {OUTPUT_DIR}")

    # ── Skeleton ───────────────────────────────────────────────────────
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        self._content = ctk.CTkFrame(self, fg_color=CONTENT_BG, corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        self._tabs: dict[str, ctk.CTkFrame] = {
            "home":    self._build_tab_home(),
            "import":  self._build_tab_import(),
            "review":  self._build_tab_review(),
            "corpus":  self._build_tab_corpus(),
            "stats":   self._build_tab_stats(),
            "analises": self._build_tab_analises(),
            "galeria":  self._build_tab_gallery(),
            "export":  self._build_tab_export(),
        }
        self._switch_tab("home")

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=SIDEBAR_BG, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(9, weight=1)

        try:
            from PIL import Image
            logo_img = ctk.CTkImage(light_image=Image.open("assets/branding/blicsa-logo-horizontal.png"), size=(180, 48))
            ctk.CTkLabel(sb, image=logo_img, text="").grid(row=0, column=0, padx=16, pady=(30, 22), sticky="w")
        except:
            ctk.CTkLabel(sb, text="Blicsa",
                         font=ctk.CTkFont(size=34, weight="bold"),
                         text_color=ACCENT).grid(
                row=0, column=0, padx=22, pady=(30, 22), sticky="w")

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self._nav_icons: dict[str, tuple] = {}
        
        from PIL import Image
        for i, (key, icon_name, label_text) in enumerate([
            ("home",    "sparkle", "Blink"),
            ("import",  "magnet", "Coletar"),
            ("corpus",  "stack", "Corpus"),
            ("stats",   "chart", "Estatísticas"),
            ("analises", "chart", "Análises"),
            ("galeria", "stack", "Galeria"),
            ("export",  "export", "Exportar"),
        ], start=1):
            try:
                img_normal = ctk.CTkImage(light_image=Image.open(f"assets/icons/{icon_name}.png"), size=(20, 20))
                img_active = ctk.CTkImage(light_image=Image.open(f"assets/icons/{icon_name}_active.png"), size=(20, 20))
                self._nav_icons[key] = (img_normal, img_active)
                image_arg = img_normal
            except Exception:
                self._nav_icons[key] = (None, None)
                image_arg = None
                
            btn = ctk.CTkButton(
                sb, text=f" {label_text}", anchor="w", image=image_arg,
                font=ctk.CTkFont(size=14, weight="normal"),
                fg_color="transparent", hover_color="#e0e0e0", text_color=INK,
                corner_radius=0, height=44, border_width=0, border_color=RED,
                command=lambda k=key: self._switch_tab(k)
            )
            btn.grid(row=i, column=0, padx=10, pady=2, sticky="ew")
            
            # Hover micro-interaction (underline)
            def on_enter(e, b=btn):
                b.configure(font=ctk.CTkFont(size=14, weight="bold", underline=True))
            def on_leave(e, b=btn, k=key):
                active = getattr(self, '_current_tab_key', '') == k
                b.configure(font=ctk.CTkFont(size=14, weight="bold" if active else "normal", underline=False))
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            
            self._nav_btns[key] = btn

        # Corpus Badge at bottom of sidebar
        self._corpus_badge = ctk.CTkLabel(sb, text="Nenhum corpus", text_color=MUTED, font=ctk.CTkFont(size=11))
        self._corpus_badge.grid(row=8, column=0, padx=16, pady=(10, 5), sticky="sw")
        
        try:
            gear_img = ctk.CTkImage(light_image=Image.open("assets/icons/gear.png"), size=(16, 16))
        except: gear_img = None
        self._settings_btn = ctk.CTkButton(sb, text=" Configurações" if gear_img else "⚙️ Configurações", image=gear_img, anchor="w", font=ctk.CTkFont(size=11), fg_color="transparent", hover_color="#e0e0e0", text_color=INK, corner_radius=0, height=32, border_width=1, border_color=INK, command=self._show_settings)
        self._settings_btn.grid(row=10, column=0, padx=16, pady=(0, 10), sticky="ew")

        self._status_square = ctk.CTkFrame(sb, width=10, height=10, fg_color=BLUE, corner_radius=0)
        self._status_square.grid(row=11, column=0, padx=(16, 0), pady=(0, 2), sticky="sw")
        self._status_lbl = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._status_lbl.grid(row=11, column=0, padx=(32, 16), pady=(0, 2), sticky="sew")

        self._progress_bar = ctk.CTkProgressBar(sb, mode="indeterminate", height=5, progress_color=YELLOW, fg_color=PAPER, border_width=1, border_color=INK, corner_radius=0)
        self._progress_bar.grid(row=12, column=0, padx=16, pady=(0, 8), sticky="sew")
        self._progress_bar.grid_remove()

        self._about_btn = ctk.CTkButton(sb, text="v3.0 • Blicsa Engine", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED, fg_color="transparent", hover_color="#e0e0e0", corner_radius=0, command=self._show_about)
        self._about_btn.grid(row=13, column=0, padx=22, pady=(0, 16), sticky="sw")

    # ── Drag-and-drop ──────────────────────────────────────────────────
    def _setup_dnd(self):
        if not _DND_AVAILABLE:
            return
        try:
            _TkDnD._require(self)
            self._file_list_frame.drop_target_register(DND_FILES)
            self._file_list_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        import re as _re
        raw = event.data or ""
        # tkinterdnd2 wraps paths with braces on macOS/Windows for spaces
        paths = _re.findall(r"\{([^}]+)\}|(\S+)", raw)
        paths = [p[0] or p[1] for p in paths]
        for path in paths:
            path = path.strip()
            if path and path not in self._file_paths:
                fmt = self._auto_detect_format(path)
                self._file_paths.append(path)
                self._file_formats.append(fmt)
                self._add_file_row(path, fmt)

    # ── Keyboard shortcuts ─────────────────────────────────────────────
    def _setup_shortcuts(self):
        self.bind_all("<Control-g>", lambda _: self._run_mapping())
        self.bind_all("<Control-G>", lambda _: self._run_mapping())
        self.bind_all("<Control-e>", lambda _: self._switch_tab("export"))
        self.bind_all("<Control-E>", lambda _: self._switch_tab("export"))
        self.bind_all("<Control-i>", lambda _: self._run_ai())
        self.bind_all("<Control-I>", lambda _: self._run_ai())
        self.bind_all("<Control-r>", lambda _: self._reset_view())
        self.bind_all("<Control-R>", lambda _: self._reset_view())
        self.bind_all("<Control-f>", lambda _: self._switch_tab("home"))
        self.bind_all("<Control-F>", lambda _: self._switch_tab("home"))
        self.bind_all("<Escape>",    lambda _: self._reset_view())

    def _set_busy(self, msg: str = "Processando…"):
        self._status_lbl.configure(text=msg)
        if msg == 'Concluído' or 'Sucesso' in msg: self.blink_status()
        self._progress_bar.grid()
        self._progress_bar.start()

    
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

    
    
    def _show_settings(self):
        import tkinter as tk
        from PIL import Image, ImageTk
        
        dlg = tk.Toplevel(self)
        dlg.title(t("menu_settings"))
        dlg.geometry("400x300")
        dlg.configure(bg="#F6F4EE")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.tk.eval('tk::PlaceWindow %s center' % dlg)
        
        f = tk.Frame(dlg, bg="#141414")
        f.pack(fill="both", expand=True)
        content = tk.Frame(f, bg="#F6F4EE")
        content.pack(fill="both", expand=True, padx=3, pady=3)
        
        tk.Label(content, text=t("menu_settings"), font=("Arial", 16, "bold"), bg="#F6F4EE", fg="#141414").pack(pady=(20, 10))
        
        # Animations toggle
        import os, json
        s_path = os.path.join(os.path.dirname(__file__), ".blicsa_settings.json")
        reduce = False
        if os.path.exists(s_path):
            try: reduce = json.load(open(s_path)).get("reduce_animations", False)
            except: pass
            
        import customtkinter as ctk
        var = ctk.BooleanVar(value=reduce)
        def toggle():
            s = {}
            if os.path.exists(s_path):
                try: s = json.load(open(s_path))
                except: pass
            s["reduce_animations"] = var.get()
            json.dump(s, open(s_path, "w"))
            
        chk = ctk.CTkCheckBox(content, text=t("reduce_animations"), variable=var, command=toggle, text_color="#141414", fg_color="#DF3117", hover_color="#B82813", corner_radius=0)
        chk.pack(pady=10)
        
        # Flags
        flag_f = tk.Frame(content, bg="#F6F4EE")
        flag_f.pack(pady=10)
        def set_l(l):
            from core.i18n import set_lang
            set_lang(l)
            self._refresh_language()
            dlg.destroy()
            
        try:
            for i, (l, f_name) in enumerate([("pt_BR", "flag-pt-br.png"), ("en", "flag-en.png"), ("fr", "flag-fr.png"), ("de", "flag-de.png")]):
                img = ImageTk.PhotoImage(Image.open(f"assets/branding/{f_name}").resize((32, 22)))
                btn = tk.Button(flag_f, image=img, command=lambda x=l: set_l(x), bg="#F6F4EE", relief="flat", bd=2, highlightbackground="#141414")
                btn.image = img
                btn.grid(row=0, column=i, padx=5)
        except:
            pass
            
        close = tk.Button(content, text=t("settings.ok"), command=dlg.destroy, bg="#DF3117", fg="white", relief="flat", highlightbackground="#141414", bd=2)
        close.pack(side="bottom", pady=20)

    def _blink_system_prompt(self) -> str:
        """System prompt do Blink + diretiva dinâmica de idioma (via get_lang())."""
        from core.i18n import get_lang
        base = t("blink.system_prompt")
        lang_names = {"pt_BR": "Brazilian Portuguese", "en": "English", "fr": "French"}
        target = lang_names.get(get_lang(), "English")
        directive = (f"IMPORTANT: Always respond to the user in {target}, "
                     f"regardless of the language of this prompt.")
        return f"{base}\n\n{directive}"

    def _refresh_language(self):
        curr_tab = getattr(self, '_current_tab_key', "home")
        for widget in self.winfo_children():
            widget.destroy()
        self._build_layout()
        import sys
        if hasattr(self, '_log_box'):
            sys.stdout = LogWriter(self._log_box)
        self._setup_shortcuts()
        self._setup_dnd()
        self._switch_tab(curr_tab)

    def _show_about(self):
        import tkinter as tk
        from PIL import Image
        import webbrowser
        
        dlg = tk.Toplevel(self)
        dlg.title(t("menu_about"))
        dlg.geometry("400x350")
        dlg.configure(bg="#F6F4EE")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.tk.eval('tk::PlaceWindow %s center' % dlg)
        
        # 3px ink border
        f = tk.Frame(dlg, bg="#141414")
        f.pack(fill="both", expand=True)
        content = tk.Frame(f, bg="#F6F4EE")
        content.pack(fill="both", expand=True, padx=3, pady=3)
        
        try:
            from PIL import ImageTk
            img = ImageTk.PhotoImage(Image.open("assets/branding/blicsa-logo-horizontal.png").resize((200, 54)))
            lbl = tk.Label(content, image=img, bg="#F6F4EE")
            lbl.image = img
            lbl.pack(pady=(20, 0))
        except:
            tk.Label(content, text="Blicsa", font=("Arial", 24, "bold"), bg="#F6F4EE", fg="#141414").pack(pady=(20, 0))
            
        tk.Label(content, text="just blink", font=("Arial", 12), bg="#F6F4EE", fg="#8A877F").pack(pady=(0, 10))
        tk.Label(content, text="v3.0", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        
        tk.Label(content, text="Desenvolvido por ICSA/UFOP", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        tk.Label(content, text="Licença MIT", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        
        btn_f = tk.Frame(content, bg="#F6F4EE")
        btn_f.pack(side="bottom", fill="x", pady=20, padx=20)
        
        gh = tk.Button(btn_f, text="GitHub", command=lambda: webbrowser.open("https://github.com"), bg="#F6F4EE", fg="#141414", relief="flat", highlightbackground="#141414", bd=2)
        gh.pack(side="left", padx=10)
        
        close = tk.Button(btn_f, text="OK", command=dlg.destroy, bg="#DF3117", fg="white", relief="flat", highlightbackground="#141414", bd=2)
        close.pack(side="right", padx=10)

    def _set_idle(self, msg: str = ""):
        self._progress_bar.stop()
        self._progress_bar.grid_remove()
        self._status_lbl.configure(text=msg)
        if msg == 'Concluído' or 'Sucesso' in msg: self.blink_status()

    def _switch_tab(self, tab_key: str):
        prev = getattr(self, '_current_tab_key', None)
        if prev and prev != tab_key:
            self._previous_tab_key = prev
        self._current_tab_key = tab_key
        
        if hasattr(self, '_blink_back_btn'):
            if tab_key == 'home' and getattr(self, '_previous_tab_key', None):
                self._blink_back_btn.pack(side="right", padx=20)
            else:
                self._blink_back_btn.pack_forget()
        for key, frame in self._tabs.items():
            frame.grid_remove()
        if tab_key in self._tabs:
            if tab_key == "corpus":
                self._refresh_corpus_tab()
            self._tabs[tab_key].grid(row=0, column=0, sticky="nsew")
        
        for k, btn in self._nav_btns.items():
            active = (k == tab_key)
            img_normal, img_active = self._nav_icons.get(k, (None, None))
            btn.configure(
                border_spacing=6 if active else 2, # spacing adjustment for left bar
                border_width=6 if active else 0, 
                font=ctk.CTkFont(size=14, weight="bold" if active else "normal", underline=False),
                image=img_active if active and img_active else img_normal
            )

    def _toggle_theme(self):
        current = ctk.get_appearance_mode().lower()
        new_mode = "light" if current == "dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self._update_treeview_style()
        if self._map_canvas:
            self._map_canvas.update_theme()
            if self._map_canvas._G and self._map_canvas._pos:
                self._map_canvas.render(
                    self._map_canvas._G,
                    self._map_canvas._pos,
                    mode=self._map_canvas._last_mode,
                    node_scale=self._map_canvas._node_scale,
                    edge_opacity=self._map_canvas._edge_opacity,
                    edge_threshold=self._map_canvas._edge_threshold,
                )

    def _update_treeview_style(self):
        _ts = ttk.Style()
        _ts.theme_use("default")
        bg_col = get_color(CARD2_BG)
        fg_col = "black" if ctk.get_appearance_mode().lower() == "light" else "#e0e0e0"
        header_bg = get_color(CARD_BG)
        sel_bg = "#b0c4de" if ctk.get_appearance_mode().lower() == "light" else "#2a2a5a"
        sel_fg = "black" if ctk.get_appearance_mode().lower() == "light" else "white"

        _ts.configure("Blicsa.Treeview",
            background=bg_col,
            fieldbackground=bg_col,
            foreground=fg_col,
            rowheight=28,
            font=("Inter", 11),
            borderwidth=0,
        )
        _ts.configure("Blicsa.Treeview.Heading",
            background=header_bg,
            foreground=ACCENT,
            font=("Inter", 11, "bold"),
            relief="flat",
            padding=(0, 5)
        )
        _ts.map("Blicsa.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        
        _ts.map("Blicsa.Treeview.Heading",
            background=[("active", ACCENT_HOV)],
        )

    # ── UI helpers ─────────────────────────────────────────────────────
    def _tab(self) -> ctk.CTkFrame:
        f = ctk.CTkFrame(self._content, fg_color=CONTENT_BG)
        f.grid_columnconfigure(0, weight=1)
        return f

    def _card(self, parent, row: int, pady: int = 8) -> ctk.CTkFrame:
        c = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=0)
        c.grid(row=row, column=0, padx=24, pady=pady, sticky="nsew")
        c.grid_columnconfigure(0, weight=1)
        return c

    def _h1(self, parent, text: str, row: int):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=row, column=0, padx=28, pady=(18, 4), sticky="w")

    def _btn(self, parent, text: str, cmd,
             color=ACCENT, hover=ACCENT_HOV,
             height: int = 44, **kw) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, height=height,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=color, hover_color=hover,
            text_color="#000" if color == ACCENT else "white",
            command=cmd, **kw)

    def _add_blink_message(self, role, text=""):
        from core.markdown_parser import configure_markdown_tags, insert_markdown
        row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
        row.pack(fill="x", pady=5)
        
        from ui.design_tokens import BLUE, WHITE_CARD, INK
        bubble = ctk.CTkFrame(row, fg_color=BLUE if role == "user" else WHITE_CARD, corner_radius=0, border_width=0 if role == "user" else 2, border_color=INK)
        bubble.pack(side="right" if role == "user" else "left", padx=10, pady=2)
        
        tb = ctk.CTkTextbox(bubble, wrap="word", font=ctk.CTkFont(size=14), fg_color="transparent", text_color=WHITE_CARD if role == "user" else INK, corner_radius=0, width=550)
        tb.pack(padx=10, pady=10)
        
        if role == "assistant":
            configure_markdown_tags(tb)
            
        if text:
            if role == "assistant":
                insert_markdown(tb, text)
            else:
                tb.insert("end", text)
        tb.configure(state="disabled")
        
        def update_height():
            try:
                lines = tb._textbox.count("1.0", "end", "displaylines")
                if lines:
                    tb.configure(height=lines[0] * 22 + 20)
            except:
                tb.configure(height=(tb.get("1.0", "end").count('\n') + 1) * 22 + 20)
            self._research_chat_history_main._parent_canvas.yview_moveto(1.0)
            
        tb.after(50, update_height)
        return tb, update_height, row

    # ── Tab: Importação ────────────────────────────────────────────────
    def _build_tab_home(self) -> ctk.CTkFrame:
        from ui.design_tokens import WHITE_CARD, MUTED, INK, RED, RED_HOV, PAPER, BLUE, ACCENT, ACCENT_HOV
        from PIL import Image
        frame = self._tab()
        
        # Top Strip for Flags
        top_strip = ctk.CTkFrame(frame, fg_color="transparent")
        top_strip.pack(fill="x", padx=24, pady=(24, 16))
        
        flag_f = ctk.CTkFrame(top_strip, fg_color="transparent")
        flag_f.pack(side="right")
        
        def set_l(l):
            from core.i18n import set_lang
            set_lang(l)
            self._refresh_language()
            
        try:
            for i, (l, f_name) in enumerate([("pt_BR", "flag-pt-br.png"), ("en", "flag-en.png"), ("fr", "flag-fr.png"), ("de", "flag-de.png")]):
                img = ctk.CTkImage(light_image=Image.open(f"assets/branding/{f_name}"), size=(32, 22))
                btn = ctk.CTkButton(flag_f, image=img, text="", width=32, height=22, fg_color="transparent", corner_radius=0, border_width=2, border_color=INK, hover_color="#e0e0e0", command=lambda x=l: set_l(x))
                btn.grid(row=0, column=i, padx=4)
        except:
            pass

        # Chat Interface
        chat_container = ctk.CTkFrame(frame, fg_color="transparent")
        chat_container.pack(fill="both", expand=True, padx=40, pady=20)
        
        title_f = ctk.CTkFrame(chat_container, fg_color="transparent")
        title_f.pack(pady=(0, 20), fill="x")
        
        lbl_f = ctk.CTkFrame(title_f, fg_color="transparent")
        lbl_f.pack(side="left")
        ctk.CTkLabel(lbl_f, text=t("blink.titulo_1"), font=ctk.CTkFont(size=32, weight="bold"), text_color=INK).pack(side="left")
        ctk.CTkLabel(lbl_f, text=t("blink.titulo_destaque"), font=ctk.CTkFont(size=32, weight="bold"), text_color=RED).pack(side="left")
        ctk.CTkLabel(lbl_f, text=t("blink.titulo_2"), font=ctk.CTkFont(size=32, weight="bold"), text_color=INK).pack(side="left")
        
        def _go_back():
            if hasattr(self, '_previous_tab_key') and self._previous_tab_key:
                self._switch_tab(self._previous_tab_key)
                
        self._blink_back_btn = ctk.CTkButton(title_f, text=t("blink.voltar"), width=80, height=30, fg_color="#E0E0E0", text_color=INK, hover_color="#C0C0C0", command=_go_back)
        
        self._research_chat_history_main = ctk.CTkScrollableFrame(chat_container, fg_color="transparent")
        self._research_chat_history_main.pack(fill="both", expand=True, pady=(0, 20))
        from core.markdown_parser import configure_markdown_tags, insert_markdown
        
        self._research_messages = [{"role": "system", "content": self._blink_system_prompt()}]


        self._add_blink_message("assistant", t("blink.saudacao"))

        input_f = ctk.CTkFrame(chat_container, fg_color="transparent")
        input_f.pack(fill="x", pady=(0, 20))

        self._research_chat_input_main = ctk.CTkEntry(input_f, placeholder_text=t("blink.placeholder"), placeholder_text_color=MUTED, font=ctk.CTkFont(size=14), fg_color=WHITE_CARD, text_color=INK, height=44, corner_radius=0, border_width=2, border_color=INK)
        self._research_chat_input_main.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def send_main_chat(e=None):
            msg = self._research_chat_input_main.get().strip()
            if not msg: return
            self._research_chat_input_main.delete(0, "end")
            
            self._add_blink_message("user", msg)
            
            system_prompt = self._blink_system_prompt()
            if self._dataframe is not None and not self._dataframe.empty:
                try:
                    from sklearn.feature_extraction.text import TfidfVectorizer
                    from sklearn.metrics.pairwise import cosine_similarity
                    df = self._dataframe.dropna(subset=['abstract'])
                    if not df.empty:
                        docs = df['abstract'].astype(str).tolist()
                        vectorizer = TfidfVectorizer(stop_words='english')
                        tfidf_matrix = vectorizer.fit_transform(docs)
                        query_vec = vectorizer.transform([msg])
                        sims = cosine_similarity(query_vec, tfidf_matrix).flatten()
                        top_indices = sims.argsort()[-5:][::-1]
                        
                        abstracts = []
                        for idx in top_indices:
                            if sims[idx] > 0.01:
                                row = df.iloc[idx]
                                title = row.get("title", "")
                                abs_txt = str(row.get("abstract", ""))[:300]
                                abstracts.append(f"Title: {title}\\nAbstract: {abs_txt}...")
                        
                        if abstracts:
                            ctx = "\\n\\n---\\n".join(abstracts)
                            system_prompt += f"\\n\\n{t('blink.rag_contexto')}\\n{ctx}"
                except Exception as ex:
                    print(f"[Blink RAG] Error: {ex}")
            
            system_prompt = system_prompt[:4000]
            self._research_messages[0] = {"role": "system", "content": system_prompt}
            self._research_messages.append({"role": "user", "content": msg})
            
            # Indicator
            indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
            indicator_row.pack(fill="x", pady=5)
            indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
            indicator.pack(side="left", padx=14, pady=14)
            
            def pulse_indicator():
                if indicator.winfo_exists():
                    current = indicator.cget("fg_color")
                    indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                    indicator.after(400, pulse_indicator)
            pulse_indicator()
            self._research_chat_history_main._parent_canvas.yview_moveto(1.0)
            
            import threading
            def worker():
                try:
                    from ai.client import AIAnalyst
                    analyst = AIAnalyst(api_key=self._api_key_var.get() or None, base_url=self._ai_base_url_var.get(), model=self._ai_model_var.get())
                    stream = analyst.chat_history_stream(self._research_messages, temperature=0.7)
                    
                    full_response = ""
                    tb_ref = []
                    
                    for chunk in stream:
                        full_response += chunk
                        
                        def update_chunk(resp=full_response):
                            if indicator_row.winfo_exists():
                                indicator_row.destroy()
                            if not tb_ref:
                                tb, upd, _ = self._add_blink_message("assistant", "")
                                tb_ref.append((tb, upd))
                            
                            tb, upd = tb_ref[0]
                            tb.configure(state="normal")
                            tb.delete("1.0", "end")
                            insert_markdown(tb, resp)
                            tb.configure(state="disabled")
                            upd()
                        self.after(0, update_chunk)
                    
                    self._research_messages.append({"role": "assistant", "content": full_response})
                except Exception as ex:
                    if indicator_row.winfo_exists(): indicator_row.destroy()
                    def err_ui():
                        self._add_blink_message("assistant", f"{t('blink.erro')} {ex}")
                    self.after(0, err_ui)
            threading.Thread(target=worker, daemon=True).start()
            
        self._research_chat_input_main.bind("<Return>", send_main_chat)
        ctk.CTkButton(input_f, text=t("blink.enviar"), font=ctk.CTkFont(size=14, weight="bold"), fg_color=RED, text_color="white", hover_color=RED_HOV, corner_radius=0, border_width=2, border_color=INK, height=44, width=100, command=send_main_chat).pack(side="right")
        
        # Suggestions
        sug_f = ctk.CTkFrame(chat_container, fg_color="transparent")
        sug_f.pack(fill="x")
        
        sugs = [
            t("blink.sugestao_1"),
            t("blink.sugestao_2"),
            t("blink.sugestao_3"),
        ]
        
        for i, s_txt in enumerate(sugs):
            btn = ctk.CTkButton(sug_f, text=s_txt, font=ctk.CTkFont(size=12), fg_color=PAPER, text_color=INK, hover_color="#e0e0e0", corner_radius=0, border_width=1, border_color=INK, command=lambda txt=s_txt: self._research_chat_input_main.insert(0, txt) or send_main_chat())
            btn.pack(side="left", padx=(0, 10))
            
        return frame

    def _build_tab_projects(self) -> ctk.CTkFrame:
        from ui.projects_view import ProjectsView
        frame = ctk.CTkFrame(self._main_content, fg_color="transparent")
        
        def on_open_project(path):
            self.after(0, lambda: self._load_project_file(path))
            
        self._projects_view = ProjectsView(frame, on_open_project)
        self._projects_view.pack(fill="both", expand=True)
        return frame
        
    def _build_tab_import(self) -> ctk.CTkFrame:
        frame = self._tab()
        
        # Search Card (Top)
        scard = self._card(frame, 0)
        scard.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(scard, text="Busca Online", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")
            
        self._search_provider_var = ctk.StringVar(value="openalex")
        sp_f = ctk.CTkFrame(scard, fg_color="transparent")
        sp_f.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="w")
        for lbl, val in [("Todas as Bases", "all"), ("OpenAlex", "openalex"), ("Crossref", "crossref"), ("PubMed", "pubmed"), ("Zotero", "zotero")]:
            ctk.CTkRadioButton(sp_f, text=lbl, variable=self._search_provider_var,
                               value=val, fg_color=ACCENT, hover_color=ACCENT_HOV).pack(side="left", padx=8)
                               
        self._search_query_entry = ctk.CTkEntry(scard, placeholder_text="Termo / Query (ex: 'deep learning')", placeholder_text_color=MUTED, height=36, fg_color=WHITE_CARD, text_color=INK)
        self._search_query_entry.grid(row=2, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        
        act_sf = ctk.CTkFrame(scard, fg_color="transparent")
        act_sf.grid(row=3, column=0, columnspan=2, padx=16, pady=(4, 16), sticky="e")
        
        ctk.CTkLabel(act_sf, text="Qtd:").pack(side="left", padx=4)
        self._search_max_entry = ctk.CTkEntry(act_sf, width=60, placeholder_text="100", placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK)
        self._search_max_entry.insert(0, "100")
        self._search_max_entry.pack(side="left", padx=4)
        
        self._search_unlimited_var = ctk.BooleanVar(value=True)
        self._search_unlimited_chk = ctk.CTkCheckBox(act_sf, text="Ilimitado", variable=self._search_unlimited_var, width=50, 
                                                     command=lambda: self._search_max_entry.configure(state="disabled" if self._search_unlimited_var.get() else "normal"))
        self._search_unlimited_chk.pack(side="left", padx=4)
        self._search_max_entry.configure(state="disabled")
        
        self._btn(act_sf, "⚙ Avançada", self._open_query_builder, height=30).pack(side="left", padx=4)
        self._btn(act_sf, "🔍 Buscar", self._on_gui_search, height=30, color=RED, hover=RED_HOV).pack(side="left", padx=4)
        self._btn(act_sf, "✨ Blink", self._trigger_import_ai_assistant, height=30, color=YELLOW, hover=YELLOW_HOV).pack(side="left", padx=4)
        
        self._search_cancel_btn = self._btn(act_sf, "✕ Cancelar", self._cancel_search, height=30, color="#E63946", hover="#C12B37")
        self._search_cancel_btn.pack_forget() # Hide initially
        
        filter_f = ctk.CTkFrame(scard, fg_color="transparent")
        filter_f.grid(row=4, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        
        ctk.CTkLabel(filter_f, text="Ano Início:", font=ctk.CTkFont(size=12)).pack(side="left", padx=4)
        self._search_year_start = ctk.CTkEntry(filter_f, width=60, placeholder_text="Ex: 2018", placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK)
        self._search_year_start.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Ano Fim:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_year_end = ctk.CTkEntry(filter_f, width=60, placeholder_text="Ex: 2024", placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK)
        self._search_year_end.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Tipo:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_type_var = ctk.StringVar(value="Todos")
        self._search_type = ctk.CTkOptionMenu(filter_f, variable=self._search_type_var, fg_color=WHITE_CARD, text_color=INK, button_color=WHITE_CARD, button_hover_color=CARD2_BG,
                                              values=["Todos", "article", "review", "book-chapter", "dataset"], width=100)
        self._search_type.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Idioma:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_lang_var = ctk.StringVar(value="Todos")
        self._search_lang = ctk.CTkOptionMenu(filter_f, variable=self._search_lang_var, fg_color=WHITE_CARD, text_color=INK, button_color=WHITE_CARD, button_hover_color=CARD2_BG,
                                              values=["Todos", "en", "pt", "es", "fr", "de"], width=70)
        self._search_lang.pack(side="left", padx=4)
        # BUG-02: no Crossref o filtro de idioma é aplicado localmente (a API não é confiável nisso).
        ctk.CTkLabel(filter_f, text="ⓘ Crossref: local", font=ctk.CTkFont(size=10), text_color=MUTED).pack(side="left", padx=(2,4))
        
        self._search_oa_var = ctk.BooleanVar(value=False)
        self._search_oa_chk = ctk.CTkCheckBox(filter_f, text="Apenas Open Access", variable=self._search_oa_var, font=ctk.CTkFont(size=12), width=20)
        self._search_oa_chk.pack(side="left", padx=(10,4))

        # File Import Hero Zone (Bottom)
        fcard = self._card(frame, 1)
        fcard.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(fcard, text="Arraste arquivos ou clique", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=16, pady=(16, 8), sticky="w")
            
        list_frame = ctk.CTkFrame(fcard, fg_color=CARD2_BG, corner_radius=0)
        list_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=(8, 16), sticky="ew")
        list_frame.grid_columnconfigure(0, weight=1)
        self._file_list_frame = ctk.CTkScrollableFrame(list_frame, fg_color=CARD2_BG, height=100)
        self._file_list_frame.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        self._file_list_frame.grid_columnconfigure(0, weight=1)
        self._file_row_widgets = []
        self._file_list_frame.grid_remove() # Hide initially
        
        fbf = ctk.CTkFrame(fcard, fg_color="transparent")
        fbf.grid(row=1, column=2, padx=12, pady=(8, 16), sticky="n")
        self._btn(fbf, "➕  Adicionar Arquivos", self._pick_file, height=36).pack(pady=(0, 6))
        self._btn(fbf, "🗑  Limpar Tudo", self._clear_files, color="#4a1a1a", hover="#6a2a2a", height=36).pack()
        
        act_f = ctk.CTkFrame(fcard, fg_color="transparent")
        act_f.grid(row=2, column=0, columnspan=3, padx=16, pady=(12, 16), sticky="ew")
        act_f.grid_columnconfigure((0, 1, 2), weight=1)
        
        self._btn(act_f, "⚡  Carregar e Combinar", self._load_data, height=40, color=RED, hover=RED_HOV).grid(
            row=0, column=0, padx=(0, 4), sticky="ew")
        self._btn(act_f, "🔍  Deduplicar", self._run_dedup, height=40,
                  color=INK, hover=INK_HOV).grid(
            row=0, column=1, padx=4, sticky="ew")
        self._btn(act_f, "📂  Abrir Projeto (.blicsa)", self._load_project_gui, height=40,
                  color=BLUE, hover=BLUE_HOV).grid(
            row=0, column=2, padx=(4, 0), sticky="ew")

        # The Log is now in toasts, so no need for log box here
        # But wait, self._log_box was used for sys.stdout redirection and background thread logs.
        # So I will create a hidden log_box to avoid exceptions from LogWriter.
        self._log_box = ctk.CTkTextbox(frame)
        self._log_box.grid_forget()

        return frame

    def _build_tab_review(self) -> ctk.CTkFrame:
        f = self._tab()
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        
        self._h1(f, "Revisar Resultados", 0)
        
        # Header counts
        self._review_counts_lbl = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED)
        self._review_counts_lbl.grid(row=0, column=0, padx=28, pady=4, sticky="e")
        
        # Main container with filter sidebar and cards
        main_c = ctk.CTkFrame(f, fg_color="transparent")
        main_c.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        main_c.grid_columnconfigure(1, weight=1)
        main_c.grid_rowconfigure(0, weight=1)
        
        # Left Filters
        flt_sidebar = ctk.CTkFrame(main_c, width=200, fg_color=CARD_BG, corner_radius=0)
        flt_sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        flt_sidebar.grid_propagate(False)
        ctk.CTkLabel(flt_sidebar, text="Filtros", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        
        # Right Feed
        self._review_feed = ctk.CTkScrollableFrame(main_c, fg_color=CARD2_BG)
        self._review_feed.grid(row=0, column=1, sticky="nsew")
        
        # Bottom Bar
        bb = ctk.CTkFrame(f, height=60, fg_color=CARD_BG, corner_radius=0)
        bb.grid(row=2, column=0, sticky="ew")
        bb.grid_columnconfigure(0, weight=1)
        
        self._review_selected_lbl = ctk.CTkLabel(bb, text="0 selecionados", font=ctk.CTkFont(size=14, weight="bold"))
        self._review_selected_lbl.grid(row=0, column=0, padx=20, sticky="w")
        
        self._btn(bb, "Importar para o Corpus", lambda: self._switch_tab("corpus"), height=40, color=RED).grid(row=0, column=1, padx=20, pady=10, sticky="e")
        
        return f

    # ── Tab: Mapa & IA ─────────────────────────────────────────────────
    def _build_tab_viz(self, parent=None) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent if parent else self._content, fg_color="transparent", corner_radius=0)
        # Col 0 (left config sidebar, fixed), Col 1 (middle canvas, expanding)
        frame.grid_columnconfigure(0, weight=0, minsize=280)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        
        # ── Left Config Sidebar ──
        config_panel = ctk.CTkFrame(frame, width=280, fg_color=CARD_BG, corner_radius=0)
        config_panel.grid(row=0, column=0, padx=(20, 6), pady=16, sticky="nsew")
        config_panel.grid_propagate(False)
        config_panel.grid_columnconfigure(0, weight=1)
        config_panel.grid_rowconfigure(1, weight=1)
        
        # Title of config sidebar
        ctk.CTkLabel(
            config_panel, text="⚙️ Parâmetros do Mapa",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ACCENT
        ).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")
        
        sc = ctk.CTkScrollableFrame(config_panel, fg_color="transparent")
        sc.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")
        sc.grid_columnconfigure(0, weight=1)
        
        self._build_config_widgets(sc)
        
        # ── Middle Viz Panel ──
        viz_panel = ctk.CTkFrame(frame, fg_color="transparent")
        viz_panel.grid(row=0, column=1, padx=6, pady=16, sticky="nsew")
        viz_panel.grid_columnconfigure(0, weight=1)
        viz_panel.grid_rowconfigure(3, weight=1) # matplotlib canvas gets all vertical height
        
        # Action buttons
        br = ctk.CTkFrame(viz_panel, fg_color=CONTENT_BG)
        br.grid(row=0, column=0, pady=(0, 4), sticky="ew")
        br.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._btn(br, "⚡  Gerar Mapa", self._run_mapping,
                  height=44).grid(row=0, column=0, padx=4, sticky="ew")
        self._btn(br, "✦  Abrir Plotly Interativo",
                  self._open_plotly, color="#1a4a7a",
                  hover="#153a60", height=44).grid(
            row=0, column=1, padx=4, sticky="ew")
        
        def save_plot():
            if not getattr(self, '_graph', None):
                messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
                return
            import os, time, re
            os.makedirs("reports", exist_ok=True)
            
            # Save a bundled Sigma.js map to the gallery
            from core.sigma_exporter import export_sigma_json
            import tempfile
            
            # Temporary path for graph.json
            with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp_json:
                sigma_path = tmp_json.name
            
            export_sigma_json(self._graph, self._positions, sigma_path)
            
            html_template_path = str(OUTPUT_DIR / "assets" / "map_template.html")
            js_path = str(OUTPUT_DIR / "assets" / "map.js")
            
            with open(html_template_path, "r", encoding="utf-8") as f:
                template = f.read()
            with open(js_path, "r", encoding="utf-8") as f:
                map_js = f.read()
            with open(sigma_path, "r", encoding="utf-8") as f:
                graph_json = f.read()
                
            os.remove(sigma_path)
            
            # Replace fetch with inline data robustly
            map_js = re.sub(
                r'const response = await fetch\("graph\.json"\);.*?data = await response\.json\(\);',
                f'data = {graph_json};',
                map_js,
                flags=re.DOTALL
            )
            
            # Inject inline script
            template = template.replace('<script type="module" src="map.js"></script>', f'<script type="module">\n{map_js}\n</script>')
            
            path = f"reports/blicsa_mapa_{int(time.time())}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(template)
                
            messagebox.showinfo("Sucesso", f"Mapa salvo na galeria!\nVerifique a aba Galeria.")
            self._refresh_gallery()

        self._btn(br, "💾  Salvar na Galeria",
                  save_plot,
                  color=RED, hover=RED_HOV, height=44).grid(
            row=0, column=2, padx=4, sticky="ew")
            
        # Removing AI insights button since Blink Research sidebar is preferred
            
        self._btn(br, "🏷️  Nomear Clusters", self._auto_label_clusters,
                  color="#1a5a3a", hover="#144a2e", height=44).grid(
            row=1, column=0, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "📈  Tendências", self._open_trends,
                  color=INK, hover=INK_HOV, height=44).grid(
            row=1, column=1, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "☁  Word Cloud", self._show_wordcloud,
                  color=YELLOW, hover=YELLOW_HOV, height=44).grid(
            row=1, column=2, columnspan=2, padx=4, pady=(4, 0), sticky="ew")

        # Row 2 Actions
        self._btn(br, "📊  Sankey (3 Campos)", self._open_sankey,
                  color="#D4A017", hover="#b88a10", height=44).grid(
            row=2, column=0, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "⏳  Linha do Tempo", self._open_timeline,
                  color="#1a4a7a", hover="#153a60", height=44).grid(
            row=2, column=1, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "💥  Surtos (Bursts)", self._open_bursts,
                  color="#800020", hover="#600018", height=44).grid(
            row=2, column=2, padx=4, pady=(4, 0), sticky="ew")

        # Row 3 Actions
        self._btn(br, "🗺️  Mapa Temático (Callon)", self._open_thematic_map,
                  color="#2A9D8F", hover="#207a6f", height=44).grid(
            row=3, column=0, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "⏳  Historiografia de Citações", self._open_historiograph,
                  color="#E76F51", hover="#c9583c", height=44).grid(
            row=3, column=1, padx=4, pady=(4, 0), sticky="ew")

        # Search + style controls
        ctrl = ctk.CTkFrame(viz_panel, fg_color=CONTENT_BG)
        ctrl.grid(row=1, column=0, pady=(4, 4), sticky="ew")
        
        # Summary Stats
        sc = ctk.CTkFrame(viz_panel, fg_color=CONTENT_BG)
        sc.grid(row=2, column=0, pady=(0, 4), sticky="ew")
        sc.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self._stat_labels = {}
        for col, (key, nice) in enumerate([
            ("total_nodes",     "Nós"),
            ("total_edges",     "Arestas"),
            ("num_clusters",    "Clusters"),
            ("avg_citations",   "Média Cit."),
            ("network_density", "Densidade"),
        ]):
            inner = ctk.CTkFrame(sc, fg_color=CARD2_BG, corner_radius=0)
            inner.grid(row=0, column=col, padx=4, pady=6, sticky="ew")
            v = ctk.CTkLabel(inner, text="—",
                             font=ctk.CTkFont(size=18, weight="bold"),
                             text_color=ACCENT)
            v.pack(pady=(6, 0))
            ctk.CTkLabel(inner, text=nice,
                          font=ctk.CTkFont(size=10),
                          text_color=TEXT_MUTED).pack(pady=(0, 6))
            self._stat_labels[key] = v

        # ── Right IA & Info Panel ──
        info_panel = ctk.CTkFrame(frame, width=340, fg_color=CARD_BG, corner_radius=0)
        info_panel.grid(row=0, column=2, padx=(6, 20), pady=16, sticky="nsew")
        info_panel.grid_propagate(False)
        info_panel.grid_columnconfigure(0, weight=1)
        info_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            info_panel, text="✨ IA & Análise",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ACCENT
        ).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")

        btabs = ctk.CTkTabview(info_panel, fg_color=CARD2_BG,
                               segmented_button_fg_color=CARD_BG,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color=ACCENT_HOV,
                               segmented_button_unselected_color=CARD_BG,
                               text_color=("#000", "white"),
                               text_color_disabled=TEXT_MUTED)
        btabs.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

        ia_tab   = btabs.add("Insights IA")
        seminal_tab = btabs.add("Autores Seminais")
        node_tab = btabs.add("Nó Selecionado")
        ia_tab.grid_rowconfigure(0, weight=1)
        ia_tab.grid_columnconfigure(0, weight=1)
        seminal_tab.grid_rowconfigure(0, weight=1)
        seminal_tab.grid_columnconfigure(0, weight=1)
        node_tab.grid_rowconfigure(0, weight=1)
        node_tab.grid_columnconfigure(0, weight=1)

        self._insights_box = ctk.CTkTextbox(
            ia_tab, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self._insights_box.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self._insights_box.insert("1.0", "Os insights aparecerão aqui após clicar em 'Insights com IA'.")
        self._insights_box.configure(state="disabled")

        self._seminal_box = ctk.CTkTextbox(
            seminal_tab, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self._seminal_box.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self._seminal_box.insert("1.0", "A análise de autores e obras seminais aparecerá aqui após gerar o mapa.")
        self._seminal_box.configure(state="disabled")

        seminal_tab.grid_rowconfigure(0, weight=1)
        seminal_tab.grid_rowconfigure(1, weight=0)
        seminal_tab.grid_columnconfigure(0, weight=1)

        sem_btn_frame = ctk.CTkFrame(seminal_tab, fg_color="transparent")
        sem_btn_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

        ctk.CTkButton(
            sem_btn_frame, text="📂 Criar Pasta da Biblioteca", height=32,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000000",
            font=ctk.CTkFont(weight="bold"), command=self._create_seminal_library
        ).pack(fill="x")

        self._node_info_box = ctk.CTkTextbox(
            node_tab, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self._node_info_box.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self._node_info_box.insert("end", "Clique em um nó no mapa para ver detalhes.")
        self._node_info_box.configure(state="disabled")

        self._bottom_tabs = btabs
        return frame

    def _build_config_widgets(self, sc):
        # 1. Tipo de Mapa
        lbl_tipo = ctk.CTkLabel(sc, text="Tipo de Mapa:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_tipo.pack(anchor="w", padx=10, pady=(8, 2))
        HoverTooltip(lbl_tipo, "O tipo de rede a ser construída.\n- Coocorrência: Itens que aparecem juntos no mesmo artigo.\n- Coautoria: Autores que publicam juntos.\n- Cocitação: Duas referências citadas pelo mesmo artigo.\n- Acoplamento: Artigos que citam as mesmas referências.")
        ctk.CTkComboBox(sc, values=MAP_TYPES, variable=self._map_type_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 2. Campo
        lbl_campo = ctk.CTkLabel(sc, text="Campo:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_campo.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_campo, "A coluna do conjunto de dados a ser extraída.\nPara Coocorrência, Palavras-chave é o padrão.\nPara Coautoria, Autores.\nPara Cocitação, Referências.")
        FIELD_LABELS = [x[0] for x in FIELD_OPTS]
        FIELD_KEYS = [x[1] for x in FIELD_OPTS]
        
        self._field_label_var = ctk.StringVar(value=FIELD_LABELS[0])
        def _on_field_combo(val):
            idx = FIELD_LABELS.index(val)
            self._field_var.set(FIELD_KEYS[idx])
            self._on_field_change()
            
        ctk.CTkComboBox(sc, values=FIELD_LABELS, variable=self._field_label_var, height=28, button_color=ACCENT, border_color=ACCENT, command=_on_field_combo).pack(fill="x", padx=10, pady=(0, 6))
        
        # 3. Método de Contagem
        lbl_contagem = ctk.CTkLabel(sc, text="Contagem:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_contagem.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_contagem, "Full: peso 1 para cada conexão. Fractional: peso diluído pelo número total de conexões no artigo (minimiza o peso de artigos com dezenas de referências).")
        ctk.CTkComboBox(sc, values=["full", "fractional"], variable=self._counting_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 4. Normalização
        chk_assoc = ctk.CTkCheckBox(sc, text="Assoc. Strength", variable=self._assoc_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV)
        chk_assoc.pack(anchor="w", padx=10, pady=8)
        HoverTooltip(chk_assoc, "Aplica Associação Van Eck & Waltman (VOSviewer) dividindo o peso das arestas pelas frequências de ocorrência dos nós, evidenciando as relações mais raras e significativas.")
        
        # 5. Frequência Mínima
        lbl_freq = ctk.CTkLabel(sc, text="Freq. Mínima:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_freq.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_freq, "O número mínimo de documentos em que um termo/autor deve aparecer para ser incluído no mapa.")
        occ_f = ctk.CTkFrame(sc, fg_color="transparent")
        occ_f.pack(fill="x", padx=10, pady=(0, 6))
        self._occ_lbl = ctk.CTkLabel(occ_f, text="3", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._occ_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            occ_f, from_=1, to=50, number_of_steps=49,
            variable=self._min_occ_var, height=14,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=self._on_occ_change,
        ).pack(side="left", fill="x", expand=True)
        
        self._thresh_lbl = ctk.CTkLabel(sc, text="", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
        self._thresh_lbl.pack(anchor="w", padx=10, pady=(0, 6))
        
        # 6. Filtro de Nós (Máx. nós ou Top %)
        lbl_max = ctk.CTkLabel(sc, text="Máx. Nós (0=∞):", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_max.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_max, "Limita o número total de nós no mapa filtrando pelos mais relevantes (com maior grau de conexão). Zero significa sem limites.")
        ctk.CTkEntry(sc, textvariable=self._max_nodes_var, height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        lbl_top = ctk.CTkLabel(sc, text="ou Top % Relevância:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_top.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_top, "Filtra apenas a porcentagem (ex: 60) de termos mais relevantes de acordo com a pontuação de densidade / tf-idf.")
        ctk.CTkEntry(sc, textvariable=self._max_pct_var, placeholder_text="ex: 60", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 7. Iterações Layout FA2
        lbl_fa2 = ctk.CTkLabel(sc, text="Iterações FA2:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_fa2.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_fa2, "Quantidade de iterações do algoritmo de espacialização ForceAtlas2. Um valor maior torna o mapa mais estável e agrupado, porém demora mais para calcular.")
        fa2_f = ctk.CTkFrame(sc, fg_color="transparent")
        fa2_f.pack(fill="x", padx=10, pady=(0, 6))
        self._fa2_lbl = ctk.CTkLabel(fa2_f, text="500", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._fa2_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            fa2_f, from_=100, to=2000, number_of_steps=19,
            variable=self._fa2_iter_var, height=14,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=lambda v: self._fa2_lbl.configure(text=str(int(v))),
        ).pack(side="left", fill="x", expand=True)
        
        chk_linlog = ctk.CTkCheckBox(sc, text="LinLog Mode", variable=self._linlog_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV)
        chk_linlog.pack(anchor="w", padx=10, pady=6)
        HoverTooltip(chk_linlog, "Um modo alternativo de força no ForceAtlas2 que afasta mais os clusters uns dos outros para uma visualização com menos sobreposição.")
        
        # Algoritmo de Cluster & Resolução
        lbl_alg = ctk.CTkLabel(sc, text="Algoritmo de Cluster:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_alg.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_alg, "O algoritmo para detectar comunidades na rede. O Leiden é mais rápido e garante melhor otimização matemática para grafos complexos do que o Louvain tradicional.")
        ctk.CTkComboBox(sc, values=["louvain", "leiden"], variable=self._cluster_alg_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        lbl_res = ctk.CTkLabel(sc, text="Resolução Cluster:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_res.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_res, "Controla o número de clusters gerados.\n- Valores > 1 geram mais clusters (menores).\n- Valores < 1 geram menos clusters (maiores).")
        res_f = ctk.CTkFrame(sc, fg_color="transparent")
        res_f.pack(fill="x", padx=10, pady=(0, 6))
        self._res_lbl = ctk.CTkLabel(res_f, text="1.00", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._res_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            res_f, from_=0.1, to=5.0, number_of_steps=49,
            variable=self._cluster_res_var, height=14,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=lambda v: self._res_lbl.configure(text=f"{v:.2f}"),
        ).pack(side="left", fill="x", expand=True)

        # 8. Modo de Visualização
        lbl_viz = ctk.CTkLabel(sc, text="Modo de Visualização:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_viz.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_viz, "As cores dos nós serão baseadas nesta métrica:\n- Clusters: Cores por agrupamento.\n- Ano Médio: Heatmap temporal.\n- Grau / Betweenness / Densidade: Métricas de centralidade.")
        ctk.CTkComboBox(sc, values=VIZ_MODES, variable=self._viz_mode_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 9. Filtro de Período (Anos)
        lbl_yr = ctk.CTkLabel(sc, text="Período (Anos):", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_yr.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_yr, "Filtra a base antes da geração do mapa considerando apenas publicações entre os anos indicados.")
        yr_f = ctk.CTkFrame(sc, fg_color="transparent")
        yr_f.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkEntry(yr_f, textvariable=self._year_min_var, placeholder_text="De", width=70, height=28, border_color=ACCENT).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkLabel(yr_f, text="-", text_color=TEXT_MUTED).pack(side="left", padx=4)
        ctk.CTkEntry(yr_f, textvariable=self._year_max_var, placeholder_text="Até", width=70, height=28, border_color=ACCENT).pack(side="left", fill="x", expand=True, padx=(4, 0))
        
        # 10. Stopwords extras
        lbl_sw = ctk.CTkLabel(sc, text="Stopwords Extras:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_sw.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_sw, "Palavras para remover explicitamente das palavras-chave separadas por vírgula (Ex: review, human, article).")
        ctk.CTkEntry(sc, textvariable=self._extra_sw_var, placeholder_text="ex: word, study", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 11. Thesaurus CSV
        ctk.CTkLabel(sc, text="Thesaurus CSV:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        th_f = ctk.CTkFrame(sc, fg_color="transparent")
        th_f.pack(fill="x", padx=10, pady=(0, 6))
        self._thesaurus_lbl = ctk.CTkLabel(th_f, text="Nenhum carregado", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
        self._thesaurus_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        self._btn(th_f, "📄", self._pick_thesaurus, height=26, width=32).pack(side="right")
        
        # 12. Cor Plotly
        ctk.CTkLabel(sc, text="Cor do Plotly:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkComboBox(sc, values=["cluster", "degree", "year"], variable=self._plotly_mode_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 13. Configuração da IA
        ctk.CTkLabel(sc, text="Provedor de IA:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkComboBox(sc, values=["groq", "openai", "openrouter", "ollama", "custom"], 
                         variable=self._ai_provider_var, command=self._on_ai_provider_change,
                         height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
                         
        ctk.CTkLabel(sc, text="URL Base da API:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkEntry(sc, textvariable=self._ai_base_url_var, placeholder_text="https://...", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        ctk.CTkLabel(sc, text="Chave API:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkEntry(sc, textvariable=self._api_key_var, show="*", placeholder_text="Chave API", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        ctk.CTkLabel(sc, text="Modelo da IA:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkEntry(sc, textvariable=self._ai_model_var, placeholder_text="Modelo", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))

        # 14. Network Pruning
        ctk.CTkLabel(sc, text="Pós-processamento:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkCheckBox(sc, text="Remover nós isolados", variable=self._prune_isolated_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV).pack(anchor="w", padx=10, pady=3)
        ctk.CTkCheckBox(sc, text="Manter só maior comp.", variable=self._prune_largest_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV).pack(anchor="w", padx=10, pady=(3, 8))

        # 15. Config Persistence
        pf = ctk.CTkFrame(sc, fg_color="transparent")
        pf.pack(fill="x", padx=10, pady=8)
        self._btn(pf, "💾 Salvar", self._save_config, height=28, color=INK, hover=INK_HOV).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._btn(pf, "📂 Carregar", self._load_config, height=28, color=INK, hover=INK_HOV).pack(side="right", fill="x", expand=True, padx=(4, 0))
    # ── Tab: Rankings ──────────────────────────────────────────────────
    def _build_tab_ranking(self, parent=None) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent if parent else self._content, fg_color="transparent", corner_radius=0)
        frame.grid_rowconfigure(2, weight=1)
        self._h1(frame, "Rankings", 0)

        ctrl = ctk.CTkFrame(frame, fg_color=CONTENT_BG)
        ctrl.grid(row=1, column=0, padx=24, pady=(0, 6), sticky="ew")
        self._rank_var = ctk.StringVar(value="keywords")
        for lbl, val in [("Top Keywords", "keywords"),
                         ("Top Autores",  "authors"),
                         ("h-index",      "hindex"),
                         ("Top Fontes",   "sources"),
                         ("Clusters",     "clusters")]:
            ctk.CTkRadioButton(ctrl, text=lbl, variable=self._rank_var,
                               value=val, fg_color=ACCENT,
                               hover_color=ACCENT_HOV).pack(
                side="left", padx=12)
        self._btn(ctrl, "Gerar", self._show_ranking,
                  height=36).pack(side="right", padx=8)

        rc = self._card(frame, 2)
        rc.grid_rowconfigure(0, weight=1)
        rc.grid_columnconfigure(0, weight=1)

        # Treeview style
        self._update_treeview_style()

        sb = ctk.CTkScrollbar(rc, orientation="vertical")
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 6))

        self._rank_tree = ttk.Treeview(
            rc,
            style="Blicsa.Treeview",
            yscrollcommand=sb.set,
            selectmode="browse",
            show="headings",
        )
        sb.configure(command=self._rank_tree.yview)
        self._rank_tree.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")
        self._rank_sort_col: str | None = None
        self._rank_sort_rev: bool = False
        return frame

    # ── Tab: Exportar ──────────────────────────────────────────────────
    def _build_tab_export(self) -> ctk.CTkFrame:
        frame = self._tab()
        
        self._h1(frame, "Exportação em Lote", 0)
        
        # Configure variables
        self._exp_adj_var = ctk.BooleanVar(value=True)
        self._exp_gml_var = ctk.BooleanVar(value=True)
        self._exp_ai_var = ctk.BooleanVar(value=True)
        self._exp_xls_var = ctk.BooleanVar(value=True)
        
        options = [
            ("Matriz de Adjacência (CSV)", self._exp_adj_var),
            ("Rede Gephi/VOSviewer (GML)", self._exp_gml_var),
            ("Relatório AI (TXT)", self._exp_ai_var),
            ("Tabela de Corpus Completa (Excel)", self._exp_xls_var),
        ]
        
        list_f = ctk.CTkFrame(frame, fg_color="transparent")
        list_f.grid(row=1, column=0, sticky="ew", padx=30, pady=20)
        
        for i, (text, var) in enumerate(options):
            card = ctk.CTkFrame(list_f, fg_color=CARD_BG, corner_radius=8)
            card.pack(fill="x", pady=5)
            cb = ctk.CTkCheckBox(
                card, text=text, variable=var, 
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color=RED, hover_color=RED_HOVER, text_color=INK
            )
            cb.pack(padx=20, pady=15, anchor="w")
            
        def run_export():
            import os, time
            os.makedirs("reports", exist_ok=True)
            ts = int(time.time())
            files_saved = []
            
            try:
                if self._exp_adj_var.get() and getattr(self, '_graph', None):
                    import networkx as nx
                    import pandas as pd
                    df_adj = nx.to_pandas_adjacency(self._graph)
                    p = f"reports/adj_{ts}.csv"
                    df_adj.to_csv(p)
                    files_saved.append(p)
                    
                if self._exp_gml_var.get() and getattr(self, '_graph', None):
                    import networkx as nx
                    p = f"reports/rede_{ts}.gml"
                    nx.write_gml(self._graph, p)
                    files_saved.append(p)
                    
                if self._exp_ai_var.get() and getattr(self, '_generator', None):
                    p = f"reports/ai_report_{ts}.txt"
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(self._generator.get_cluster_report())
                    files_saved.append(p)
                    
                if self._exp_xls_var.get() and getattr(self, '_dataframe', None) is not None:
                    p = f"reports/corpus_{ts}.xlsx"
                    self._dataframe.to_excel(p, index=False)
                    files_saved.append(p)
                    
                if files_saved:
                    msg = "Arquivos exportados com sucesso!\n" + "\n".join(files_saved)
                    messagebox.showinfo("Exportação Concluída", msg)
                else:
                    messagebox.showwarning("Atenção", "Nenhum dado para exportar (verifique se os dados estão carregados).")
            except Exception as e:
                messagebox.showerror("Erro na exportação", str(e))

        # Bottom right button
        bottom_f = ctk.CTkFrame(frame, fg_color="transparent")
        bottom_f.grid(row=2, column=0, sticky="ew", padx=30, pady=40)
        bottom_f.grid_columnconfigure(0, weight=1)
        
        self._btn(
            bottom_f, "Exportar Selecionados", run_export,
            color=RED, hover=RED_HOV, height=50
        ).pack(side="right")

        return frame

    # ── Actions: data loading ──────────────────────────────────────────
    _FORMAT_LABELS = {
        "scopus":   "Scopus CSV",
        "wos":      "WoS TXT",
        "bibtex":   "BibTeX",
        "pubmed":   "PubMed",
        "openalex": "OpenAlex JSON",
        "crossref": "Crossref JSON",
        "ris":      "RIS",
    }

    def _auto_detect_format(self, path: str) -> str:
        p = Path(path)
        ext = p.suffix.lower()
        
        # Simple extensions
        if ext == ".ris":
            return "ris"
        if ext in (".bib", ".bibtex"):
            return "bibtex"
        if ext == ".nbib":
            return "pubmed"
            
        # Read the start of the file to inspect header/tags
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
        except Exception:
            return "ambiguous" # fallback to dropdown
            
        # 1. JSON analysis
        if ext == ".json" or head.strip().startswith("{") or head.strip().startswith("["):
            if '"results"' in head or '"id":' in head:
                return "openalex"
            if '"message"' in head or '"items"' in head:
                return "crossref"
            return "openalex"
            
        # 2. PubMed Medline / Tagged text
        if "PMID-" in head or "OWN -" in head:
            return "pubmed"
            
        # 3. Web of Science TXT
        if "FN " in head or "VR " in head or "PT " in head:
            return "wos"
            
        # 4. CSV analysis: Scopus vs Web of Science CSV
        if ext == ".csv" or "," in head or ";" in head:
            lines = head.splitlines()
            first_line = lines[0] if lines else ""
            if "Authors" in first_line or "Source title" in first_line or "Cited by" in first_line:
                return "scopus"
            # WoS CSV files use AU, TI, SO, PY, etc.
            if "AU" in first_line or "TI" in first_line or "PY" in first_line or "SO" in first_line:
                return "wos"
                
        return "ambiguous"

    def _pick_file(self):
        paths = filedialog.askopenfilenames(
            filetypes=[
                ("Todos os formatos", "*.csv *.txt *.bib *.nbib *.json *.ris"),
                ("CSV", "*.csv"), ("TXT / NBIB / RIS", "*.txt *.nbib *.ris"),
                ("BibTeX", "*.bib"), ("JSON", "*.json"), ("All files", "*.*"),
            ])
        if paths:
            self._file_list_frame.grid() # show the list
            
        for p in paths:
            if p not in self._file_paths:
                fmt = self._auto_detect_format(p)
                if fmt == "ambiguous":
                    fmt = "scopus" # Default if totally unknown but show dropdown?
                self._file_paths.append(p)
                self._file_formats.append(fmt)
                self._add_file_row(p, fmt)

    def _add_file_row(self, path: str, fmt: str):
        row_f = ctk.CTkFrame(self._file_list_frame, fg_color=CARD_BG, corner_radius=0)
        row_f.pack(fill="x", pady=2)
        row_f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(row_f, text=Path(path).name, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=8, pady=4, sticky="ew")
            
        if fmt == "ambiguous" or True: # Just show a dropdown always for safety, but style it like a badge
            fmt_var = ctk.StringVar(value=fmt)
            cb = ctk.CTkComboBox(
                row_f,
                values=list(self._FORMAT_LABELS.keys()),
                variable=fmt_var,
                width=110, height=24,
                fg_color=RED, text_color="white", button_color=RED, border_color=RED, dropdown_hover_color=RED_HOV,
                command=lambda v, p=path: self._set_file_format(p, v),
            )
            cb.grid(row=0, column=1, padx=4, pady=4)
            
        ctk.CTkButton(
            row_f, text="✕", width=28, height=24,
            fg_color="#4a1a1a", hover_color="#6a2a2a",
            font=ctk.CTkFont(size=10),
            command=lambda p=path, f=row_f: self._remove_file(p, f),
        ).grid(row=0, column=2, padx=4, pady=4)
        self._file_row_widgets.append((row_f, path))

    def _set_file_format(self, path: str, fmt: str):
        try:
            idx = self._file_paths.index(path)
            self._file_formats[idx] = fmt
        except ValueError:
            pass

    def _remove_file(self, path: str, frame: ctk.CTkFrame):
        try:
            idx = self._file_paths.index(path)
            self._file_paths.pop(idx)
            self._file_formats.pop(idx)
        except ValueError:
            pass
        self._file_row_widgets = [(f, p) for f, p in self._file_row_widgets if p != path]
        frame.destroy()
        if not self._file_paths:
            self._file_list_frame.grid_remove()

    def _clear_files(self):
        self._file_paths.clear()
        self._file_formats.clear()
        for f, _ in self._file_row_widgets:
            f.destroy()
        self._file_row_widgets.clear()
        self._file_list_frame.grid_remove()

    def _load_data(self):
        if not self._file_paths:
            messagebox.showwarning("Sem arquivo", "Adicione pelo menos um arquivo.")
            return
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        self.after(0, self._set_busy, "Carregando arquivos…")
        try:
            loaders_map = {
                "scopus":   "load_scopus_csv",
                "wos":      "load_wos_txt",
                "bibtex":   "load_bibtex",
                "pubmed":   "load_pubmed_medline",
                "openalex": "load_openalex_json",
                "crossref": "load_crossref_json",
                "ris":      "load_ris",
                "pdf":      "load_pdf",
            }
            dfs = []
            for path, fmt in zip(self._file_paths, self._file_formats):
                method_name = loaders_map.get(fmt, "load_scopus_csv")
                print(f"[Blicsa] Carregando {Path(path).name} ({fmt}) ...")
                parser = BibliometricParser(path)
                df = getattr(parser, method_name)()
                dfs.append(df)
                print(f"  → {len(df)} registros\n")
            if not dfs:
                raise ValueError("Nenhum arquivo carregado.")
            combined = dfs[0] if len(dfs) == 1 else BibliometricParser.merge(*dfs)
            if len(dfs) > 1:
                print(f"[OK] Combinados: {len(combined)} registros únicos.\n")
            self._dataframe = combined
            print(f"[OK] Total: {len(combined)} registros.\n")
            self._refresh_candidate_counts()
            
            # Auto-populate year filter range
            if "year" in combined.columns:
                valid_years = combined["year"].dropna()
                valid_years = valid_years[valid_years > 0]
                if not valid_years.empty:
                    ymin = int(valid_years.min())
                    ymax = int(valid_years.max())
                    self.after(0, lambda y1=ymin, y2=ymax: (
                        self._year_min_var.set(str(y1)),
                        self._year_max_var.set(str(y2))
                    ))
            
            self.after(0, self._update_stats_tab)
            self.after(0, self._set_idle, f"{len(combined)} registros carregados")
            self.after(0, lambda: self._switch_tab("viz"))
        except Exception as exc:
            print(f"[ERRO] {exc}\n")
            self.after(0, self._set_idle, "Erro ao carregar")
            self.after(0, lambda e=exc: messagebox.showerror("Erro ao carregar", str(e)))

    def _cancel_search(self):
        if hasattr(self, '_search_cancel_event') and self._search_cancel_event:
            self._search_cancel_event.set()
            self._set_idle("Cancelando busca... (Aguarde)")
            self._search_cancel_btn.pack_forget()

    def _on_gui_search(self):
        query = self._search_query_entry.get().strip()
        if not query:
            messagebox.showwarning("Campo vazio", "Por favor, digite um termo de busca.")
            return
        provider = self._search_provider_var.get()
        
        if self._search_unlimited_var.get():
            max_results = 9999999
        else:
            try:
                max_results = int(self._search_max_entry.get().strip() or "100")
            except ValueError:
                max_results = 100
            
        filters = {}
        if self._search_year_start.get().strip(): filters["year_start"] = self._search_year_start.get().strip()
        if self._search_year_end.get().strip(): filters["year_end"] = self._search_year_end.get().strip()
        
        doc_type = self._search_type_var.get()
        if doc_type and doc_type != "Todos":
            filters["type"] = doc_type
            
        lang = getattr(self, "_search_lang_var", ctk.StringVar(value="Todos")).get()
        if lang and lang != "Todos":
            filters["language"] = lang
            
        oa = getattr(self, "_search_oa_var", ctk.BooleanVar(value=False)).get()
        if oa:
            filters["is_oa"] = True
            
        self.search_to_dataset(query, provider, max_results, filters)

    def _open_query_builder(self):
        from ui.query_builder import show_query_builder
        def on_query_built(query_str):
            self._search_query_entry.delete(0, 'end')
            self._search_query_entry.insert(0, query_str)
        show_query_builder(self, on_query_built)

    def search_to_dataset(self, query: str, provider_name: str, max_results: int, filters: dict = None):
        import threading
        if filters is None: filters = {}
        
        # Setup cancel event
        self._search_cancel_event = threading.Event()
        self._search_cancel_btn.pack(side="left", padx=4)
        
        threading.Thread(target=self._search_worker, args=(query, provider_name, max_results, filters, self._search_cancel_event), daemon=True).start()

    def _search_worker(self, query: str, provider_name: str, max_results: int, filters: dict, cancel_event):
        self.after(0, self._set_busy, f"Buscando em {provider_name.upper()}...")
        try:
            from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider
            from core.sources.zotero import ZoteroProvider
            
            providers_to_run = []
            if provider_name.lower() == "all":
                providers_to_run = [OpenAlexProvider(), CrossrefProvider(), PubMedProvider()]
            elif provider_name.lower() == "openalex":
                providers_to_run = [OpenAlexProvider()]
            elif provider_name.lower() == "crossref":
                providers_to_run = [CrossrefProvider()]
            elif provider_name.lower() == "zotero":
                providers_to_run = [ZoteroProvider()]
            else:
                providers_to_run = [PubMedProvider()]
                
            records = []
            max_per_provider = max_results
            total_found_sum = 0
            lang_filtered_total = 0  # BUG-02: records descartados por idioma (Crossref client-side)

            # --- Streaming: cria o feed em modo "carregamento vivo" imediatamente ---
            import time as _time
            _t_start = _time.perf_counter()
            _first_batch = [False]
            self._feed_cbs = {}

            def begin_feed():
                from ui.search_feed import SearchFeedView
                self._search_cancel_btn.pack(side="left", padx=4)
                review_tab = self._tabs["review"]
                for w in review_tab.winfo_children():
                    w.destroy()
                self.search_feed_view = SearchFeedView(
                    review_tab,
                    lambda recs, dd=False: self._feed_cbs.get("import", lambda *a: None)(recs, dd),
                    lambda: self._feed_cbs.get("cancel", lambda: None)(),
                    lambda recs, sel: self._feed_cbs.get("ai", lambda *a: None)(recs, sel),
                )
                self.search_feed_view.pack(fill="both", expand=True)
                self.search_feed_view.begin_stream(max_results)
                self._switch_tab("review")
            self.after(0, begin_feed)

            def push_batch():
                snap = records[:]  # snapshot thread-safe
                loaded = len(snap)
                total = total_found_sum
                def _upd():
                    fv = getattr(self, "search_feed_view", None)
                    if fv is not None:
                        fv.stream_update(snap, loaded, total)
                self.after(0, _upd)

            BATCH = 25

            for prov in providers_to_run:
                if cancel_event.is_set(): break

                prov_name = prov.__class__.__name__.replace("Provider", "")
                self.after(0, self._set_busy, f"Consultando {prov_name}...")

                def progress(current, total):
                    nonlocal total_found_sum
                    if total > total_found_sum: total_found_sum = total

                    if cancel_event.is_set():
                        self.after(0, self._set_idle, "Busca cancelada.")
                    else:
                        self.after(0, self._set_busy, f"Baixando ({prov_name}): {current}/{total} (Total na base: {total})")

                try:
                    for r in prov.search(query=query, filters=filters, max_results=max_per_provider, progress_cb=progress, cancel_event=cancel_event):
                        records.append(r)
                        n = len(records)
                        if n == 1 or n % BATCH == 0:
                            if not _first_batch[0]:
                                print(f"[feed] primeiro lote em {_time.perf_counter() - _t_start:.1f}s")
                                _first_batch[0] = True
                            push_batch()
                except InterruptedError:
                    print(f"Busca em {prov_name} abortada pelo usuário.")
                    break
                except TypeError:
                    # Fallback if filters argument is not supported by the provider
                    for r in prov.search(query=query, max_results=max_per_provider, progress_cb=progress):
                        if cancel_event.is_set(): break
                        records.append(r)
                        n = len(records)
                        if n == 1 or n % BATCH == 0:
                            if not _first_batch[0]:
                                print(f"[feed] primeiro lote em {_time.perf_counter() - _t_start:.1f}s")
                                _first_batch[0] = True
                            push_batch()

                lang_filtered_total += getattr(prov, "language_filtered_count", 0)

            push_batch()  # descarrega o lote parcial final no contador vivo

            if not records:
                def _empty_feed():
                    fv = getattr(self, "search_feed_view", None)
                    if fv is not None:
                        fv.finish_stream([], "Encontrados 0 · baixados 0")
                self.after(0, _empty_feed)
                self.after(0, self._set_idle, "Busca vazia ou cancelada")
                if not cancel_event.is_set():
                    self.after(0, lambda: messagebox.showinfo("Busca concluída", "Nenhum registro encontrado para essa busca."))
                self.after(0, self._search_cancel_btn.pack_forget)
                return
                
            df = pd.DataFrame(records)
            if provider_name.lower() == "all":
                self.after(0, self._set_busy, "Deduplicando registros (Fuzzy Match)...")
            
            if "language" not in df.columns:
                df["language"] = ""
            if "language_source" not in df.columns:
                df["language_source"] = "api"
                
            try:
                import langdetect
                for idx, row in df.iterrows():
                    lang = row.get("language", "")
                    if pd.isna(lang) or not str(lang).strip():
                        text = f"{row.get('title', '')} {row.get('abstract', '')}".strip()
                        if text:
                            try:
                                detected = langdetect.detect(text)
                                df.at[idx, "language"] = detected
                                df.at[idx, "language_source"] = "detected"
                            except Exception:
                                df.at[idx, "language"] = ""
                                df.at[idx, "language_source"] = "api"
                    else:
                        df.at[idx, "language_source"] = "api"
            except ImportError:
                pass
            
            baixados = len(df)

            baixados = len(df)

            df["is_duplicate"] = False
            df["dup_reason"] = ""

            # Identify duplicates
            # First by DOI
            if 'doi' in df.columns:
                doi_mask = df.duplicated(subset=['doi'], keep='first') & (df['doi'] != '') & df['doi'].notna()
                df.loc[doi_mask, 'is_duplicate'] = True
                df.loc[doi_mask, 'dup_reason'] = "DOI duplicado"
            
            # Then by title normalized
            if 'title' in df.columns:
                import re
                def norm_title(t):
                    return re.sub(r'[^a-z0-9]', '', str(t).lower())
                
                df['norm_title'] = df['title'].apply(norm_title)
                title_mask = df.duplicated(subset=['norm_title'], keep='first') & ~df['is_duplicate'] & (df['norm_title'] != '')
                df.loc[title_mask, 'is_duplicate'] = True
                df.loc[title_mask, 'dup_reason'] = "Título duplicado"
                df.drop(columns=['norm_title'], inplace=True)
                
            apos_dedup = len(df[~df["is_duplicate"]])
            trail = f"Encontrados {total_found_sum} · baixados {baixados} (limite {max_results}) · após deduplicação {apos_dedup}"
            if lang_filtered_total:
                trail += f" · filtrados por idioma: {lang_filtered_total}"
            print(f"[Search] {trail}")
            
            # Show SearchFeedView for import review
            def on_import_confirm(selected_records, fuzzy_dedup=False):
                if not selected_records:
                    self._switch_tab("home")
                    return
                df_selected = pd.DataFrame(selected_records)
                if self._dataframe is not None and not self._dataframe.empty:
                    combined = BibliometricParser.merge(self._dataframe, df_selected)
                else:
                    combined = df_selected
                    
                if fuzzy_dedup:
                    from core.harmonization import fuzzy_deduplicate_papers
                    self.after(0, self._set_busy, "Deduplicando com o corpus atual (Fuzzy Match)...")
                    combined = fuzzy_deduplicate_papers(combined)
                    self.after(0, self._set_idle, "Pronto!")
                    
                self._dataframe = combined
                self._refresh_candidate_counts()
                
                if "year" in combined.columns:
                    valid_years = combined["year"].dropna()
                    valid_years = valid_years[valid_years > 0]
                    if not valid_years.empty:
                        ymin = int(valid_years.min())
                        ymax = int(valid_years.max())
                        self._year_min_var.set(str(ymin))
                        self._year_max_var.set(str(ymax))
                        
                self._update_stats_tab()
                self._set_idle(f"{len(df_selected)} registros adicionados")
                messagebox.showinfo("Importação", f"{len(df_selected)} registros importados para o corpus com sucesso.")
                self._switch_tab("corpus")
                
            def on_cancel():
                self._switch_tab("import")

            def on_ai_assistant(records_list, selected_idx):
                if not records_list: return
                df_temp = pd.DataFrame(records_list)
                langs = df_temp['language'].value_counts().head(3).to_dict() if 'language' in df_temp.columns else {}
                years = df_temp['year'].value_counts().head(3).to_dict() if 'year' in df_temp.columns else {}
                top_sources = df_temp['source'].value_counts().head(3).to_dict() if 'source' in df_temp.columns else {}
                
                context = f"**Resultados Baixados:** {len(records_list)}\n**Artigos Selecionados:** {len(selected_idx)}\n"
                context += f"**Principais Idiomas:** {langs}\n**Principais Anos:** {years}\n**Principais Fontes:** {top_sources}\n"
                
                prompt_msg = f"Acabei de baixar {len(records_list)} artigos e filtrei {len(selected_idx)}. Analise essas estatísticas de fontes, idiomas e anos. Justifique os prós e contras desse conjunto, apontando se há algum viés claro nessa distribuição que eu deveria considerar ou ajustar antes de consolidar meu corpus final."
                
                self._switch_tab("home")
                self._add_blink_message("user", prompt_msg)
                
                system_prompt = self._research_messages[0]["content"]
                system_prompt += f"\n\nContexto Atual (Revisão Pós-Busca):\n{context}"
                
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._research_chat_history_main._parent_canvas.yview_moveto(1.0)
                
                import threading
                def _stream_worker_ai():
                    try:
                        from ai.client import AIAnalyst
                        analyst = AIAnalyst(api_key=self._api_key_var.get() or None, base_url=self._ai_base_url_var.get(), model=self._ai_model_var.get())
                        stream = analyst.chat_history_stream(messages, temperature=0.7)
                        full_response = ""
                        tb_ref = []
                        from core.markdown_parser import insert_markdown
                        
                        for chunk in stream:
                            full_response += chunk
                            def update_chunk(resp=full_response):
                                if indicator_row.winfo_exists(): indicator_row.destroy()
                                if not tb_ref:
                                    tb, upd, _ = self._add_blink_message("assistant", "")
                                    tb_ref.append((tb, upd))
                                tb, upd = tb_ref[0]
                                tb.configure(state="normal")
                                tb.delete("1.0", "end")
                                insert_markdown(tb, resp)
                                tb.configure(state="disabled")
                                upd()
                            self.after(0, update_chunk)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                    except Exception as ex:
                        if indicator_row.winfo_exists(): indicator_row.destroy()
                        self.after(0, lambda e=ex: self._add_blink_message("assistant", f"Erro: {e}"))
                threading.Thread(target=_stream_worker_ai, daemon=True).start()
                
            # Liga os callbacks reais aos lambdas do feed (criado em begin_feed).
            self._feed_cbs = {"import": on_import_confirm, "cancel": on_cancel, "ai": on_ai_assistant}

            def finalize():
                self._search_cancel_btn.pack_forget()
                fv = getattr(self, "search_feed_view", None)
                if fv is not None:
                    fv.finish_stream(df.to_dict('records'), trail)
                else:
                    from ui.search_feed import SearchFeedView
                    review_tab = self._tabs["review"]
                    for w in review_tab.winfo_children():
                        w.destroy()
                    self.search_feed_view = SearchFeedView(review_tab, on_import_confirm, on_cancel, on_ai_assistant)
                    self.search_feed_view.pack(fill="both", expand=True)
                    self.search_feed_view.load_results(df.to_dict('records'), trail)
                self._set_idle("Pronto para revisar")
                self._switch_tab("review")

            self.after(0, finalize)

        except Exception as e:
            print(f"[Search Error] {e}")
            self.after(0, self._set_idle, "Erro na busca")
            self.after(0, lambda e_msg=str(e): messagebox.showerror("Erro na busca", f"Ocorreu um erro ao buscar:\n{e_msg}"))

    def _pick_thesaurus(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._thesaurus = load_thesaurus(path)
            self._thesaurus_path = path
            self._thesaurus_lbl.configure(
                text=f"{Path(path).name} ({len(self._thesaurus)} entradas)",
                text_color=("gray10", "white"),
            )
            self._refresh_candidate_counts()
            print(f"[Thesaurus] {len(self._thesaurus)} mapeamentos carregados.\n")
        except Exception as exc:
            messagebox.showerror("Erro ao carregar thesaurus", str(exc))

    # ── Threshold preview ──────────────────────────────────────────────
    def _refresh_candidate_counts(self):
        if self._dataframe is None:
            return
        threading.Thread(target=self._candidate_worker, daemon=True).start()

    def _candidate_worker(self):
        try:
            gen = NetworkGenerator(self._dataframe)
            field = self._field_var.get() if hasattr(self, "_field_var") else "keywords"
            _, counts, _, scores = gen.get_candidate_terms(
                field=field, thesaurus=self._thesaurus)
            self._candidate_counts = counts
            self._candidate_scores = scores
            self.after(0, self._update_thresh_label)
        except Exception:
            pass

    def _update_thresh_label(self):
        if not self._candidate_counts:
            return
        min_occ = self._min_occ_var.get()
        total   = len(self._candidate_counts)
        passing = sum(1 for n in self._candidate_counts.values() if n >= min_occ)
        self._thresh_lbl.configure(
            text=f"→  {passing} de {total} termos passam")

    def _on_occ_change(self, val):
        self._occ_lbl.configure(text=str(int(val)))
        self._update_thresh_label()

    def _on_field_change(self):
        self._refresh_candidate_counts()

    # ── Map generation ─────────────────────────────────────────────────
    def _run_mapping(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return

        map_type = self._map_type_var.get()
        # Only show verification dialog for keyword/term types
        if map_type == MAP_TYPES[0] and self._candidate_counts:
            min_occ = self._min_occ_var.get()
            field   = self._field_var.get()
            terms_data = [
                (term, count, 0, self._candidate_scores.get(term, 0.0))
                for term, count in self._candidate_counts.items()
                if count >= min_occ
            ]
            # Enrich with doc_freq
            from core.matrix_builders import _extract_term_lists
            try:
                term_lists = _extract_term_lists(
                    self._dataframe, field, self._thesaurus, None)
                from collections import Counter as _C
                doc_freq = _C()
                for lst in term_lists:
                    for t in set(lst):
                        doc_freq[t] += 1
                terms_data = [
                    (term, count, doc_freq.get(term, 0), self._candidate_scores.get(term, 0.0))
                    for term, count, _, score in terms_data
                ]
            except Exception:
                pass

            if terms_data:
                VerificationDialog(
                    self, terms_data,
                    on_confirm=lambda selected: threading.Thread(
                        target=self._mapping_worker, args=(selected,), daemon=True
                    ).start(),
                )
                return

        threading.Thread(target=self._mapping_worker, args=(None,), daemon=True).start()

    def _mapping_worker(self, allowed_terms: set[str] | None):
        self.after(0, self._set_busy, "Gerando rede…")
        try:
            print("[Blicsa Engine] Calculando rede...")

            # Apply year filter
            df = self._dataframe.copy()
            try:
                yr_min = int(self._year_min_var.get().strip()) if self._year_min_var.get().strip() else None
                yr_max = int(self._year_max_var.get().strip()) if self._year_max_var.get().strip() else None
            except ValueError:
                yr_min = yr_max = None
            if yr_min is not None:
                df = df[df["year"] >= yr_min]
            if yr_max is not None:
                df = df[df["year"] <= yr_max]
            if yr_min or yr_max:
                print(f"[Filtro] Período {yr_min or '?'} – {yr_max or '?'}: {len(df)} registros\n")

            # Extra stop words
            extra_sw_raw = self._extra_sw_var.get().strip()
            extra_sw: set[str] | None = None
            if extra_sw_raw:
                extra_sw = {w.strip().lower() for w in extra_sw_raw.split(",") if w.strip()}

            # Compute max_nodes from top%
            max_nodes = int(self._max_nodes_var.get() or 0)
            pct_str   = self._max_pct_var.get().strip()
            if pct_str and not max_nodes:
                try:
                    pct = float(pct_str)
                    _, counts, _, _ = NetworkGenerator(df).get_candidate_terms(
                        field=self._field_var.get(), thesaurus=self._thesaurus,
                        extra_stop_words=extra_sw,
                    )
                    passing = sum(1 for n in counts.values() if n >= self._min_occ_var.get())
                    max_nodes = max(1, int(passing * pct / 100))
                    print(f"[Top {pct}%] → {max_nodes} nós selecionados\n")
                except ValueError:
                    pass

            gen      = NetworkGenerator(df)
            gen.clustering_algorithm = self._cluster_alg_var.get()
            gen.clustering_resolution = self._cluster_res_var.get()
            map_type = self._map_type_var.get()
            min_occ  = self._min_occ_var.get()
            field    = self._field_var.get()
            counting = self._counting_var.get()
            strength = self._assoc_var.get()

            if map_type == MAP_TYPES[0]:
                gen.build_keyword_cooccurrence(
                    min_occurrence=min_occ,
                    counting_method=counting,
                    normalize_strength=strength,
                    field=field,
                    thesaurus=self._thesaurus,
                    max_nodes=max_nodes,
                    allowed_terms=allowed_terms,
                    extra_stop_words=extra_sw,
                )
            elif map_type == MAP_TYPES[1]:
                gen.build_coauthorship_network(
                    min_publications=min_occ,
                    counting_method=counting,
                )
            elif map_type == MAP_TYPES[2]:
                gen.build_cocitation_network(min_cocitations=min_occ)
            elif map_type == MAP_TYPES[3]:
                gen.build_bibliographic_coupling(min_shared_refs=max(min_occ, 2))
            elif map_type == MAP_TYPES[4]:
                gen.build_direct_citation_network(min_citations=max(min_occ, 1))
            else:
                gen.build_ipc_cooccurrence(min_occurrence=min_occ)

            self._generator = gen

            # Network pruning
            if self._prune_isolated_var.get():
                isolated = list(nx.isolates(gen.G))
                if isolated:
                    gen.G.remove_nodes_from(isolated)
                    print(f"[Pruning] {len(isolated)} nó(s) isolado(s) removido(s)\n")
            if self._prune_largest_var.get() and not nx.is_connected(gen.G):
                largest = max(nx.connected_components(gen.G), key=len)
                remove  = [n for n in gen.G.nodes() if n not in largest]
                gen.G.remove_nodes_from(remove)
                print(f"[Pruning] Mantendo maior componente: {len(largest)} nós\n")

            print("[FA2] Calculando layout ForceAtlas2...")
            iters   = self._fa2_iter_var.get()
            linlog  = self._linlog_var.get()
            self._positions = compute_fa2_layout(gen.G, iterations=iters, linlog=linlog)

            stats = gen.get_summary_stats()
            mode  = self._viz_mode_var.get()
            plotly_color = self._plotly_mode_var.get()

            gen.export_to_html(MAP_PATH)
            
            from core.sigma_exporter import export_sigma_json
            sigma_path = str(OUTPUT_DIR / "assets" / "graph.json")
            export_sigma_json(gen.G, self._positions, sigma_path)
            
            import webbrowser
            url = f"http://127.0.0.1:{self._local_server_port}/assets/map_template.html"
            webbrowser.open(url)
            print("[OK] Mapas prontos.\n")

            self.after(0, self._update_stats, stats)
            if getattr(self, '_tv_analises', None):
                self._tv_analises.set("Mapa")
            self.after(0, self._switch_tab, "analises")
            self.after(0, self._set_idle, "Mapa gerado")
            
            if self._api_key_var.get().strip() or os.environ.get("GROQ_API_KEY"):
                self._show_ai_modal = False
                self.after(200, lambda: threading.Thread(target=self._trigger_map_ai_insights, daemon=True).start())
        except Exception as exc:
            print(f"[ERRO] {exc}\n")
            self.after(0, self._set_idle, "Erro")
            self.after(0, lambda e=exc: messagebox.showerror("Erro", str(e)))

    def _update_stats(self, stats: dict):
        for key, lbl in self._stat_labels.items():
            lbl.configure(text=str(stats.get(key, "—")))

    # ── Viz controls ───────────────────────────────────────────────────
    def _apply_style(self):
        pass

    # ── Node info panel ────────────────────────────────────────────────
    def _on_node_click(self, node: str | None):
        if node is None:
            return
        self._bottom_tabs.set("Nó Selecionado")
        threading.Thread(target=self._build_node_info, args=(node,), daemon=True).start()

    def _build_node_info(self, node: str):
        lines: list[str] = []
        G   = self._generator.G if self._generator else None
        df  = self._dataframe

        lines.append(f"{'━'*52}")
        lines.append(f"  {node.upper()}")
        lines.append(f"{'━'*52}")

        if G and node in G.nodes:
            d = G.nodes[node]
            lines.append(f"  Cluster        : {d.get('group','—')}")
            lines.append(f"  Ocorrências    : {d.get('occurrence','—')}")
            lines.append(f"  Grau ponderado : {G.degree(node, weight='weight'):.2f}")
            bc = nx.betweenness_centrality(G, weight="weight")
            lines.append(f"  Betweenness    : {bc.get(node,0):.4f}")
            pr = nx.pagerank(G, weight="weight")
            lines.append(f"  PageRank       : {pr.get(node,0):.4f}")
            yr = d.get("year_mean", 0)
            if yr:
                lines.append(f"  Ano médio      : {yr:.0f}")
            nbrs = sorted(G.neighbors(node),
                          key=lambda n: G[node][n].get("weight", 0), reverse=True)
            if nbrs:
                lines.append("")
                lines.append(f"  TOP CO-OCORRENTES:")
                for nb in nbrs[:8]:
                    w = G[node][nb].get("weight", 0)
                    lines.append(f"    · {nb:<32} {w:.3f}")

        if df is not None:
            field_map = {"keywords":"keywords","titles":"title",
                         "abstracts":"abstract","titles_abstracts":"abstract"}
            col = field_map.get(
                self._field_var.get() if hasattr(self, "_field_var") else "keywords",
                "keywords")
            t_low = node.lower()

            def _has(s):
                if not isinstance(s, str): return False
                sep = ";" if ";" in s else ","
                return t_low in [x.strip().lower() for x in s.split(sep)]

            mask  = df[col].apply(_has)
            papers = df[mask].sort_values("citations", ascending=False).head(10)
            if not papers.empty:
                lines.append("")
                lines.append(f"  ARTIGOS RELACIONADOS ({len(papers)} exibidos):")
                lines.append(f"  {'─'*50}")
                for _, row in papers.iterrows():
                    title = str(row.get("title",""))[:55]
                    yr    = int(row.get("year", 0) or 0)
                    cit   = int(row.get("citations", 0) or 0)
                    lines.append(f"  [{yr}] {title}")
                    lines.append(f"        {str(row.get('authors',''))[:45]}  cit:{cit}")

        lines.append("")
        text = "\n".join(lines)
        self.after(0, self._update_node_info_box, text)

    def _update_node_info_box(self, text: str):
        self._node_info_box.configure(state="normal")
        self._node_info_box.delete("1.0", "end")
        self._node_info_box.insert("end", text)
        self._node_info_box.configure(state="disabled")

    def _populate_cluster_filter(self):
        """Rebuild the cluster checkbox strip after a new map is generated."""
        for w in self._cluster_filter_frame.winfo_children():
            w.destroy()
        self._cluster_filter_vars.clear()
        if self._generator is None:
            return
        report = self._generator.get_cluster_report()
        if not report:
            return
        ctk.CTkLabel(
            self._cluster_filter_frame, text="Clusters:",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        for c in report:
            cid   = c["cluster_id"]
            color = CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)]
            label = self._cluster_labels.get(cid) or f"C{cid}"
            var   = ctk.BooleanVar(value=True)
            self._cluster_filter_vars[cid] = var
            ctk.CTkCheckBox(
                self._cluster_filter_frame,
                text=f"{label[:16]} ({c['size']})",
                variable=var,
                fg_color=color, hover_color=color,
                checkmark_color="#000000",
                font=ctk.CTkFont(size=10),
                width=20, checkbox_width=14, checkbox_height=14,
                command=self._apply_cluster_filter,
            ).pack(side="left", padx=4)

    def _apply_cluster_filter(self):
        pass

    def _on_edge_thresh_change(self, val: float):
        pass

    def _search_node(self):
        pass

    def _reset_view(self):
        pass

    def _open_in_webview(self, title: str, path: str):
        import webbrowser
        webbrowser.open(str(path))

    def _open_plotly(self):
        if self._generator is None or not self._positions:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro antes de abrir a visualização.")
            return
            
        try:
            from core.visualizer import build_plotly_map
            fig = build_plotly_map(
                self._generator.G,
                self._positions,
                color_mode=self._plotly_mode_var.get(),
                df=self._dataframe
            )
            
            import time
            map_type = self._viz_mode_var.get().replace(" ", "_")
            out_name = f"blicsa_mapa_{map_type}_{int(time.time())}.html"
            path = str(OUTPUT_DIR / out_name)
            
            fig.write_html(path, include_plotlyjs="cdn")
            print(f"[Plotly] Interativo salvo → {path}\n")
            
            self._open_in_webview("Blicsa - Visualização Interativa", path)
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Plotly", str(exc))

    def _open_map_browser(self):
        target = PLOTLY_PATH if Path(PLOTLY_PATH).exists() else MAP_PATH
        if Path(target).exists():
            webbrowser.open(str(target))
        else:
            messagebox.showinfo("Não gerado", "Gere o mapa primeiro.")

    def _open_sankey(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        try:
            from core.visualizer import build_sankey_diagram
            fig = build_sankey_diagram(self._dataframe, "authors", "keywords", "source", top_n=10)
            
            import time
            sankey_path = str(OUTPUT_DIR / f"blicsa_sankey_{int(time.time())}.html")
            fig.write_html(sankey_path, include_plotlyjs="cdn")
            print(f"[Sankey] Diagrama salvo → {sankey_path}\n")
            self._open_in_webview("Blicsa - Sankey", sankey_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
            
            # Removed automatic AI call, Blink Research sidebar can be used instead
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Sankey", str(exc))

    def _open_timeline(self):
        if self._generator is None or not self._positions:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro antes de visualizar a Linha do Tempo.")
            return
        try:
            from core.visualizer import build_timeline_view
            fig = build_timeline_view(self._generator.G, self._positions)
            
            import time
            timeline_path = str(OUTPUT_DIR / f"blicsa_linha_tempo_{int(time.time())}.html")
            fig.write_html(timeline_path, include_plotlyjs="cdn")
            print(f"[Linha do Tempo] Salva → {timeline_path}\n")
            self._open_in_webview("Blicsa - Linha do Tempo", timeline_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Linha do Tempo", str(exc))

    def _open_bursts(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        try:
            from core.nlp import detect_bursts
            extra_sw_raw = self._extra_sw_var.get().strip()
            extra_sw = None
            if extra_sw_raw:
                extra_sw = {w.strip().lower() for w in extra_sw_raw.split(",") if w.strip()}
                
            bursts = detect_bursts(
                self._dataframe,
                field=self._field_var.get(),
                thesaurus=self._thesaurus,
                extra_stop_words=extra_sw
            )
            
            if not bursts:
                messagebox.showinfo("Nenhum surto", "Nenhum surto estatisticamente significativo detectado no dataset.")
                return
                
            BurstDetectionWindow(self, bursts)
        except Exception as exc:
            messagebox.showerror("Erro na análise de surtos", str(exc))

    def _open_thematic_map(self):
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro antes de visualizar o Mapa Temático.")
            return
        try:
            fig = build_thematic_map(self._generator.G)
            import time
            thematic_path = str(OUTPUT_DIR / f"blicsa_mapa_tematico_{int(time.time())}.html")
            fig.write_html(thematic_path, include_plotlyjs="cdn")
            print(f"[Mapa Temático] Salvo → {thematic_path}\n")
            self._open_in_webview("Blicsa - Mapa Temático", thematic_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
            
            # Removed automatic AI call
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Mapa Temático", str(exc))

    def _open_historiograph(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        try:
            fig = build_historiograph(self._dataframe)
            import time
            hist_path = str(OUTPUT_DIR / f"blicsa_historiografia_{int(time.time())}.html")
            fig.write_html(hist_path, include_plotlyjs="cdn")
            print(f"[Historiografia] Salva → {hist_path}\n")
            self._open_in_webview("Blicsa - Historiografia", hist_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
            
            # Removed automatic AI call
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Historiografia", str(exc))

    # ── AI ─────────────────────────────────────────────────────────────
    def _run_ai(self):
        if getattr(self, '_dataframe', None) is None or self._dataframe.empty:
            messagebox.showwarning("Sem dados", "Importe ou busque dados antes de analisar.")
            return

        report_txt = ""
        try:
            if self._generator is not None:
                report = self._generator.get_cluster_report()
                report_txt += f"Relatório de Clusters (Mapa):\n{report}\n"
                
            # Adiciona informações gerais do dataset
            df = self._dataframe
            total_docs = len(df)
            anos = df['year'].dropna().tolist() if 'year' in df else []
            min_ano, max_ano = min(anos) if anos else '?', max(anos) if anos else '?'
            report_txt += f"\nDataset possui {total_docs} documentos, período de publicação de {min_ano} a {max_ano}.\n"
            
            if hasattr(self, '_inject_ai_context'):
                self._inject_ai_context(report_txt)
            if hasattr(self, '_toggle_ai_drawer'):
                self._toggle_ai_drawer(force_open=True)
        except Exception as e:
            messagebox.showerror("Erro IA", f"Falha ao iniciar assistente: {e}")

    def _ai_sankey_worker(self):
        try:
            self.after(0, self._set_busy, "IA analisando Sankey…")
            df = self._dataframe
            from collections import Counter as _C
            
            # Simple author -> keyword relation summary
            auths_kws = _C()
            for _, row in df.dropna(subset=["authors", "keywords"]).iterrows():
                a_list = [a.strip() for a in str(row["authors"]).split(";") if a.strip()]
                k_list = [k.strip().lower() for k in str(row["keywords"]).split(";") if k.strip()]
                for a in a_list[:5]:
                    for k in k_list[:5]:
                        auths_kws[(a, k)] += 1
            
            summary = "Top fluxos Autor -> Palavra-chave:\n"
            for (a, k), count in auths_kws.most_common(15):
                summary += f"  - Autor {a} estuda {k} ({count} vezes)\n"
                
            analyst = self._get_ai_analyst()
            result = analyst.generate_sankey_insights(summary)
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights Sankey prontos")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao analisar Sankey:\n{e}"))

    def _ai_thematic_worker(self):
        try:
            self.after(0, self._set_busy, "IA analisando Tema…")
            G = self._generator.G
            partition = nx.get_node_attributes(G, "group")
            clusters = {}
            for node, grp in partition.items():
                clusters.setdefault(grp, []).append(node)
                
            summary = "Clusters e seus termos centrais:\n"
            for c, nodes in list(clusters.items())[:8]:
                top_nodes = sorted(nodes, key=lambda n: G.nodes[n].get("occurrence", 0), reverse=True)[:5]
                cent = sum(G[u][v].get("weight", 1.0) for u in nodes for v in G.neighbors(u) if v not in nodes)
                dens = sum(G[u][v].get("weight", 1.0) for u in nodes for v in G.neighbors(u) if v in nodes) / (2.0 * len(nodes))
                summary += f"  - Cluster {c} ({len(nodes)} nós, Centralidade: {cent:.1f}, Densidade: {dens:.3f}): {', '.join(top_nodes)}\n"
                
            analyst = self._get_ai_analyst()
            result = analyst.generate_thematic_insights(summary)
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights Temáticos prontos")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao analisar Mapa Temático:\n{e}"))

    def _ai_historiograph_worker(self):
        try:
            self.after(0, self._set_busy, "IA analisando História…")
            df = self._dataframe
            top_papers = df.sort_values(by="citations", ascending=False).head(15)
            summary = "Artigos principais na linha evolutiva:\n"
            for _, row in top_papers.iterrows():
                authors = str(row.get("authors", ""))
                first = authors.split(";")[0].strip() if authors else "Anon"
                year = int(row.get("year", 0))
                cit = int(row.get("citations", 0))
                title = str(row.get("title", ""))[:60]
                summary += f"  - {first} ({year}) com {cit} citações: \"{title}...\"\n"
                
            analyst = self._get_ai_analyst()
            result = analyst.generate_historiograph_insights(summary)
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights Historiografia prontos")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao analisar Historiografia:\n{e}"))

    def _trigger_map_ai_insights(self):
        if self._dataframe is None:
            return
        try:
            print("[IA] Coletando sumário do mapa e de autores seminais...")
            df = self._dataframe
            
            # 1. Seminal authors summary
            ref_col = None
            for col in ("CR", "References", "Cited References", "references"):
                if col in df.columns:
                    ref_col = col
                    break
                    
            seminal_summary = ""
            if ref_col:
                from collections import Counter
                import re
                counter = Counter()
                for val in df[ref_col].dropna():
                    refs = [r.strip() for r in re.split(r"[;\n]", str(val)) if r.strip()]
                    for r in refs:
                        counter[r] += 1
                top_refs = counter.most_common(20)
                if top_refs:
                    seminal_summary = "Principais Trabalhos/Autores Seminais:\n"
                    for ref, count in top_refs:
                        seminal_summary += f"  - {ref} (citado {count} vezes)\n"
            
            # 2. Map thematic summary
            thematic_summary = ""
            if getattr(self, '_generator', None) and getattr(self._generator, 'G', None):
                import networkx as nx
                G = self._generator.G
                partition = nx.get_node_attributes(G, "group")
                clusters = {}
                for node, grp in partition.items():
                    clusters.setdefault(grp, []).append(node)
                
                thematic_summary = "Clusters Temáticos do Mapa:\n"
                for c, nodes in list(clusters.items())[:8]:
                    top_nodes = sorted(nodes, key=lambda n: G.nodes[n].get("occurrence", 0), reverse=True)[:5]
                    thematic_summary += f"  - Cluster {c} (Termos principais: {', '.join(top_nodes)})\n"
                    
            # 3. Request streaming response in Blink Research chat
            if not seminal_summary and not thematic_summary:
                return
                
            full_context = f"{thematic_summary}\n\n{seminal_summary}"
            prompt_msg = "O mapa bibliométrico acabou de ser gerado! Por favor, me dê:\n1. Alguns insights sobre os clusters temáticos do mapa.\n2. Quais são os principais autores seminais (trabalhos mais citados) com um pequeno resuminho sobre eles."
            
            # Use after(0) to update UI
            def _start_streaming():
                # Switch to Blink Research (home) tab automatically
                self._switch_tab("home")
                self._add_blink_message("user", prompt_msg)
                
                # Setup context
                system_prompt = self._research_messages[0]["content"]
                system_prompt += f"\n\nContexto atual:\n{full_context}"
                
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                # Indicator
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._research_chat_history_main._parent_canvas.yview_moveto(1.0)
                
                import threading
                def _stream_worker():
                    try:
                        from ai.client import AIAnalyst
                        analyst = AIAnalyst(api_key=self._api_key_var.get() or None, base_url=self._ai_base_url_var.get(), model=self._ai_model_var.get())
                        stream = analyst.chat_history_stream(messages, temperature=0.7)
                        
                        full_response = ""
                        tb_ref = []
                        from core.markdown_parser import insert_markdown
                        
                        for chunk in stream:
                            full_response += chunk
                            def update_chunk(resp=full_response):
                                if indicator_row.winfo_exists():
                                    indicator_row.destroy()
                                if not tb_ref:
                                    tb, upd, _ = self._add_blink_message("assistant", "")
                                    tb_ref.append((tb, upd))
                                tb, upd = tb_ref[0]
                                tb.configure(state="normal")
                                tb.delete("1.0", "end")
                                insert_markdown(tb, resp)
                                tb.configure(state="disabled")
                                upd()
                            self.after(0, update_chunk)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                    except Exception as ex:
                        if indicator_row.winfo_exists(): indicator_row.destroy()
                        self.after(0, lambda e=ex: self._add_blink_message("assistant", f"Erro: {e}"))
                threading.Thread(target=_stream_worker, daemon=True).start()
                
            self.after(0, _start_streaming)
            
        except Exception as exc:
            print(f"[ERRO IA] {exc}\n")

    def _trigger_corpus_ai_insights(self):
        if self._dataframe is None or self._dataframe.empty:
            return
            
        try:
            print("[IA] Analisando o corpus selecionado...")
            df = self._dataframe
            
            # Prepare context
            total_docs = len(df)
            years = df.get('year', df.iloc[:,0]).dropna()
            try:
                years = years.astype(int)
                years = years[years > 0]
                year_min, year_max = int(years.min()), int(years.max()) if not years.empty else ("?", "?")
            except:
                year_min, year_max = "?", "?"
            
            # Top authors
            from collections import Counter
            all_authors = []
            if 'authors' in df.columns:
                for a in df['authors'].dropna().astype(str):
                    all_authors.extend([x.strip() for x in a.split(';') if x.strip()])
            top_authors = [a for a, c in Counter(all_authors).most_common(5)]
            
            # Top sources
            all_sources = []
            if 'source' in df.columns:
                for s in df['source'].dropna().astype(str):
                    all_sources.extend([x.strip() for x in s.split(';') if x.strip()])
            top_sources = [s for s, c in Counter(all_sources).most_common(5)]
            
            # User filters (search queries or local filters)
            query = self._search_query.get().strip() if getattr(self, '_search_query', None) else "Não especificada / Filtro Local"
            
            context = f"**Estatísticas do Corpus:**\n"
            context += f"- Documentos: {total_docs}\n"
            context += f"- Período: {year_min} a {year_max}\n"
            context += f"- Top Autores: {', '.join(top_authors)}\n"
            context += f"- Top Fontes: {', '.join(top_sources)}\n"
            context += f"- Termo de Busca Original: {query}\n"
            
            prompt_msg = "Gere uma análise justificando a escolha e a utilidade acadêmica deste corpus. Para que ele serve? Quais critérios parecem unir esses documentos e por que outros documentos (de outras épocas, áreas ou autores) podem ter sido deixados de fora dessa filtragem?"
            
            def _start_streaming():
                self._switch_tab("home")
                self._add_blink_message("user", prompt_msg)
                
                system_prompt = self._research_messages[0]["content"]
                system_prompt += f"\n\nContexto atual (Corpus Selecionado):\n{context}"
                
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._research_chat_history_main._parent_canvas.yview_moveto(1.0)
                
                import threading
                def _stream_worker():
                    try:
                        from ai.client import AIAnalyst
                        analyst = AIAnalyst(api_key=self._api_key_var.get() or None, base_url=self._ai_base_url_var.get(), model=self._ai_model_var.get())
                        stream = analyst.chat_history_stream(messages, temperature=0.7)
                        
                        full_response = ""
                        tb_ref = []
                        from core.markdown_parser import insert_markdown
                        
                        for chunk in stream:
                            full_response += chunk
                            def update_chunk(resp=full_response):
                                if indicator_row.winfo_exists():
                                    indicator_row.destroy()
                                if not tb_ref:
                                    tb, upd, _ = self._add_blink_message("assistant", "")
                                    tb_ref.append((tb, upd))
                                tb, upd = tb_ref[0]
                                tb.configure(state="normal")
                                tb.delete("1.0", "end")
                                insert_markdown(tb, resp)
                                tb.configure(state="disabled")
                                upd()
                            self.after(0, update_chunk)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                    except Exception as ex:
                        if indicator_row.winfo_exists(): indicator_row.destroy()
                        self.after(0, lambda e=ex: self._add_blink_message("assistant", f"Erro: {e}"))
                threading.Thread(target=_stream_worker, daemon=True).start()
                
            self.after(0, _start_streaming)
            
        except Exception as exc:
            print(f"[ERRO IA Corpus] {exc}\n")

    def _trigger_import_ai_assistant(self):
        try:
            print("[IA] Analisando os parâmetros de busca...")
            
            query = self._search_query_entry.get().strip()
            if not query:
                prompt_msg = "Preciso de ajuda para criar uma string de busca bibliométrica. Quais dicas e operadores booleanos você sugere para uma pesquisa eficiente? OBRIGATÓRIO 1: No final da sua resposta, forneça pelo menos um exemplo de string de busca completa e pronta para copiar e colar. OBRIGATÓRIO 2: A string DEVE CONTER APENAS termos de pesquisa e booleanos. NUNCA INCLUA filtros de ano ou idioma DENTRO DA STRING, pois o software já possui filtros visuais para isso."
                context = "**Nenhuma string de busca informada.**"
            else:
                provider = self._search_provider_var.get()
                start_yr = self._search_year_start.get().strip() or "Qualquer"
                end_yr = self._search_year_end.get().strip() or "Qualquer"
                doc_type = self._search_type_var.get()
                lang = self._search_lang_var.get()
                oa = "Sim" if self._search_oa_var.get() else "Não exigido"
                
                context = f"**Parâmetros de Busca Configurados:**\n"
                context += f"- Base: {provider.upper()}\n"
                context += f"- String: `{query}`\n"
                context += f"- Período: {start_yr} a {end_yr}\n"
                context += f"- Tipo de Documento: {doc_type}\n"
                context += f"- Idioma: {lang}\n"
                context += f"- Open Access: {oa}\n"
                
                prompt_msg = f"Eu configurei esta busca bibliométrica. Justifique as escolhas dessa string (prós e contras) e me dê sugestões de refinamento. OBRIGATÓRIO 1: No final da resposta, forneça pelo menos uma nova string de busca completa e pronta para copiar e colar. OBRIGATÓRIO 2: A nova string DEVE CONTER APENAS termos temáticos e booleanos. NUNCA INCLUA idioma, anos ou tipos de documento (ex: 2020:*, English, etc) DENTRO DA STRING. O software tem filtros nativos para isso, instrua o usuário a usar os botões do Blicsa para essas restrições adicionais."

            def _start_streaming():
                self._switch_tab("home")
                self._add_blink_message("user", prompt_msg)
                
                system_prompt = self._research_messages[0]["content"]
                system_prompt += f"\n\nContexto atual (Busca em Configuração):\n{context}"
                
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._research_chat_history_main._parent_canvas.yview_moveto(1.0)
                
                import threading
                def _stream_worker():
                    try:
                        from ai.client import AIAnalyst
                        analyst = AIAnalyst(api_key=self._api_key_var.get() or None, base_url=self._ai_base_url_var.get(), model=self._ai_model_var.get())
                        stream = analyst.chat_history_stream(messages, temperature=0.7)
                        
                        full_response = ""
                        tb_ref = []
                        from core.markdown_parser import insert_markdown
                        
                        for chunk in stream:
                            full_response += chunk
                            def update_chunk(resp=full_response):
                                if indicator_row.winfo_exists():
                                    indicator_row.destroy()
                                if not tb_ref:
                                    tb, upd, _ = self._add_blink_message("assistant", "")
                                    tb_ref.append((tb, upd))
                                tb, upd = tb_ref[0]
                                tb.configure(state="normal")
                                tb.delete("1.0", "end")
                                insert_markdown(tb, resp)
                                tb.configure(state="disabled")
                                upd()
                            self.after(0, update_chunk)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                    except Exception as ex:
                        if indicator_row.winfo_exists(): indicator_row.destroy()
                        self.after(0, lambda e=ex: self._add_blink_message("assistant", f"Erro: {e}"))
                threading.Thread(target=_stream_worker, daemon=True).start()
                
            self.after(0, _start_streaming)
            
        except Exception as exc:
            print(f"[ERRO IA Assistente Busca] {exc}\n")


    def _show_seminal_insights(self, text: str):
        from ui.components import insert_markdown
        insert_markdown(self._seminal_box, text)

    def _create_seminal_library(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return
            
        ref_col = None
        for col in ("CR", "References", "Cited References", "references"):
            if col in self._dataframe.columns:
                ref_col = col
                break
        if not ref_col:
            messagebox.showerror("Erro", "Nenhuma coluna de referências encontrada no dataset.")
            return
            
        folder_path = filedialog.askdirectory(title="Selecione onde criar a pasta da biblioteca")
        if not folder_path:
            return
            
        from tkinter import simpledialog
        folder_name = simpledialog.askstring("Nome da Pasta", "Qual o nome da pasta da biblioteca?", initialvalue="Biblioteca_Artigos_Seminais")
        if not folder_name:
            return
            
        full_path = Path(folder_path) / folder_name.strip()
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            
            from collections import Counter
            import re
            
            counter = Counter()
            for val in self._dataframe[ref_col].dropna():
                refs = [r.strip() for r in re.split(r"[;\n]", str(val)) if r.strip()]
                for r in refs:
                    counter[r] += 1
                    
            top_refs = counter.most_common(20)
            if not top_refs:
                messagebox.showinfo("Sem referências", "Nenhuma referência encontrada para gerar arquivos.")
                return
                
            self._set_busy("Buscando metadados dos artigos seminais (OpenAlex)...")
            threading.Thread(
                target=self._create_seminal_library_worker,
                args=(full_path, top_refs),
                daemon=True
            ).start()
            
        except Exception as exc:
            messagebox.showerror("Erro ao criar biblioteca", str(exc))

    def _create_seminal_library_worker(self, full_path, top_refs):
        import urllib.request
        import urllib.parse
        import json
        import re
        
        created_count = 0
        for ref, count in top_refs:
            # 1. Determinar o nome base do arquivo
            match = re.search(r'\b(19\d\d|20\d\d)\b', ref)
            if match:
                year = match.group(1)
                parts = ref.split(year)
                author = parts[0].strip(", \n\t")
                author = re.sub(r'[\\/*?:"<>|]', "", author)
                filename = f"{author} ({year})"
            else:
                filename = re.sub(r'[\\/*?:"<>|]', "", ref)
                
            filename = filename.strip()
            if len(filename) > 110:
                filename = filename[:107] + "..."
            
            # 2. Buscar metadados e resumo (abstract) via OpenAlex API
            title = None
            abstract = None
            url = None
            
            # Tenta encontrar um DOI no formato 10.xxxx/...
            doi_match = re.search(r'(10\.\d{4,9}/[^\s,;]+)', ref)
            if doi_match:
                doi = doi_match.group(1).strip(".,;()")
                url = f"https://doi.org/{doi}"
                try:
                    openalex_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
                    req = urllib.request.Request(
                        openalex_url, 
                        headers={'User-Agent': 'mailto:leopaniago2@gmail.com'}
                    )
                    with urllib.request.urlopen(req, timeout=5) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        title = data.get("title")
                        inv_index = data.get("abstract_inverted_index")
                        if inv_index:
                            abstract_words = {}
                            for word, pos_list in inv_index.items():
                                for pos in pos_list:
                                    abstract_words[pos] = word
                            sorted_words = [abstract_words[p] for p in sorted(abstract_words.keys())]
                            abstract = " ".join(sorted_words)
                        
                        oa = data.get("open_access", {})
                        if oa.get("is_oa") and oa.get("oa_url"):
                            url = oa.get("oa_url")
                except Exception:
                    pass
            
            # Se não resolveu por DOI, faz busca textual no OpenAlex
            if not title or not abstract:
                try:
                    clean_ref = re.sub(r'\[.*?\]', '', ref)  # limpa colchetes
                    query = urllib.parse.quote(clean_ref)
                    openalex_url = f"https://api.openalex.org/works?q={query}&limit=1"
                    req = urllib.request.Request(
                        openalex_url, 
                        headers={'User-Agent': 'mailto:leopaniago2@gmail.com'}
                    )
                    with urllib.request.urlopen(req, timeout=5) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        results = data.get("results", [])
                        if results:
                            work = results[0]
                            title = work.get("title")
                            inv_index = work.get("abstract_inverted_index")
                            if inv_index:
                                abstract_words = {}
                                for word, pos_list in inv_index.items():
                                    for pos in pos_list:
                                        abstract_words[pos] = word
                                sorted_words = [abstract_words[p] for p in sorted(abstract_words.keys())]
                                abstract = " ".join(sorted_words)
                            
                            if not url:
                                oa = work.get("open_access", {})
                                if oa.get("is_oa") and oa.get("oa_url"):
                                    url = oa.get("oa_url")
                                else:
                                    url = work.get("doi") or work.get("id")
                except Exception:
                    pass
            
            # 3. Escrever arquivo de descrição em formato .txt
            txt_filename = filename + "_DESCRICAO.txt"
            content_lines = [
                f"==================================================",
                f" ARTIGO SEMINAL - BLICSA / PYBIBLIOMICS",
                f"==================================================\n",
                f"Referência Original: {ref}",
                f"Citações no Dataset: {count} vezes\n",
                f"Título do Artigo:   {title or 'Não identificado pela API OpenAlex'}",
                f"Link / DOI / OA:    {url or 'Link não encontrado'}\n",
                f"Resumo / Descrição:",
                f"--------------------------------------------------",
                f"{abstract or 'Resumo/Abstract não disponível nas fontes de dados abertos.'}",
                f"--------------------------------------------------"
            ]
            
            try:
                with open(full_path / txt_filename, "w", encoding="utf-8") as f:
                    f.write("\n".join(content_lines))
                created_count += 1
            except Exception as e:
                print(f"[ERRO ao gravar arquivo {txt_filename}] {e}")
                
        # 4. Finalização na main thread do Tkinter
        def _done():
            self._set_idle()
            messagebox.showinfo("Sucesso", f"Biblioteca de seminais criada com sucesso!\n\nPasta: {full_path}\nArquivos de descrição gerados: {created_count}")
            webbrowser.open(f"file://{full_path}")
            
        self.after(0, _done)

    # ── Rankings ────────────────────────────────────────────────────────
    def _show_ranking(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo.")
            return
        gen  = self._generator or NetworkGenerator(self._dataframe)
        kind = self._rank_var.get()

        # Clear existing rows and columns
        self._rank_tree.delete(*self._rank_tree.get_children())
        self._rank_sort_col = None
        self._rank_sort_rev = False

        def _setup_cols(cols: list[tuple[str, int, str]]):
            self._rank_tree.configure(columns=[c[0] for c in cols])
            for name, width, anchor in cols:
                self._rank_tree.heading(
                    name, text=name,
                    command=lambda c=name: self._sort_rank_tree(c))
                self._rank_tree.column(name, width=width, anchor=anchor, stretch=(width > 150))

        if kind == "keywords":
            _setup_cols([
                ("#",          48,  "center"),
                ("Termo",     300,  "w"),
                ("Ocorrências", 110, "e"),
                ("Grau",       90,  "e"),
                ("Ano Médio",  100, "e"),
            ])
            if self._generator and self._generator.G.number_of_nodes() > 0:
                G = self._generator.G
                nodes = sorted(
                    G.nodes(data=True),
                    key=lambda x: x[1].get("occurrence", 0),
                    reverse=True,
                )[:100]
                for i, (n, d) in enumerate(nodes, 1):
                    yr = d.get("year_mean", 0)
                    self._rank_tree.insert("", "end", values=(
                        i, n,
                        d.get("occurrence", "—"),
                        f"{G.degree(n, weight='weight'):.1f}",
                        f"{yr:.0f}" if yr else "—",
                    ))
            else:
                for i, (kw, n) in enumerate(gen.get_top_keywords(100), 1):
                    self._rank_tree.insert("", "end", values=(i, kw, n, "—", "—"), tags=("striped",) if i % 2 == 0 else ())

        elif kind == "authors":
            _setup_cols([
                ("#",         48,  "center"),
                ("Autor",    400,  "w"),
                ("Publicações", 110, "e"),
            ])
            for i, (a, n) in enumerate(gen.get_top_authors(100), 1):
                self._rank_tree.insert("", "end", values=(i, a, n), tags=("striped",) if i % 2 == 0 else ())

        elif kind == "hindex":
            _setup_cols([
                ("#",          48,  "center"),
                ("Autor",     280,  "w"),
                ("h-index",    80,  "e"),
                ("g-index",    80,  "e"),
                ("Artigos",    80,  "e"),
                ("Cit. Média", 100, "e"),
            ])
            for i, (author, h, g, papers, avg) in enumerate(gen.get_author_hindex(100), 1):
                self._rank_tree.insert("", "end", values=(
                    i, author, h, g, papers, f"{avg:.1f}"))

        elif kind == "sources":
            _setup_cols([
                ("#",              48,  "center"),
                ("Fonte / Periódico", 440, "w"),
                ("Publicações",    110, "e"),
            ])
            for i, (s, n) in enumerate(gen.get_top_sources(100), 1):
                self._rank_tree.insert("", "end", values=(i, s, n), tags=("striped",) if i % 2 == 0 else ())

        else:  # clusters
            _setup_cols([
                ("Cluster",   70,  "center"),
                ("Rótulo IA", 220, "w"),
                ("Nós",       70,  "e"),
                ("Top Termos / Autores", 450, "w"),
            ])
            for c in gen.get_cluster_report():
                label = self._cluster_labels.get(c["cluster_id"], "—")
                self._rank_tree.insert("", "end", values=(
                    f"C{c['cluster_id']}",
                    label,
                    c["size"],
                    ", ".join(c["top_nodes"][:8]),
                ))

    def _sort_rank_tree(self, col: str):
        reverse = (self._rank_sort_col == col) and (not self._rank_sort_rev)
        self._rank_sort_col = col
        self._rank_sort_rev = reverse
        data = [
            (self._rank_tree.set(child, col), child)
            for child in self._rank_tree.get_children("")
        ]
        try:
            data.sort(key=lambda x: float(x[0].replace("—", "-1")), reverse=reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for idx, (_, child) in enumerate(data):
            self._rank_tree.move(child, "", idx)

    # ── Exports ─────────────────────────────────────────────────────────
    def _require_gen(self) -> NetworkGenerator | None:
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
        return self._generator

    def _export_nodes_csv(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")]):
            gen.export_rankings_csv(path)
            print(f"[Export] Nós → {path}")

    def _export_edges_csv(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")]):
            gen.export_edges_csv(path)
            print(f"[Export] Arestas → {path}")

    def _export_df_csv(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")]):
            self._dataframe.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"[Export] DataFrame → {path}")

    def _export_clusters_txt(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".txt", filetypes=[("Text", "*.txt")]):
            with open(path, "w", encoding="utf-8") as f:
                for c in gen.get_cluster_report():
                    f.write(
                        f"Cluster {c['cluster_id']}  |  "
                        f"{c['size']} nós  |  {c['color']}\n"
                        f"  Top nós: {', '.join(c['top_nodes'])}\n\n"
                    )
            print(f"[Export] Clusters → {path}")

    def _export_plotly_html(self):
        if not Path(PLOTLY_PATH).exists():
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".html", filetypes=[("HTML", "*.html")]):
            import shutil
            shutil.copy(PLOTLY_PATH, path)
            print(f"[Export] Plotly HTML → {path}")

    def _export_pyvis_html(self):
        if not Path(MAP_PATH).exists():
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".html", filetypes=[("HTML", "*.html")]):
            import shutil
            shutil.copy(MAP_PATH, path)
            print(f"[Export] PyVis HTML → {path}")

    def _export_png(self):
        if self._map_canvas is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".png", filetypes=[("PNG", "*.png")]):
            export_figure_image(self._map_canvas.figure, path, dpi=300)

    def _export_svg(self):
        if self._map_canvas is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".svg", filetypes=[("SVG", "*.svg")]):
            export_figure_image(self._map_canvas.figure, path, dpi=150)

    def _export_pdf(self):
        if self._map_canvas is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".pdf", filetypes=[("PDF", "*.pdf")]):
            export_figure_image(self._map_canvas.figure, path, dpi=300)

    def _export_excel(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")]):
            gen.export_excel(path, df_raw=self._dataframe)
            print(f"[Export] Excel → {path}\n")

    def _export_gml(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".gml", filetypes=[("GML", "*.gml")]):
            gen.export_gml(path)
            print(f"[Export] GML → {path}")

    def _export_gexf(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".gexf", filetypes=[("GEXF", "*.gexf")]):
            gen.export_gexf(path)
            print(f"[Export] GEXF → {path}\n")

    def _export_pajek(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".net", filetypes=[("Pajek", "*.net")]):
            gen.export_pajek(path)
            print(f"[Export] Pajek → {path}")

    def _export_json(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".json", filetypes=[("JSON", "*.json")]):
            gen.export_json_topology(path, positions=self._positions)
            print(f"[Export] JSON topologia → {path}")

    def _export_vosviewer(self):
        if not (gen := self._require_gen()):
            return
        map_path = filedialog.asksaveasfilename(
            title="Salvar VOSviewer Map File",
            defaultextension=".txt",
            filetypes=[("VOSviewer Map (*.txt)", "*.txt")]
        )
        if not map_path:
            return
        net_path = map_path.replace(".txt", "_network.txt")
        if net_path == map_path:
            net_path = map_path + "_network.txt"
        gen.export_vosviewer(map_path, net_path, positions=self._positions)
        print(f"[Export] VOSviewer Map → {map_path}")
        print(f"[Export] VOSviewer Network → {net_path}")
        messagebox.showinfo("Exportação Concluída", f"Arquivos do VOSviewer exportados com sucesso!\n\nMapa: {map_path}\nRede: {net_path}")

    def _save_project_gui(self):
        import os
        proj_dir = getattr(self, "_projects_dir_var", ctk.StringVar(value=os.path.expanduser("~/Blicsa/projects"))).get()
        os.makedirs(proj_dir, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=proj_dir,
            defaultextension=".blicsa",
            filetypes=[("Projeto Blicsa", "*.blicsa")],
            title="Salvar Projeto Blicsa",
        )
        if not path:
            return
        self._set_busy("Salvando projeto...")
        try:
            from core.project import save_blicsa_project
            config = {
                "map_type":     self._map_type_var.get(),
                "field":        self._field_var.get(),
                "counting":     self._counting_var.get(),
                "assoc_strength": self._assoc_var.get(),
                "min_occ":      self._min_occ_var.get(),
                "max_nodes":    self._max_nodes_var.get(),
                "max_pct":      self._max_pct_var.get(),
                "fa2_iter":     self._fa2_iter_var.get(),
                "linlog":       self._linlog_var.get(),
                "viz_mode":     self._viz_mode_var.get(),
                "plotly_mode":  self._plotly_mode_var.get(),
                "year_min":     self._year_min_var.get(),
                "year_max":     self._year_max_var.get(),
                "extra_sw":     self._extra_sw_var.get(),
                "cluster_algorithm": self._cluster_alg_var.get(),
                "cluster_resolution": self._cluster_res_var.get(),
            }
            
            thumbnail_path = None
            if hasattr(self, '_map_canvas') and getattr(self._map_canvas, 'figure', None) is not None:
                import tempfile
                tmp_png = tempfile.mktemp(suffix=".png")
                self._map_canvas.figure.savefig(tmp_png, dpi=72, bbox_inches='tight')
                thumbnail_path = tmp_png

            save_blicsa_project(
                path,
                df=self._dataframe,
                config=config,
                positions=self._positions,
                G=self._generator.G if self._generator else None,
                cluster_labels=self._cluster_labels,
                searches=getattr(self, "_searches", []),
                thumbnail_path=thumbnail_path
            )
            
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                
            self._set_idle(f"Projeto salvo: {Path(path).name}")
            messagebox.showinfo("Sucesso", "Projeto salvo com sucesso!")
            
            if hasattr(self, "_projects_view"):
                self._projects_view.refresh()
                
        except Exception as e:
            self._set_idle("Erro ao salvar projeto")
            messagebox.showerror("Erro ao salvar", str(e))

    def _load_project_gui(self):
        path = filedialog.askopenfilename(
            filetypes=[("Projeto Blicsa", "*.blicsa")],
            title="Carregar Projeto Blicsa",
        )
        if not path:
            return
        self._set_busy("Carregando projeto...")
        try:
            from core.project import load_blicsa_project
            from core.matrix_builders import NetworkGenerator
            
            project_data = load_blicsa_project(path)
            
            # 1. Restore configuration
            config = project_data.get("config", {})
            setters: list[tuple] = [
                ("map_type",      self._map_type_var,  "set"),
                ("field",         self._field_var,      "set"),
                ("counting",      self._counting_var,   "set"),
                ("assoc_strength",self._assoc_var,      "set"),
                ("min_occ",       self._min_occ_var,    "set"),
                ("fa2_iter",      self._fa2_iter_var,   "set"),
                ("linlog",        self._linlog_var,      "set"),
                ("viz_mode",      self._viz_mode_var,   "set"),
                ("plotly_mode",   self._plotly_mode_var,"set"),
                ("cluster_algorithm", self._cluster_alg_var, "set"),
                ("cluster_resolution", self._cluster_res_var, "set"),
            ]
            for key, var, _ in setters:
                if (v := config.get(key)) is not None:
                    var.set(v)
            for key, var in [
                ("max_nodes", self._max_nodes_var),
                ("max_pct",   self._max_pct_var),
                ("year_min",  self._year_min_var),
                ("year_max",  self._year_max_var),
                ("extra_sw",  self._extra_sw_var),
            ]:
                if (v := config.get(key)) is not None:
                    var.set(str(v))
                    
            # 2. Restore dataset
            self._dataframe = project_data.get("df")
            
            # 3. Restore layout and generator
            self._positions = project_data.get("positions", {})
            self._cluster_labels = project_data.get("cluster_labels", {})
            
            G = project_data.get("G")
            if G is not None:
                self._generator = NetworkGenerator(self._dataframe)
                self._generator.G = G
                self._generator.clustering_algorithm = self._cluster_alg_var.get()
                self._generator.clustering_resolution = self._cluster_res_var.get()
                
            self._refresh_candidate_counts()
            self._update_stats_tab()
            self._set_idle("Projeto carregado com sucesso")
            
            if self._dataframe is not None and not self._dataframe.empty:
                self.after(0, lambda: self._switch_tab("viz"))
                
            messagebox.showinfo("Sucesso", "Projeto carregado com sucesso!")
        except Exception as e:
            self._set_idle("Erro ao carregar projeto")
            messagebox.showerror("Erro ao carregar", str(e))

    def _get_ai_analyst(self):
        from ai.client import GroqBibliometricAnalyst
        return GroqBibliometricAnalyst(
            api_key=self._api_key_var.get().strip() or None,
            base_url=self._ai_base_url_var.get().strip() or None,
            model=self._ai_model_var.get().strip() or None
        )

    def _on_ai_provider_change(self, provider):
        presets = {
            "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
            "openai": ("https://api.openai.com/v1", "gpt-4o"),
            "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3-70b-instruct"),
            "ollama": ("http://localhost:11434/v1", "llama3"),
        }
        if provider in presets:
            base, model = presets[provider]
            self._ai_base_url_var.set(base)
            self._ai_model_var.set(model)

    # ── Tab: Estatísticas ──────────────────────────────────────────────
    # ── Deduplication ──────────────────────────────────────────────────
    def _run_dedup(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return
        print("[Dedup] Procurando duplicatas…")
        df    = self._dataframe
        dupes = find_duplicates(df, title_threshold=0.93)
        if not dupes:
            messagebox.showinfo("Deduplicação", "Nenhuma duplicata encontrada.")
            print("[Dedup] Nenhuma duplicata.\n")
            return
        print(f"[Dedup] {len(dupes)} par(es) encontrado(s).\n")
        DeduplicationDialog(self, df, dupes, self._apply_dedup)

    def _apply_dedup(self, to_remove: set[int]):
        if not to_remove:
            return
        before = len(self._dataframe)
        self._dataframe = (
            self._dataframe
            .drop(index=list(to_remove))
            .reset_index(drop=True)
        )
        removed = before - len(self._dataframe)
        print(f"[Dedup] {removed} registro(s) removido(s). Base: {len(self._dataframe)} registros.\n")
        self._generator = None
        self.after(0, self._update_stats_tab)

    # ── Word Cloud ─────────────────────────────────────────────────────
    def _show_wordcloud(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return
        try:
            from wordcloud import WordCloud
        except ImportError:
            messagebox.showerror("Dependência", "Instale: pip install wordcloud")
            return

        self._set_busy("Gerando Nuvem de Palavras…")
        threading.Thread(target=self._wordcloud_worker, daemon=True).start()

    def _wordcloud_worker(self):
        try:
            import re
            from wordcloud import WordCloud
            
            field = self._field_var.get() if hasattr(self, "_field_var") else "keywords"
            col   = {"keywords": "keywords", "titles": "title",
                     "abstracts": "abstract", "titles_abstracts": "abstract"}.get(field, "keywords")

            if self._candidate_counts:
                freq = dict(self._candidate_counts)
            else:
                from collections import Counter as _C
                sep_re = re.compile(r"[;,]")
                words: list[str] = []
                for s in self._dataframe[col].dropna():
                    words.extend(w.strip().lower() for w in sep_re.split(str(s)) if len(w.strip()) > 2)
                freq = dict(_C(words).most_common(200))

            if not freq:
                self.after(0, self._set_idle, "Pronto")
                self.after(0, lambda: messagebox.showinfo("Word Cloud", "Nenhum termo encontrado."))
                return

            wc = WordCloud(
                width=1000, height=600,
                background_color="#0d0d1f",
                colormap="plasma",
                max_words=150,
                prefer_horizontal=0.85,
                min_font_size=8,
                max_font_size=90,
                collocations=False,
            ).generate_from_frequencies(freq)

            self.after(0, self._display_wordcloud, wc)
        except Exception as exc:
            self.after(0, self._set_idle, "Erro Nuvem")
            self.after(0, lambda e=exc: messagebox.showerror("Erro", f"Erro ao gerar nuvem de palavras:\n{e}"))

    def _display_wordcloud(self, wc):
        self._set_idle("Nuvem gerada")
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            win = ctk.CTkToplevel(self)
            win.title("Blicsa — Nuvem de Palavras")
            win.geometry("1020x640")
            win.configure(fg_color="#0d0d1f")
            win.grid_rowconfigure(0, weight=1)
            win.grid_columnconfigure(0, weight=1)

            fig, ax = plt.subplots(figsize=(10, 6), dpi=110, facecolor="#0d0d1f")
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            fig.tight_layout(pad=0)

            cv = FigureCanvasTkAgg(fig, master=win)
            cv.get_tk_widget().grid(row=0, column=0, sticky="nsew")

            def _save():
                path = filedialog.asksaveasfilename(
                    defaultextension=".png", filetypes=[("PNG", "*.png"), ("SVG", "*.svg")])
                if path:
                    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="#0d0d1f")
                    print(f"[Word Cloud] Salva → {path}\n")

            ctk.CTkButton(
                win, text="💾  Salvar", height=34,
                fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000",
                command=_save,
            ).grid(row=1, column=0, pady=8)
            cv.draw()
            win.lift()
            win.focus()
        except Exception as exc:
            messagebox.showerror("Erro de Exibição", str(exc))

    # ── Trend chart ────────────────────────────────────────────────────
    def _open_trends(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return
        counts = Counter(self._candidate_counts)
        if not counts and self._generator:
            counts = Counter({
                n: d.get("occurrence", 1)
                for n, d in self._generator.G.nodes(data=True)
            })
        if not counts:
            messagebox.showwarning(
                "Sem termos",
                "Carregue dados e gere o mapa (ou os candidatos) antes de abrir as Tendências.",
            )
            return
        field_map = {
            "keywords":         "keywords",
            "titles":           "title",
            "abstracts":        "abstract",
            "titles_abstracts": "abstract",
        }
        field = field_map.get(self._field_var.get(), "keywords")
        win = TrendChartWindow(
            self, self._dataframe, counts,
            field=field, thesaurus=self._thesaurus,
        )
        win.lift()
        win.focus()

    # ── Cluster auto-labeling ───────────────────────────────────────────
    def _auto_label_clusters(self):
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        threading.Thread(target=self._label_clusters_worker, daemon=True).start()

    def _label_clusters_worker(self):
        try:
            self.after(0, self._set_busy, "IA nomeando clusters…")
            print("[IA] Nomeando clusters com IA...")
            analyst = self._get_ai_analyst()
            report = self._generator.get_cluster_report()
            labels = analyst.label_clusters(report, context=self._field_var.get())
            self._cluster_labels = labels

            self.after(0, self._set_idle, f"{len(labels)} clusters nomeados")
            print(f"[IA] {len(labels)} clusters nomeados.\n")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro ao nomear clusters")
            print(f"[ERRO labeling] {exc}\n")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao nomear clusters com IA:\n{e}"))

    # ── Config save / load ─────────────────────────────────────────────
    def _save_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Salvar configuração",
        )
        if not path:
            return
        import json
        config = {
            "map_type":     self._map_type_var.get(),
            "field":        self._field_var.get(),
            "counting":     self._counting_var.get(),
            "assoc_strength": self._assoc_var.get(),
            "min_occ":      self._min_occ_var.get(),
            "max_nodes":    self._max_nodes_var.get(),
            "max_pct":      self._max_pct_var.get(),
            "fa2_iter":     self._fa2_iter_var.get(),
            "linlog":       self._linlog_var.get(),
            "viz_mode":     self._viz_mode_var.get(),
            "plotly_mode":  self._plotly_mode_var.get(),
            "year_min":     self._year_min_var.get(),
            "year_max":     self._year_max_var.get(),
            "extra_sw":     self._extra_sw_var.get(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"[Config] Salvo → {path}\n")

    def _load_config(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Carregar configuração",
        )
        if not path:
            return
        import json
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        setters: list[tuple] = [
            ("map_type",      self._map_type_var,  "set"),
            ("field",         self._field_var,      "set"),
            ("counting",      self._counting_var,   "set"),
            ("assoc_strength",self._assoc_var,      "set"),
            ("min_occ",       self._min_occ_var,    "set"),
            ("fa2_iter",      self._fa2_iter_var,   "set"),
            ("linlog",        self._linlog_var,      "set"),
            ("viz_mode",      self._viz_mode_var,   "set"),
            ("plotly_mode",   self._plotly_mode_var,"set"),
        ]
        for key, var, _ in setters:
            if (v := config.get(key)) is not None:
                var.set(v)
        for key, var in [
            ("max_nodes", self._max_nodes_var),
            ("max_pct",   self._max_pct_var),
            ("year_min",  self._year_min_var),
            ("year_max",  self._year_max_var),
            ("extra_sw",  self._extra_sw_var),
        ]:
            if (v := config.get(key)) is not None:
                var.set(str(v))
        self._update_thresh_label()
        print(f"[Config] Carregado ← {path}\n")

    def _build_tab_stats(self) -> ctk.CTkFrame:
        frame = self._tab()
        frame.grid_rowconfigure(1, weight=1)
        self._h1(frame, "Estatísticas da Base", 0)

        card = self._card(frame, 1)
        card.grid_rowconfigure(0, weight=1)
        self._stats_box = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Courier", size=12),
            fg_color=CARD2_BG,
        )
        self._stats_box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self._stats_box.insert(
            "end",
            "Carregue um arquivo para ver as estatísticas da base.\n",
        )
        self._stats_box.configure(state="disabled")
        return frame

    def _update_stats_tab(self):
        if self._dataframe is None:
            return
        df = self._dataframe
        lines: list[str] = []

        lines.append("═" * 60)
        lines.append("  ESTATÍSTICAS DESCRITIVAS DA BASE")
        lines.append("═" * 60)
        lines.append(f"  Total de registros : {len(df)}")

        if "year" in df.columns:
            yr = df["year"].replace(0, None).dropna()
            if not yr.empty:
                lines.append(f"  Período             : {int(yr.min())} – {int(yr.max())}")
                lines.append(f"  Mediana (ano)       : {int(yr.median())}")

        if "citations" in df.columns:
            cit = df["citations"].dropna()
            if not cit.empty:
                lines.append(f"  Citações totais     : {int(cit.sum())}")
                lines.append(f"  Média de citações   : {cit.mean():.1f}")
                lines.append(f"  Máx. citações       : {int(cit.max())}")

        if "source" in df.columns:
            lines.append("")
            lines.append("─" * 60)
            lines.append("  TOP 15 FONTES / PERIÓDICOS")
            lines.append("─" * 60)
            top_sources = Counter(df["source"].dropna()).most_common(15)
            for i, (src, n) in enumerate(top_sources, 1):
                lines.append(f"  {i:>2}. {src[:48]:<48} {n:>5}")

        if "year" in df.columns:
            lines.append("")
            lines.append("─" * 60)
            lines.append("  DISTRIBUIÇÃO POR ANO")
            lines.append("─" * 60)
            yr = df["year"].replace(0, None).dropna().astype(int)
            year_counts = Counter(yr)
            
            # Calculate Compound Annual Growth Rate (CAGR)
            years = sorted(year_counts.keys())
            if len(years) > 1:
                y_start, y_end = years[0], years[-1]
                n_start, n_end = year_counts[y_start], year_counts[y_end]
                span = y_end - y_start
                if span > 0 and n_start > 0 and n_end > 0:
                    cagr = (n_end / n_start) ** (1 / span) - 1
                    lines.append(f"  Produção Inicial ({y_start}): {n_start} artigos")
                    lines.append(f"  Produção Final ({y_end}): {n_end} artigos")
                    lines.append(f"  Taxa de Crescimento Anual (CAGR): {cagr:.1%}")
                    lines.append("─" * 60)

            max_count = max(year_counts.values(), default=1)
            for year in sorted(year_counts):
                count = year_counts[year]
                bar = "█" * int(count / max_count * 30)
                lines.append(f"  {year}  {bar:<30} {count}")

        if "keywords" in df.columns:
            lines.append("")
            lines.append("─" * 60)
            lines.append("  TOP 20 PALAVRAS-CHAVE")
            lines.append("─" * 60)
            all_kws: list[str] = []
            for kw_str in df["keywords"].dropna():
                if isinstance(kw_str, str):
                    sep = ";" if ";" in kw_str else ","
                    all_kws.extend(k.strip().lower() for k in kw_str.split(sep) if k.strip())
            for i, (kw, n) in enumerate(Counter(all_kws).most_common(20), 1):
                lines.append(f"  {i:>2}. {kw:<46} {n:>5}")

        # ── Lei de Bradford ────────────────────────────────────────────────
        if "source" in df.columns:
            src_counts = Counter(df["source"].dropna()).most_common()
            total_arts = sum(n for _, n in src_counts)
            if total_arts > 0:
                lines.append("")
                lines.append("─" * 60)
                lines.append("  LEI DE BRADFORD — Dispersão por Zonas")
                lines.append("─" * 60)
                third = total_arts / 3
                cumsum = zone = zone_src = 0
                zone_data: list[tuple[int,int,int]] = []
                for _, count in src_counts:
                    cumsum += count
                    zone_src += 1
                    if cumsum >= third * (zone + 1) or zone_src == len(src_counts):
                        zone += 1
                        zone_data.append((zone, zone_src, int(cumsum)))
                        zone_src = 0
                        if zone >= 3:
                            break
                for z, nsrc, nart in zone_data:
                    lines.append(f"  Zona {z}  {nsrc:>5} fontes   {nart:>6} artigos")
                if len(zone_data) >= 2:
                    k = zone_data[1][1] / max(zone_data[0][1], 1)
                    lines.append(f"  Multiplicador k ≈ {k:.1f}")

        # ── Lei de Lotka ───────────────────────────────────────────────
        if "authors" in df.columns:
            auth_pub: Counter = Counter()
            for raw in df["authors"].dropna():
                sep = ";" if ";" in str(raw) else ","
                for a in str(raw).split(sep):
                    if a.strip():
                        auth_pub[a.strip()] += 1
            if auth_pub:
                pub_dist = Counter(auth_pub.values())
                n1 = pub_dist.get(1, 0)
                lines.append("")
                lines.append("─" * 60)
                lines.append("  LEI DE LOTKA — Produtividade de Autores")
                lines.append("─" * 60)
                lines.append(f"  Total de autores únicos : {len(auth_pub)}")
                lines.append(f"  Autores com 1 artigo    : {n1} "
                             f"({100*n1/len(auth_pub):.1f}%)")
                lines.append(f"  {'Artigos':>8}  {'Autores (real)':>14}  {'Lotka C/n²':>12}")
                lines.append("  " + "─" * 38)
                c = n1
                for np_ in sorted(pub_dist)[:8]:
                    real = pub_dist[np_]
                    lotka = round(c / (np_ ** 2))
                    lines.append(f"  {np_:>8}  {real:>14}  {lotka:>12}")

        # ── Métricas de rede ───────────────────────────────────────────
        # ── Citation burst ─────────────────────────────────────────────
        if "keywords" in df.columns and "year" in df.columns:
            yr_series = df["year"].replace(0, None).dropna().astype(int)
            if not yr_series.empty:
                yr_max = int(yr_series.max())
                recent_cut = yr_max - 2   # last 3 years
                early_cut  = yr_max - 7   # 3-year window before that
                bursts: list[tuple[str, float]] = []
                kw_counter_recent: Counter = Counter()
                kw_counter_early:  Counter = Counter()
                for _, row in df.iterrows():
                    yr  = int(row.get("year", 0) or 0)
                    kws = str(row.get("keywords", "") or "")
                    if not kws or not yr:
                        continue
                    sep = ";" if ";" in kws else ","
                    terms = [k.strip().lower() for k in kws.split(sep) if k.strip()]
                    if yr >= recent_cut:
                        kw_counter_recent.update(terms)
                    elif yr >= early_cut:
                        kw_counter_early.update(terms)
                for term, recent_n in kw_counter_recent.items():
                    if recent_n < 2:
                        continue
                    early_n = kw_counter_early.get(term, 0)
                    ratio = recent_n / (early_n + 0.5)
                    bursts.append((term, ratio))
                bursts.sort(key=lambda x: x[1], reverse=True)
                if bursts:
                    lines.append("")
                    lines.append("─" * 60)
                    lines.append(f"  TERMOS EM ASCENSÃO (burst {recent_cut}–{yr_max} vs {early_cut}–{recent_cut-1})")
                    lines.append("─" * 60)
                    for term, ratio in bursts[:15]:
                        bar = "▲" * min(int(ratio), 12)
                        lines.append(f"  {term:<36} {bar} ×{ratio:.1f}")

        if self._generator is not None and self._generator.G.number_of_nodes() > 0:
            try:
                G = self._generator.G
                lines.append("")
                lines.append("─" * 60)
                lines.append("  MÉTRICAS DA REDE")
                lines.append("─" * 60)
                lines.append(f"  Nós               : {G.number_of_nodes()}")
                lines.append(f"  Arestas           : {G.number_of_edges()}")
                lines.append(f"  Densidade         : {nx.density(G):.4f}")
                lines.append(f"  Coef. clustering  : {nx.average_clustering(G, weight='weight'):.4f}")
                comps = list(nx.connected_components(G))
                lines.append(f"  Componentes       : {len(comps)}")
                sg = G.subgraph(max(comps, key=len))
                if sg.number_of_nodes() > 1:
                    lines.append(f"  Diâmetro (maior comp.) : {nx.diameter(sg)}")
                    lines.append(f"  Caminho médio          : {nx.average_shortest_path_length(sg):.3f}")
                # Degree stats
                degs = [d for _, d in G.degree(weight="weight")]
                lines.append(f"  Grau médio        : {sum(degs)/len(degs):.2f}")
                lines.append(f"  Grau máximo       : {max(degs):.2f}  "
                             f"({max(G.degree(weight='weight'), key=lambda x: x[1])[0]})")
            except Exception:
                pass

        if self._generator is not None:
            try:
                field = self._field_var.get() if hasattr(self, "_field_var") else "keywords"
                evolution = self._generator.get_temporal_evolution(
                    period_size=5, field=field,
                    min_occurrence=2, thesaurus=self._thesaurus,
                )
                if evolution:
                    lines.append("")
                    lines.append("─" * 60)
                    lines.append("  EVOLUÇÃO TEMPORAL DA REDE (períodos de 5 anos)")
                    lines.append("─" * 60)
                    lines.append(f"  {'Período':<14}{'Artigos':>7}{'Nós':>6}{'Arestas':>8}{'Clusters':>10}")
                    lines.append("  " + "─" * 46)
                    for ev in evolution:
                        lines.append(
                            f"  {ev['period']:<14}{ev['papers']:>7}{ev['nodes']:>6}"
                            f"{ev['edges']:>8}{ev['clusters']:>10}"
                        )
                        if ev.get("top_terms"):
                            lines.append(f"    Termos: {', '.join(ev['top_terms'][:5])}")
            except Exception:
                pass

        lines.append("")
        lines.append("═" * 60)

        self._stats_box.configure(state="normal")
        self._stats_box.delete("1.0", "end")
        self._stats_box.insert("end", "\n".join(lines))
        self._stats_box.configure(state="disabled")
    def _build_tab_analises(self) -> ctk.CTkFrame:
        f = self._tab()
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(0, weight=1)
        
        main_content = ctk.CTkFrame(f, fg_color="transparent")
        main_content.grid(row=0, column=0, sticky="nsew")
        main_content.grid_rowconfigure(1, weight=1)
        
        self._tv_analises = ctk.CTkTabview(main_content, fg_color=CONTENT_BG, text_color=INK, segmented_button_selected_color=RED, segmented_button_selected_hover_color=RED_HOVER, segmented_button_unselected_color=PAPER, segmented_button_unselected_hover_color="#e0e0e0")
        self._tv_analises.pack(fill="both", expand=True, padx=20, pady=20)
        
        tab_mapa = self._tv_analises.add("Mapa")
        tab_rankings = self._tv_analises.add("Rankings")
        
        viz_f = self._build_tab_viz(parent=tab_mapa)
        viz_f.pack(in_=tab_mapa, fill="both", expand=True)
        
        rank_f = self._build_tab_ranking(parent=tab_rankings)
        rank_f.pack(in_=tab_rankings, fill="both", expand=True)
        
        return f

    def _build_tab_gallery(self) -> ctk.CTkFrame:
        f = self._tab()
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(0, weight=1)
        
        main_content = ctk.CTkFrame(f, fg_color="transparent")
        main_content.grid(row=0, column=0, sticky="nsew")
        main_content.grid_rowconfigure(1, weight=1)
        main_content.grid_columnconfigure(0, weight=1)
        
        # Header
        hdr = ctk.CTkFrame(main_content, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(hdr, text="🖼️ Galeria de Mapas", font=ctk.CTkFont(size=24, weight="bold"), text_color=INK).pack(side="left")
        ctk.CTkButton(hdr, text="🔄 Atualizar", width=100, height=32, fg_color=CARD_BG, hover_color=CARD2_BG, text_color=INK, border_width=1, border_color=INK, command=self._refresh_gallery).pack(side="right")
        
        # Grid/List of maps
        self._gallery_scroll = ctk.CTkScrollableFrame(main_content, fg_color=CONTENT_BG)
        self._gallery_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
        # IA Drawer for Gallery
        self._gallery_drawer = ctk.CTkFrame(f, fg_color=WHITE_CARD, width=300, corner_radius=0, border_width=1, border_color=INK)
        self._gallery_drawer.grid_propagate(False)
        self._gallery_drawer.grid_rowconfigure(1, weight=1)
        self._gallery_drawer.grid_columnconfigure(0, weight=1)
        
        header = ctk.CTkFrame(self._gallery_drawer, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(header, text="✨ Blink", font=ctk.CTkFont(size=16, weight="bold"), text_color=INK).pack(side="left")
        
        self._gallery_chat_history = ctk.CTkTextbox(self._gallery_drawer, wrap="word", font=ctk.CTkFont(size=13), fg_color=PAPER, text_color=INK, border_width=1, border_color=INK, corner_radius=0)
        self._gallery_chat_history.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        from core.markdown_parser import configure_markdown_tags, insert_markdown
        configure_markdown_tags(self._gallery_chat_history)
        insert_markdown(self._gallery_chat_history, "**Blink:** Selecione um mapa na galeria e pergunte-me sobre ele!\n\n")
        self._gallery_chat_history.configure(state="disabled")
        
        input_f = ctk.CTkFrame(self._gallery_drawer, fg_color="transparent")
        input_f.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        input_f.grid_columnconfigure(0, weight=1)
        
        self._gallery_chat_input = ctk.CTkEntry(input_f, placeholder_text="Sua pergunta...", placeholder_text_color=MUTED, font=ctk.CTkFont(size=13), fg_color=WHITE_CARD, text_color=INK, height=36, corner_radius=0, border_width=1, border_color=INK)
        self._gallery_chat_input.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        def send_chat(e=None):
            msg = self._gallery_chat_input.get().strip()
            if not msg: return
            self._gallery_chat_input.delete(0, "end")
            self._gallery_chat_history.configure(state="normal")
            insert_markdown(self._gallery_chat_history, f"**Você:** {msg}\n")
            self._gallery_chat_history.see("end")
            self._gallery_chat_history.configure(state="disabled")
            
            if not hasattr(self, '_gallery_messages') or not self._gallery_messages:
                self._gallery_messages = [{"role": "system", "content": "Você é o 'Blink', um assistente focado em analisar mapas bibliométricos na galeria. Use markdown."}]
            
            self._gallery_messages.append({"role": "user", "content": msg})
            
            import threading
            def worker():
                try:
                    from ai.client import AIAnalyst
                    analyst = AIAnalyst(api_key=self._api_key_var.get() or None, base_url=self._ai_base_url_var.get(), model=self._ai_model_var.get())
                    resp = analyst.chat_history(self._gallery_messages, temperature=0.7)
                    self._gallery_messages.append({"role": "assistant", "content": resp})
                except Exception as ex:
                    resp = f"Erro: {ex}"
                def update_ui():
                    self._gallery_chat_history.configure(state="normal")
                    insert_markdown(self._gallery_chat_history, f"**Blink:**\n{resp}\n")
                    self._gallery_chat_history.see("end")
                    self._gallery_chat_history.configure(state="disabled")
                self.after(0, update_ui)
            threading.Thread(target=worker, daemon=True).start()
            
        self._gallery_chat_input.bind("<Return>", send_chat)
        ctk.CTkButton(input_f, text="➤", width=36, height=36, fg_color=RED, hover_color=RED_HOVER, corner_radius=0, command=send_chat).grid(row=0, column=1)
        
        # Default show drawer
        self._gallery_drawer.grid(row=0, column=1, sticky="ns")
        
        self.after(500, self._refresh_gallery)
        
        return f

    def _refresh_gallery(self):
        if not hasattr(self, '_gallery_scroll'): return
        
        # Clear existing
        for w in self._gallery_scroll.winfo_children():
            w.destroy()
            
        from pathlib import Path
        import os, time
        
        reports_dir = Path("reports")
        if not reports_dir.exists(): return
        
        files = list(reports_dir.glob("*.html"))
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        if not files:
            ctk.CTkLabel(self._gallery_scroll, text="Nenhum mapa salvo ainda.", font=ctk.CTkFont(size=14, slant="italic"), text_color=MUTED).pack(pady=40)
            return
            
        for idx, fpath in enumerate(files):
            mtime = os.path.getmtime(fpath)
            date_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(mtime))
            name = fpath.stem.replace("blicsa_", "").replace("_", " ").title()
            
            card = ctk.CTkFrame(self._gallery_scroll, fg_color=CARD_BG, border_width=1, border_color=INK, corner_radius=4)
            card.pack(fill="x", padx=10, pady=5)
            
            info_f = ctk.CTkFrame(card, fg_color="transparent")
            info_f.pack(side="left", padx=15, pady=15, fill="x", expand=True)
            
            ctk.CTkLabel(info_f, text=f"📊 {name}", font=ctk.CTkFont(size=14, weight="bold"), text_color=INK, anchor="w").pack(fill="x")
            ctk.CTkLabel(info_f, text=f"Salvo em: {date_str}", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, anchor="w").pack(fill="x")
            
            btn_f = ctk.CTkFrame(card, fg_color="transparent")
            btn_f.pack(side="right", padx=15, pady=15)
            
            def open_map(p=fpath, n=name):
                import urllib.parse
                rel_path = p.relative_to(OUTPUT_DIR).as_posix()
                url = f"http://127.0.0.1:{self._local_server_port}/{urllib.parse.quote(rel_path)}"
                import webbrowser
                webbrowser.open(url)
                
            def delete_map(p=fpath):
                import os
                if messagebox.askyesno("Excluir", "Deseja excluir este mapa salvo?"):
                    try:
                        os.remove(p)
                        self._refresh_gallery()
                    except Exception as e:
                        messagebox.showerror("Erro", str(e))
                        
            ctk.CTkButton(btn_f, text="Abrir", width=80, height=28, fg_color=BLUE, hover_color="#103050", command=open_map).pack(side="left", padx=5)
            ctk.CTkButton(btn_f, text="Excluir", width=80, height=28, fg_color=RED, hover_color=RED_HOV, command=delete_map).pack(side="left", padx=5)

        return f

    
    def _download_oa_pdfs(self):
        if self._dataframe is None or self._dataframe.empty:
            return
            
        oa_records = self._dataframe[self._dataframe.get("is_oa", False) == True].to_dict('records')
        if not oa_records:
            messagebox.showinfo("PDFs", "Nenhum documento Open Access encontrado no corpus.")
            return
            
        import threading
        import urllib.request
        import urllib.error
        import os
        import re
        
        # Determine project name for folder
        proj_name = "Projeto_Sem_Nome"
        if getattr(self, "_current_tab_key", "") == "projects":
            # Can't reliably get current from tab, fallback to a timestamp or default
            pass
            
        import time
        proj_name = f"projeto_{int(time.time())}"
        out_dir = os.path.expanduser(f"~/Blicsa/pdfs/{proj_name}")
        os.makedirs(out_dir, exist_ok=True)
        
        self._pdf_cancel_event = threading.Event()
        
        def slugify(value):
            value = str(value).lower().strip()
            value = re.sub(r'[^\w\s-]', '', value)
            value = re.sub(r'[-\s]+', '-', value)
            return value[:50]
            
        def worker():
            downloaded = 0
            failed = 0
            
            for i, r in enumerate(oa_records):
                if self._pdf_cancel_event.is_set():
                    break
                    
                self.after(0, self._set_busy, f"Baixando PDF {i+1}/{len(oa_records)}...")
                
                url = r.get("oa_url")
                if not url:
                    failed += 1
                    continue
                    
                authors = str(r.get("authors", "Autor"))
                first_author = authors.split(";")[0].split(",")[0].strip()
                first_author = slugify(first_author)
                
                year = str(r.get("year", "0000"))
                title = slugify(r.get("title", "Sem titulo"))
                
                filename = f"{first_author}_{year}_{title}.pdf"
                filepath = os.path.join(out_dir, filename)
                
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response, open(filepath, 'wb') as out_file:
                        out_file.write(response.read())
                    downloaded += 1
                except Exception:
                    failed += 1
                    
            self.after(0, self._set_idle, f"PDFs baixados. {downloaded} sucessos, {failed} falhas.")
            self.after(0, lambda: messagebox.showinfo("Download Concluído", f"{downloaded} baixados, {failed} falhas.\n\nSalvos em:\n{out_dir}"))
            
        threading.Thread(target=worker, daemon=True).start()

    def _build_tab_corpus(self) -> ctk.CTkFrame:
        self._corpus_tab_frame = self._tab()
        self._corpus_tab_frame.grid_columnconfigure(0, weight=1)
        self._corpus_tab_frame.grid_rowconfigure(1, weight=1)
        self._refresh_corpus_tab()
        return self._corpus_tab_frame
        
    def _refresh_corpus_tab(self):
        if not hasattr(self, '_corpus_tab_frame'):
            return
            
        # Clear existing
        for w in self._corpus_tab_frame.winfo_children():
            w.destroy()
            
        if self._dataframe is None or self._dataframe.empty:
            empty_container = ctk.CTkFrame(self._corpus_tab_frame, fg_color="transparent")
            empty_container.pack(expand=True)
            
            ctk.CTkLabel(empty_container, text="📂", font=ctk.CTkFont(size=64)).pack(pady=10)
            ctk.CTkLabel(empty_container, text="Nenhum corpus carregado.", font=ctk.CTkFont(size=20, weight="bold"), text_color=MUTED).pack(pady=10)
            self._btn(empty_container, "Coletar Dados", lambda: self._switch_tab("import"), height=40).pack(pady=20)
            return

        # Header
        hdr = ctk.CTkFrame(self._corpus_tab_frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=30, pady=(30, 20))
        hdr.grid_columnconfigure(1, weight=1)
        
        df = self._dataframe
        total_docs = len(df)
        total_cites = int(df['citations'].sum()) if 'citations' in df.columns else 0
        
        ctk.CTkLabel(hdr, text="Seu Corpus", font=ctk.CTkFont(size=28, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text=f"{total_docs} documentos • {total_cites} citações totais", font=ctk.CTkFont(size=14), text_color=MUTED).grid(row=1, column=0, sticky="w")
        
        btns_f = ctk.CTkFrame(hdr, fg_color="transparent")
        btns_f.grid(row=0, column=2, rowspan=2, sticky="e")
        self._btn(btns_f, "Análise IA do Corpus", self._trigger_corpus_ai_insights, height=40, color=YELLOW, hover=YELLOW_HOV).pack(side="left", padx=(0, 10))
        self._btn(btns_f, "Baixar PDFs abertos", self._download_oa_pdfs, height=40, color="#1E4DA0").pack(side="left", padx=(0, 10))
        self._btn(btns_f, "Ir para Análises", lambda: self._switch_tab("analises"), height=40, color=RED).pack(side="left")
        
        # Main content
        main = ctk.CTkFrame(self._corpus_tab_frame, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=30, pady=10)
        main.grid_columnconfigure(0, weight=7)
        main.grid_columnconfigure(1, weight=3)
        main.grid_rowconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        
        # Left: Histogram
        hist_card = self._card(main, 0, pady=0)
        hist_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        hist_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(hist_card, text="Publicações por Ano", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        hist_f = ctk.CTkFrame(hist_card, fg_color="transparent")
        hist_f.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            fig = Figure(figsize=(6, 3), dpi=100)
            fig.patch.set_facecolor(CARD_BG)
            ax = fig.add_subplot(111)
            ax.set_facecolor(CARD_BG)
            if 'year' in df.columns:
                years = df['year'].dropna()
                years = years[years > 0]
                if not years.empty:
                    counts = years.value_counts().sort_index()
                    ax.bar(counts.index, counts.values, color=RED)
                    ax.tick_params(colors=INK)
                    for spine in ax.spines.values():
                        spine.set_color(MUTED)
            fig.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, master=hist_f)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
        except Exception as e:
            ctk.CTkLabel(hist_f, text=f"Erro no gráfico: {e}").pack()

        # Right: Quick Summary
        sum_card = self._card(main, 0, pady=0)
        sum_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        ctk.CTkLabel(sum_card, text="Visão Geral", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
        sum_f = ctk.CTkFrame(sum_card, fg_color="transparent")
        sum_f.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        
        def get_top3(col):
            if col not in df.columns: return []
            items = df[col].dropna().astype(str)
            all_items = []
            for it in items:
                all_items.extend([x.strip() for x in it.split(";") if x.strip()])
            from collections import Counter
            return [x[0] for x in Counter(all_items).most_common(3)]
            
        top_auth = get_top3('authors')
        top_src = get_top3('source')
        
        ctk.CTkLabel(sum_f, text="Top Autores:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5,0))
        for a in top_auth: ctk.CTkLabel(sum_f, text=f"• {a}", text_color=MUTED).pack(anchor="w", padx=10)
        
        ctk.CTkLabel(sum_f, text="Top Fontes:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(15,0))
        for s in top_src: ctk.CTkLabel(sum_f, text=f"• {s[:30]}", text_color=MUTED).pack(anchor="w", padx=10)
        
        # Bottom: Preview Table
        tab_card = self._card(main, 1, pady=0)
        tab_card.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(20, 0))
        tab_card.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(tab_card, text="Prévia dos Dados (10 registros)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        try:
            import tkinter.ttk as ttk
            style = ttk.Style()
            style.theme_use("default")
            style.configure("Treeview", background=WHITE, foreground=INK, rowheight=25, fieldbackground=WHITE, borderwidth=0)
            style.configure("Treeview.Heading", background=PAPER, foreground=INK, font=('Archivo', 10, 'bold'))
            
            tree_f = ctk.CTkFrame(tab_card, fg_color="transparent")
            tree_f.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
            
            cols = [c for c in ['title', 'authors', 'year', 'source', 'citations'] if c in df.columns]
            if not cols: cols = list(df.columns[:5])
            
            tree = ttk.Treeview(tree_f, columns=cols, show="headings", selectmode="none")
            vsb = ttk.Scrollbar(tree_f, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(tree_f, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            tree_f.grid_columnconfigure(0, weight=1)
            tree_f.grid_rowconfigure(0, weight=1)
            
            for c in cols:
                tree.heading(c, text=c.capitalize())
                tree.column(c, width=150)
                
            for _, r in df.head(10).iterrows():
                tree.insert("", "end", values=[str(r[c])[:50] for c in cols])
        except Exception as e:
            ctk.CTkLabel(tab_card, text=f"Erro na tabela: {e}").grid(row=1, column=0)


if __name__ == "__main__":
    import sys
    if "--selfcheck" in sys.argv:
        try:
            from core.parsers import BibliometricParser
            from core.matrix_builders import NetworkGenerator
            from core.visualizer import build_plotly_map
            from core.nlp import extract_ngrams
            # Check translation parity
            import json, os
            locales_dir = os.path.join(os.path.dirname(__file__), "locales")
            with open(os.path.join(locales_dir, "en.json")) as f: en = json.load(f)
            with open(os.path.join(locales_dir, "fr.json")) as f: fr = json.load(f)
            with open(os.path.join(locales_dir, "pt_BR.json")) as f: pt = json.load(f)
            en_keys = set(k for k in en.keys() if k != "_note")
            fr_keys = set(k for k in fr.keys() if k != "_note")
            pt_keys = set(k for k in pt.keys() if k != "_note")
            if not (en_keys == fr_keys == pt_keys):
                print(f"Self-check FAILED: Translation keys do not match. Missing in fr: {en_keys - fr_keys}, Missing in pt: {en_keys - pt_keys}", file=sys.stderr)
                sys.exit(1)
            print("Blicsa v3.0-upgrade")
            print("Self-check passed: Core modules imported successfully and catalogs match.")
            sys.exit(0)
        except Exception as e:
            print(f"Self-check FAILED: {e}", file=sys.stderr)
            sys.exit(1)

    import tkinter as tk
    from PIL import Image, ImageTk
    
    app = BlicsaApp()
    app.withdraw()
    
    splash = tk.Toplevel(app)
    splash.overrideredirect(True)
    splash.geometry("600x400")
    
    # 3px ink border
    splash.configure(bg="#141414")
    content = tk.Frame(splash, bg="#F6F4EE")
    content.pack(fill="both", expand=True, padx=3, pady=3)
    
    lbl = tk.Label(content, bg="#F6F4EE")
    lbl.place(relx=0.5, rely=0.5, anchor="center")
    
    # Version string
    ver = tk.Label(content, text="v3.0", bg="#F6F4EE", fg="#8A877F", font=("Arial", 11))
    ver.place(relx=0.98, rely=0.98, anchor="se")
    
    frames = []
    try:
        gif = Image.open("assets/branding/blicsa-splash.gif")
        for i in range(gif.n_frames):
            gif.seek(i)
            frames.append(ImageTk.PhotoImage(gif.copy()))
    except:
        pass
        
    def play_gif(idx):
        if not frames: return
        
        # Check settings
        import os, json
        s_path = os.path.join(os.path.dirname(__file__), ".blicsa_settings.json")
        reduce = False
        if os.path.exists(s_path):
            try:
                s = json.load(open(s_path))
                reduce = s.get("reduce_animations", False)
            except: pass
            
        if reduce:
            lbl.config(image=frames[-1])
            return
            
        lbl.config(image=frames[idx])
        splash.after(42, play_gif, (idx + 1) % len(frames))
        
    if frames:
        play_gif(0)
        
    # Apply app icon
    try:
        if sys.platform == "win32":
            app.iconbitmap("assets/branding/blicsa-icon.ico")
        else:
            ico = tk.PhotoImage(file="assets/branding/blicsa-icon-256.png")
            app.iconphoto(True, ico)
    except:
        pass
        
    def center_splash():
        splash.update_idletasks()
        w = splash.winfo_width()
        h = splash.winfo_height()
        ws = splash.winfo_screenwidth()
        hs = splash.winfo_screenheight()
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)
        splash.geometry('%dx%d+%d+%d' % (w, h, x, y))
        
    center_splash()
    
    def close_splash():
        splash.destroy()
        app.deiconify()
        
    # Close after 3 seconds (max) or let one pass finish
    app.after(3000, close_splash)
    app.mainloop()
