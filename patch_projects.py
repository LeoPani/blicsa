import re
import os

with open("main.py", "r") as f:
    content = f.read()

# 1. Add "projects" to sidebar tabs
nav_list_old = """        for i, (key, icon_name, label_text) in enumerate([
            ("home",    "sparkle", "Blink Research"),
            ("import",  "download", "Coleta de Dados"),
            ("corpus",  "database", "Corpus"),
            ("analises","pie-chart", "Análises"),
            ("viz",     "map", "Mapa"),
            ("stats",   "settings", "Ajustes")
        ]):"""

nav_list_new = """        for i, (key, icon_name, label_text) in enumerate([
            ("home",    "sparkle", "Blink Research"),
            ("projects","folder", "Meus Projetos"),
            ("import",  "download", "Coleta de Dados"),
            ("corpus",  "database", "Corpus"),
            ("analises","pie-chart", "Análises"),
            ("viz",     "map", "Mapa"),
            ("stats",   "settings", "Ajustes")
        ]):"""

content = content.replace(nav_list_old, nav_list_new)

# 2. Add projects to self._tabs
tabs_old = """        self._tabs = {
            "home":     self._build_tab_home(),
            "import":   self._build_tab_import(),
            "review":   self._build_tab_review(),
            "viz":      self._build_tab_viz(),
            "stats":    self._build_tab_stats(),
            "analises": self._build_tab_analises(),
            "gallery":  self._build_tab_gallery(),
            "corpus":   self._build_tab_corpus()
        }"""

tabs_new = """        self._tabs = {
            "home":     self._build_tab_home(),
            "projects": self._build_tab_projects(),
            "import":   self._build_tab_import(),
            "review":   self._build_tab_review(),
            "viz":      self._build_tab_viz(),
            "stats":    self._build_tab_stats(),
            "analises": self._build_tab_analises(),
            "gallery":  self._build_tab_gallery(),
            "corpus":   self._build_tab_corpus()
        }"""

content = content.replace(tabs_old, tabs_new)

# 3. Add self._searches = [] in __init__
init_old = """        self._positions = None
        
        self.update_idletasks()"""

init_new = """        self._positions = None
        self._searches = []
        
        self.update_idletasks()"""
content = content.replace(init_old, init_new)

# 4. _build_tab_projects
build_proj = """    def _build_tab_projects(self) -> ctk.CTkFrame:
        from ui.projects_view import ProjectsView
        frame = ctk.CTkFrame(self._main_content, fg_color="transparent")
        
        def on_open_project(path):
            self.after(0, lambda: self._load_project_file(path))
            
        self._projects_view = ProjectsView(frame, on_open_project)
        self._projects_view.pack(fill="both", expand=True)
        return frame
        
    def _build_tab_import"""

content = content.replace("    def _build_tab_import", build_proj)

with open("main.py", "w") as f:
    f.write(content)
