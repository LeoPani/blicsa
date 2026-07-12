import re

with open("main.py", "r") as f:
    content = f.read()

hdr_old = """        ctk.CTkLabel(hdr, text="Seu Corpus", font=ctk.CTkFont(size=28, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text=f"{total_docs} documentos • {total_cites} citações totais", font=ctk.CTkFont(size=14), text_color=MUTED).grid(row=1, column=0, sticky="w")
        
        self._btn(hdr, "Ir para Análises", lambda: self._switch_tab("analises"), height=40, color=RED).grid(row=0, column=2, rowspan=2, sticky="e")"""

hdr_new = """        ctk.CTkLabel(hdr, text="Seu Corpus", font=ctk.CTkFont(size=28, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text=f"{total_docs} documentos • {total_cites} citações totais", font=ctk.CTkFont(size=14), text_color=MUTED).grid(row=1, column=0, sticky="w")
        
        btns_f = ctk.CTkFrame(hdr, fg_color="transparent")
        btns_f.grid(row=0, column=2, rowspan=2, sticky="e")
        self._btn(btns_f, "Baixar PDFs abertos", self._download_oa_pdfs, height=40, color="#1E4DA0").pack(side="left", padx=(0, 10))
        self._btn(btns_f, "Ir para Análises", lambda: self._switch_tab("analises"), height=40, color=RED).pack(side="left")"""

content = content.replace(hdr_old, hdr_new)

with open("main.py", "w") as f:
    f.write(content)
