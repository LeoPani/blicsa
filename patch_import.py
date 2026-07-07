import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# We want to replace everything from "def _build_tab_import(self) -> ctk.CTkFrame:" up to "def _build_tab_review(self) -> ctk.CTkFrame:"
start_str = "def _build_tab_import(self) -> ctk.CTkFrame:"
end_str = "def _build_tab_review(self) -> ctk.CTkFrame:"

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx == -1 or end_idx == -1:
    print("Could not find bounds.")
    exit(1)

new_method = """def _build_tab_import(self) -> ctk.CTkFrame:
        frame = self._tab()
        
        # Search Card (Top)
        scard = self._card(frame, 0)
        scard.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(scard, text="Busca Online", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")
            
        self._search_provider_var = ctk.StringVar(value="openalex")
        sp_f = ctk.CTkFrame(scard, fg_color="transparent")
        sp_f.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="w")
        for lbl, val in [("Todas as Bases", "all"), ("OpenAlex", "openalex"), ("Crossref", "crossref"), ("PubMed", "pubmed")]:
            ctk.CTkRadioButton(sp_f, text=lbl, variable=self._search_provider_var,
                               value=val, fg_color=ACCENT, hover_color=ACCENT_HOV).pack(side="left", padx=8)
                               
        self._search_query_entry = ctk.CTkEntry(scard, placeholder_text="Termo / Query (ex: 'deep learning')", height=36, fg_color=WHITE, text_color=INK)
        self._search_query_entry.grid(row=2, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        
        act_sf = ctk.CTkFrame(scard, fg_color="transparent")
        act_sf.grid(row=3, column=0, columnspan=2, padx=16, pady=(4, 16), sticky="e")
        
        ctk.CTkLabel(act_sf, text="Qtd:").pack(side="left", padx=4)
        self._search_max_entry = ctk.CTkEntry(act_sf, width=60, placeholder_text="100", fg_color=WHITE, text_color=INK)
        self._search_max_entry.insert(0, "100")
        self._search_max_entry.pack(side="left", padx=4)
        
        self._search_unlimited_var = ctk.BooleanVar(value=True)
        self._search_unlimited_chk = ctk.CTkCheckBox(act_sf, text="Ilimitado", variable=self._search_unlimited_var, width=50, 
                                                     command=lambda: self._search_max_entry.configure(state="disabled" if self._search_unlimited_var.get() else "normal"))
        self._search_unlimited_chk.pack(side="left", padx=4)
        self._search_max_entry.configure(state="disabled")
        
        self._btn(act_sf, "⚙ Avançada", self._open_query_builder, height=30).pack(side="left", padx=4)
        self._btn(act_sf, "🔍 Buscar", self._on_gui_search, height=30, color=RED, hover=RED_HOV).pack(side="left", padx=4)
        
        self._search_cancel_btn = self._btn(act_sf, "✕ Cancelar", self._cancel_search, height=30, color="#E63946", hover="#C12B37")
        self._search_cancel_btn.pack_forget() # Hide initially
        
        filter_f = ctk.CTkFrame(scard, fg_color="transparent")
        filter_f.grid(row=4, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        
        ctk.CTkLabel(filter_f, text="Ano Início:", font=ctk.CTkFont(size=12)).pack(side="left", padx=4)
        self._search_year_start = ctk.CTkEntry(filter_f, width=60, placeholder_text="Ex: 2018", fg_color=WHITE, text_color=INK)
        self._search_year_start.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Ano Fim:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_year_end = ctk.CTkEntry(filter_f, width=60, placeholder_text="Ex: 2024", fg_color=WHITE, text_color=INK)
        self._search_year_end.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Tipo de Doc:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_type_var = ctk.StringVar(value="Todos")
        self._search_type = ctk.CTkOptionMenu(filter_f, variable=self._search_type_var, fg_color=WHITE, text_color=INK, button_color=WHITE, button_hover_color=CARD2_BG,
                                              values=["Todos", "article", "review", "book-chapter", "dataset"], width=120)
        self._search_type.pack(side="left", padx=4)

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

"""

new_content = content[:start_idx] + new_method + content[end_idx:]

with open("main.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Patched main.py")
