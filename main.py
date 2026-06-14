import sys
import os
import json
import threading
import webbrowser
import tempfile
from pathlib import Path
from collections import Counter

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
import networkx as nx
import customtkinter as ctk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD as _TkDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from core.parsers import BibliometricParser, find_duplicates
from core.matrix_builders import NetworkGenerator, CLUSTER_PALETTE
from core.visualizer import compute_fa2_layout, build_plotly_map, build_plotly_density, export_plotly_html, export_figure_image
from core.nlp import load_thesaurus
from ai.client import GroqBibliometricAnalyst

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

OUTPUT_DIR  = Path(__file__).parent
MAP_PATH    = str(OUTPUT_DIR / "blicsa_mapa.html")
PLOTLY_PATH = str(OUTPUT_DIR / "blicsa_plotly.html")

SIDEBAR_BG  = "#0f0f1a"
CONTENT_BG  = "#13131f"
CARD_BG     = "#1a1a2e"
CARD2_BG    = "#0d0d1f"
ACCENT      = "#D4A017"
ACCENT_HOV  = "#b88a10"
TEXT_MUTED  = "#888899"
GREEN       = "#1a7a4a"
GREEN_HOV   = "#145c38"
PURPLE      = "#7c3aed"
PURPLE_HOV  = "#5b21b6"
TEAL        = "#0e7490"
TEAL_HOV    = "#0c5f76"

MAP_TYPES = [
    "Coocorrência de Palavras-chave",
    "Coautoria",
    "Cocitação de Referências",
    "Acoplamento Bibliográfico",
    "Citação Direta (paper→paper)",
    "Co-classificação IPC (patentes)",
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


# ── Log redirector ─────────────────────────────────────────────────────────────
class LogWriter:
    def __init__(self, widget: ctk.CTkTextbox):
        self._w, self._orig = widget, sys.__stdout__

    def write(self, msg: str):
        self._w.after(0, self._append, msg)
        try:
            self._orig.write(msg)
        except Exception:
            pass

    def _append(self, msg: str):
        self._w.configure(state="normal")
        self._w.insert("end", msg)
        self._w.see("end")
        self._w.configure(state="disabled")

    def flush(self):
        pass


# ── Verification dialog ────────────────────────────────────────────────────────
# ── Deduplication Dialog ───────────────────────────────────────────────────────
class DeduplicationDialog(ctk.CTkToplevel):
    """Shows fuzzy-duplicate pairs and lets the user confirm which to remove."""

    def __init__(self, parent, df, dupes: list[tuple[int, int, str]], on_apply):
        super().__init__(parent)
        self.title("Blicsa — Deduplicação")
        self.geometry("900x620")
        self.minsize(700, 420)
        self.configure(fg_color=CONTENT_BG)
        self.grab_set()

        self._df       = df
        self._dupes    = dupes       # [(keep_idx, remove_idx, reason)]
        self._on_apply = on_apply
        self._vars: list[ctk.BooleanVar] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=CONTENT_BG)
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            hdr,
            text=f"{len(dupes)} par(es) de duplicata detectado(s) — marque os que deseja remover:",
            font=ctk.CTkFont(size=13),
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="Todos", width=72, height=28,
            fg_color=TEAL, hover_color=TEAL_HOV,
            command=lambda: [v.set(True) for v in self._vars],
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            hdr, text="Nenhum", width=72, height=28,
            fg_color=CARD_BG, hover_color=CARD2_BG,
            command=lambda: [v.set(False) for v in self._vars],
        ).pack(side="right")

        # Scrollable pair list
        sf = ctk.CTkScrollableFrame(self, fg_color=CARD2_BG, corner_radius=10)
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
            row_f = ctk.CTkFrame(sf, fg_color=bg, corner_radius=6)
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
        foot = ctk.CTkFrame(self, fg_color=CONTENT_BG)
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
        self.configure(fg_color=CONTENT_BG)

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

        self._term_vars:   dict[str, ctk.BooleanVar]   = {}
        self._term_checks: dict[str, ctk.CTkCheckBox]  = {}
        for term in self._all_terms:
            var = ctk.BooleanVar(value=False)
            label = term if len(term) <= 28 else term[:27] + "…"
            cb = ctk.CTkCheckBox(
                sf, text=label, variable=var,
                fg_color=ACCENT, hover_color=ACCENT_HOV,
                font=ctk.CTkFont(size=11),
            )
            cb.pack(anchor="w", pady=1, padx=4)
            self._term_vars[term]   = var
            self._term_checks[term] = cb

        # Quick-select row
        qf = ctk.CTkFrame(lp, fg_color="transparent")
        qf.grid(row=3, column=0, padx=6, pady=(0, 4), sticky="ew")
        ctk.CTkButton(
            qf, text="Top 5", width=64, height=26,
            fg_color=TEAL, hover_color=TEAL_HOV,
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

        self._fig, self._ax = plt.subplots(facecolor=CARD2_BG)
        self._ax.set_facecolor(CARD2_BG)
        self._chart_cv = FigureCanvasTkAgg(self._fig, master=rp)
        self._chart_cv.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        NavigationToolbar2Tk(self._chart_cv, rp).grid(
            row=1, column=0, sticky="ew", padx=6, pady=(0, 6))

        self._ax.text(
            0.5, 0.5,
            "Selecione termos à esquerda\ne clique em Plotar",
            ha="center", va="center", color=TEXT_MUTED, fontsize=13,
            transform=self._ax.transAxes,
        )
        self._chart_cv.draw()

    # ── helpers ────────────────────────────────────────────────────────
    def _filter_terms(self, *_):
        q = self._search_var.get().strip().lower()
        for term, cb in self._term_checks.items():
            if q in term.lower():
                cb.pack(anchor="w", pady=1, padx=4)
            else:
                cb.pack_forget()

    def _select_top5(self):
        self._deselect_all()
        for term in self._all_terms[:5]:
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
        self._ax.set_facecolor(CARD2_BG)
        self._fig.set_facecolor(CARD2_BG)

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

        self._ax.set_xlabel("Ano",        color="#e0e0e0", fontsize=11)
        self._ax.set_ylabel("Frequência", color="#e0e0e0", fontsize=11)
        self._ax.set_title(
            "Tendência de Termos ao Longo do Tempo",
            color=ACCENT, fontsize=13, fontweight="bold",
        )
        self._ax.tick_params(colors="#e0e0e0")
        for spine in self._ax.spines.values():
            spine.set_color("#333355")
        self._ax.grid(True, color="#333355", alpha=0.5, linestyle="--")
        self._ax.legend(
            fontsize=9, framealpha=0.3,
            facecolor=CARD_BG, edgecolor=ACCENT, labelcolor="#e0e0e0",
        )
        self._fig.tight_layout()
        self._chart_cv.draw()


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
        self.geometry("700x600")
        self.configure(fg_color=CONTENT_BG)
        self.resizable(True, True)
        self.grab_set()

        self._on_confirm = on_confirm
        self._all_data = sorted(terms_data, key=lambda x: x[3], reverse=True)
        self._vars: dict[str, ctk.BooleanVar] = {}
        self._rows: list[tuple] = []   # (term, occ, score, frame)

        self._build()

    def _build(self):
        top = ctk.CTkFrame(self, fg_color=CONTENT_BG)
        top.pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            top,
            text=f"Termos candidatos: {len(self._all_data)} — desmarque os que não deseja incluir",
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        btn_f = ctk.CTkFrame(top, fg_color="transparent")
        btn_f.pack(side="right")
        ctk.CTkButton(btn_f, text="Todos", width=70, height=28,
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      text_color="#000",
                      command=self._select_all).pack(side="left", padx=4)
        ctk.CTkButton(btn_f, text="Nenhum", width=70, height=28,
                      fg_color="#333355", hover_color="#444466",
                      command=self._deselect_all).pack(side="left", padx=4)

        # Search
        sf = ctk.CTkFrame(self, fg_color=CONTENT_BG)
        sf.pack(fill="x", padx=16, pady=4)
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ctk.CTkEntry(sf, textvariable=self._search_var,
                     placeholder_text="Filtrar termos...",
                     border_color=ACCENT).pack(fill="x")

        # Header
        hdr = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=6)
        hdr.pack(fill="x", padx=16, pady=(4, 0))
        for col, (txt, w) in enumerate([
            ("✓", 32), ("Termo", 330), ("Ocorrências", 110), ("Doc. Freq.", 100), ("Relevância", 100),
        ]):
            ctk.CTkLabel(
                hdr, text=txt,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=ACCENT, width=w, anchor="w",
            ).grid(row=0, column=col, padx=4, pady=4, sticky="w")

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(self, fg_color=CARD2_BG, corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=16, pady=4)
        self._scroll = scroll
        self._populate(self._all_data)

        # Footer
        foot = ctk.CTkFrame(self, fg_color=CONTENT_BG)
        foot.pack(fill="x", padx=16, pady=(4, 14))
        self._count_lbl = ctk.CTkLabel(
            foot, text="", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="left")
        ctk.CTkButton(
            foot, text="✕  Cancelar", width=110, height=38,
            fg_color="#333355", hover_color="#444466",
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            foot, text="⚡  Gerar Mapa", width=140, height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirm,
        ).pack(side="right")
        self._refresh_count()

    def _populate(self, data: list[tuple]):
        for widget in self._scroll.winfo_children():
            widget.destroy()
        self._rows.clear()
        for i, (term, occ, doc_freq, score) in enumerate(data):
            if term not in self._vars:
                self._vars[term] = ctk.BooleanVar(value=True)
            bg = CARD_BG if i % 2 == 0 else CARD2_BG
            row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4)
            row.pack(fill="x", padx=2, pady=1)
            ctk.CTkCheckBox(
                row, text="", variable=self._vars[term],
                width=32, checkbox_width=16, checkbox_height=16,
                fg_color=ACCENT, hover_color=ACCENT_HOV,
                command=self._refresh_count,
            ).grid(row=0, column=0, padx=4, pady=3)
            ctk.CTkLabel(row, text=term, anchor="w", width=330,
                         font=ctk.CTkFont(size=11)).grid(row=0, column=1, padx=4, sticky="w")
            ctk.CTkLabel(row, text=str(occ), anchor="w", width=110,
                         font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=4, sticky="w")
            ctk.CTkLabel(row, text=str(doc_freq), anchor="w", width=100,
                         font=ctk.CTkFont(size=11)).grid(row=0, column=3, padx=4, sticky="w")
            ctk.CTkLabel(row, text=f"{score:.2f}", anchor="w", width=100,
                         font=ctk.CTkFont(size=11)).grid(row=0, column=4, padx=4, sticky="w")
            self._rows.append((term, occ, score, row))

    def _filter(self):
        q = self._search_var.get().strip().lower()
        filtered = [d for d in self._all_data if q in d[0].lower()] if q else self._all_data
        self._populate(filtered)

    def _select_all(self):
        for v in self._vars.values():
            v.set(True)
        self._refresh_count()

    def _deselect_all(self):
        for v in self._vars.values():
            v.set(False)
        self._refresh_count()

    def _refresh_count(self):
        selected = sum(1 for v in self._vars.values() if v.get())
        self._count_lbl.configure(text=f"{selected} de {len(self._vars)} selecionados")

    def _confirm(self):
        selected = {t for t, v in self._vars.items() if v.get()}
        self.destroy()
        self._on_confirm(selected)


# ── Embedded matplotlib canvas ─────────────────────────────────────────────────
class MapCanvas:
    def __init__(self, parent: ctk.CTkFrame, node_click_cb=None):
        self._parent = parent
        self._node_click_cb = node_click_cb
        self._fig, self._ax = plt.subplots(figsize=(11, 7), dpi=130)
        self._fig.patch.set_facecolor(CARD2_BG)
        self._ax.set_facecolor(CARD2_BG)
        self._ax.axis("off")

        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        tb_frame = ctk.CTkFrame(parent, fg_color="#0a0a18", height=30)
        tb_frame.grid(row=1, column=0, sticky="ew")
        self._toolbar = NavigationToolbar2Tk(self._canvas, tb_frame)
        self._toolbar.config(background="#0a0a18")
        for child in self._toolbar.winfo_children():
            try:
                child.config(background="#0a0a18", foreground="#cccccc",
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
            bbox=dict(boxstyle="round,pad=0.5", fc="#1a1a3a",
                      ec=ACCENT, lw=1.2, alpha=0.95),
            color="white", fontsize=9, visible=False, zorder=20,
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

    def _redraw(
        self,
        G: nx.Graph,
        pos: dict,
        mode: str,
        node_scale: float,
        edge_opacity: float,
    ):
        import matplotlib.colors as mc

        self._ax.clear()
        self._ax.set_facecolor(CARD2_BG)
        self._ax.axis("off")
        self._ax.set_aspect("equal", adjustable="datalim")
        self._nodes = list(G.nodes())

        if G.number_of_nodes() == 0:
            self._ax.text(0.5, 0.5, "Nenhum nó.\nReduz a frequência mínima.",
                          ha="center", va="center",
                          color=TEXT_MUTED, fontsize=13,
                          transform=self._ax.transAxes)
            self._canvas.draw()
            return

        partition  = nx.get_node_attributes(G, "group")
        raw_sizes  = nx.get_node_attributes(G, "size")
        year_means = nx.get_node_attributes(G, "year_mean")

        # Filter hidden clusters
        if self._hidden_clusters:
            self._nodes = [n for n in self._nodes
                           if partition.get(n, 0) not in self._hidden_clusters]

        xs = np.array([pos[n][0] for n in self._nodes])
        ys = np.array([pos[n][1] for n in self._nodes])

        raw  = np.array([raw_sizes.get(n, 20) for n in self._nodes], float)
        mn, mx = raw.min(), raw.max()
        span = mx - mn if mx != mn else 1
        sizes = (40 + 380 * (raw - mn) / span) * node_scale

        # ── Color determination ────────────────────────────────────────
        if mode == "Clusters":
            colors = [CLUSTER_PALETTE[partition.get(n, 0) % len(CLUSTER_PALETTE)]
                      for n in self._nodes]
        elif mode == "Grau (Degree)":
            degs   = np.array([G.degree(n, weight="weight") for n in self._nodes], float)
            normed = (degs - degs.min()) / (degs.max() - degs.min() + 1e-9)
            colors = [plt.cm.plasma(v) for v in normed]
        elif mode == "Ano Médio":
            yrs = np.array([year_means.get(n, 0) for n in self._nodes], float)
            valid = yrs[yrs > 0]
            if len(valid) > 1:
                mn_y, mx_y = valid.min(), valid.max()
                normed = np.where(yrs > 0, (yrs - mn_y) / (mx_y - mn_y + 1e-9), 0.5)
                colors = [plt.cm.coolwarm(v) for v in normed]
            else:
                colors = [CLUSTER_PALETTE[0]] * len(self._nodes)
        elif mode == "Betweenness":
            bc = nx.betweenness_centrality(G, weight="weight")
            vals = np.array([bc.get(n, 0) for n in self._nodes], float)
            normed = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9)
            colors = [plt.cm.YlOrRd(v) for v in normed]
        elif mode == "PageRank":
            pr = nx.pagerank(G, weight="weight")
            vals = np.array([pr.get(n, 0) for n in self._nodes], float)
            normed = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9)
            colors = [plt.cm.cool(v) for v in normed]
        else:  # Densidade
            from scipy.stats import gaussian_kde
            if len(xs) > 2:
                kde    = gaussian_kde(np.vstack([xs, ys]))
                dens   = kde(np.vstack([xs, ys]))
                normed = (dens - dens.min()) / (dens.max() - dens.min() + 1e-9)
                colors = [plt.cm.inferno(v) for v in normed]
            else:
                colors = [CLUSTER_PALETTE[0]] * len(self._nodes)

        # Neighborhood highlight: fade non-neighbors
        hl = self._highlighted_node
        nbrs: set[str] = set()
        if hl and hl in G.nodes():
            nbrs = set(G.neighbors(hl)) | {hl}
            colors = [c if n in nbrs else "#1a1a2e" for c, n in zip(colors, self._nodes)]

        # Pre-compute per-node RGBA for edge blending
        rgba_map = {n: mc.to_rgba(c) for n, c in zip(self._nodes, colors)}

        # ── Edges with blended endpoint colors ────────────────────────
        weights = np.array([G[u][v].get("weight", 1) for u, v in G.edges()], float)
        max_w   = weights.max() if len(weights) else 1.0
        thresh  = self._edge_threshold * max_w

        visible_set = set(self._nodes)
        for (u, v), w in zip(G.edges(), weights):
            if w < thresh:
                continue
            if u not in visible_set or v not in visible_set:
                continue
            in_nbr = (not hl) or (u in nbrs and v in nbrs)
            ratio  = w / max_w
            alpha  = (0.07 + 0.38 * ratio) * edge_opacity * (1.0 if in_nbr else 0.04)
            lw     = (0.4 + 2.2 * ratio) * (1.0 if in_nbr else 0.3)
            cu = rgba_map.get(u, (0.4, 0.4, 0.8, 1))
            cv = rgba_map.get(v, (0.4, 0.4, 0.8, 1))
            edge_c = ((cu[0]+cv[0])/2, (cu[1]+cv[1])/2, (cu[2]+cv[2])/2, max(alpha, 0.004))
            xu, yu = pos[u]
            xv, yv = pos[v]
            self._ax.plot([xu, xv], [yu, yv],
                          color=edge_c, lw=lw, zorder=1, solid_capstyle="round")

        # ── Glow layers (per-node color) ───────────────────────────────
        fade = 0.55 if hl else 1.0
        for size_mul, alpha_mul in [(9.0, 0.018), (5.5, 0.032), (3.2, 0.055),
                                     (2.0, 0.095), (1.55, 0.15)]:
            self._ax.scatter(xs, ys, s=sizes * size_mul, c=colors,
                             alpha=alpha_mul * fade, linewidths=0, zorder=2)

        # ── Node bodies with color-matched rim ────────────────────────
        rim_colors = []
        for c in colors:
            r, g, b, _ = mc.to_rgba(c)
            rim_colors.append((min(1, r*0.55 + 0.55), min(1, g*0.55 + 0.55),
                                min(1, b*0.55 + 0.55), 0.9))

        self._scatter = self._ax.scatter(
            xs, ys, s=sizes, c=colors,
            linewidths=1.4, edgecolors=rim_colors, zorder=6,
        )

        # ── Labels with tinted dark backdrop ──────────────────────────
        if G.number_of_nodes() <= 160:
            y_span = ys.max() - ys.min() + 1e-9
            fs_base = max(6.0, min(10.5, 9.5 - G.number_of_nodes() / 45))
            for n, x, y, s, c in zip(self._nodes, xs, ys, sizes, colors):
                if s < 48 * node_scale:
                    continue
                label = n if len(n) <= 24 else n[:22] + "…"
                r, g, b, _ = mc.to_rgba(c)
                bg = (r * 0.12, g * 0.12, b * 0.12, 0.78)
                self._ax.text(
                    x, y + 0.017 * y_span, label,
                    ha="center", va="bottom",
                    fontsize=fs_base, color="white", fontweight="bold", zorder=7,
                    bbox=dict(fc=bg, ec="none", pad=1.5, boxstyle="round,pad=0.3"),
                )

        # ── Cluster legend ─────────────────────────────────────────────
        if mode == "Clusters":
            cluster_tops: dict[int, list[str]] = {}
            for n in self._nodes:
                grp = partition.get(n, 0)
                cluster_tops.setdefault(grp, []).append(n)
            clusters = sorted(set(partition.values()))[:14]
            patches  = []
            for c in clusters:
                members = cluster_tops.get(c, [])
                top3 = sorted(members, key=lambda n: G.degree(n, weight="weight"),
                              reverse=True)[:3]
                if c in self._cluster_labels:
                    lbl = f"C{c}: {self._cluster_labels[c]}"
                elif top3:
                    lbl = f"C{c}: {' · '.join(top3)}"
                else:
                    lbl = f"Cluster {c}"
                patches.append(mpatches.Patch(
                    color=CLUSTER_PALETTE[c % len(CLUSTER_PALETTE)], label=lbl))
            self._ax.legend(
                handles=patches, loc="upper left",
                fontsize=7.5, framealpha=0.6,
                facecolor="#0a0a18", edgecolor=ACCENT,
                labelcolor="white",
            )

        # ── Highlight ring ─────────────────────────────────────────────
        if hl and hl in G.nodes():
            hx, hy = pos[hl]
            hi = self._nodes.index(hl)
            self._ax.scatter([hx], [hy], s=sizes[hi] * 4.0,
                             c="none", linewidths=2.8,
                             edgecolors=ACCENT, zorder=9, alpha=0.97)

        self._ax.margins(0.05)
        self._fig.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.01)
        self._canvas.draw()
        if not hl:
            print(f"[Mapa] {G.number_of_nodes()} nós · {G.number_of_edges()} arestas · modo {mode}\n")

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
        xs = np.array([self._pos[n][0] for n in self._nodes])
        ys = np.array([self._pos[n][1] for n in self._nodes])
        dists  = (xs - event.xdata) ** 2 + (ys - event.ydata) ** 2
        idx    = int(np.argmin(dists))
        thresh = ((xs.max() - xs.min()) * 0.05) ** 2
        zoom_node: str | None = None
        if dists[idx] < thresh:
            clicked = self._nodes[idx]
            if self._highlighted_node == clicked:
                self._highlighted_node = None  # deselect
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
        # Zoom to clicked node
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
        dists  = (xs - event.xdata) ** 2 + (ys - event.ydata) ** 2
        idx    = int(np.argmin(dists))
        thresh = ((xs.max() - xs.min()) * 0.04) ** 2
        if dists[idx] < thresh:
            node = self._nodes[idx]
            attrs = self._G.nodes[node] if self._G else {}
            lines = [node]
            if attrs.get("occurrence"):
                lines.append(f"Ocorrências: {attrs['occurrence']}")
            if attrs.get("year_mean"):
                lines.append(f"Ano médio: {attrs['year_mean']}")
            deg = self._G.degree(node, weight="weight") if self._G else 0
            lines.append(f"Grau: {deg:.2f}")
            self._annot.xy = (xs[idx], ys[idx])
            self._annot.set_text("\n".join(lines))
            self._annot.set_visible(True)
        else:
            self._annot.set_visible(False)
        self._canvas.draw_idle()

    def clear(self):
        self._ax.clear()
        self._ax.set_facecolor(CARD2_BG)
        self._ax.axis("off")
        self._canvas.draw()

    @property
    def figure(self):
        return self._fig


# ── Main App ───────────────────────────────────────────────────────────────────
class BlicsaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Blicsa — Inteligência Bibliométrica")
        self.geometry("1360x860")
        self.minsize(1100, 700)
        self.resizable(True, True)
        self.configure(fg_color=CONTENT_BG)

        self._file_paths: list[str]              = []
        self._file_formats: list[str]            = []   # parallel list of format per file
        self._dataframe                          = None
        self._generator: NetworkGenerator | None = None
        self._positions: dict                    = {}
        self._map_canvas: MapCanvas | None       = None
        self._thesaurus: dict[str, str]          = {}
        self._thesaurus_path: str | None         = None
        self._candidate_counts: Counter          = Counter()
        self._candidate_scores: dict             = {}
        self._cluster_labels: dict[int, str]     = {}
        self._max_edge_weight: float             = 1.0

        self._build_layout()
        sys.stdout = LogWriter(self._log_box)
        self._setup_dnd()
        self._setup_shortcuts()

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
            "import":  self._build_tab_import(),
            "config":  self._build_tab_config(),
            "viz":     self._build_tab_viz(),
            "ranking": self._build_tab_ranking(),
            "export":  self._build_tab_export(),
            "stats":   self._build_tab_stats(),
        }
        self._switch_tab("import")

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=SIDEBAR_BG, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(sb, text="Blicsa",
                     font=ctk.CTkFont(size=34, weight="bold"),
                     text_color=ACCENT).grid(
            row=0, column=0, padx=22, pady=(30, 22), sticky="w")

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        for i, (key, icon, label) in enumerate([
            ("import",  "📂", "Importação"),
            ("config",  "⚙️",  "Configurar Mapa"),
            ("viz",     "🗺️", "Mapa & IA"),
            ("ranking", "📊", "Rankings"),
            ("export",  "💾", "Exportar"),
            ("stats",   "📈", "Estatísticas"),
        ], start=1):
            btn = ctk.CTkButton(
                sb, text=f"{icon}  {label}", anchor="w",
                font=ctk.CTkFont(size=13),
                fg_color="transparent", hover_color="#1a1a35",
                text_color="white", corner_radius=8, height=44,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.grid(row=i, column=0, padx=10, pady=2, sticky="ew")
            self._nav_btns[key] = btn

        self._status_lbl = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._status_lbl.grid(row=10, column=0, padx=16, pady=(0, 2), sticky="sew")

        self._progress_bar = ctk.CTkProgressBar(sb, mode="indeterminate", height=5,
                                                 progress_color=ACCENT, fg_color=CARD2_BG)
        self._progress_bar.grid(row=11, column=0, padx=16, pady=(0, 8), sticky="sew")
        self._progress_bar.grid_remove()

        ctk.CTkLabel(sb, text="v3.0  •  Blicsa Engine",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).grid(
            row=12, column=0, padx=22, pady=(0, 16), sticky="sw")

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
        self.bind_all("<Control-f>", lambda _: self._switch_tab("import"))
        self.bind_all("<Control-F>", lambda _: self._switch_tab("import"))
        self.bind_all("<Escape>",    lambda _: self._reset_view())

    def _set_busy(self, msg: str = "Processando…"):
        self._status_lbl.configure(text=msg)
        self._progress_bar.grid()
        self._progress_bar.start()

    def _set_idle(self, msg: str = ""):
        self._progress_bar.stop()
        self._progress_bar.grid_remove()
        self._status_lbl.configure(text=msg)

    def _switch_tab(self, key: str):
        for f in self._tabs.values():
            f.grid_remove()
        self._tabs[key].grid(row=0, column=0, sticky="nsew")
        for k, btn in self._nav_btns.items():
            active = k == key
            btn.configure(fg_color=ACCENT if active else "transparent",
                          text_color="#000" if active else "white")

    # ── UI helpers ─────────────────────────────────────────────────────
    def _tab(self) -> ctk.CTkFrame:
        f = ctk.CTkFrame(self._content, fg_color=CONTENT_BG)
        f.grid_columnconfigure(0, weight=1)
        return f

    def _card(self, parent, row: int, pady: int = 8) -> ctk.CTkFrame:
        c = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12)
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

    # ── Tab: Importação ────────────────────────────────────────────────
    def _build_tab_import(self) -> ctk.CTkFrame:
        frame = self._tab()
        frame.grid_rowconfigure(3, weight=1)
        self._h1(frame, "Importação de Dados", 0)

        card = self._card(frame, 1)
        card.grid_columnconfigure(1, weight=1)

        # Default format for new files
        ctk.CTkLabel(card, text="Formato padrão:",
                     font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        rf = ctk.CTkFrame(card, fg_color="transparent")
        rf.grid(row=0, column=1, columnspan=2, padx=8, pady=(16, 8), sticky="w")
        self._origin_var = ctk.StringVar(value="scopus")
        for lbl, val in [
            ("Scopus",    "scopus"),
            ("WoS",       "wos"),
            ("BibTeX",    "bibtex"),
            ("PubMed",    "pubmed"),
            ("OpenAlex",  "openalex"),
            ("Crossref",  "crossref"),
        ]:
            ctk.CTkRadioButton(rf, text=lbl, variable=self._origin_var,
                               value=val, fg_color=ACCENT,
                               hover_color=ACCENT_HOV).pack(side="left", padx=8)

        # File list
        ctk.CTkLabel(card, text="Arquivos:",
                     font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=16, pady=(8, 0), sticky="nw")
        list_frame = ctk.CTkFrame(card, fg_color=CARD2_BG, corner_radius=8)
        list_frame.grid(row=1, column=1, padx=8, pady=(8, 0), sticky="ew")
        list_frame.grid_columnconfigure(0, weight=1)
        self._file_list_frame = ctk.CTkScrollableFrame(
            list_frame, fg_color=CARD2_BG, height=100)
        self._file_list_frame.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        self._file_list_frame.grid_columnconfigure(0, weight=1)
        self._file_row_widgets: list[tuple] = []  # (frame, path)

        # File buttons
        fbf = ctk.CTkFrame(card, fg_color="transparent")
        fbf.grid(row=1, column=2, padx=12, pady=(8, 0), sticky="n")
        self._btn(fbf, "➕  Adicionar", self._pick_file,
                  height=36).pack(pady=(0, 6))
        self._btn(fbf, "🗑  Limpar Tudo", self._clear_files,
                  color="#4a1a1a", hover="#6a2a2a",
                  height=36).pack()

        act_f = ctk.CTkFrame(card, fg_color="transparent")
        act_f.grid(row=2, column=0, columnspan=3, padx=16, pady=(12, 16), sticky="ew")
        act_f.grid_columnconfigure((0, 1), weight=1)
        self._btn(act_f, "⚡  Carregar e Combinar", self._load_data).grid(
            row=0, column=0, padx=(0, 6), sticky="ew")
        self._btn(act_f, "🔍  Deduplicar", self._run_dedup,
                  color=TEAL, hover=TEAL_HOV).grid(
            row=0, column=1, padx=(6, 0), sticky="ew")

        self._h1(frame, "Log", 2)
        lc = self._card(frame, 3)
        lc.grid_rowconfigure(0, weight=1)
        self._log_box = ctk.CTkTextbox(
            lc, state="disabled",
            font=ctk.CTkFont(family="Courier", size=11),
            fg_color=CARD2_BG, text_color="#88dd88")
        self._log_box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        return frame

    # ── Tab: Configurar Mapa ───────────────────────────────────────────
    def _build_tab_config(self) -> ctk.CTkFrame:
        frame = self._tab()
        frame.grid_rowconfigure(2, weight=1)
        self._h1(frame, "Configuração do Mapa", 0)

        card = self._card(frame, 1)
        card.grid_columnconfigure(1, weight=1)

        row = 0

        # Map type
        ctk.CTkLabel(card, text="Tipo de Mapa:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=(16, 8), sticky="w")
        self._map_type_var = ctk.StringVar(value=MAP_TYPES[0])
        ctk.CTkComboBox(card, values=MAP_TYPES, variable=self._map_type_var,
                        width=340, button_color=ACCENT,
                        border_color=ACCENT).grid(
            row=row, column=1, padx=16, pady=(16, 8), sticky="w")
        row += 1

        # Field selector
        ctk.CTkLabel(card, text="Campo:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        self._field_var = ctk.StringVar(value="keywords")
        ff = ctk.CTkFrame(card, fg_color="transparent")
        ff.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        for lbl, val in FIELD_OPTS:
            ctk.CTkRadioButton(ff, text=lbl, variable=self._field_var, value=val,
                               fg_color=ACCENT, hover_color=ACCENT_HOV,
                               command=self._on_field_change).pack(
                side="left", padx=10)
        row += 1

        # Counting method
        ctk.CTkLabel(card, text="Método de Contagem:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        self._counting_var = ctk.StringVar(value="full")
        cf = ctk.CTkFrame(card, fg_color="transparent")
        cf.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        ctk.CTkRadioButton(cf, text="Full Counting", variable=self._counting_var,
                           value="full", fg_color=ACCENT,
                           hover_color=ACCENT_HOV).pack(side="left", padx=10)
        ctk.CTkRadioButton(cf, text="Fractional Counting", variable=self._counting_var,
                           value="fractional", fg_color=ACCENT,
                           hover_color=ACCENT_HOV).pack(side="left", padx=10)
        row += 1

        # Association Strength
        ctk.CTkLabel(card, text="Normalização:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        self._assoc_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(card, text="Calcular Association Strength",
                        variable=self._assoc_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOV).grid(
            row=row, column=1, padx=16, pady=8, sticky="w")
        row += 1

        # Min occurrence + threshold preview
        ctk.CTkLabel(card, text="Freq. mínima:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        occ_f = ctk.CTkFrame(card, fg_color="transparent")
        occ_f.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        self._min_occ_var = ctk.IntVar(value=3)
        self._occ_lbl = ctk.CTkLabel(
            occ_f, text="3", width=40,
            font=ctk.CTkFont(size=15, weight="bold"), text_color=ACCENT)
        self._occ_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            occ_f, from_=1, to=50, number_of_steps=49,
            variable=self._min_occ_var, width=240,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=self._on_occ_change,
        ).pack(side="left")
        self._thresh_lbl = ctk.CTkLabel(
            occ_f, text="",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED)
        self._thresh_lbl.pack(side="left", padx=12)
        row += 1

        # Max nodes + top %
        ctk.CTkLabel(card, text="Filtro de nós:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        mf = ctk.CTkFrame(card, fg_color="transparent")
        mf.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        self._max_nodes_var = ctk.StringVar(value="0")
        ctk.CTkLabel(mf, text="Máx. nós (0=∞):", font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(mf, textvariable=self._max_nodes_var,
                     width=70, border_color=ACCENT).pack(side="left", padx=(0, 16))
        self._max_pct_var = ctk.StringVar(value="")
        ctk.CTkLabel(mf, text="ou Top % relevância:", font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(mf, textvariable=self._max_pct_var,
                     placeholder_text="ex: 60", width=70,
                     border_color=ACCENT).pack(side="left")
        row += 1

        # FA2 iterations + LinLog
        ctk.CTkLabel(card, text="Layout FA2:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        fa2_f = ctk.CTkFrame(card, fg_color="transparent")
        fa2_f.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        self._fa2_iter_var = ctk.IntVar(value=500)
        self._fa2_lbl = ctk.CTkLabel(
            fa2_f, text="500", width=50,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._fa2_lbl.pack(side="left", padx=(0, 4))
        ctk.CTkSlider(
            fa2_f, from_=100, to=2000, number_of_steps=19,
            variable=self._fa2_iter_var, width=200,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=lambda v: self._fa2_lbl.configure(text=str(int(v))),
        ).pack(side="left", padx=(0, 16))
        self._linlog_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(fa2_f, text="LinLog mode",
                        variable=self._linlog_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOV).pack(side="left")
        row += 1

        # Viz mode
        ctk.CTkLabel(card, text="Modo de visualização:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        self._viz_mode_var = ctk.StringVar(value=VIZ_MODES[0])
        ctk.CTkComboBox(card, values=VIZ_MODES, variable=self._viz_mode_var,
                        width=240, button_color=ACCENT,
                        border_color=ACCENT).grid(
            row=row, column=1, padx=16, pady=8, sticky="w")
        row += 1

        # Year range filter
        ctk.CTkLabel(card, text="Período (anos):",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        yr_f = ctk.CTkFrame(card, fg_color="transparent")
        yr_f.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        self._year_min_var = ctk.StringVar(value="")
        self._year_max_var = ctk.StringVar(value="")
        ctk.CTkEntry(yr_f, textvariable=self._year_min_var,
                     placeholder_text="De (ex: 2015)",
                     width=120, border_color=ACCENT).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(yr_f, text="até", text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(yr_f, textvariable=self._year_max_var,
                     placeholder_text="Até (ex: 2024)",
                     width=120, border_color=ACCENT).pack(side="left")
        row += 1

        # Extra stop words
        ctk.CTkLabel(card, text="Stop words extras:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        self._extra_sw_var = ctk.StringVar(value="")
        ctk.CTkEntry(card, textvariable=self._extra_sw_var,
                     placeholder_text="ex: process, system, method (separadas por vírgula)",
                     width=420, border_color=ACCENT).grid(
            row=row, column=1, padx=16, pady=8, sticky="w")
        row += 1

        # Thesaurus
        ctk.CTkLabel(card, text="Thesaurus CSV:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        th_f = ctk.CTkFrame(card, fg_color="transparent")
        th_f.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        self._thesaurus_lbl = ctk.CTkLabel(
            th_f, text="Nenhum carregado",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11))
        self._thesaurus_lbl.pack(side="left", padx=(0, 10))
        self._btn(th_f, "📄  Carregar", self._pick_thesaurus,
                  height=30).pack(side="left")
        row += 1

        # Plotly color mode
        ctk.CTkLabel(card, text="Cor do Plotly:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=8, sticky="w")
        self._plotly_mode_var = ctk.StringVar(value="cluster")
        pm_f = ctk.CTkFrame(card, fg_color="transparent")
        pm_f.grid(row=row, column=1, padx=16, pady=8, sticky="w")
        for lbl, val in [("Clusters", "cluster"), ("Grau ponderado", "degree"), ("Ano médio", "year")]:
            ctk.CTkRadioButton(pm_f, text=lbl, variable=self._plotly_mode_var,
                               value=val, fg_color=ACCENT,
                               hover_color=ACCENT_HOV).pack(side="left", padx=10)
        row += 1

        # API key
        ctk.CTkLabel(card, text="Chave API Groq:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=(8, 16), sticky="w")
        self._api_key_var = ctk.StringVar(
            value=os.environ.get("GROQ_API_KEY", ""))
        ctk.CTkEntry(card, textvariable=self._api_key_var,
                     show="*", placeholder_text="gsk_...",
                     width=380, border_color=ACCENT).grid(
            row=row, column=1, padx=16, pady=(8, 16), sticky="w")
        row += 1

        # Network pruning
        ctk.CTkLabel(card, text="Pós-processamento:",
                     font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=16, pady=(8, 8), sticky="w")
        prf = ctk.CTkFrame(card, fg_color="transparent")
        prf.grid(row=row, column=1, padx=16, pady=(8, 8), sticky="w")
        self._prune_isolated_var = ctk.BooleanVar(value=True)
        self._prune_largest_var  = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(prf, text="Remover nós isolados",
                        variable=self._prune_isolated_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOV).pack(side="left", padx=(0, 18))
        ctk.CTkCheckBox(prf, text="Manter só maior componente",
                        variable=self._prune_largest_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOV).pack(side="left")
        row += 1

        # Config persistence
        pf = ctk.CTkFrame(card, fg_color="transparent")
        pf.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="w")
        self._btn(pf, "💾  Salvar Configuração", self._save_config,
                  height=36, color=TEAL, hover=TEAL_HOV).pack(side="left", padx=(0, 10))
        self._btn(pf, "📂  Carregar Configuração", self._load_config,
                  height=36, color=TEAL, hover=TEAL_HOV).pack(side="left")

        return frame

    # ── Tab: Mapa & IA ─────────────────────────────────────────────────
    def _build_tab_viz(self) -> ctk.CTkFrame:
        frame = self._tab()
        frame.grid_rowconfigure(3, weight=5)
        frame.grid_rowconfigure(4, weight=2)

        # Action buttons
        br = ctk.CTkFrame(frame, fg_color=CONTENT_BG)
        br.grid(row=0, column=0, padx=24, pady=(16, 4), sticky="ew")
        br.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._btn(br, "⚡  Gerar Mapa", self._run_mapping,
                  height=48).grid(row=0, column=0, padx=5, sticky="ew")
        self._btn(br, "✦  Abrir Plotly Interativo",
                  self._open_plotly, color="#1a4a7a",
                  hover="#153a60", height=48).grid(
            row=0, column=1, padx=5, sticky="ew")
        self._btn(br, "🌐  HTML no Navegador",
                  self._open_map_browser,
                  color=GREEN, hover=GREEN_HOV, height=48).grid(
            row=0, column=2, padx=5, sticky="ew")
        self._btn(br, "✨  Insights com IA", self._run_ai,
                  color=PURPLE, hover=PURPLE_HOV, height=48).grid(
            row=0, column=3, padx=5, sticky="ew")
        self._btn(br, "🏷️  Nomear Clusters", self._auto_label_clusters,
                  color="#1a5a3a", hover="#144a2e", height=48).grid(
            row=1, column=0, padx=5, pady=(4, 0), sticky="ew")
        self._btn(br, "📈  Tendências", self._open_trends,
                  color=TEAL, hover=TEAL_HOV, height=48).grid(
            row=1, column=1, padx=5, pady=(4, 0), sticky="ew")
        self._btn(br, "☁  Word Cloud", self._show_wordcloud,
                  color=PURPLE, hover=PURPLE_HOV, height=48).grid(
            row=1, column=2, columnspan=2, padx=5, pady=(4, 0), sticky="ew")

        # Search + style controls
        ctrl = ctk.CTkFrame(frame, fg_color=CONTENT_BG)
        ctrl.grid(row=1, column=0, padx=24, pady=(0, 4), sticky="ew")
        ctrl.grid_columnconfigure(1, weight=1)

        # Search bar
        sf = ctk.CTkFrame(ctrl, fg_color="transparent")
        sf.grid(row=0, column=0, sticky="w")
        self._search_var = ctk.StringVar()
        ctk.CTkEntry(sf, textvariable=self._search_var,
                     placeholder_text="Buscar nó...",
                     width=220, border_color=ACCENT).pack(side="left", padx=(0, 6))
        self._btn(sf, "🔍", self._search_node, height=32, width=36).pack(side="left", padx=(0, 8))
        self._btn(sf, "↺", self._reset_view, height=32, width=36,
                  color="#333355", hover="#444466").pack(side="left")

        # Style sliders
        sl_f = ctk.CTkFrame(ctrl, fg_color="transparent")
        sl_f.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(sl_f, text="Tamanho nós:", font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
        self._node_scale_var = ctk.DoubleVar(value=1.0)
        ctk.CTkSlider(sl_f, from_=0.3, to=2.5, variable=self._node_scale_var,
                      width=100, button_color=ACCENT, progress_color=ACCENT,
                      command=lambda _: self._apply_style()).pack(side="left")
        ctk.CTkLabel(sl_f, text=" Opacidade arestas:", font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(side="left", padx=(12, 4))
        self._edge_opacity_var = ctk.DoubleVar(value=1.0)
        ctk.CTkSlider(sl_f, from_=0.05, to=1.0, variable=self._edge_opacity_var,
                      width=100, button_color=ACCENT, progress_color=ACCENT,
                      command=lambda _: self._apply_style()).pack(side="left")
        ctk.CTkLabel(sl_f, text=" Min. peso aresta:", font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(side="left", padx=(12, 4))
        self._edge_thresh_var = ctk.DoubleVar(value=0.0)
        self._edge_thresh_lbl = ctk.CTkLabel(
            sl_f, text="0.00", width=44,
            font=ctk.CTkFont(size=10), text_color=ACCENT)
        self._edge_thresh_lbl.pack(side="left", padx=(0, 2))
        self._edge_thresh_slider = ctk.CTkSlider(
            sl_f, from_=0.0, to=1.0, variable=self._edge_thresh_var,
            width=90, button_color=ACCENT, progress_color=ACCENT,
            command=self._on_edge_thresh_change)
        self._edge_thresh_slider.pack(side="left")

        # Cluster filter strip (populated after map generation)
        self._cluster_filter_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        self._cluster_filter_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self._cluster_filter_vars: dict[int, ctk.BooleanVar] = {}

        # Stats bar
        sc = self._card(frame, 2, pady=(0, 4))
        sc.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        for col, (key, nice) in enumerate([
            ("total_papers",    "Artigos"),
            ("total_nodes",     "Nós"),
            ("total_edges",     "Arestas"),
            ("num_clusters",    "Clusters"),
            ("avg_citations",   "Média Cit."),
            ("network_density", "Densidade"),
        ]):
            inner = ctk.CTkFrame(sc, fg_color=CARD2_BG, corner_radius=8)
            inner.grid(row=0, column=col, padx=5, pady=8, sticky="ew")
            v = ctk.CTkLabel(inner, text="—",
                             font=ctk.CTkFont(size=18, weight="bold"),
                             text_color=ACCENT)
            v.pack(pady=(6, 0))
            ctk.CTkLabel(inner, text=nice,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack(pady=(0, 6))
            self._stat_labels[key] = v

        # Matplotlib canvas
        map_card = self._card(frame, 3, pady=(0, 4))
        map_card.grid_rowconfigure(0, weight=1)
        map_card.grid_columnconfigure(0, weight=1)
        self._map_canvas = MapCanvas(map_card, node_click_cb=self._on_node_click)

        # Bottom tabview: Insights IA | Nó Selecionado
        btabs = ctk.CTkTabview(frame, fg_color=CARD_BG,
                               segmented_button_fg_color=CARD2_BG,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color=ACCENT_HOV,
                               segmented_button_unselected_color=CARD2_BG,
                               text_color="#000", text_color_disabled=TEXT_MUTED)
        btabs.grid(row=4, column=0, padx=24, pady=(0, 16), sticky="nsew")
        frame.grid_rowconfigure(4, weight=2)

        ia_tab   = btabs.add("Insights IA")
        node_tab = btabs.add("Nó Selecionado")
        ia_tab.grid_rowconfigure(0, weight=1)
        ia_tab.grid_columnconfigure(0, weight=1)
        node_tab.grid_rowconfigure(0, weight=1)
        node_tab.grid_columnconfigure(0, weight=1)

        self._insights_box = ctk.CTkTextbox(
            ia_tab, font=ctk.CTkFont(size=12), fg_color=CARD2_BG)
        self._insights_box.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        self._insights_box.insert("end",
            "Os insights aparecerão aqui após clicar em 'Insights com IA'.")
        self._insights_box.configure(state="disabled")

        self._node_info_box = ctk.CTkTextbox(
            node_tab, font=ctk.CTkFont(family="Courier", size=11), fg_color=CARD2_BG)
        self._node_info_box.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        self._node_info_box.insert("end", "Clique em um nó no mapa para ver detalhes.")
        self._node_info_box.configure(state="disabled")

        self._bottom_tabs = btabs
        return frame

    # ── Tab: Rankings ──────────────────────────────────────────────────
    def _build_tab_ranking(self) -> ctk.CTkFrame:
        frame = self._tab()
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

        # Dark-themed Treeview style
        _ts = ttk.Style()
        _ts.theme_use("default")
        _ts.configure("Blicsa.Treeview",
            background=CARD2_BG,
            fieldbackground=CARD2_BG,
            foreground="#e0e0e0",
            rowheight=26,
            font=("Inter", 11),
            borderwidth=0,
        )
        _ts.configure("Blicsa.Treeview.Heading",
            background=CARD_BG,
            foreground=ACCENT,
            font=("Inter", 11, "bold"),
            relief="flat",
        )
        _ts.map("Blicsa.Treeview",
            background=[("selected", "#2a2a5a")],
            foreground=[("selected", "white")],
        )
        _ts.map("Blicsa.Treeview.Heading",
            background=[("active", ACCENT_HOV)],
        )

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
        self._h1(frame, "Exportar Resultados", 0)

        card = self._card(frame, 1)
        card.grid_columnconfigure((0, 1), weight=1)

        exports = [
            # col 0
            [
                ("📋  Ranking de Nós (CSV)",        self._export_nodes_csv),
                ("🔗  Arestas / Matriz (CSV)",       self._export_edges_csv),
                ("📄  DataFrame Completo (CSV)",      self._export_df_csv),
                ("🏷️  Relatório de Clusters (TXT)",  self._export_clusters_txt),
            ],
            # col 1
            [
                ("✦   Mapa Plotly Interativo (HTML)", self._export_plotly_html),
                ("🌐  Mapa PyVis (HTML)",             self._export_pyvis_html),
                ("🖼️  Imagem PNG (300dpi)",           self._export_png),
                ("✏️  Imagem SVG (vetorial)",         self._export_svg),
                ("📑  Imagem PDF (para artigos)",     self._export_pdf),
            ],
        ]
        for col, items in enumerate(exports):
            for i, (lbl, cmd) in enumerate(items):
                self._btn(card, lbl, cmd, height=44).grid(
                    row=i, column=col, padx=16, pady=8, sticky="ew")

        # Excel export
        self._h1(frame, "Excel / Planilha", 2)
        xcard = self._card(frame, 3)
        xcard.grid_columnconfigure(0, weight=1)
        self._btn(xcard, "📊  Exportar Tudo para Excel (.xlsx)",
                  self._export_excel, color=GREEN, hover=GREEN_HOV,
                  height=44).grid(row=0, column=0, padx=16, pady=12, sticky="ew")

        # Graph format exports
        self._h1(frame, "Formatos de Grafo", 4)
        gcard = self._card(frame, 5)
        gcard.grid_columnconfigure((0, 1, 2, 3), weight=1)
        for col, (lbl, cmd) in enumerate([
            ("🔷  GML (Gephi / Cytoscape)",    self._export_gml),
            ("🟣  GEXF (Gephi nativo)",         self._export_gexf),
            ("🕸️  Pajek .net",                 self._export_pajek),
            ("{ }  JSON Topologia (frontend)", self._export_json),
        ]):
            self._btn(gcard, lbl, cmd, height=44, color=TEAL, hover=TEAL_HOV).grid(
                row=0, column=col, padx=10, pady=12, sticky="ew")

        return frame

    # ── Actions: data loading ──────────────────────────────────────────
    _FORMAT_LABELS = {
        "scopus":   "Scopus CSV",
        "wos":      "WoS TXT",
        "bibtex":   "BibTeX",
        "pubmed":   "PubMed",
        "openalex": "OpenAlex JSON",
        "crossref": "Crossref JSON",
    }

    def _auto_detect_format(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext == ".bib":
            return "bibtex"
        if ext == ".nbib":
            return "pubmed"
        return self._origin_var.get()

    def _pick_file(self):
        paths = filedialog.askopenfilenames(
            filetypes=[
                ("Todos os formatos", "*.csv *.txt *.bib *.nbib *.json"),
                ("CSV", "*.csv"), ("TXT / NBIB", "*.txt *.nbib"),
                ("BibTeX", "*.bib"), ("JSON", "*.json"), ("All files", "*.*"),
            ])
        for p in paths:
            if p not in self._file_paths:
                fmt = self._auto_detect_format(p)
                self._file_paths.append(p)
                self._file_formats.append(fmt)
                self._add_file_row(p, fmt)

    def _add_file_row(self, path: str, fmt: str):
        row_f = ctk.CTkFrame(self._file_list_frame, fg_color=CARD_BG, corner_radius=6)
        row_f.pack(fill="x", pady=2)
        row_f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(row_f, text=Path(path).name, anchor="w",
                     font=ctk.CTkFont(size=11)).grid(
            row=0, column=0, padx=8, pady=4, sticky="ew")
        fmt_var = ctk.StringVar(value=fmt)
        ctk.CTkComboBox(
            row_f,
            values=list(self._FORMAT_LABELS.keys()),
            variable=fmt_var,
            width=110, height=24,
            button_color=ACCENT, border_color=ACCENT,
            command=lambda v, p=path: self._set_file_format(p, v),
        ).grid(row=0, column=1, padx=4, pady=4)
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

    def _clear_files(self):
        self._file_paths.clear()
        self._file_formats.clear()
        for f, _ in self._file_row_widgets:
            f.destroy()
        self._file_row_widgets.clear()

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
            self.after(0, self._update_stats_tab)
            self.after(0, self._set_idle, f"{len(combined)} registros carregados")
        except Exception as exc:
            print(f"[ERRO] {exc}\n")
            self.after(0, self._set_idle, "Erro ao carregar")
            self.after(0, lambda: messagebox.showerror("Erro ao carregar", str(exc)))

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
                text_color="white",
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

            # Store max edge weight for threshold slider scaling
            weights = [d.get("weight", 1) for _, _, d in gen.G.edges(data=True)]
            self._max_edge_weight = max(weights, default=1.0)
            self.after(0, lambda: self._edge_thresh_slider.configure(
                to=self._max_edge_weight))

            stats = gen.get_summary_stats()
            mode  = self._viz_mode_var.get()
            plotly_color = self._plotly_mode_var.get()

            gen.export_to_html(MAP_PATH)
            if "Densidade (Plotly)" in mode:
                fig = build_plotly_density(gen.G, self._positions)
            else:
                fig = build_plotly_map(gen.G, self._positions, color_mode=plotly_color)
            export_plotly_html(fig, PLOTLY_PATH)
            print("[OK] Mapas prontos.\n")

            self.after(0, self._update_stats, stats)
            self.after(0, lambda: self._map_canvas.render(
                gen.G, self._positions, mode,
                self._node_scale_var.get(),
                self._edge_opacity_var.get(),
                self._edge_thresh_var.get(),
            ))
            self.after(0, self._populate_cluster_filter)
            self.after(0, lambda: self._switch_tab("viz"))
            self.after(0, self._set_idle, "Mapa gerado")
        except Exception as exc:
            print(f"[ERRO] {exc}\n")
            self.after(0, self._set_idle, "Erro")
            self.after(0, lambda: messagebox.showerror("Erro", str(exc)))

    def _update_stats(self, stats: dict):
        for key, lbl in self._stat_labels.items():
            lbl.configure(text=str(stats.get(key, "—")))

    # ── Viz controls ───────────────────────────────────────────────────
    def _apply_style(self):
        if self._map_canvas:
            self._map_canvas.refresh_style(
                self._node_scale_var.get(),
                self._edge_opacity_var.get(),
                self._edge_thresh_var.get(),
            )

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
        if not self._map_canvas:
            return
        hidden = {cid for cid, var in self._cluster_filter_vars.items() if not var.get()}
        self._map_canvas.set_hidden_clusters(hidden)
        self._map_canvas.refresh_style(
            self._node_scale_var.get(),
            self._edge_opacity_var.get(),
            self._edge_thresh_var.get(),
        )

    def _on_edge_thresh_change(self, val: float):
        self._edge_thresh_lbl.configure(text=f"Peso mín.: {val:.2f}")
        self._apply_style()

    def _search_node(self):
        if not self._map_canvas:
            return
        query = self._search_var.get().strip().lower()
        if not query:
            return
        nodes = list(self._generator.G.nodes()) if self._generator else []
        match = next((n for n in nodes if query in n.lower()), None)
        if match:
            found = self._map_canvas.highlight_node(match)
            if not found:
                messagebox.showinfo("Busca", f'Nó "{match}" não encontrado no canvas.')
        else:
            messagebox.showinfo("Busca", f'Nenhum nó contendo "{query}".')

    def _reset_view(self):
        if self._map_canvas:
            self._map_canvas.reset_view()

    # ── Plotly / browser ───────────────────────────────────────────────
    def _open_plotly(self):
        if not Path(PLOTLY_PATH).exists():
            messagebox.showinfo("Não gerado", "Gere o mapa primeiro.")
            return
        threading.Thread(target=self._launch_webview, daemon=True).start()

    def _launch_webview(self):
        try:
            import webview
            webview.create_window(
                "Blicsa — Mapa Interativo",
                url=f"file://{PLOTLY_PATH}",
                width=1200, height=800,
                background_color="#0d0d1f",
            )
            webview.start()
        except Exception as exc:
            print(f"[ERRO webview] {exc} — abrindo no navegador.\n")
            webbrowser.open(f"file://{PLOTLY_PATH}")

    def _open_map_browser(self):
        target = PLOTLY_PATH if Path(PLOTLY_PATH).exists() else MAP_PATH
        if Path(target).exists():
            webbrowser.open(f"file://{target}")
        else:
            messagebox.showinfo("Não gerado", "Gere o mapa primeiro.")

    # ── AI ─────────────────────────────────────────────────────────────
    def _run_ai(self):
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        threading.Thread(target=self._ai_worker, daemon=True).start()

    def _ai_worker(self):
        self.after(0, self._set_busy, "IA gerando insights…")
        try:
            print("[IA] Enviando dados para Groq...")
            analyst = GroqBibliometricAnalyst(
                api_key=self._api_key_var.get().strip() or None)
            cluster_report = self._generator.get_cluster_report()
            year_dist: dict | None = None
            if self._dataframe is not None and "year" in self._dataframe.columns:
                yr = self._dataframe["year"].replace(0, None).dropna().astype(int)
                year_dist = dict(Counter(yr))
            result = analyst.generate_insights(
                top_keywords=self._generator.get_top_keywords(20),
                summary_stats=self._generator.get_summary_stats(),
                cluster_report=cluster_report,
                year_distribution=year_dist,
            )
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights prontos")
            print("[IA] Insights gerados.\n")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            print(f"[ERRO IA] {exc}\n")

    def _show_insights(self, text: str):
        self._insights_box.configure(state="normal")
        self._insights_box.delete("1.0", "end")
        self._insights_box.insert("end", text)
        self._insights_box.configure(state="disabled")

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
                    self._rank_tree.insert("", "end", values=(i, kw, n, "—", "—"))

        elif kind == "authors":
            _setup_cols([
                ("#",         48,  "center"),
                ("Autor",    400,  "w"),
                ("Publicações", 110, "e"),
            ])
            for i, (a, n) in enumerate(gen.get_top_authors(100), 1):
                self._rank_tree.insert("", "end", values=(i, a, n))

        elif kind == "hindex":
            _setup_cols([
                ("#",          48,  "center"),
                ("Autor",     320,  "w"),
                ("h-index",    80,  "e"),
                ("Artigos",    80,  "e"),
                ("Cit. Média", 100, "e"),
            ])
            for i, (author, h, papers, avg) in enumerate(gen.get_author_hindex(100), 1):
                self._rank_tree.insert("", "end", values=(
                    i, author, h, papers, f"{avg:.1f}"))

        elif kind == "sources":
            _setup_cols([
                ("#",              48,  "center"),
                ("Fonte / Periódico", 440, "w"),
                ("Publicações",    110, "e"),
            ])
            for i, (s, n) in enumerate(gen.get_top_sources(100), 1):
                self._rank_tree.insert("", "end", values=(i, s, n))

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

        field = self._field_var.get() if hasattr(self, "_field_var") else "keywords"
        col   = {"keywords": "keywords", "titles": "title",
                 "abstracts": "abstract", "titles_abstracts": "abstract"}.get(field, "keywords")

        # Build frequency dict from candidate_counts or raw column
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
            messagebox.showinfo("Word Cloud", "Nenhum termo encontrado.")
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

        win = ctk.CTkToplevel(self)
        win.title("Blicsa — Word Cloud")
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

        # Save button
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
            analyst = GroqBibliometricAnalyst(
                api_key=self._api_key_var.get().strip() or None)
            report = self._generator.get_cluster_report()
            labels = analyst.label_clusters(report, context=self._field_var.get())
            self._cluster_labels = labels
            if self._map_canvas:
                self._map_canvas.set_cluster_labels(labels)
                self.after(0, lambda: self._map_canvas.refresh_style(
                    self._node_scale_var.get(),
                    self._edge_opacity_var.get(),
                    self._edge_thresh_var.get(),
                ))
            self.after(0, self._set_idle, f"{len(labels)} clusters nomeados")
            print(f"[IA] {len(labels)} clusters nomeados.\n")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro ao nomear clusters")
            print(f"[ERRO labeling] {exc}\n")

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


if __name__ == "__main__":
    app = BlicsaApp()
    app.mainloop()
