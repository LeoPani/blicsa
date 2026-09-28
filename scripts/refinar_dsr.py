"""Reaplica a triagem DSR após corrigir títulos com quebras literais."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project import append_backlog, normalize_dataframe, open_project, project_dir, save_blicsa_project
from scripts.importar_rebuscas import dedup_key, metadata_score, screening_reason

SLUG = "qualificacao-2026-dsr-e-pi-rebusca"


def select(records: list[dict]) -> tuple[list[dict], list[str], set[int]]:
    reasons = [screening_reason("dsr-pi", item) for item in records]
    best = {}
    for index, (item, reason) in enumerate(zip(records, reasons)):
        if reason:
            continue
        key = dedup_key(item)
        old = best.get(key)
        if old is None or metadata_score(item) > metadata_score(records[old]):
            best[key] = index
    keep = set(best.values())
    return [item for i, item in enumerate(records) if i in keep], reasons, keep


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    state = open_project(SLUG)
    folder = project_dir(SLUG)
    raw = json.loads((folder / "searches/consulta_openalex_completa.json").read_text())
    records = raw["records"]
    selected, reasons, keep = select(records)
    old = state["df"]
    old_ids = set(old.get("openalex_id", []))
    new_ids = {item.get("openalex_id") for item in selected}
    removed = old_ids - new_ids
    added = new_ids - old_ids
    print(json.dumps({"before": len(old), "after": len(selected),
                      "removed": sorted(removed), "added": sorted(added)},
                     ensure_ascii=False))
    if args.dry_run:
        return
    if added or len(removed) != 1 or len(selected) != len(old) - 1:
        raise RuntimeError("Revisão inesperada; nenhum dado foi modificado")

    backup = folder / "searches/antes_da_revisao_dsr.blicsa"
    shutil.copyfile(folder / "project.blicsa", backup)
    shutil.copyfile(folder / "searches/triagem.csv",
                    folder / "searches/triagem_antes_da_revisao.csv")
    shutil.copyfile(folder / "exports/termos/mapa.png",
                    folder / "exports/termos/mapa-antes-da-revisao.png")
    with (folder / "searches/triagem.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(("openalex_id", "title", "year", "document_type", "source",
                         "included", "reason"))
        for i, item in enumerate(records):
            reason = reasons[i] or ("duplicata de título após normalizar quebras de linha"
                                    if i not in keep else "")
            writer.writerow((item.get("openalex_id"), item.get("title"),
                             item.get("year"), item.get("document_type"),
                             item.get("source"), i in keep, reason))
    config = state["config"] | {
        "research_context": (
            "Rebusca exploratória sobre design science research, propriedade intelectual, "
            "transferência de tecnologia e gestão da inovação. Triagem automática com "
            "deduplicação de título; os trabalhos contextuais devem ser revisados "
            "manualmente antes de interpretar clusters como interseção DSR–PI."
        ),
    }
    snapshot = folder / "project.blicsa.tmp"
    save_blicsa_project(str(snapshot), normalize_dataframe(pd.DataFrame(selected)), config,
                        positions=None, G=None, cluster_labels=None,
                        searches=state.get("searches"))
    snapshot.replace(folder / "project.blicsa")
    method_path = folder / "metodologia.json"
    method = json.loads(method_path.read_text(encoding="utf-8"))
    method.update({
        "selected": len(selected),
        "duplicates_removed": sum(not reason and i not in keep
                                  for i, reason in enumerate(reasons)),
        "types": dict(Counter(item.get("document_type") or "unknown" for item in selected)),
        "with_references": sum(bool(item.get("references")) for item in selected),
        "revision": {"reason": "quebra literal no título duplicado", "removed_ids": sorted(removed)},
    })
    method_path.write_text(json.dumps(method, ensure_ascii=False, indent=2), encoding="utf-8")
    append_backlog(SLUG, "dedup", {"reason": "quebra literal no título", "removed": 1})
    print("Reexporte os mapas: exportar_mapas_rebusca.py --name dsr-pi")


if __name__ == "__main__":
    main()
