import re

def clean_analises_drawer():
    with open('/Users/leopani/PyBibliomics/main.py', 'r') as f:
        content = f.read()

    # Find where the AI Drawer in analises tab starts
    start_str = "    # ── Legacy AI Drawer in Analises Tab ──"
    end_str = "    def _build_tab_corpus(self) -> ctk.CTkFrame:"
    
    idx_start = content.find(start_str)
    idx_end = content.find(end_str)
    
    if idx_start != -1 and idx_end != -1:
        # replace everything between start_str and end_str with just return f
        content = content[:idx_start] + "        return f\n\n" + content[idx_end:]
        
        with open('/Users/leopani/PyBibliomics/main.py', 'w') as f:
            f.write(content)
        print("Success")
    else:
        print("Failed to find boundaries")

if __name__ == "__main__":
    clean_analises_drawer()
