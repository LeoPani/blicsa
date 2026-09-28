"""Remove a homonímia médica de ``patent`` dos projetos da qualificação."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project import append_backlog, open_project, project_dir, save_blicsa_project


TARGETS = {
    "qualificacao-2026-grace-period-rebusca": {"https://openalex.org/W7154128333"},
    "qualificacao-2026-patentbert-rebusca": {"https://openalex.org/W7160828580"},
}
REASON = "homonímia médica: patent ductus arteriosus, sem propriedade intelectual"


def update_triage(path: Path, removed_ids: set[str]) -> None:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    fieldnames = list(rows[0]) if rows else []
    for row in rows:
        if row.get("openalex_id") in removed_ids:
            row["included"] = "False"
            row["reason"] = REASON
    backup = path.with_name(f"{path.stem}_antes_homonimia{path.suffix}")
    if not backup.exists():
        shutil.copyfile(path, backup)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def refine(slug: str, removed_ids: set[str]) -> None:
    folder = project_dir(slug)
    state = open_project(slug)
    df = state["df"]
    mask = df["openalex_id"].isin(removed_ids)
    found = set(df.loc[mask, "openalex_id"])
    if found != removed_ids:
        raise RuntimeError(f"IDs inesperados em {slug}: esperados={removed_ids}, encontrados={found}")

    backup = folder / "searches" / "antes_da_correcao_homonimia.blicsa"
    if not backup.exists():
        shutil.copyfile(folder / "project.blicsa", backup)
    for triage in (folder / "searches").glob("triagem*.csv"):
        if "antes" not in triage.stem:
            update_triage(triage, removed_ids)

    revised = df.loc[~mask].reset_index(drop=True)
    config = state["config"] | {
        "research_context": (
            str(state["config"].get("research_context") or "").rstrip()
            + " A triagem exclui o uso médico de patent ductus arteriosus quando "
              "não há evidência de propriedade intelectual."
        )
    }
    snapshot = folder / "project.blicsa.tmp"
    save_blicsa_project(
        str(snapshot), revised, config, positions=None, G=None,
        cluster_labels=None, searches=state.get("searches"),
    )
    snapshot.replace(folder / "project.blicsa")

    method_path = folder / "metodologia.json"
    method = json.loads(method_path.read_text(encoding="utf-8"))
    method.update({
        "selected": len(revised),
        "types": dict(Counter(revised["document_type"].fillna("unknown"))),
        "with_references": int(revised["references"].map(bool).sum()),
        "homonym_revision": {"reason": REASON, "removed_ids": sorted(removed_ids)},
    })
    if "expansion" in method:
        method["expansion"]["total_records"] = len(revised)
        method["expansion"]["type_counts"] = method["types"]
    method_path.write_text(
        json.dumps(method, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    append_backlog(slug, "dedup", {"reason": REASON, "removed": len(removed_ids)})
    print(json.dumps({"slug": slug, "before": len(df), "after": len(revised),
                      "removed": sorted(removed_ids)}, ensure_ascii=False))


def main() -> None:
    for slug, removed_ids in TARGETS.items():
        refine(slug, removed_ids)


if __name__ == "__main__":
    main()
