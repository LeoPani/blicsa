import re

def clean_main():
    with open('/Users/leopani/PyBibliomics/main.py', 'r') as f:
        content = f.read()
        
    # Remove _map_canvas references from _update_theme
    content = re.sub(
        r'        if self\._map_canvas:.*?(?=        if self\._thesaurus)',
        '',
        content,
        flags=re.DOTALL
    )
    
    # Remove _search_node body
    content = re.sub(
        r'    def _search_node\(self\):.*?    def _reset_view\(self\):',
        '    def _search_node(self):\n        pass\n\n    def _reset_view(self):',
        content,
        flags=re.DOTALL
    )
    
    # Remove _reset_view body
    content = re.sub(
        r'    def _reset_view\(self\):.*?    def _open_in_webview',
        '    def _reset_view(self):\n        pass\n\n    def _open_in_webview',
        content,
        flags=re.DOTALL
    )
    
    # In _build_tab_export, remove map export blocks
    content = re.sub(
        r'        self\._btn\(f_map, "💾  SVG \(Vetor\)", lambda: export\("svg"\)\)\.pack\(side="left", padx=4\)\n        self\._btn\(f_map, "💾  PNG \(Alta Res\)", lambda: export\("png"\)\)\.pack\(side="left", padx=4\)\n        self\._btn\(f_map, "💾  PDF", lambda: export\("pdf"\)\)\.pack\(side="left", padx=4\)',
        '        ctk.CTkLabel(f_map, text="Use a visualização interativa do mapa para salvar as imagens.\\nAs ferramentas do Plotly oferecem download nativo em PNG.").pack(pady=10)',
        content,
        flags=re.DOTALL
    )
    
    # Remove the inner export function in _build_tab_export
    content = re.sub(
        r'        def export\(fmt\):.*?            export_figure_image\(self\._map_canvas\.figure, path, dpi=300\)',
        '',
        content,
        flags=re.DOTALL
    )
    
    # Remove cluster label update from _auto_label_clusters
    content = re.sub(
        r'            if self\._map_canvas:.*?                \)\)',
        '',
        content,
        flags=re.DOTALL
    )

    with open('/Users/leopani/PyBibliomics/main.py', 'w') as f:
        f.write(content)

if __name__ == "__main__":
    clean_main()
