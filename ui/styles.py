import logging
import customtkinter as ctk

# ── Brand v2 Palette ────────────────────────────────────────────────────────
PAPER  = "#F6F4EE"
INK    = "#141414"
RED    = "#DF3117"
BLUE   = "#1E4DA0"
YELLOW = "#F5BE00"
MUTED  = "#8A877F"

# UI mapping
SIDEBAR_BG  = PAPER
CONTENT_BG  = PAPER
CARD_BG     = PAPER
CARD2_BG    = PAPER
TEXT_MUTED  = MUTED
ACCENT      = RED
ACCENT_HOV  = "#B82813"

def get_color(color_val):
    if isinstance(color_val, tuple):
        return color_val[0]
    return color_val

class TextboxLogHandler(logging.Handler):
    """Alimenta o log box da UI via logging — sys.stdout/stderr ficam INTACTOS
    (tracebacks continuam aparecendo no terminal)."""

    def __init__(self, widget: ctk.CTkTextbox):
        super().__init__()
        self._w = widget
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            self._w.after(0, self._append, self.format(record) + "\n")
        except Exception:
            pass

    def _append(self, msg: str):
        try:
            if not self._w.winfo_exists():
                return
            self._w.configure(state="normal")
            self._w.insert("end", msg)
            self._w.see("end")
            self._w.configure(state="disabled")
        except Exception:
            pass
INK_HOV = "#2a2a2a"
BLUE_HOV = "#153a60"
YELLOW_HOV = "#d4a017"
RED_HOV = "#B82813"
