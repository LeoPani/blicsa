import os
import sys
import time
import threading
from PIL import ImageGrab
import subprocess

def dump_widget_tree(widget, file, indent=0):
    try:
        geom = widget.winfo_geometry()
        w_class = widget.winfo_class()
        file.write(f"{'  ' * indent}{w_class} {geom}\n")
    except Exception:
        pass
    for child in widget.winfo_children():
        dump_widget_tree(child, file, indent + 1)

def capture_screen(app, phase, screen_name, delay=2.0):
    def _capture():
        time.sleep(delay)
        os.makedirs("docs/evidence", exist_ok=True)
        try:
            # Attempt to screenshot
            x = app.winfo_rootx()
            y = app.winfo_rooty()
            w = app.winfo_width()
            h = app.winfo_height()
            img = ImageGrab.grab(bbox=(x, y, x+w, y+h))
            img.save(f"docs/evidence/{phase}_{screen_name}.png")
            print(f"Captured screenshot for {phase}_{screen_name}")
        except Exception as e:
            print(f"Screenshot failed: {e}. Falling back to widget dump.")
            with open(f"docs/evidence/{phase}_{screen_name}.txt", "w") as f:
                dump_widget_tree(app, f)
            print(f"Dumped widget tree for {phase}_{screen_name}")
        app.quit()
    threading.Thread(target=_capture, daemon=True).start()

if __name__ == "__main__":
    if sys.platform.startswith("linux") and "DISPLAY" not in os.environ and "XVFB_RUN_CALLED" not in os.environ:
        print("Linux without DISPLAY detected. Re-running under xvfb-run...")
        os.environ["XVFB_RUN_CALLED"] = "1"
        sys.exit(subprocess.call(["xvfb-run", "-a", sys.executable] + sys.argv))

    import importlib.util
    spec = importlib.util.spec_from_file_location("main", "main.py")
    main_mod = importlib.util.module_from_spec(spec)
    sys.modules["main"] = main_mod
    spec.loader.exec_module(main_mod)
    
    app = main_mod.BlicsaApp()
    
    phase = sys.argv[1] if len(sys.argv) > 1 else "phaseX"
    screen = sys.argv[2] if len(sys.argv) > 2 else "unknown"
    
    # Simple navigation logic if needed
    if screen == "corpus":
        app._switch_tab("corpus")
    elif screen == "analises":
        app._switch_tab("viz")
        
    capture_screen(app, phase, screen)
    app.mainloop()
