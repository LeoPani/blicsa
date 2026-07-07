import customtkinter as ctk
import pandas as pd
from typing import Callable, Optional, List
from collections import Counter
import threading
import time

PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
BLUE = "#1E4DA0"
WHITE = "#FFFFFF"

class SkeletonCard(ctk.CTkFrame):
    """
    A placeholder skeleton loading card with pulse animation to indicate
    that data is currently being fetched or processed.
    """
    def __init__(self, master):
        super().__init__(master, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.grid_columnconfigure(0, weight=1)
        
        self.title_skel = ctk.CTkFrame(self, fg_color="#E0E0E0", height=20, corner_radius=0)
        self.title_skel.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        self.title_skel.configure(width=300)
        
        self.meta_skel = ctk.CTkFrame(self, fg_color="#E0E0E0", height=14, corner_radius=0)
        self.meta_skel.grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self.meta_skel.configure(width=200)

        self.abs_skel = ctk.CTkFrame(self, fg_color="#E0E0E0", height=30, corner_radius=0)
        self.abs_skel.grid(row=2, column=0, padx=12, pady=(4, 12), sticky="ew")
        
        self._pulse_state = 0
        self._animating = True
        self._animate()

    def _animate(self):
        if not self._animating: return
        colors = ["#E0E0E0", "#EEEEEE", "#F5F5F5", "#EEEEEE"]
        color = colors[self._pulse_state % len(colors)]
        self.title_skel.configure(fg_color=color)
        self.meta_skel.configure(fg_color=color)
        self.abs_skel.configure(fg_color=color)
        self._pulse_state += 1
        self.after(250, self._animate)

    def stop(self):
        self._animating = False

class ArticleCard(ctk.CTkFrame):
    """
    A UI card representing a single bibliometric record/article.
    Provides a checkbox for selection and displays title, year,
    citations, authors, source, and a truncated abstract.
    """
    def __init__(self, master, record: dict, on_toggle: Callable[[bool, int], None], index: int):
        super().__init__(master, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.record = record
        self.on_toggle = on_toggle
        self.index = index
        self._selected = True
        
        self.grid_columnconfigure(1, weight=1)
        
        # Left edge bar
        self.left_bar = ctk.CTkFrame(self, width=6, fg_color=WHITE, corner_radius=0)
        self.left_bar.grid(row=0, column=0, rowspan=4, sticky="ns")
        
        # Checkbox
        self.cb = ctk.CTkCheckBox(
            self, text="", width=24, corner_radius=0, 
            border_color=INK, fg_color=RED, hover_color=RED,
            command=self._on_check
        )
        self.cb.select()
        self.cb.grid(row=0, column=1, rowspan=4, padx=(8, 4), pady=12, sticky="nw")
        
        # Badges & Title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=2, padx=(4, 12), pady=(12, 2), sticky="ew")
        title_frame.grid_columnconfigure(3, weight=1)
        
        year = record.get("year", "")
        if year:
            ctk.CTkLabel(title_frame, text=str(year), fg_color=INK, text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            
        cites = record.get("citations", 0)
        if cites > 0:
            ctk.CTkLabel(title_frame, text=f"★ {cites}", fg_color="#F5BE00", text_color=INK, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            
        if record.get("is_oa"):
            ctk.CTkLabel(title_frame, text="OPEN ACCESS", fg_color="#7A9E7E", text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            
        lang = str(record.get("language", "")).upper()
        if lang:
            ctk.CTkLabel(title_frame, text=lang, fg_color="#E0E0E0", text_color=INK, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
        
        title = str(record.get("title", "Sem título"))
        ctk.CTkLabel(self, text=title, text_color=BLUE, font=ctk.CTkFont(size=14, weight="bold"), anchor="w", justify="left", wraplength=700).grid(row=1, column=2, padx=(4, 12), pady=0, sticky="w")
        
        # Meta: Authors - Journal
        authors = str(record.get("authors", ""))
        journal = str(record.get("source", ""))
        meta_text = ""
        if authors: meta_text += authors
        if journal: meta_text += f" — {journal}"
        ctk.CTkLabel(self, text=meta_text, text_color=INK, font=ctk.CTkFont(size=12, slant="italic"), anchor="w", justify="left").grid(row=2, column=2, padx=(4, 12), pady=(2, 4), sticky="w")
        
        # Abstract
        abs_text = str(record.get("abstract", ""))
        if len(abs_text) > 200: abs_text = abs_text[:197] + "..."
        if abs_text:
            ctk.CTkLabel(self, text=abs_text, text_color="#555555", font=ctk.CTkFont(size=12), anchor="w", justify="left", wraplength=700).grid(row=3, column=2, padx=(4, 12), pady=(0, 12), sticky="w")
            
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)
            
    def _on_enter(self, e):
        self.configure(border_width=4)
        self.left_bar.configure(fg_color=RED)
        
    def _on_leave(self, e):
        self.configure(border_width=2)
        self.left_bar.configure(fg_color=WHITE)

    def _on_check(self):
        self._selected = bool(self.cb.get())
        self.on_toggle(self._selected, self.index)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.cb.select()
        else:
            self.cb.deselect()

class SearchFeedView(ctk.CTkFrame):
    """
    A comprehensive UI view for displaying search results from APIs.
    Features filtering sidebars, pagination, selection logic,
    and a bottom bar for confirming import to the corpus.
    """
    def __init__(self, master, on_import_confirm: Callable, on_cancel: Callable):
        super().__init__(master, fg_color=PAPER, corner_radius=0)
        self.on_import_confirm = on_import_confirm
        self.on_cancel = on_cancel
        self.records = []
        self.filtered_indices = []
        self.selected_indices = set()
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        hdr = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK, height=60)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 8))
        hdr.pack_propagate(False)
        self.title_lbl = ctk.CTkLabel(hdr, text="Resultados da Busca", font=ctk.CTkFont(size=18, weight="bold"), text_color=INK)
        self.title_lbl.pack(side="left", padx=16)
        
        self.trail_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12), text_color="#555555")
        self.trail_lbl.pack(side="left", padx=16)
        
        ctk.CTkButton(hdr, text="Cancelar", fg_color=WHITE, text_color=INK, hover_color="#EEEEEE", border_width=2, border_color=INK, corner_radius=0, command=self.on_cancel).pack(side="right", padx=16)
        
        # Sidebar
        self.sidebar = ctk.CTkScrollableFrame(self, width=250, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.sidebar.grid(row=1, column=0, sticky="ns", padx=(16, 8), pady=8)
        
        # Main feed
        self.feed = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.feed.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=8)
        self.feed.grid_columnconfigure(0, weight=1)
        
        # Bottom Bar
        self.bottom_bar = ctk.CTkFrame(self, fg_color=INK, corner_radius=0, height=60)
        self.bottom_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.bottom_bar.pack_propagate(False)
        
        self.sel_lbl = ctk.CTkLabel(self.bottom_bar, text="0 selecionados de 0", text_color=WHITE, font=ctk.CTkFont(size=14, weight="bold"))
        self.sel_lbl.pack(side="left", padx=24)
        
        ctk.CTkButton(self.bottom_bar, text="Importar para o corpus", fg_color=RED, text_color=WHITE, hover_color="#b82611", corner_radius=0, border_width=0, font=ctk.CTkFont(weight="bold"), command=self._show_summary_and_import).pack(side="right", padx=24)
        
        self.cards = []
        self.page = 0
        self.page_size = 25
        self.load_more_btn = ctk.CTkButton(self.feed, text="Carregar mais", fg_color=WHITE, text_color=INK, hover_color="#EEEEEE", border_width=2, border_color=INK, corner_radius=0, command=self._render_page)

    def load_results(self, records: List[dict], count_trail: str):
        self.records = records
        self.filtered_indices = list(range(len(records)))
        self.selected_indices = set(self.filtered_indices)
        
        langs = Counter([r.get('language') for r in records if r.get('language')]).most_common(3)
        lang_str = " · ".join(f"{l.upper()}: {c}" for l, c in langs) if langs else "Sem idioma detectado"
        self.trail_lbl.configure(text=f"{count_trail} | Idiomas: {lang_str}")
        
        self._build_sidebar()
        self._clear_feed()
        self.page = 0
        self._render_page()
        self._update_bottom_bar()

    def _build_sidebar(self):
        for widget in self.sidebar.winfo_children():
            widget.destroy()
            
        if not self.records:
            return
            
        # Filters logic
        self.filter_vars = {}
        
        # Year
        years = [r.get("year") for r in self.records if r.get("year")]
        if years:
            min_y, max_y = min(years), max(years)
            ctk.CTkLabel(self.sidebar, text="Ano de Publicação", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(8, 0))
            self.year_slider = ctk.CTkSlider(self.sidebar, from_=min_y, to=max_y, number_of_steps=max_y - min_y, command=self._apply_filters)
            self.year_slider.set(min_y)
            self.year_slider.pack(fill="x", pady=4)
            self.year_lbl = ctk.CTkLabel(self.sidebar, text=f"A partir de {min_y}")
            self.year_lbl.pack(anchor="w")
            
        # Open Access
        ctk.CTkLabel(self.sidebar, text="Acesso", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        self.oa_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.sidebar, text="Apenas Open Access", variable=self.oa_var, command=self._apply_filters, corner_radius=0).pack(anchor="w", pady=4)
        
        # Journals (Top 10)
        ctk.CTkLabel(self.sidebar, text="Principais Fontes", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        journals = [r.get("source") for r in self.records if r.get("source")]
        top_journals = Counter(journals).most_common(10)
        self.journal_vars = {}
        for j, c in top_journals:
            var = ctk.BooleanVar(value=True)
            self.journal_vars[j] = var
            cb = ctk.CTkCheckBox(self.sidebar, text=f"{j[:20]} ({c})", variable=var, command=self._apply_filters, corner_radius=0)
            cb.pack(anchor="w", pady=2)
            
        # Language
        ctk.CTkLabel(self.sidebar, text="Idioma", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        languages = [r.get("language") for r in self.records if r.get("language")]
        self.lang_var = ctk.StringVar(value="Todos")
        lang_options = ["Todos"] + [lang for lang, _ in Counter(languages).most_common()]
        ctk.CTkOptionMenu(self.sidebar, variable=self.lang_var, values=lang_options, command=self._apply_filters, corner_radius=0).pack(fill="x", pady=4)
        
        # Opções de Importação
        ctk.CTkLabel(self.sidebar, text="Importação", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        self.dedup_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.sidebar, text="Fuzzy Deduplicate", variable=self.dedup_var, corner_radius=0).pack(anchor="w", pady=4)
        
    def _apply_filters(self, *args):
        if hasattr(self, "year_slider"):
            y = int(self.year_slider.get())
            self.year_lbl.configure(text=f"A partir de {y}")
        else:
            y = 0
            
        oa_only = self.oa_var.get() if hasattr(self, "oa_var") else False
        allowed_journals = {j for j, v in self.journal_vars.items() if v.get()} if hasattr(self, "journal_vars") else set()
        sel_lang = self.lang_var.get() if hasattr(self, "lang_var") else "Todos"
        
        new_filtered = []
        for i, r in enumerate(self.records):
            if hasattr(self, "year_slider") and r.get("year", 0) < y:
                continue
            if oa_only and not r.get("is_oa"):
                continue
            if hasattr(self, "journal_vars") and r.get("source") in self.journal_vars and r.get("source") not in allowed_journals:
                continue
            if sel_lang != "Todos" and r.get("language") != sel_lang:
                continue
            new_filtered.append(i)
            
        # Update selection: uncheck non-matching
        for i in self.filtered_indices:
            if i not in new_filtered and i in self.selected_indices:
                self.selected_indices.remove(i)
                
        self.filtered_indices = new_filtered
        self._clear_feed()
        self.page = 0
        self._render_page()
        self._update_bottom_bar()

    def _clear_feed(self):
        for c in self.cards:
            c.destroy()
        self.cards.clear()
        self.load_more_btn.pack_forget()
        
    def _render_page(self):
        start = self.page * self.page_size
        end = start + self.page_size
        indices = self.filtered_indices[start:end]
        
        self.load_more_btn.pack_forget()
        
        for i in indices:
            r = self.records[i]
            card = ArticleCard(self.feed, r, self._on_card_toggle, i)
            card.pack(fill="x", pady=4)
            card.set_selected(i in self.selected_indices)
            self.cards.append(card)
            
        self.page += 1
        if end < len(self.filtered_indices):
            self.load_more_btn.pack(pady=12)
            
    def _on_card_toggle(self, selected: bool, index: int):
        if selected:
            self.selected_indices.add(index)
        else:
            self.selected_indices.discard(index)
        self._update_bottom_bar()
        
    def _update_bottom_bar(self):
        self.sel_lbl.configure(text=f"{len(self.selected_indices)} selecionados de {len(self.records)}")
        
    def _show_summary_and_import(self):
        selected_records = [self.records[i] for i in sorted(list(self.selected_indices))]
        if not selected_records:
            return
            
        years = [r.get("year") for r in selected_records if r.get("year")]
        yr_range = f"{min(years)} - {max(years)}" if years else "N/A"
        
        # Summary Dialog
        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirmar Importação")
        dlg.geometry("400x300")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        
        ctk.CTkLabel(dlg, text="Resumo da Importação", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=16)
        
        frame = ctk.CTkFrame(dlg, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24)
        
        ctk.CTkLabel(frame, text=f"Total a importar: {len(selected_records)}", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=4)
        ctk.CTkLabel(frame, text=f"Período: {yr_range}").pack(anchor="w", pady=4)
        
        def on_confirm():
            dlg.destroy()
            do_dedup = getattr(self, "dedup_var", ctk.BooleanVar(value=False)).get()
            self.on_import_confirm(selected_records, do_dedup)
            
        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", pady=16, padx=24)
        ctk.CTkButton(btns, text="Voltar", fg_color=WHITE, text_color=INK, border_width=2, border_color=INK, command=dlg.destroy).pack(side="left", expand=True, padx=4)
        ctk.CTkButton(btns, text="Confirmar", fg_color=RED, text_color=WHITE, command=on_confirm).pack(side="right", expand=True, padx=4)
