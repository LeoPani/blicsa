import sys
import customtkinter as ctk

# ── Color Definitions ─────────────────────────────────────────────────────────
SIDEBAR_BG  = ("#e6e6fa", "#0f0f1a")
CONTENT_BG  = ("#f0f2f5", "#13131f")
CARD_BG     = ("#ffffff", "#1a1a2e")
CARD2_BG    = ("#eef0f6", "#0d0d1f")
ACCENT      = "#D4A017"
ACCENT_HOV  = "#b88a10"
TEXT_MUTED  = ("#555566", "#888899")
GREEN       = "#1a7a4a"
GREEN_HOV   = "#145c38"
PURPLE      = "#7c3aed"
PURPLE_HOV  = "#5b21b6"
TEAL        = "#0e7490"
TEAL_HOV    = "#0c5f76"

def get_color(color_val):
    if isinstance(color_val, tuple):
        mode = ctk.get_appearance_mode().lower()
        return color_val[0] if mode == "light" else color_val[1]
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
