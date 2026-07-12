import customtkinter as ctk
import os
import zipfile
import json
from pathlib import Path
from tkinter import messagebox, filedialog
import shutil
from PIL import Image
from core.i18n import t

PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
BLUE = "#1E4DA0"
WHITE = "#FFFFFF"

class ProjectCard(ctk.CTkFrame):
    def __init__(self, master, proj_path, on_open, on_rename, on_duplicate, on_delete):
        super().__init__(master, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.proj_path = proj_path
        self.on_open = on_open
        self.on_rename = on_rename
        self.on_duplicate = on_duplicate
        self.on_delete = on_delete
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        # Load details from zip
        manifest = {}
        config = {}
        searches = []
        df_count = 0
        has_thumbnail = False
        
        try:
            with zipfile.ZipFile(proj_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                if "dataset.json.gz" in zf.namelist():
                    import gzip
                    compressed_df = zf.read("dataset.json.gz")
                    df_json = gzip.decompress(compressed_df).decode("utf-8")
                    df_count = df_json.count('"title":') # quick estimation
                if "searches.json" in zf.namelist():
                    searches = json.loads(zf.read("searches.json").decode("utf-8"))
                if "thumbnail.png" in zf.namelist():
                    has_thumbnail = True
        except Exception:
            pass
            
        # Left side: Thumbnail
        self.thumb_frame = ctk.CTkFrame(self, width=120, height=120, fg_color="#E0E0E0", corner_radius=0, border_width=2, border_color=INK)
        self.thumb_frame.grid(row=0, column=0, rowspan=4, padx=12, pady=12, sticky="nsew")
        self.thumb_frame.pack_propagate(False)
        
        if has_thumbnail:
            try:
                import io
                with zipfile.ZipFile(proj_path, "r") as zf:
                    img_data = zf.read("thumbnail.png")
                    img = Image.open(io.BytesIO(img_data))
                    ctk_img = ctk.CTkImage(light_image=img, size=(116, 116))
                    ctk.CTkLabel(self.thumb_frame, text="", image=ctk_img).pack(expand=True, fill="both")
            except Exception:
                ctk.CTkLabel(self.thumb_frame, text=t("projects.card_map"), text_color=INK, font=ctk.CTkFont(weight="bold")).pack(expand=True)
        else:
            ctk.CTkLabel(self.thumb_frame, text=t("projects.card_no_map"), text_color="#999999", font=ctk.CTkFont(weight="bold")).pack(expand=True)

        # Info
        name = Path(proj_path).stem
        date = manifest.get("saved_at", t("projects.date_unknown"))

        ctk.CTkLabel(self, text=name, text_color=BLUE, font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=1, sticky="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(self, text=t("projects.card_updated", date=date), text_color=INK, font=ctk.CTkFont(size=12)).grid(row=1, column=1, sticky="w", padx=12, pady=0)

        details = t("projects.card_documents", count=df_count)
        if searches:
            sources = list(set([s.get("provider", "") for s in searches]))
            details += t("projects.card_sources", sources=', '.join(sources))
            
        ctk.CTkLabel(self, text=details, text_color="#555555", font=ctk.CTkFont(size=12)).grid(row=2, column=1, sticky="nw", padx=12, pady=(4, 12))
        
        # Actions
        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.grid(row=3, column=1, sticky="w", padx=12, pady=(0, 12))
        
        ctk.CTkButton(actions_frame, text=t("projects.action_open"), width=60, fg_color=BLUE, corner_radius=0, command=lambda: self.on_open(self.proj_path)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions_frame, text=t("projects.action_rename"), width=60, fg_color=WHITE, text_color=INK, border_width=1, border_color=INK, hover_color="#EEEEEE", corner_radius=0, command=lambda: self.on_rename(self.proj_path)).pack(side="left", padx=8)
        ctk.CTkButton(actions_frame, text=t("projects.action_duplicate"), width=60, fg_color=WHITE, text_color=INK, border_width=1, border_color=INK, hover_color="#EEEEEE", corner_radius=0, command=lambda: self.on_duplicate(self.proj_path)).pack(side="left", padx=8)
        ctk.CTkButton(actions_frame, text=t("projects.action_delete"), width=60, fg_color=RED, text_color=WHITE, hover_color="#b82611", corner_radius=0, command=lambda: self.on_delete(self.proj_path)).pack(side="left", padx=8)

class ProjectsView(ctk.CTkFrame):
    def __init__(self, master, on_open_project):
        super().__init__(master, fg_color=PAPER, corner_radius=0)
        self.on_open_project = on_open_project
        self.projects_dir = os.path.expanduser("~/Blicsa/projects")
        os.makedirs(self.projects_dir, exist_ok=True)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        hdr = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK, height=60)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=t("projects.title"), font=ctk.CTkFont(size=20, weight="bold"), text_color=INK).pack(side="left", padx=16)
        ctk.CTkButton(hdr, text=t("projects.refresh"), fg_color=WHITE, text_color=INK, border_width=2, border_color=INK, corner_radius=0, hover_color="#EEEEEE", command=self.refresh).pack(side="right", padx=16)
        
        # Scrollable container
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.scroll.grid_columnconfigure(0, weight=1)
        
        self.refresh()
        
    def refresh(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        projects = []
        if os.path.exists(self.projects_dir):
            for f in os.listdir(self.projects_dir):
                if f.endswith(".blicsa"):
                    projects.append(os.path.join(self.projects_dir, f))
                    
        # Sort by modification time, newest first
        projects.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        if not projects:
            ctk.CTkLabel(self.scroll, text=t("projects.empty"), text_color="#555555", font=ctk.CTkFont(size=14)).pack(pady=40)
            return
            
        for p in projects:
            card = ProjectCard(self.scroll, p, self.on_open_project, self._rename, self._duplicate, self._delete)
            card.pack(fill="x", pady=8, padx=8)

    def _rename(self, proj_path):
        current_name = Path(proj_path).stem
        dlg = ctk.CTkInputDialog(text=t("projects.rename_prompt"), title=t("projects.rename_title"))
        new_name = dlg.get_input()
        if new_name and new_name.strip():
            new_path = os.path.join(self.projects_dir, f"{new_name.strip()}.blicsa")
            if os.path.exists(new_path):
                messagebox.showerror(t("projects.error_title"), t("projects.rename_exists"))
                return
            os.rename(proj_path, new_path)
            self.refresh()
            
    def _duplicate(self, proj_path):
        current_name = Path(proj_path).stem
        new_name = f"{current_name} {t('projects.copy_suffix')}"
        new_path = os.path.join(self.projects_dir, f"{new_name}.blicsa")
        counter = 1
        while os.path.exists(new_path):
            new_name = f"{current_name} {t('projects.copy_suffix_n', n=counter)}"
            new_path = os.path.join(self.projects_dir, f"{new_name}.blicsa")
            counter += 1
        shutil.copy2(proj_path, new_path)
        self.refresh()
        
    def _delete(self, proj_path):
        name = Path(proj_path).stem
        if messagebox.askyesno(t("projects.delete_title"), t("projects.delete_confirm", name=name)):
            os.remove(proj_path)
            self.refresh()
