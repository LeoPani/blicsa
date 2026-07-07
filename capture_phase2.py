import os
import tkinter as tk
from ui.search_feed import SearchFeedView

def run_app():
    root = tk.Tk()
    root.geometry("1000x800")
    
    records = [
        {"title": "Test 1", "abstract": "Abstract", "year": 2023, "source": "Nature", "language": "en", "is_oa": True, "authors": "John Doe", "citations": 5},
        {"title": "Test 2", "abstract": "Resumo", "year": 2022, "source": "Science", "language": "pt", "is_oa": False, "authors": "Jane Doe", "citations": 2}
    ]
    
    def on_import(recs, dedup):
        print("Imported", recs, dedup)
        
    def on_cancel():
        root.destroy()
        
    feed = SearchFeedView(root, on_import, on_cancel)
    feed.pack(fill="both", expand=True)
    feed.load_results(records, "Encontrados 2 · baixados 2 (limite 500) · após deduplicação 2")
    
    # Wait to render and take screenshot using Mac OS screencapture
    def screenshot():
        os.makedirs("docs/evidence", exist_ok=True)
        # Capture the window
        os.system('screencapture -l $(osascript -e \'tell app "System Events" to id of window 1 of process "Python"\') docs/evidence/fase2_idiomas.png')
        root.destroy()
        
    root.after(2000, screenshot)
    root.mainloop()

if __name__ == "__main__":
    run_app()
