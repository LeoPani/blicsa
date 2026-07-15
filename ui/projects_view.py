import customtkinter as ctk
import os
import zipfile
import json
import shutil
from pathlib import Path
from tkinter import messagebox
from PIL import Image
from core.i18n import t
from core.project import (PROJECTS_DIR, migrate_loose_projects, list_projects,
                          load_backlog, project_dir, slugify)

PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
BLUE = "#1E4DA0"
WHITE = "#FFFFFF"


class ProjectCard(ctk.CTkFrame):
    """Card de um projeto-PASTA: manifest/config do project.blicsa + contagens
    do backlog (nº docs, nº buscas, última atividade)."""

    def __init__(self, master, slug, projects_dir, on_open, on_rename, on_duplicate, on_delete):
        super().__init__(master, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.slug = slug
        self.proj_dir = Path(projects_dir) / slug
        blicsa_path = self.proj_dir / "project.blicsa"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        manifest, config, df_count, has_thumbnail = {}, {}, 0, False
        try:
            with zipfile.ZipFile(blicsa_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                if "config.json" in zf.namelist():
                    config = json.loads(zf.read("config.json").decode("utf-8"))
                if "dataset.json.gz" in zf.namelist():
                    import gzip
                    df_json = gzip.decompress(zf.read("dataset.json.gz")).decode("utf-8")
                    df_count = df_json.count('"title":')  # quick estimation
                if "thumbnail.png" in zf.namelist():
                    has_thumbnail = True
        except Exception:
            pass

        backlog = load_backlog(slug, projects_dir)
        n_buscas = sum(1 for e in backlog if e.get("action") == "search")
        last_ts = backlog[-1].get("ts", "")[:19].replace("T", " ") if backlog else \
            manifest.get("saved_at", t("projects.date_unknown"))

        # Thumbnail
        self.thumb_frame = ctk.CTkFrame(self, width=120, height=120, fg_color="#E0E0E0",
                                        corner_radius=0, border_width=2, border_color=INK)
        self.thumb_frame.grid(row=0, column=0, rowspan=4, padx=12, pady=12, sticky="nsew")
        self.thumb_frame.pack_propagate(False)
        if has_thumbnail:
            try:
                import io
                with zipfile.ZipFile(blicsa_path, "r") as zf:
                    img = Image.open(io.BytesIO(zf.read("thumbnail.png")))
                ctk_img = ctk.CTkImage(light_image=img, size=(116, 116))
                ctk.CTkLabel(self.thumb_frame, text="", image=ctk_img).pack(expand=True, fill="both")
            except Exception:
                ctk.CTkLabel(self.thumb_frame, text=t("projects.card_map"), text_color=INK,
                             font=ctk.CTkFont(weight="bold")).pack(expand=True)
        else:
            ctk.CTkLabel(self.thumb_frame, text=t("projects.card_no_map"), text_color="#999999",
                         font=ctk.CTkFont(weight="bold")).pack(expand=True)

        name = config.get("name") or slug
        ctk.CTkLabel(self, text=name, text_color=BLUE, font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=1, sticky="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(self, text=t("projects.card_last_activity", ts=last_ts), text_color=INK,
                     font=ctk.CTkFont(size=12)).grid(row=1, column=1, sticky="w", padx=12, pady=0)

        details = t("projects.card_documents", count=df_count)
        details += t("projects.card_searches", n=n_buscas)
        details += t("projects.card_events", n=len(backlog))
        ctk.CTkLabel(self, text=details, text_color="#555555", font=ctk.CTkFont(size=12)).grid(
            row=2, column=1, sticky="nw", padx=12, pady=(4, 12))

        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.grid(row=3, column=1, sticky="w", padx=12, pady=(0, 12))
        # width=100 cabe o maior rótulo medido nos 3 idiomas ("Renommer"=84px) + folga.
        ctk.CTkButton(actions_frame, text=t("projects.action_open"), width=100, fg_color=BLUE,
                      corner_radius=0, command=lambda: on_open(self.slug)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions_frame, text=t("projects.action_rename"), width=100, fg_color=WHITE,
                      text_color=INK, border_width=1, border_color=INK, hover_color="#EEEEEE",
                      corner_radius=0, command=lambda: on_rename(self.slug)).pack(side="left", padx=8)
        ctk.CTkButton(actions_frame, text=t("projects.action_duplicate"), width=100, fg_color=WHITE,
                      text_color=INK, border_width=1, border_color=INK, hover_color="#EEEEEE",
                      corner_radius=0, command=lambda: on_duplicate(self.slug)).pack(side="left", padx=8)
        ctk.CTkButton(actions_frame, text=t("projects.action_delete"), width=100, fg_color=RED,
                      text_color=WHITE, hover_color="#b82611", corner_radius=0,
                      command=lambda: on_delete(self.slug)).pack(side="left", padx=8)


class ProjectsView(ctk.CTkFrame):
    def __init__(self, master, on_open_project, on_new_project=None):
        super().__init__(master, fg_color=PAPER, corner_radius=0)
        self.on_open_project = on_open_project   # recebe o SLUG
        self.on_new_project = on_new_project
        self.projects_dir = os.path.expanduser("~/Blicsa/projects")
        os.makedirs(self.projects_dir, exist_ok=True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK, height=60)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=t("projects.title"), font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=INK).pack(side="left", padx=16)
        ctk.CTkButton(hdr, text=t("projects.refresh"), fg_color=WHITE, text_color=INK, border_width=2,
                      border_color=INK, corner_radius=0, hover_color="#EEEEEE",
                      command=self.refresh).pack(side="right", padx=16)
        if self.on_new_project:
            ctk.CTkButton(hdr, text=t("projects.new"), fg_color=RED, text_color=WHITE, corner_radius=0,
                          hover_color="#b82611", command=self.on_new_project).pack(side="right", padx=4)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.scroll.grid_columnconfigure(0, weight=1)

        self.refresh()

    def refresh(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()

        # MIGRAÇÃO SUAVE: .blicsa soltos viram pastas na primeira listagem.
        migrated = migrate_loose_projects(self.projects_dir)
        if migrated:
            messagebox.showinfo("Blicsa", t("projects.migrated", n=len(migrated)))

        slugs = list_projects(self.projects_dir)
        if not slugs:
            ctk.CTkLabel(self.scroll, text=t("projects.empty"), text_color="#555555",
                         font=ctk.CTkFont(size=14)).pack(pady=40)
            return
        for slug in slugs:
            card = ProjectCard(self.scroll, slug, self.projects_dir, self.on_open_project,
                               self._rename, self._duplicate, self._delete)
            card.pack(fill="x", pady=8, padx=8)

    def _rename(self, slug):
        dlg = ctk.CTkInputDialog(text=t("projects.rename_prompt"), title=t("projects.rename_title"))
        new_name = dlg.get_input()
        if not (new_name and new_name.strip()):
            return
        new_slug = slugify(new_name.strip())
        new_dir = Path(self.projects_dir) / new_slug
        if new_dir.exists():
            messagebox.showerror(t("projects.error_title"), t("projects.rename_exists"))
            return
        os.rename(Path(self.projects_dir) / slug, new_dir)
        # nome legível vai no config do snapshot na próxima gravação; o slug já reflete.
        self.refresh()

    def _duplicate(self, slug):
        base = Path(self.projects_dir)
        new_slug, n = f"{slug}-copia", 2
        while (base / new_slug).exists():
            new_slug = f"{slug}-copia-{n}"
            n += 1
        shutil.copytree(base / slug, base / new_slug)
        self.refresh()

    def _delete(self, slug):
        if messagebox.askyesno(t("projects.delete_title"), t("projects.delete_confirm", name=slug)):
            shutil.rmtree(Path(self.projects_dir) / slug, ignore_errors=True)
            self.refresh()
