import re

with open("ui/search_feed.py", "r") as f:
    content = f.read()

# 1. Add PDF badge and Abrir DOI / Baixar PDF buttons to ArticleCard
badge_old = """        if record.get("is_oa"):
            ctk.CTkLabel(title_frame, text="OPEN ACCESS", fg_color="#7A9E7E", text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))"""

badge_new = """        if record.get("is_oa"):
            ctk.CTkLabel(title_frame, text="OPEN ACCESS", fg_color="#7A9E7E", text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            if record.get("oa_url"):
                ctk.CTkLabel(title_frame, text="PDF", fg_color="#DF3117", text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))"""

content = content.replace(badge_old, badge_new)

# Add "Abrir DOI" to ArticleCard
abstract_old = """        # Abstract
        abs_text = str(record.get("abstract", ""))
        if len(abs_text) > 200: abs_text = abs_text[:197] + "..."
        if abs_text:
            ctk.CTkLabel(self, text=abs_text, text_color="#555555", font=ctk.CTkFont(size=12), anchor="w", justify="left", wraplength=700).grid(row=3, column=2, padx=(4, 12), pady=(0, 12), sticky="w")"""

abstract_new = """        # Abstract
        abs_text = str(record.get("abstract", ""))
        if len(abs_text) > 200: abs_text = abs_text[:197] + "..."
        if abs_text:
            ctk.CTkLabel(self, text=abs_text, text_color="#555555", font=ctk.CTkFont(size=12), anchor="w", justify="left", wraplength=700).grid(row=3, column=2, padx=(4, 12), pady=(0, 4), sticky="w")
            
        actions_f = ctk.CTkFrame(self, fg_color="transparent")
        actions_f.grid(row=4, column=2, padx=(4, 12), pady=(0, 12), sticky="w")
        if not record.get("is_oa") and record.get("doi"):
            import webbrowser
            ctk.CTkButton(actions_f, text="Abrir DOI", width=80, height=24, fg_color="#EEEEEE", text_color=INK, command=lambda d=record.get("doi"): webbrowser.open(f"https://doi.org/{d}")).pack(side="left")"""

content = content.replace(abstract_old, abstract_new)

with open("ui/search_feed.py", "w") as f:
    f.write(content)
