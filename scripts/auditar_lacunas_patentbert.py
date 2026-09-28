"""Lista trabalhos de treinamento/adaptação já presentes na busca PatentBERT."""

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.project import open_project

root = Path.home() / "Blicsa"
records = json.loads((root / "rebusca-2026-09-17/patentbert.json").read_text())["records"]
triage = root / "projects/qualificacao-2026-patentbert-rebusca/searches/triagem.csv"
with triage.open(encoding="utf-8-sig") as stream:
    included = {row["openalex_id"] for row in csv.DictReader(stream) if row["included"] == "True"}

patterns = {
    "masked": re.compile(r"mask(?:ed|ing) (?:language|pre.?train|token|word)|\bMLM\b", re.I),
    "pretraining": re.compile(r"pre.?train|domain.adapt|fine.tun|fine.tuning", re.I),
    "embeddings": re.compile(r"embedding|semantic similarity|dense retrieval", re.I),
}
for label, pattern in patterns.items():
    found = [r for r in records if pattern.search(str(r.get("title") or "") + " " + str(r.get("abstract") or ""))]
    selected = [r for r in found if r.get("openalex_id") in included]
    print(f"{label}: {len(found)} na busca, {len(selected)} no corpus, {len(found)-len(selected)} excluídos")
    for r in sorted(found, key=lambda item: (-int(item.get("citations") or 0), item.get("title") or ""))[:15]:
        print(" + " if r.get("openalex_id") in included else " - ",
              r.get("year"), r.get("title"), sep="")

old = open_project("seminario-qualificacao-patentbert-2")["df"]
old_masked = old[old.apply(lambda row: bool(patterns["masked"].search(
    str(row.get("title") or "") + " " + str(row.get("abstract") or ""))), axis=1)]
print(f"Projeto original: {len(old_masked)} de {len(old)} citam treinamento mascarado")
for _, row in old_masked.iterrows():
    print(f"  {row['year']} {row['title']}")
