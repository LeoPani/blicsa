import os
import sys
import time

# Add root project path to pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import BlicsaApp
from PIL import ImageGrab

def capture_tabs():
    evidence_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'docs', 'evidence'))
    os.makedirs(evidence_dir, exist_ok=True)

    app = BlicsaApp()
    # In Xvfb, we can actually display the app
    app.update()
    
    # Wait for app to render
    time.sleep(2)
    
    tabs_to_capture = ["home", "import", "corpus", "analises", "export"]
    
    for tab in tabs_to_capture:
        # Switch tab
        app._switch_tab(tab)
        app.update()
        app.update_idletasks()
        time.sleep(1) # Let animations/rendering settle
        
        # Geometry for capturing the exact window area
        x = app.winfo_rootx()
        y = app.winfo_rooty()
        w = app.winfo_width()
        h = app.winfo_height()
        
        # Some OSes/Xvfb might have issues with ImageGrab bounding boxes, 
        # but this is standard procedure.
        try:
            screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            path = os.path.join(evidence_dir, f"{tab}.png")
            screenshot.save(path)
            print(f"Captured {tab} -> {path}")
        except Exception as e:
            print(f"Failed to capture {tab}: {e}")
            
    app.destroy()

if __name__ == "__main__":
    capture_tabs()
