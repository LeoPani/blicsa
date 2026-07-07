import re

with open('main.py', 'r') as f:
    c = f.read()

SETTINGS = """
    def _show_settings(self):
        import tkinter as tk
        from PIL import Image, ImageTk
        
        dlg = tk.Toplevel(self)
        dlg.title(t("menu_settings"))
        dlg.geometry("400x300")
        dlg.configure(bg="#F6F4EE")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.eval('tk::PlaceWindow %s center' % dlg.winfo_toplevel())
        
        f = tk.Frame(dlg, bg="#141414")
        f.pack(fill="both", expand=True)
        content = tk.Frame(f, bg="#F6F4EE")
        content.pack(fill="both", expand=True, padx=3, pady=3)
        
        tk.Label(content, text=t("menu_settings"), font=("Arial", 16, "bold"), bg="#F6F4EE", fg="#141414").pack(pady=(20, 10))
        
        # Animations toggle
        import os, json
        s_path = os.path.join(os.path.dirname(__file__), ".blicsa_settings.json")
        reduce = False
        if os.path.exists(s_path):
            try: reduce = json.load(open(s_path)).get("reduce_animations", False)
            except: pass
            
        import customtkinter as ctk
        var = ctk.BooleanVar(value=reduce)
        def toggle():
            s = {}
            if os.path.exists(s_path):
                try: s = json.load(open(s_path))
                except: pass
            s["reduce_animations"] = var.get()
            json.dump(s, open(s_path, "w"))
            
        chk = ctk.CTkCheckBox(content, text=t("reduce_animations"), variable=var, command=toggle, text_color="#141414", fg_color="#DF3117", hover_color="#B82813", corner_radius=0)
        chk.pack(pady=10)
        
        # Flags
        flag_f = tk.Frame(content, bg="#F6F4EE")
        flag_f.pack(pady=10)
        def set_l(l):
            from core.i18n import set_lang
            set_lang(l)
            import tkinter.messagebox as mb
            mb.showinfo("Blicsa", "Language changed. Please restart the app.")
            
        try:
            for i, (l, f_name) in enumerate([("pt_BR", "flag-pt-br.png"), ("en", "flag-en.png"), ("fr", "flag-fr.png")]):
                img = ImageTk.PhotoImage(Image.open(f"assets/branding/{f_name}").resize((32, 22)))
                btn = tk.Button(flag_f, image=img, command=lambda x=l: set_l(x), bg="#F6F4EE", relief="flat", bd=2, highlightbackground="#141414")
                btn.image = img
                btn.grid(row=0, column=i, padx=5)
        except:
            pass
            
        close = tk.Button(content, text="OK", command=dlg.destroy, bg="#DF3117", fg="white", relief="flat", highlightbackground="#141414", bd=2)
        close.pack(side="bottom", pady=20)
"""

if "def _show_settings" not in c:
    c = c.replace("def _show_about", SETTINGS + "\n    def _show_about")

# Add Settings button to sidebar
if "self._settings_btn = ctk.CTkButton" not in c:
    c = c.replace(
        'self._theme_btn.grid(row=9, column=0, padx=16, pady=(10, 10), sticky="ew")',
        'self._theme_btn.grid(row=9, column=0, padx=16, pady=(10, 5), sticky="ew")\n        self._settings_btn = ctk.CTkButton(sb, text="⚙️ " + t("menu_settings"), font=ctk.CTkFont(size=11), fg_color="transparent", hover_color="#e0e0e0", text_color=INK, corner_radius=0, height=32, border_width=1, border_color=INK, command=self._show_settings)\n        self._settings_btn.grid(row=10, column=0, padx=16, pady=(0, 10), sticky="ew")'
    )
    # Also adjust grid row of _status_square and _status_lbl
    c = c.replace('row=10, column=0, padx=(16, 0), pady=(0, 2)', 'row=11, column=0, padx=(16, 0), pady=(0, 2)')
    c = c.replace('row=10, column=0, padx=(32, 16), pady=(0, 2)', 'row=11, column=0, padx=(32, 16), pady=(0, 2)')
    c = c.replace('row=11, column=0, padx=16, pady=(0, 8)', 'row=12, column=0, padx=16, pady=(0, 8)')
    c = c.replace('row=12, column=0, padx=22, pady=(0, 16)', 'row=13, column=0, padx=22, pady=(0, 16)')

with open('main.py', 'w') as f:
    f.write(c)
