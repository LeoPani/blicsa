import re

with open("ui/search_feed.py", "r") as f:
    content = f.read()

# 1. Modify ArticleCard.__init__ to show duplicates
card_init_old = """        title = str(record.get("title", "Sem título"))
        ctk.CTkLabel(self, text=title, text_color=BLUE, font=ctk.CTkFont(size=14, weight="bold"), anchor="w", justify="left", wraplength=700).grid(row=1, column=2, padx=(4, 12), pady=0, sticky="w")"""

card_init_new = """        if record.get("is_duplicate"):
            ctk.CTkLabel(title_frame, text=str(record.get("dup_reason", "Duplicado")).upper(), fg_color=RED, text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))

        title = str(record.get("title", "Sem título"))
        ctk.CTkLabel(self, text=title, text_color=BLUE if not record.get("is_duplicate") else "#999999", font=ctk.CTkFont(size=14, weight="bold"), anchor="w", justify="left", wraplength=700).grid(row=1, column=2, padx=(4, 12), pady=0, sticky="w")"""

content = content.replace(card_init_old, card_init_new)

# 2. Modify load_results to uncheck duplicates
load_res_old = """    def load_results(self, records: List[dict], count_trail: str):
        self.records = records
        self.filtered_indices = list(range(len(records)))
        self.selected_indices = set(self.filtered_indices)"""

load_res_new = """    def load_results(self, records: List[dict], count_trail: str):
        self.records = records
        self.filtered_indices = list(range(len(records)))
        self.selected_indices = {i for i, r in enumerate(records) if not r.get("is_duplicate")}"""

content = content.replace(load_res_old, load_res_new)

# 3. Add Type filter in _build_sidebar
build_sb_old = """        # Language
        ctk.CTkLabel(self.sidebar, text="Idioma", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))"""

build_sb_new = """        # Type
        ctk.CTkLabel(self.sidebar, text="Tipo", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        types = [r.get("type", "unknown") for r in self.records if r.get("type")]
        self.type_var = ctk.StringVar(value="Todos")
        type_options = ["Todos"] + [t for t, _ in Counter(types).most_common()]
        ctk.CTkOptionMenu(self.sidebar, variable=self.type_var, values=type_options, command=self._apply_filters, corner_radius=0).pack(fill="x", pady=4)

        # Language
        ctk.CTkLabel(self.sidebar, text="Idioma", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))"""

content = content.replace(build_sb_old, build_sb_new)

# 4. Add Type filter in _apply_filters
apply_flt_old = """        sel_lang = self.lang_var.get() if hasattr(self, "lang_var") else "Todos"
        
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
            new_filtered.append(i)"""

apply_flt_new = """        sel_lang = self.lang_var.get() if hasattr(self, "lang_var") else "Todos"
        sel_type = self.type_var.get() if hasattr(self, "type_var") else "Todos"
        
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
            if sel_type != "Todos" and r.get("type", "unknown") != sel_type:
                continue
            new_filtered.append(i)"""

content = content.replace(apply_flt_old, apply_flt_new)

with open("ui/search_feed.py", "w") as f:
    f.write(content)
