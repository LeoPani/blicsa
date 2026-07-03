import sys
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

class LogWriter:
    def __init__(self, widget: ctk.CTkTextbox):
        self._w, self._orig = widget, sys.__stdout__

    def write(self, msg: str):
        self._w.after(0, self._append, msg)
        try:
            self._orig.write(msg)
        except Exception:
            pass

    def _append(self, msg: str):
        self._w.configure(state="normal")
        self._w.insert("end", msg)
        self._w.see("end")
        self._w.configure(state="disabled")

    def flush(self):
        pass
INK_HOV = "#2a2a2a"
BLUE_HOV = "#153a60"
YELLOW_HOV = "#d4a017"
RED_HOV = "#B82813"
