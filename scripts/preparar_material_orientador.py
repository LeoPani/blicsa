"""Monta o pacote de resultados preliminares para discussão com o orientador."""

from __future__ import annotations

import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.matrix_builders import parse_author_list
from core.project import open_project


OUTPUT = Path.home() / "Blicsa" / "pacote-orientador-2026-09-19"
PROJECT_ROOT = Path.home() / "Blicsa" / "projects"
PROJECTS = {
    "PatentBERT": "qualificacao-2026-patentbert-rebusca",
    "DSR e PI": "qualificacao-2026-dsr-e-pi-rebusca",
    "Grace Period": "qualificacao-2026-grace-period-rebusca",
}
FOLDER_NAMES = {
    "PatentBERT": "01_patentbert",
    "DSR e PI": "02_dsr_e_pi",
    "Grace Period": "03_grace_period",
}
COLORS = {
    "PatentBERT": "#D62828",
    "DSR e PI": "#0057B8",
    "Grace Period": "#E1AD01",
}
MAP_COUNTS = {
    "PatentBERT": {"termos": (66, 350, 1), "coautoria": (62, 80, 18),
                   "acoplamento": (99, 354, 9)},
    "DSR e PI": {"termos": (62, 350, 1), "coautoria": (89, 137, 25),
                 "acoplamento": (15, 25, 2)},
    "Grace Period": {"termos": (57, 350, 1), "coautoria": (50, 53, 20)},
}


def clean_label(value: object, maximum: int = 54) -> str:
    text = " ".join(str(value or "Sem informação").split())
    return text if len(text) <= maximum else text[:maximum - 1].rstrip() + "…"


def chart_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "#F7F4EE",
        "axes.facecolor": "#F7F4EE",
        "savefig.facecolor": "#F7F4EE",
    })


def save_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def copy_material() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, slug in PROJECTS.items():
        destination = OUTPUT / FOLDER_NAMES[name]
        destination.mkdir(parents=True, exist_ok=True)
        source = PROJECT_ROOT / slug
        for kind in MAP_COUNTS[name]:
            shutil.copytree(source / "exports" / kind,
                            destination / f"mapa_{kind}_interativo",
                            dirs_exist_ok=True)
        for filename in ("metodologia.json",):
            shutil.copyfile(source / filename, destination / filename)
        shutil.copyfile(source / "searches" / "triagem.csv",
                        destination / "triagem_completa.csv")
        if name == "PatentBERT":
            for filename in ("analise-seminais-ia.md",
                             "referencias-seminais-verificadas.txt"):
                shutil.copyfile(source / "exports" / filename,
                                destination / filename)

    methods = OUTPUT / "04_metodologia"
    methods.mkdir(exist_ok=True)
    shutil.copyfile(Path.home() / "Blicsa" / "rebusca-2026-09-17" / "LEIA-ME.md",
                    methods / "estrategia_busca_e_limitacoes.md")
    shutil.copyfile(Path.home() / "Blicsa" / "auditoria-bases-2026-09-17.md",
                    methods / "auditoria_bases.md")
    for name in ("DIAGNOSTICO-MAPAS-TERMOS-QUALIFICACAO.md",
                 "DIAGNOSTICO-DUPLICATA-DSR.md",
                 "DIAGNOSTICO-HOMONIMIA-PATENT-GRACE-PERIOD.md"):
        source = Path(__file__).resolve().parents[1] / "docs" / name
        if source.exists():
            shutil.copyfile(source, methods / name.lower())


def prepare_data() -> dict[str, pd.DataFrame]:
    frames = {
        name: open_project(PROJECT_ROOT / slug)["df"].copy()
        for name, slug in PROJECTS.items()
    }
    data_dir = OUTPUT / "05_tabelas"
    data_dir.mkdir(exist_ok=True)

    summary_rows = []
    type_rows = []
    source_rows = []
    author_rows = []
    cited_rows = []
    for name, df in frames.items():
        years = pd.to_numeric(df["year"], errors="coerce")
        years = years[years > 0]
        refs = int(df["references"].fillna("").astype(str).str.strip().ne("").sum())
        summary_rows.append({
            "projeto": name, "documentos": len(df),
            "ano_inicial": int(years.min()), "ano_final": int(years.max()),
            "com_referencias": refs,
            "cobertura_referencias_percentual": round(100 * refs / len(df), 1),
        })
        for doc_type, count in df["document_type"].fillna("unknown").value_counts().items():
            type_rows.append({"projeto": name, "tipo": doc_type, "documentos": int(count)})
        for rank, (source, count) in enumerate(
            df["source"].fillna("").replace("", pd.NA).dropna().value_counts().head(12).items(), 1
        ):
            source_rows.append({"projeto": name, "posicao": rank,
                                "fonte": source, "documentos": int(count)})
        authors = Counter(
            author for raw in df["authors"] for author in parse_author_list(raw)
        )
        for rank, (author, count) in enumerate(authors.most_common(15), 1):
            author_rows.append({"projeto": name, "posicao": rank,
                                "autor": author, "documentos": int(count)})
        ranked = df.assign(
            _citations=pd.to_numeric(df["citations"], errors="coerce").fillna(0)
        ).sort_values(["_citations", "title"], ascending=[False, True]).head(15)
        for rank, (_, row) in enumerate(ranked.iterrows(), 1):
            cited_rows.append({
                "projeto": name, "posicao": rank, "citacoes": int(row["_citations"]),
                "ano": int(row["year"]) if row.get("year") else "",
                "titulo": row.get("title", ""), "openalex_id": row.get("openalex_id", ""),
                "doi": row.get("doi", ""),
            })

    save_csv(data_dir / "resumo_corpus.csv", list(summary_rows[0]), summary_rows)
    save_csv(data_dir / "tipos_documento.csv", list(type_rows[0]), type_rows)
    save_csv(data_dir / "principais_fontes.csv", list(source_rows[0]), source_rows)
    save_csv(data_dir / "principais_autores.csv", list(author_rows[0]), author_rows)
    save_csv(data_dir / "documentos_mais_citados.csv", list(cited_rows[0]), cited_rows)
    return frames


def make_charts(frames: dict[str, pd.DataFrame]) -> None:
    chart_style()
    panorama = OUTPUT / "00_panorama"
    panorama.mkdir(exist_ok=True)

    types = ["article", "review", "conference-paper", "preprint",
             "dissertation", "book", "book-chapter", "report"]
    type_labels = ["Artigo", "Revisão", "Congresso", "Preprint",
                   "Dissertação", "Livro", "Capítulo", "Relatório"]
    type_colors = ["#0057B8", "#2F80ED", "#D62828", "#E1AD01",
                   "#6A4C93", "#2A9D8F", "#5C677D", "#111111"]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    bottom = np.zeros(len(PROJECTS))
    x = np.arange(len(PROJECTS))
    for doc_type, label, color in zip(types, type_labels, type_colors):
        values = np.array([int((frames[name]["document_type"] == doc_type).sum())
                           for name in PROJECTS])
        ax.bar(x, values, bottom=bottom, label=label, color=color,
               edgecolor="#F7F4EE", linewidth=0.8)
        bottom += values
    ax.set_xticks(x, PROJECTS)
    ax.set_ylabel("Documentos")
    ax.set_title("Composição dos três corpora de trabalho")
    ax.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(panorama / "composicao_documental.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    values = []
    for name, df in frames.items():
        refs = int(df["references"].fillna("").astype(str).str.strip().ne("").sum())
        values.append(100 * refs / len(df))
    bars = ax.bar(PROJECTS.keys(), values, color=[COLORS[n] for n in PROJECTS], width=0.62)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 1.2,
                f"{value:.1f}%".replace(".", ","), ha="center", fontweight="bold")
    ax.set_ylim(0, 70)
    ax.set_ylabel("Documentos com lista de referências (%)")
    ax.set_title("Cobertura de referências por corpus")
    ax.grid(axis="y", alpha=0.18)
    fig.tight_layout()
    fig.savefig(panorama / "cobertura_referencias.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(10, 8.5), constrained_layout=True)
    for ax, (name, df) in zip(axes, frames.items()):
        years = pd.to_numeric(df["year"], errors="coerce")
        counts = years[years > 0].astype(int).value_counts().sort_index()
        full = counts.reindex(range(int(counts.index.min()), int(counts.index.max()) + 1), fill_value=0)
        ax.plot(full.index, full.values, color=COLORS[name], linewidth=2.2, marker="s", markersize=3)
        ax.fill_between(full.index, full.values, color=COLORS[name], alpha=0.10)
        ax.set_title(name, loc="left", fontsize=11)
        ax.set_ylabel("Docs.")
        ax.grid(alpha=0.18)
    axes[-1].set_xlabel("Ano de publicação")
    fig.suptitle("Distribuição temporal dos corpora", fontsize=15, fontweight="bold")
    fig.savefig(panorama / "distribuicao_temporal.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    for name, df in frames.items():
        destination = OUTPUT / FOLDER_NAMES[name]
        sources = df["source"].fillna("").replace("", pd.NA).dropna().value_counts().head(8)
        fig, ax = plt.subplots(figsize=(9, 5.3))
        labels = [clean_label(value) for value in sources.index][::-1]
        ax.barh(labels, sources.values[::-1], color=COLORS[name])
        ax.set_xlabel("Documentos")
        ax.set_title(f"{name}: fontes mais frequentes")
        ax.grid(axis="x", alpha=0.18)
        fig.tight_layout()
        fig.savefig(destination / "fontes_mais_frequentes.png", dpi=220, bbox_inches="tight")
        plt.close(fig)

        cited = df.assign(
            _citations=pd.to_numeric(df["citations"], errors="coerce").fillna(0)
        ).sort_values(["_citations", "title"], ascending=[False, True]).head(8)
        fig, ax = plt.subplots(figsize=(9, 5.7))
        labels = [clean_label(value, 62) for value in cited["title"]][::-1]
        ax.barh(labels, cited["_citations"].values[::-1], color=COLORS[name])
        ax.set_xlabel("Citações informadas pelo OpenAlex")
        ax.set_title(f"{name}: documentos mais citados no corpus")
        ax.grid(axis="x", alpha=0.18)
        fig.tight_layout()
        fig.savefig(destination / "documentos_mais_citados.png", dpi=220, bbox_inches="tight")
        plt.close(fig)


def make_contact_sheet() -> None:
    items = []
    for name in PROJECTS:
        for kind in MAP_COUNTS[name]:
            path = OUTPUT / FOLDER_NAMES[name] / f"mapa_{kind}_interativo" / "mapa.png"
            items.append((f"{name} · {kind}", path))
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 24)
    rows = (len(items) + 1) // 2
    canvas = Image.new("RGB", (1000, rows * 360), (247, 244, 238))
    draw = ImageDraw.Draw(canvas)
    for index, (label, path) in enumerate(items):
        image = Image.open(path).convert("RGB")
        image.thumbnail((480, 300))
        column, row = index % 2, index // 2
        x = column * 500 + (500 - image.width) // 2
        y = row * 360 + 45
        draw.text((column * 500 + 20, row * 360 + 10), label,
                  fill=(20, 20, 20), font=font)
        canvas.paste(image, (x, y))
    canvas.save(OUTPUT / "00_panorama" / "visao_geral_dos_mapas.png", quality=94)


def write_readme() -> None:
    text = """PACOTE DE RESULTADOS BIBLIOMÉTRICOS PRELIMINARES
Data de consolidação: 19/09/2026

O arquivo PDF é a versão pronta para envio. O DOCX é editável.

00_panorama contém gráficos comparativos e uma visão geral dos oito mapas.
01_patentbert contém três mapas, dois gráficos, a triagem e a análise exploratória de referências.
02_dsr_e_pi contém três mapas, dois gráficos e a triagem.
03_grace_period contém dois mapas, dois gráficos e a triagem.
04_metodologia documenta strings, critérios, correções e limites.
05_tabelas contém tabelas em CSV para conferência e reutilização.

Para abrir um mapa interativo, entre na pasta correspondente e abra mapa.html.
Os arquivos PNG servem para leitura rápida e inserção futura em slides.

Os mapas e as contagens são exploratórios. A triagem automática foi preservada
e deve ser complementada por leitura humana antes da versão final do referencial teórico.
"""
    (OUTPUT / "LEIA-ME.txt").write_text(text, encoding="utf-8")


def main() -> None:
    copy_material()
    frames = prepare_data()
    make_charts(frames)
    make_contact_sheet()
    write_readme()
    print(OUTPUT)


if __name__ == "__main__":
    main()
