import customtkinter as ctk

FIELD_MAP = {
    "Título, Resumo e Palavras": "TITLE-ABS-KEY",
    "Apenas Título": "TITLE",
    "Nome do Autor": "AUTHOR",
    "Ano de Publicação": "YEAR"
}
INV_FIELD_MAP = {v: k for k, v in FIELD_MAP.items()}

class QueryBuilderDialog(ctk.CTkToplevel):
    def __init__(self, master, on_submit, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.title("Construtor de Busca Avançada")
        self.geometry("750x580")
        self.on_submit = on_submit
        
        self.rows = []
        
        # --- Header ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(header_frame, text="Busca Avançada (Padrão Scopus)", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header_frame, text="Combine múltiplos campos para refinar os resultados e remover falsos-positivos da pesquisa.", 
                     text_color=("gray40", "gray70"), font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(2, 0))
        
        # --- Main Rules Area ---
        self.main_frame = ctk.CTkScrollableFrame(self, fg_color=("gray95", "gray15"))
        self.main_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        # --- Bottom Area ---
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.pack(fill="x", padx=15, pady=(5, 5))
        
        self.add_btn = ctk.CTkButton(self.bottom_frame, text="+ Adicionar Regra", fg_color="#1f538d", hover_color="#14375e", width=140, command=self.add_row)
        self.add_btn.pack(side="left")
        
        # --- Live Preview ---
        preview_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray10"))
        preview_frame.pack(fill="x", padx=15, pady=(5, 15))
        
        ctk.CTkLabel(preview_frame, text="Pré-visualização da Query:", font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray30", "gray60")).pack(anchor="w", padx=10, pady=(5, 0))
        
        self.preview_lbl = ctk.CTkLabel(preview_frame, text="", font=ctk.CTkFont(family="Courier", size=13), text_color=("#1f538d", "#639dda"), wraplength=700, justify="left")
        self.preview_lbl.pack(fill="x", padx=10, pady=(2, 10), anchor="w")
        
        # --- Submit ---
        self.submit_btn = ctk.CTkButton(self.bottom_frame, text="Aplicar Filtros 🔍", fg_color="#2A9D8F", hover_color="#21867a", width=160, font=ctk.CTkFont(weight="bold"), command=self.submit)
        self.submit_btn.pack(side="right")
        
        # Add initial rows
        self.add_row(initial_field="Título, Resumo e Palavras")
        self.add_row(initial_field="Apenas Título", hide_if_first=True)
        
        self._update_preview()
        
    def add_row(self, initial_field="Título, Resumo e Palavras", hide_if_first=False):
        row_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=6)
        
        logic_var = ctk.StringVar(value="AND")
        logic_menu = ctk.CTkOptionMenu(
            row_frame, values=["AND", "OR", "AND NOT"], 
            variable=logic_var, width=90,
            command=lambda _: self._update_preview()
        )
        
        # Only show AND/OR/NOT for rows after the first
        if len(self.rows) > 0:
            logic_menu.pack(side="left", padx=(0, 10))
        else:
            # Dummy space for alignment
            ctk.CTkLabel(row_frame, text=" ONDE ", width=90, font=ctk.CTkFont(weight="bold"), text_color=("gray50", "gray60")).pack(side="left", padx=(0, 10))
        
        field_var = ctk.StringVar(value=initial_field)
        field_menu = ctk.CTkOptionMenu(
            row_frame, 
            values=list(FIELD_MAP.keys()), 
            variable=field_var, 
            width=200,
            command=lambda _: self._update_preview()
        )
        field_menu.pack(side="left", padx=(0, 10))
        
        entry = ctk.CTkEntry(row_frame, placeholder_text="Ex: machine learning, artificial intelligence...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        entry.bind("<KeyRelease>", lambda e: self._update_preview())
        
        del_btn = ctk.CTkButton(row_frame, text="✕", width=35, fg_color="#E63946", hover_color="#C12B37", command=lambda f=row_frame: self.remove_row(f))
        
        if len(self.rows) > 0:
            del_btn.pack(side="left")
        else:
            # Add a dummy disabled button to maintain alignment for the first row
            dummy_btn = ctk.CTkButton(row_frame, text="", width=35, fg_color="transparent", hover=False, state="disabled")
            dummy_btn.pack(side="left")
        
        self.rows.append({
            "frame": row_frame,
            "logic": logic_var,
            "field": field_var,
            "entry": entry
        })
        self._update_preview()
        
    def remove_row(self, frame):
        for row in self.rows:
            if row["frame"] == frame:
                self.rows.remove(row)
                frame.destroy()
                break
        self._update_preview()
                
    def _build_query_string(self):
        query_parts = []
        for i, row in enumerate(self.rows):
            val = row["entry"].get().strip()
            if not val: 
                continue
            
            friendly_field = row["field"].get()
            field = FIELD_MAP.get(friendly_field, "TITLE-ABS-KEY")
            logic = row["logic"].get()
            
            # format as TITLE("...")
            if " " in val and not val.startswith('"'):
                part = f'{field}("{val}")'
            else:
                part = f'{field}({val})'
            
            if len(query_parts) > 0:
                query_parts.append(logic)
                
            query_parts.append(part)
            
        return " ".join(query_parts)
        
    def _update_preview(self):
        q = self._build_query_string()
        if not q:
            self.preview_lbl.configure(text="[ Digite um termo acima para iniciar ]", text_color=("gray50", "gray50"))
        else:
            self.preview_lbl.configure(text=q, text_color=("#1f538d", "#639dda"))

    def submit(self):
        final_query = self._build_query_string()
        if final_query:
            self.on_submit(final_query)
        self.destroy()

def show_query_builder(parent, callback):
    dialog = QueryBuilderDialog(parent, callback)
    dialog.focus()
