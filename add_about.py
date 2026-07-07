import re

with open('main.py', 'r') as f:
    c = f.read()

ABOUT = """
    def _show_about(self):
        import tkinter as tk
        from PIL import Image
        import webbrowser
        
        dlg = tk.Toplevel(self)
        dlg.title(t("menu_about"))
        dlg.geometry("400x350")
        dlg.configure(bg="#F6F4EE")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.eval('tk::PlaceWindow %s center' % dlg.winfo_toplevel())
        
        # 3px ink border
        f = tk.Frame(dlg, bg="#141414")
        f.pack(fill="both", expand=True)
        content = tk.Frame(f, bg="#F6F4EE")
        content.pack(fill="both", expand=True, padx=3, pady=3)
        
        try:
            from PIL import ImageTk
            img = ImageTk.PhotoImage(Image.open("assets/branding/blicsa-logo-horizontal.png").resize((200, 54)))
            lbl = tk.Label(content, image=img, bg="#F6F4EE")
            lbl.image = img
            lbl.pack(pady=(20, 0))
        except:
            tk.Label(content, text="Blicsa", font=("Arial", 24, "bold"), bg="#F6F4EE", fg="#141414").pack(pady=(20, 0))
            
        tk.Label(content, text="just blink", font=("Arial", 12), bg="#F6F4EE", fg="#8A877F").pack(pady=(0, 10))
        tk.Label(content, text="v3.0", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        
        tk.Label(content, text="Desenvolvido por ICSA/UFOP", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        tk.Label(content, text="Licença MIT", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        
        btn_f = tk.Frame(content, bg="#F6F4EE")
        btn_f.pack(side="bottom", fill="x", pady=20, padx=20)
        
        gh = tk.Button(btn_f, text="GitHub", command=lambda: webbrowser.open("https://github.com"), bg="#F6F4EE", fg="#141414", relief="flat", highlightbackground="#141414", bd=2)
        gh.pack(side="left", padx=10)
        
        close = tk.Button(btn_f, text="OK", command=dlg.destroy, bg="#DF3117", fg="white", relief="flat", highlightbackground="#141414", bd=2)
        close.pack(side="right", padx=10)
"""

if "def _show_about" not in c:
    c = c.replace("def _set_idle", ABOUT + "\n    def _set_idle")

# Add about button to sidebar replacing the label
if "self._about_btn = ctk.CTkButton" not in c:
    c = re.sub(
        r'ctk\.CTkLabel\(sb, text="v3\.0  •  Blicsa Engine",\s*font=ctk\.CTkFont\(size=10\),\s*text_color=TEXT_MUTED\)\.grid\(\s*row=12, column=0, padx=22, pady=\(0, 16\), sticky="sw"\)',
        'self._about_btn = ctk.CTkButton(sb, text="v3.0 • Blicsa Engine", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED, fg_color="transparent", hover_color="#e0e0e0", corner_radius=0, command=self._show_about)\n        self._about_btn.grid(row=12, column=0, padx=22, pady=(0, 16), sticky="sw")',
        c
    )

with open('main.py', 'w') as f:
    f.write(c)
