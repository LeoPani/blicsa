import sys
import re
import math
import numpy as np
import networkx as nx
import customtkinter as ctk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
from collections import Counter
from pathlib import Path
from scipy.stats import gaussian_kde

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import os

_style_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'core', 'viz', 'blicsa.mplstyle')
if os.path.exists(_style_path): plt.style.use(_style_path)
import matplotlib.patches as mpatches
import matplotlib.colors as mc
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from ui.styles import get_color, SIDEBAR_BG, CONTENT_BG, CARD_BG, CARD2_BG, ACCENT, ACCENT_HOV, TEXT_MUTED, BLUE, YELLOW, INK, INK_HOV, BLUE_HOV, YELLOW_HOV, RED_HOV
from core.matrix_builders import CLUSTER_PALETTE

class HoverTooltip:
    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.id = None
        self.tw = None
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.unschedule)
        self.widget.bind("<ButtonPress>", self.unschedule)

    def schedule(self, event=None):
        self.unschedule()
        self.id = self.widget.after(self.delay, self.show)

    def unschedule(self, event=None):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)
        self.hide()

    def show(self):
        self.hide()
        import tkinter as tk
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        
        is_light = ctk.get_appearance_mode().lower() == "light"
        bg_col = "#ffffff" if is_light else "#141414"
        fg_col = "#000000" if is_light else "#e0e0e0"
        
        label = tk.Label(self.tw, text=self.text, justify='left',
                         background=bg_col, foreground=fg_col, relief='solid', borderwidth=1,
                         font=("Helvetica", 11, "normal"))
        label.pack(ipadx=4, ipady=4)

    def hide(self):
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()

# ── Deduplication Dialog ───────────────────────────────────────────────────────
class DeduplicationDialog(ctk.CTkToplevel):
    """Shows fuzzy-duplicate pairs and lets the user confirm which to remove."""

    def __init__(self, parent, df, dupes: list[tuple[int, int, str]], on_apply):
        super().__init__(parent)
        self.title("Blicsa — Deduplicação")
        self.geometry("900x620")
        self.minsize(700, 420)
        self.configure(fg_color=CONTENT_BG, border_width=3, border_color=INK)
        self.grab_set()

        self._df       = df
        self._dupes    = dupes       # [(keep_idx, remove_idx, reason)]
        self._on_apply = on_apply
        self._vars: list[ctk.BooleanVar] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=CONTENT_BG, border_width=3, border_color=INK)
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            hdr,
            text=f"{len(dupes)} par(es) de duplicata detectado(s) — marque os que deseja remover:",
            font=ctk.CTkFont(size=13),
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="Todos", width=72, height=28,
            fg_color=INK, hover_color=INK_HOV,
            command=lambda: [v.set(True) for v in self._vars],
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            hdr, text="Nenhum", width=72, height=28,
            fg_color=CARD_BG, hover_color=CARD2_BG,
            command=lambda: [v.set(False) for v in self._vars],
        ).pack(side="right")

        # Scrollable pair list
        sf = ctk.CTkScrollableFrame(self, fg_color=CARD2_BG, corner_radius=0)
        sf.grid(row=1, column=0, sticky="nsew", padx=20, pady=4)
        sf.grid_columnconfigure(1, weight=1)

        for idx, (ki, ri, reason) in enumerate(dupes):
            var = ctk.BooleanVar(value=True)
            self._vars.append(var)

            keep_title   = str(df.at[ki, "title"])[:70]
            remove_title = str(df.at[ri, "title"])[:70]
            keep_origin  = df.at[ki, "origin"]
            rm_origin    = df.at[ri, "origin"]
            yr           = df.at[ri, "year"]

            bg = CARD_BG if idx % 2 == 0 else CARD2_BG
            row_f = ctk.CTkFrame(sf, fg_color=bg, corner_radius=0)
            row_f.grid(row=idx, column=0, columnspan=2, sticky="ew", pady=2, padx=2)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkCheckBox(
                row_f, text="", variable=var,
                width=28, checkbox_width=16, checkbox_height=16,
                fg_color=ACCENT, hover_color=ACCENT_HOV,
            ).grid(row=0, column=0, padx=(8, 4), pady=6, rowspan=2)

            ctk.CTkLabel(
                row_f,
                text=f"MANTER  [{keep_origin}]  {keep_title}",
                anchor="w", font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#88ee88",
            ).grid(row=0, column=1, padx=4, pady=(6, 0), sticky="w")
            ctk.CTkLabel(
                row_f,
                text=f"REMOVER [{rm_origin}] ({yr})  {remove_title}",
                anchor="w", font=ctk.CTkFont(size=11),
                text_color="#ee8888",
            ).grid(row=1, column=1, padx=4, pady=(0, 2), sticky="w")
            ctk.CTkLabel(
                row_f,
                text=f"  {reason}",
                anchor="w", font=ctk.CTkFont(size=10),
                text_color=TEXT_MUTED,
            ).grid(row=2, column=1, padx=4, pady=(0, 6), sticky="w")

        # Footer
        foot = ctk.CTkFrame(self, fg_color=CONTENT_BG, border_width=3, border_color=INK)
        foot.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 16))
        ctk.CTkButton(
            foot, text="✕  Cancelar", width=110, height=38,
            fg_color="#333355", hover_color="#444466",
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            foot, text="🗑  Aplicar Remoção", width=180, height=38,
            fg_color="#7a1a1a", hover_color="#9a2a2a",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._apply,
        ).pack(side="right")

    def _apply(self):
        to_remove = {self._dupes[i][1] for i, v in enumerate(self._vars) if v.get()}
        self.destroy()
        self._on_apply(to_remove)


def insert_markdown(textbox, text: str):
    """Parses basic Markdown syntax (headings, bold, bullet points) and applies Tkinter tags for visual styling."""
    textbox.configure(state="normal")
    textbox.delete("1.0", "end")
    
    raw_text = textbox._textbox # Get the underlying standard Tkinter Text widget
    
    is_light = ctk.get_appearance_mode().lower() == "light"
    text_color = "#1f2937" if is_light else "#e0e0e0"
    header_color = "#0047AB" if is_light else get_color(ACCENT)
    
    base_font = ("Helvetica", 12)
    h_font = ("Helvetica", 13, "bold")
    b_font = ("Helvetica", 12, "bold")
    i_font = ("Helvetica", 12, "italic")
    
    raw_text.tag_config("h2", font=h_font, foreground=header_color)
    raw_text.tag_config("bold", font=b_font, foreground=text_color)
    raw_text.tag_config("italic", font=i_font, foreground=text_color)
    raw_text.tag_config("normal", font=base_font, foreground=text_color)
    raw_text.tag_config("bullet", font=base_font, foreground=text_color)
    
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            raw_text.insert("end", "\n", "normal")
            continue
            
        # Headers (## Section)
        if line.startswith("## ") or line.startswith("### "):
            hdr_text = line.lstrip("#").strip()
            raw_text.insert("end", f"\n{hdr_text}\n", "h2")
            continue
            
        # Bullet points
        if line.startswith("* ") or line.startswith("- "):
            raw_text.insert("end", "  • ", "bullet")
            line = line[2:].strip()
            
        # Parse inline bold (**bold**) and italics (*italic*)
        parts = line.split("**")
        for i, part in enumerate(parts):
            tag = "bold" if i % 2 == 1 else "normal"
            subparts = part.split("*")
            for j, subpart in enumerate(subparts):
                subtag = "italic" if j % 2 == 1 else tag
                raw_text.insert("end", subpart, subtag)
                
        raw_text.insert("end", "\n", "normal")
        
    textbox.configure(state="disabled")


class AIInsightsWindow(ctk.CTkToplevel):
    """Centered popup modal displaying AI-generated insights for the current network."""

    def __init__(self, parent, text: str):
        super().__init__(parent)
        self.title("Blicsa — Insights Analíticos com IA")
        self.geometry("820x600")
        self.minsize(600, 400)
        self.configure(fg_color=CONTENT_BG, border_width=3, border_color=INK)
        
        # Center on screen
        self.transient(parent)
        self.grab_set()
        
        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        hdr = ctk.CTkFrame(self, fg_color=CARD_BG, height=52, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        hdr.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            hdr, text="✨ Percepções & Insights com IA (Groq)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ACCENT
        ).grid(row=0, column=0, padx=16, pady=10, sticky="w")
        
        # Insights text box
        self.txt = ctk.CTkTextbox(
            self, font=ctk.CTkFont(size=13), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self.txt.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        insert_markdown(self.txt, text)
        
        # Footer
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        
        def copy():
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copiado", "Insights copiados para a área de transferência!")
            
        ctk.CTkButton(
            ftr, text="📋 Copiar Texto", width=130, height=32,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000000",
            font=ctk.CTkFont(weight="bold"), command=copy
        ).pack(side="left", padx=4)
        
        ctk.CTkButton(
            ftr, text="Fechar", width=100, height=32,
            fg_color=CARD_BG, hover_color=CARD2_BG,
            command=self.destroy
        ).pack(side="right", padx=4)


# ── Trend Chart Window ─────────────────────────────────────────────────────────
class TrendChartWindow(ctk.CTkToplevel):
    """Line chart of term frequency per year for user-selected terms."""

    def __init__(
        self,
        parent,
        df,
        candidate_counts: Counter,
        field: str = "keywords",
        thesaurus: dict | None = None,
    ):
        super().__init__(parent)
        self.title("Blicsa — Tendências de Termos")
        self.geometry("1140x680")
        self.minsize(820, 500)
        self.configure(fg_color=CONTENT_BG, border_width=3, border_color=INK)

        self._df         = df
        self._field      = field
        self._thesaurus  = thesaurus or {}
        self._all_terms  = [t for t, _ in candidate_counts.most_common(80)]

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Left panel ─────────────────────────────────────────────────
        lp = ctk.CTkFrame(self, fg_color=CARD_BG, width=230)
        lp.grid(row=0, column=0, sticky="ns", padx=(12, 4), pady=12)
        lp.grid_propagate(False)
        lp.grid_rowconfigure(2, weight=1)
        lp.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            lp, text="Termos", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT,
        ).grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._filter_terms)
        ctk.CTkEntry(
            lp, textvariable=self._search_var,
            placeholder_text="Filtrar…", height=30,
        ).grid(row=1, column=0, padx=8, pady=(0, 4), sticky="ew")

        sf = ctk.CTkScrollableFrame(lp, fg_color=CARD2_BG)
        sf.grid(row=2, column=0, padx=6, pady=(0, 4), sticky="nsew")
        self._scroll_frame = sf

        self._term_vars: dict[str, ctk.BooleanVar] = {}
        self._filter_terms()

        # Selection controls
        qf = ctk.CTkFrame(lp, fg_color="transparent")
        qf.grid(row=3, column=0, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(
            qf, text="Top 5", width=64, height=26,
            fg_color=INK, hover_color=INK_HOV,
            command=self._select_top5,
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            qf, text="Nenhum", width=64, height=26,
            fg_color=CARD_BG, hover_color=CARD2_BG,
            command=self._deselect_all,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            lp, text="📈  Plotar", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="#000000", font=ctk.CTkFont(weight="bold"),
            command=self._plot,
        ).grid(row=4, column=0, padx=10, pady=(0, 12), sticky="ew")

        # ── Right panel: matplotlib ─────────────────────────────────────
        rp = ctk.CTkFrame(self, fg_color=CARD_BG)
        rp.grid(row=0, column=1, sticky="nsew", padx=(4, 12), pady=12)
        rp.grid_rowconfigure(0, weight=1)
        rp.grid_columnconfigure(0, weight=1)

        bg_col = get_color(CARD2_BG)
        self._fig, self._ax = plt.subplots(facecolor=bg_col)
        self._ax.set_facecolor(bg_col)
        self._chart_cv = FigureCanvasTkAgg(self._fig, master=rp)
        self._chart_cv.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        
        tb_frame = ctk.CTkFrame(rp, fg_color="transparent", height=32)
        tb_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        NavigationToolbar2Tk(self._chart_cv, tb_frame)

        self._ax.text(
            0.5, 0.5, "Seleciona termos e clica em Plotar",
            ha="center", va="center", color=get_color(TEXT_MUTED), transform=self._ax.transAxes
        )
        self._chart_cv.draw()

    def _filter_terms(self, *_):
        query = self._search_var.get().strip().lower()
        for child in self._scroll_frame.winfo_children():
            child.destroy()

        for term in self._all_terms:
            if query and query not in term.lower():
                continue
            if term not in self._term_vars:
                self._term_vars[term] = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                self._scroll_frame, text=term, variable=self._term_vars[term],
                font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV
            ).pack(anchor="w", padx=4, pady=3)

    def _select_top5(self):
        for idx, term in enumerate(self._all_terms[:5]):
            if term in self._term_vars:
                self._term_vars[term].set(True)

    def _deselect_all(self):
        for var in self._term_vars.values():
            var.set(False)

    def _plot(self):
        selected = [t for t, v in self._term_vars.items() if v.get()]
        if not selected:
            return

        field  = self._field
        df     = self._df
        yr_col = df["year"].replace(0, None).dropna().astype(int)
        if yr_col.empty:
            return

        yr_min, yr_max = int(yr_col.min()), int(yr_col.max())
        years = list(range(yr_min, yr_max + 1))

        self._ax.clear()
        bg_col = get_color(CARD2_BG)
        self._ax.set_facecolor(bg_col)
        self._fig.set_facecolor(bg_col)

        for idx, term in enumerate(selected[:14]):
            t_lower = term.lower()

            def _has(s, _t=t_lower):
                if not isinstance(s, str) or not s:
                    return False
                sep = ";" if ";" in s else ","
                return _t in [x.strip().lower() for x in s.split(sep)]

            mask  = df[field].apply(_has) & (df["year"] > 0)
            counts = Counter(df.loc[mask, "year"].astype(int))
            ys    = [counts.get(y, 0) for y in years]
            color = CLUSTER_PALETTE[idx % len(CLUSTER_PALETTE)]
            self._ax.plot(
                years, ys,
                marker="o", markersize=4, linewidth=2,
                label=term[:28], color=color,
            )

        lbl_col = "black" if ctk.get_appearance_mode().lower() == "light" else "#e0e0e0"
        spine_col = "#cccccc" if ctk.get_appearance_mode().lower() == "light" else "#333355"
        self._ax.set_xlabel("Ano",        color=lbl_col, fontsize=11)
        self._ax.set_ylabel("Frequência", color=lbl_col, fontsize=11)
        self._ax.set_title(
            "Tendência de Termos ao Longo do Tempo",
            color=ACCENT, fontsize=13, fontweight="bold",
        )
        self._ax.tick_params(colors=lbl_col)
        for spine in self._ax.spines.values():
            spine.set_color(spine_col)
        self._ax.grid(True, color=spine_col, alpha=0.5, linestyle="--")
        self._ax.legend(
            fontsize=9, framealpha=0.3,
            facecolor=get_color(CARD_BG), edgecolor=ACCENT, labelcolor=lbl_col,
        )
        self._fig.tight_layout()
        self._chart_cv.draw()


# ── Verification Dialog ────────────────────────────────────────────────────────
class VerificationDialog(ctk.CTkToplevel):
    """Pre-graph checklist: Term | Occurrences | Relevance — user can uncheck."""

    def __init__(
        self,
        parent,
        terms_data: list[tuple[str, int, int, float]],  # (term, occ, doc_freq, score)
        on_confirm,   # callback(selected: set[str])
    ):
        super().__init__(parent)
        self.title("Verificação de Termos")
        self.geometry("800x600")
        self.minsize(600, 400)
        self.configure(fg_color=CONTENT_BG, border_width=3, border_color=INK)
        self.resizable(True, True)
        self.grab_set()

        self._on_confirm = on_confirm
        # Store terms and their check status: {term: bool}
        self._terms_status = {item[0]: True for item in terms_data}
        self._all_data = sorted(terms_data, key=lambda x: x[3], reverse=True)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build()
        self._populate_tree()

    def _build(self):
        # Top filters
        top = ctk.CTkFrame(self, fg_color=CONTENT_BG, border_width=3, border_color=INK)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))

        ctk.CTkLabel(top, text="Filtrar por nome:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self._filter_var = ctk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._filter())
        ctk.CTkEntry(top, textvariable=self._filter_var, width=180, height=28).pack(side="left")

        # Select all / Deselect all / inverse
        ctk.CTkButton(
            top, text="Marcar Todos", width=100, height=28, fg_color=INK, hover_color=INK_HOV,
            command=self._select_all
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            top, text="Desmarcar Todos", width=110, height=28, fg_color=CARD_BG, hover_color=CARD2_BG,
            command=self._deselect_all
        ).pack(side="right", padx=(4, 0))

        # Stats bar
        sf = ctk.CTkFrame(self, fg_color=CONTENT_BG, border_width=3, border_color=INK)
        sf.grid(row=1, column=0, sticky="ew", padx=20, pady=2)
        self._count_lbl = ctk.CTkLabel(sf, text="0 selecionados", font=ctk.CTkFont(size=12, weight="bold"))
        self._count_lbl.pack(side="left")
        
        hint = "Dica: Clique duplo ou Espaço para marcar/desmarcar o termo selecionado"
        ctk.CTkLabel(sf, text=hint, font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="right")

        # Scroll list card
        card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0)
        card.grid(row=2, column=0, sticky="nsew", padx=20, pady=4)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        # Style Treeview
        _ts = ttk.Style()
        _ts.theme_use("default")
        bg_col = get_color(CARD2_BG)
        fg_col = "black" if ctk.get_appearance_mode().lower() == "light" else "#e0e0e0"
        header_bg = get_color(CARD_BG)
        _ts.configure("Verify.Treeview",
            background=bg_col, fieldbackground=bg_col, foreground=fg_col,
            rowheight=26, font=("Inter", 11), borderwidth=0,
        )
        _ts.configure("Verify.Treeview.Heading",
            background=header_bg, foreground=ACCENT, font=("Inter", 11, "bold"), relief="flat",
        )

        sb = ctk.CTkScrollbar(card, orientation="vertical")
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 6))

        self._tree = ttk.Treeview(
            card, style="Verify.Treeview", yscrollcommand=sb.set, selectmode="browse", show="headings"
        )
        sb.configure(command=self._tree.yview)
        self._tree.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")

        self._tree["columns"] = ("status", "term", "occ", "doc_freq", "score")
        self._tree.heading("status", text="Manter?")
        self._tree.heading("term", text="Termo / Palavra-chave")
        self._tree.heading("occ", text="Ocorrências")
        self._tree.heading("doc_freq", text="Doc. Freq.")
        self._tree.heading("score", text="Relevância (TF-IDF)")

        self._tree.column("status", width=80, anchor="center")
        self._tree.column("term", width=300, anchor="w")
        self._tree.column("occ", width=90, anchor="center")
        self._tree.column("doc_freq", width=90, anchor="center")
        self._tree.column("score", width=120, anchor="center")

        # Events
        self._tree.bind("<Double-1>", self._toggle_row)
        self._tree.bind("<space>", self._toggle_row)

        # Footer
        foot = ctk.CTkFrame(self, fg_color=CONTENT_BG, border_width=3, border_color=INK)
        foot.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 16))
        self._btn = ctk.CTkButton(
            foot, text="Confirmar e Gerar Mapa",
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000",
            height=38, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirm,
        )
        self._btn.pack(side="right")
        ctk.CTkButton(
            foot, text="Cancelar", width=90, height=38,
            fg_color="#333355", hover_color="#444466",
            command=self.destroy
        ).pack(side="right", padx=(0, 8))

    def _populate_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)

        query = self._filter_var.get().strip().lower() if hasattr(self, "_filter_var") else ""

        for term, occ, df_val, score in self._all_data:
            if query and query not in term.lower():
                continue
            status_str = "☑ SIM" if self._terms_status[term] else "☐ NÃO"
            self._tree.insert("", "end", values=(status_str, term, occ, df_val, f"{score:.4f}"))

        self._refresh_count()

    def _toggle_row(self, event=None):
        sel = self._tree.selection()
        if not sel:
            return
        item_id = sel[0]
        vals = self._tree.item(item_id, "values")
        term = vals[1]
        new_status = not self._terms_status[term]
        self._terms_status[term] = new_status
        new_status_str = "☑ SIM" if new_status else "☐ NÃO"
        self._tree.item(item_id, values=(new_status_str, vals[1], vals[2], vals[3], vals[4]))
        self._refresh_count()

    def _filter(self):
        self._populate_tree()

    def _select_all(self):
        for term in self._terms_status:
            self._terms_status[term] = True
        self._populate_tree()

    def _deselect_all(self):
        for term in self._terms_status:
            self._terms_status[term] = False
        self._populate_tree()

    def _refresh_count(self):
        selected = sum(1 for v in self._terms_status.values() if v)
        self._count_lbl.configure(text=f"{selected} de {len(self._terms_status)} selecionados")

    def _confirm(self):
        selected = {term for term, status in self._terms_status.items() if status}
        self.destroy()
        self._on_confirm(selected)


# ── Embedded Matplotlib Canvas ─────────────────────────────────────────────────
class MapCanvas:
    def __init__(self, parent: ctk.CTkFrame, node_click_cb=None):
        self._parent = parent
        self._node_click_cb = node_click_cb
        self._fig, self._ax = plt.subplots(figsize=(11, 7), dpi=130)
        self._fig.patch.set_facecolor(get_color(CARD2_BG))
        self._ax.set_facecolor(get_color(CARD2_BG))
        self._ax.axis("off")

        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        tb_bg = ("#eef0f6", "#0a0a18")
        tb_fg = ("#000000", "#cccccc")
        tb_frame = ctk.CTkFrame(parent, fg_color=tb_bg, height=30)
        tb_frame.grid(row=1, column=0, sticky="ew")
        self._toolbar = NavigationToolbar2Tk(self._canvas, tb_frame)
        self._toolbar.config(background=get_color(tb_bg))
        for child in self._toolbar.winfo_children():
            try:
                child.config(background=get_color(tb_bg), foreground=get_color(tb_fg),
                             relief="flat", bd=0)
            except Exception:
                pass
        self._toolbar.update()

        self._pos: dict   = {}
        self._nodes: list = []
        self._G: nx.Graph | None = None
        self._node_scale: float = 1.0
        self._edge_opacity: float = 1.0
        self._last_mode: str = "Clusters"
        self._highlighted_node: str | None = None
        self._edge_threshold: float = 0.0
        self._cluster_labels: dict[int, str] = {}
        self._hidden_clusters: set[int] = set()

        self._annot = self._ax.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=get_color(("#ffffff", "#1a1a3a")),
                      ec=ACCENT, lw=1.2, alpha=0.95),
            color="black" if ctk.get_appearance_mode().lower() == "light" else "white",
            fontsize=9, visible=False, zorder=20,
        )
        self._fig.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self._fig.canvas.mpl_connect("button_press_event", self._on_click)
        self._scatter = None

    def render(
        self,
        G: nx.Graph,
        pos: dict,
        mode: str = "Clusters",
        node_scale: float = 1.0,
        edge_opacity: float = 1.0,
        edge_threshold: float = 0.0,
    ):
        self._G = G
        self._pos = pos
        self._last_mode = mode
        self._node_scale = node_scale
        self._edge_opacity = edge_opacity
        self._edge_threshold = edge_threshold
        self._highlighted_node = None
        self._redraw(G, pos, mode, node_scale, edge_opacity)

    def set_cluster_labels(self, labels: dict[int, str]):
        self._cluster_labels = labels

    def set_hidden_clusters(self, hidden: set[int]):
        self._hidden_clusters = hidden

    def refresh_style(
        self,
        node_scale: float,
        edge_opacity: float,
        edge_threshold: float = 0.0,
    ):
        if self._G is None or not self._pos:
            return
        self._node_scale = node_scale
        self._edge_opacity = edge_opacity
        self._edge_threshold = edge_threshold
        self._redraw(self._G, self._pos, self._last_mode, node_scale, edge_opacity)
    def update_theme(self):
        bg = get_color(CARD2_BG)
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(bg)
        tb_bg = ("#eef0f6", "#0a0a18")
        tb_fg = ("#000000", "#cccccc")
        self._toolbar.config(background=get_color(tb_bg))
        for child in self._toolbar.winfo_children():
            try:
                child.config(background=get_color(tb_bg), foreground=get_color(tb_fg))
            except Exception:
                pass
        is_light = ctk.get_appearance_mode().lower() == "light"
        self._annot.get_bbox_patch().set_facecolor("#ffffff" if is_light else "#1a1a3a")
        self._annot.set_color("black" if is_light else "white")

    def _redraw(
        self,
        G: nx.Graph,
        pos: dict,
        mode: str,
        node_scale: float,
        edge_opacity: float,
    ):
        import matplotlib.colors as mc
        import matplotlib.patheffects as path_effects
        from scipy.spatial import ConvexHull
        from matplotlib.patches import Polygon

        self._ax.clear()
        
        PAPER = "#F6F4EE"
        INK = "#141414"
        CLUSTER_PALETTE = ["#DF3117", "#1E4DA0", "#F5BE00", "#141414", "#7A9E7E", "#B65CA2", "#5CB0B8", "#C97B2D"]
        
        self._fig.patch.set_facecolor(PAPER)
        self._ax.set_facecolor(PAPER)
        
        # 3px border
        for spine in self._ax.spines.values():
            spine.set_visible(True)
            spine.set_color(INK)
            spine.set_linewidth(3)
            
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._ax.set_aspect("equal", adjustable="datalim")
        
        self._nodes = list(G.nodes())
        if G.number_of_nodes() == 0:
            self._ax.text(0.5, 0.5, "Nenhum nó.", ha="center", va="center", color=INK, transform=self._ax.transAxes)
            self._canvas.draw()
            return

        partition = nx.get_node_attributes(G, "group")
        weights = {n: G.nodes[n].get("weight", G.degree(n)) for n in self._nodes}
        
        xs = np.array([pos[n][0] for n in self._nodes])
        ys = np.array([pos[n][1] for n in self._nodes])

        node_w = np.array([weights[n] for n in self._nodes], float)
        mn, mx = node_w.min(), node_w.max()
        span = mx - mn if mx != mn else 1
        
        # sizes for scatter (points^2)
        sizes = (20 + 400 * (node_w - mn) / span) * node_scale
        
        colors = [CLUSTER_PALETTE[partition.get(n, 0) % len(CLUSTER_PALETTE)] for n in self._nodes]

        # Flat cluster panels
        cluster_points = {}
        for n, x, y in zip(self._nodes, xs, ys):
            c = partition.get(n, 0)
            cluster_points.setdefault(c, []).append((x, y))
            
        for c, pts in cluster_points.items():
            if len(pts) >= 3:
                try:
                    pts_arr = np.array(pts)
                    hull = ConvexHull(pts_arr)
                    poly = Polygon(pts_arr[hull.vertices], closed=True, 
                                 facecolor=CLUSTER_PALETTE[c % len(CLUSTER_PALETTE)], 
                                 alpha=0.08, zorder=0, edgecolor='none')
                    self._ax.add_patch(poly)
                except Exception:
                    pass

        # Edges
        edge_weights = np.array([G[u][v].get("weight", 1) for u, v in G.edges()], float)
        if len(edge_weights) > 0:
            ew_mn, ew_mx = edge_weights.min(), edge_weights.max()
            ew_span = ew_mx - ew_mn if ew_mx != ew_mn else 1
            
            from matplotlib.collections import LineCollection
            lines = []
            line_colors = []
            line_widths = []
            for (u, v), w in zip(G.edges(), edge_weights):
                w_norm = (w - ew_mn) / ew_span
                opacity = 0.08 + 0.14 * w_norm
                width = 1 + 3 * w_norm
                lines.append([pos[u], pos[v]])
                line_colors.append(mc.to_rgba(INK, alpha=opacity))
                line_widths.append(width)
                
            lc = LineCollection(lines, colors=line_colors, linewidths=line_widths, zorder=1)
            self._ax.add_collection(lc)

        # Nodes
        self._ax.scatter(xs, ys, s=sizes, c=colors, edgecolor=PAPER, linewidth=3, zorder=2)

        # Labels (Top 25)
        top_nodes = set(sorted(self._nodes, key=lambda n: weights[n], reverse=True)[:25])
        for n, x, y, s in zip(self._nodes, xs, ys, sizes):
            if n in top_nodes:
                font_size = max(8, int(np.sqrt(s) * 0.4))
                txt = self._ax.text(x, y, str(n), color=INK, fontsize=font_size, 
                                  ha='center', va='center', zorder=3, fontweight='bold')
                txt.set_path_effects([path_effects.withStroke(linewidth=3, foreground=PAPER)])

        self._canvas.draw()

    def highlight_node(self, name: str) -> bool:
        """Flash-highlight a node by name. Returns True if found."""
        if name not in self._nodes or not self._pos:
            return False
        x, y = self._pos[name]
        xs = np.array([self._pos[n][0] for n in self._nodes])
        ys = np.array([self._pos[n][1] for n in self._nodes])
        span = max(xs.max() - xs.min(), ys.max() - ys.min(), 1e-9)
        self._ax.scatter([x], [y], s=800, c=[ACCENT], linewidths=2.5,
                         edgecolors="white", zorder=15, alpha=0.9)
        self._ax.set_xlim(x - span * 0.25, x + span * 0.25)
        self._ax.set_ylim(y - span * 0.25, y + span * 0.25)
        self._canvas.draw()
        return True

    def _on_click(self, event):
        if event.inaxes != self._ax or not self._pos or event.button != 1:
            return
        zoom_node = None
        xs = np.array([self._pos[n][0] for n in self._nodes])
        ys = np.array([self._pos[n][1] for n in self._nodes])
        dists = (xs - event.xdata) ** 2 + (ys - event.ydata) ** 2
        idx = np.argmin(dists)
        if dists[idx] < 0.01:
            clicked = self._nodes[idx]
            if self._highlighted_node == clicked:
                self._highlighted_node = None
            else:
                self._highlighted_node = clicked
                zoom_node = clicked
        else:
            self._highlighted_node = None
        self._redraw(self._G, self._pos, self._last_mode,
                     self._node_scale, self._edge_opacity)
        if self._highlighted_node and self._node_click_cb:
            self._node_click_cb(self._highlighted_node)
        elif not self._highlighted_node and self._node_click_cb:
            self._node_click_cb(None)
        if zoom_node:
            hx, hy = self._pos[zoom_node]
            span = max(xs.max() - xs.min(), ys.max() - ys.min(), 1e-9)
            margin = span * 0.2
            self._ax.set_xlim(hx - margin, hx + margin)
            self._ax.set_ylim(hy - margin, hy + margin)
            self._canvas.draw()

    def reset_view(self):
        self._highlighted_node = None
        if self._G and self._pos:
            self._redraw(self._G, self._pos, self._last_mode,
                          self._node_scale, self._edge_opacity)

    def _on_hover(self, event):
        if event.inaxes != self._ax or not self._pos:
            if self._annot.get_visible():
                self._annot.set_visible(False)
                self._canvas.draw_idle()
            return

        xs = np.array([self._pos[n][0] for n in self._nodes])
        ys = np.array([self._pos[n][1] for n in self._nodes])
        dists = (xs - event.xdata) ** 2 + (ys - event.ydata) ** 2
        idx = np.argmin(dists)

        if dists[idx] < 0.01:
            term = self._nodes[idx]
            self._annot.xy = (xs[idx], ys[idx])
            lines = [f"Termo: {term}"]
            partition = nx.get_node_attributes(self._G, "group")
            raw_sizes = nx.get_node_attributes(self._G, "size")
            lines.append(f"Cluster: {partition.get(term, 0)}")
            lines.append(f"Ocorrências: {raw_sizes.get(term, 0)}")
            self._annot.set_text("\n".join(lines))
            self._annot.set_visible(True)
            self._canvas.draw_idle()
        else:
            if self._annot.get_visible():
                self._annot.set_visible(False)
                self._canvas.draw_idle()

    def clear(self):
        self._ax.clear()
        self._ax.set_facecolor(get_color(CARD2_BG))
        self._ax.axis("off")
        self._canvas.draw()

    @property
    def figure(self):
        return self._fig


# ── Burst Detection Window ─────────────────────────────────────────────────────
class BurstDetectionWindow(ctk.CTkToplevel):
    """Displays a list of terms with high citation or occurrence bursts."""
    def __init__(self, parent, bursts_data: list[dict]):
        super().__init__(parent)
        self.title("Blicsa — Detecção de Surtos (Bursts)")
        self.geometry("680x540")
        self.minsize(500, 400)
        self.configure(fg_color=CONTENT_BG, border_width=3, border_color=INK)
        self.grab_set()

        # Title
        ctk.CTkLabel(
            self, text="Surtos de Ocorrência (Kleinberg/Z-Score Burst Detection)",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT
        ).pack(pady=12, padx=20, anchor="w")

        # Description
        desc = (
            "Esta análise identifica palavras-chave ou termos que tiveram um aumento repentino "
            "e estatisticamente significativo de frequência de publicações em determinados períodos."
        )
        ctk.CTkLabel(
            self, text=desc, font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
            wraplength=640, justify="left"
        ).pack(pady=(0, 10), padx=20, anchor="w")

        # Scrollable table card
        card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        # Style Treeview
        _ts = ttk.Style()
        _ts.theme_use("default")
        bg_col = get_color(CARD2_BG)
        fg_col = "black" if ctk.get_appearance_mode().lower() == "light" else "#e0e0e0"
        header_bg = get_color(CARD_BG)
        _ts.configure("Burst.Treeview",
            background=bg_col, fieldbackground=bg_col, foreground=fg_col,
            rowheight=26, font=("Inter", 11), borderwidth=0,
        )
        _ts.configure("Burst.Treeview.Heading",
            background=header_bg, foreground=ACCENT, font=("Inter", 11, "bold"), relief="flat",
        )

        sb = ctk.CTkScrollbar(card, orientation="vertical")
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 6))

        tree = ttk.Treeview(
            card, style="Burst.Treeview", yscrollcommand=sb.set, selectmode="none", show="headings"
        )
        sb.configure(command=tree.yview)
        tree.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")

        tree["columns"] = ("term", "period", "strength", "total")
        tree.heading("term", text="Termo / Palavra-chave")
        tree.heading("period", text="Período do Surto")
        tree.heading("strength", text="Intensidade (Z-Score Sum)")
        tree.heading("total", text="Total Ocorrências")

        tree.column("term", width=220, anchor="w")
        tree.column("period", width=120, anchor="center")
        tree.column("strength", width=140, anchor="center")
        tree.column("total", width=100, anchor="center")

        for b in bursts_data[:40]:
            period = f"{b['start']} – {b['end']}"
            tree.insert("", "end", values=(b["term"], period, f"{b['strength']:.2f}", b["total_occ"]))
