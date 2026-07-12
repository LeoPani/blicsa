"""
SearchPanel — Coletar redesenhada, estilo Scopus/WoS (só OpenAlex):
busca avançada por campo + filtros → resultados PAGINADOS server-side (rápidos, nada
baixado) → "Formar corpus" dispara a colheita (on_harvest). Cada página substitui a anterior.
"""
import threading
import customtkinter as ctk
from typing import Callable

from ui.search_feed import ArticleCard

PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
WHITE = "#FFFFFF"
MUTED = "#8A877F"

FIELDS = [("Tudo", "all"), ("Título", "title"), ("Autor", "author"), ("Abstract", "abstract")]
_FIELD_LABEL_TO_KEY = {lbl: key for lbl, key in FIELDS}


class SearchPanel(ctk.CTkFrame):
    def __init__(self, master, on_harvest: Callable[[str, dict, int], None]):
        super().__init__(master, fg_color=PAPER, corner_radius=0)
        self.on_harvest = on_harvest
        self.page = 1
        self.per_page = 25
        self.total = 0
        self._busy = False
        self._rows = []  # (field_var, entry)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---- Busca avançada ----
        form = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        form.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        form.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(form, text="Busca avançada", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=INK).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self.rows_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.rows_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12)
        self.rows_frame.grid_columnconfigure(1, weight=1)
        self._add_row(first=True)
        self._add_row()

        ctk.CTkButton(form, text="+ campo", width=80, height=26, corner_radius=0, fg_color=PAPER,
                      text_color=INK, border_width=1, border_color=INK, command=self._add_row
                      ).grid(row=2, column=0, sticky="w", padx=12, pady=(2, 6))

        # filtros
        fl = ctk.CTkFrame(form, fg_color="transparent")
        fl.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        ctk.CTkLabel(fl, text="Ano:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.y0 = ctk.CTkEntry(fl, width=56, placeholder_text="de", placeholder_text_color=MUTED,
                               fg_color=WHITE, text_color=INK, corner_radius=0, border_width=1, border_color=INK)
        self.y0.pack(side="left", padx=4)
        self.y1 = ctk.CTkEntry(fl, width=56, placeholder_text="até", placeholder_text_color=MUTED,
                               fg_color=WHITE, text_color=INK, corner_radius=0, border_width=1, border_color=INK)
        self.y1.pack(side="left", padx=4)
        ctk.CTkLabel(fl, text="Tipo:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 2))
        self.type_var = ctk.StringVar(value="Todos")
        ctk.CTkOptionMenu(fl, variable=self.type_var, width=110, corner_radius=0, fg_color=WHITE,
                          text_color=INK, button_color=INK,
                          values=["Todos", "article", "review", "book-chapter", "dataset"]).pack(side="left", padx=4)
        self.oa_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(fl, text="OA", variable=self.oa_var, width=20, corner_radius=0).pack(side="left", padx=(10, 4))
        ctk.CTkLabel(fl, text="Idioma:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 2))
        self.lang_var = ctk.StringVar(value="Todos")
        ctk.CTkOptionMenu(fl, variable=self.lang_var, width=70, corner_radius=0, fg_color=WHITE,
                          text_color=INK, button_color=INK,
                          values=["Todos", "en", "pt", "es", "fr", "de"]).pack(side="left", padx=4)
        ctk.CTkLabel(fl, text="Ordenar:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 2))
        self.sort_var = ctk.StringVar(value="Relevância")
        ctk.CTkOptionMenu(fl, variable=self.sort_var, width=130, corner_radius=0, fg_color=WHITE,
                          text_color=INK, button_color=INK, command=lambda *_: self._on_sort(),
                          values=["Relevância", "Mais citados", "Mais recentes"]).pack(side="left", padx=4)
        ctk.CTkButton(fl, text="🔍 Pesquisar", height=30, corner_radius=0, fg_color=RED,
                      text_color=WHITE, border_width=2, border_color=INK,
                      command=self.do_search).pack(side="right", padx=4)

        # ---- Cabeçalho de contagem ----
        self.count_lbl = ctk.CTkLabel(self, text="Monte a busca e clique Pesquisar (nada é baixado ainda).",
                                      font=ctk.CTkFont(size=14, weight="bold"), text_color=INK)
        self.count_lbl.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 4))

        # ---- Resultados (uma página) ----
        self.results = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results.grid(row=2, column=0, sticky="nsew", padx=16, pady=4)
        self.results.grid_columnconfigure(0, weight=1)

        # ---- Rodapé: paginação + formar corpus ----
        self.bar = bar = ctk.CTkFrame(self, fg_color=INK, corner_radius=0, height=54)
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_propagate(False)
        self.prev_btn = ctk.CTkButton(bar, text="◀", width=44, corner_radius=0, fg_color=WHITE,
                                      text_color=INK, command=self.prev_page)
        self.prev_btn.pack(side="left", padx=(16, 4), pady=8)
        self.page_lbl = ctk.CTkLabel(bar, text="—", text_color=WHITE, font=ctk.CTkFont(size=13, weight="bold"))
        self.page_lbl.pack(side="left", padx=8)
        self.next_btn = ctk.CTkButton(bar, text="▶", width=44, corner_radius=0, fg_color=WHITE,
                                      text_color=INK, command=self.next_page)
        self.next_btn.pack(side="left", padx=4)
        self.harvest_btn = ctk.CTkButton(bar, text="Formar corpus", corner_radius=0, fg_color=RED,
                                         text_color=WHITE, font=ctk.CTkFont(weight="bold"),
                                         command=self._harvest)
        self.harvest_btn.pack(side="right", padx=16)

    def _add_row(self, first=False):
        i = len(self._rows)
        row = ctk.CTkFrame(self.rows_frame, fg_color="transparent")
        row.grid(row=i, column=0, columnspan=2, sticky="ew", pady=2)
        row.grid_columnconfigure(1, weight=1)
        if not first:
            ctk.CTkLabel(row, text="E", font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=MUTED, width=18).grid(row=0, column=0, padx=(0, 4))
        else:
            ctk.CTkLabel(row, text="   ", width=18).grid(row=0, column=0, padx=(0, 4))
        fvar = ctk.StringVar(value=FIELDS[0][0] if first else "Título")
        ctk.CTkOptionMenu(row, variable=fvar, width=100, corner_radius=0, fg_color=WHITE,
                          text_color=INK, button_color=INK,
                          values=[lbl for lbl, _ in FIELDS]).grid(row=0, column=2, padx=(0, 6))
        ent = ctk.CTkEntry(row, placeholder_text="termo…", placeholder_text_color=MUTED,
                           fg_color=WHITE, text_color=INK, height=32, corner_radius=0,
                           border_width=1, border_color=INK)
        ent.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ent.bind("<Return>", lambda e: self.do_search())
        self._rows.append((fvar, ent))

    # ---- construção de filtros ----
    def _sort_value(self):
        return {"Relevância": "relevance", "Mais citados": "citations",
                "Mais recentes": "date"}.get(self.sort_var.get(), "relevance")

    def _build_filters(self) -> dict:
        f = {"fields": [], "sort": self._sort_value()}
        for fvar, ent in self._rows:
            v = ent.get().strip()
            if v:
                f["fields"].append((_FIELD_LABEL_TO_KEY.get(fvar.get(), "all"), v))
        if self.y0.get().strip():
            f["year_start"] = self.y0.get().strip()
        if self.y1.get().strip():
            f["year_end"] = self.y1.get().strip()
        if self.type_var.get() != "Todos":
            f["type"] = self.type_var.get()
        if self.oa_var.get():
            f["is_oa"] = True
        if self.lang_var.get() != "Todos":
            f["language"] = self.lang_var.get()
        return f

    # ---- ações ----
    def do_search(self):
        self.page = 1
        self._refresh()

    def _on_sort(self):
        if self.total or any(e.get().strip() for _, e in self._rows):
            self.page = 1
            self._refresh()

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            self._refresh()

    def next_page(self):
        if self.page * self.per_page < min(self.total, 10000):
            self.page += 1
            self._refresh()

    def _harvest(self):
        if self.total == 0:
            return
        # Colhe o conjunto que bate a busca (query por campo). Só aqui baixa de fato.
        self.on_harvest("", self._build_filters(), self.total)

    def _refresh(self):
        if self._busy:
            return
        filters = self._build_filters()
        if not filters["fields"] and "year_start" not in filters and "year_end" not in filters:
            self.count_lbl.configure(text="Preencha ao menos um campo de busca.")
            return
        self._busy = True
        self.count_lbl.configure(text="Consultando…")
        page, per_page = self.page, self.per_page

        def worker():
            from core.sources import OpenAlexProvider
            err, recs, total = None, [], 0
            try:
                recs, total = OpenAlexProvider().browse("", filters, page=page, per_page=per_page)
            except Exception as e:
                err = str(e)
            self.after(0, lambda: self._render(recs, total, err))
        threading.Thread(target=worker, daemon=True).start()

    def _render(self, recs, total, err):
        self._busy = False
        for w in self.results.winfo_children():
            w.destroy()
        if err:
            self.count_lbl.configure(text=f"Erro: {err}")
            return
        self.total = total
        frm = (self.page - 1) * self.per_page + 1
        to = min(self.page * self.per_page, total)
        self.count_lbl.configure(
            text=(f"Encontrados {total:,}".replace(",", ".") +
                  f" · mostrando {frm}–{to} · nada baixado ainda") if total else "Nenhum resultado.")
        for i, r in enumerate(recs):
            ArticleCard(self.results, r, lambda *a, **k: None, i).pack(fill="x", pady=4)
        max_page = max(1, (min(total, 10000) + self.per_page - 1) // self.per_page)
        self.page_lbl.configure(text=f"pág {self.page}/{max_page}")
        self.harvest_btn.configure(text=f"Formar corpus ({total:,})".replace(",", ".") if total else "Formar corpus")
