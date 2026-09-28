"""Une consultas metodológicas completas ao projeto PatentBERT e registra a triagem.

Execute depois de baixar as três buscas adicionais com refazer_qualificacao.py.
Não modifica o projeto se faltar uma consulta ou se a coleta estiver incompleta.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project import append_backlog, normalize_dataframe, open_project, project_dir, save_blicsa_project
from scripts.importar_rebuscas import SCHOLARLY_TYPES, dedup_key
from scripts.refazer_qualificacao import PATENT_EXTRA_QUERIES


SLUG = "qualificacao-2026-patentbert-rebusca"
STAGING = Path.home() / "Blicsa" / "rebusca-2026-09-17"
PATENT = re.compile(r"\bpatents?\b|\bprior.art\b", re.I)
MASKED = re.compile(
    r"mask(?:ed|ing).{0,30}(?:language|pre.?train|token|word)",
    re.I,
)
ADAPTATION = re.compile(
    r"domain.adapt|continu(?:ed|al) pre.?train|"
    r"patent.{0,24}language.model|language.model.{0,24}patent",
    re.I,
)
SEMANTIC = re.compile(
    r"semantic.similar|sentence.embedding|dense.retriev|document.embedding|"
    r"patent.embedding|semantic.search",
    re.I,
)
MODEL = re.compile(r"\bbert\b|transformer|language.model|embedding", re.I)


def screen(record: dict, family: str) -> str:
    """Pré-triagem local, sempre registrada por linha para revisão humana."""
    if record.get("document_type") not in SCHOLARLY_TYPES:
        return "tipo fora do corpus bibliográfico"
    if "zenodo" in str(record.get("source") or "").casefold():
        return "repositório Zenodo: revisão manual necessária"
    title = str(record.get("title") or "")
    abstract = str(record.get("abstract") or "")
    if not PATENT.search(title) and len(PATENT.findall(abstract)) < 2:
        return "patentes ou anterioridade pouco explícitas no título/resumo"
    topic = {"patent-masked": MASKED, "patent-adaptation": ADAPTATION,
             "patent-semantic": SEMANTIC}[family]
    if not topic.search(title) and not topic.search(abstract):
        return "método da vertente não encontrado no título/resumo"
    if family == "patent-semantic" and not MODEL.search(title + " " + abstract):
        return "não descreve modelo de linguagem ou embeddings"
    return ""


def load_extra(staging: Path = STAGING) -> dict[str, dict]:
    result = {}
    for family, query in PATENT_EXTRA_QUERIES.items():
        path = staging / f"{family}.json"
        if not path.exists():
            raise FileNotFoundError(f"Busca não executada: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("query") != query or len(payload.get("records") or []) < payload.get("announced", 0):
            raise RuntimeError(f"Consulta incompleta ou string diferente: {path}")
        result[family] = payload
    return result


def main() -> None:
    payloads = load_extra()
    state = open_project(SLUG)
    folder = project_dir(SLUG)
    if any(entry.get("raw_file") == "searches/patent-masked.json"
           for entry in state.get("searches") or []):
        raise RuntimeError("Ampliação já incorporada; projeto preservado sem alterações")
    old_df = state["df"].copy()
    old_df["search_family"] = old_df.get("search_family", "patentbert")
    keys = {dedup_key(row) for row in old_df.to_dict("records")}
    extras, rows, histories = [], [], list(state.get("searches") or [])
    for family, payload in payloads.items():
        accepted = 0
        for record in payload["records"]:
            reason = screen(record, family)
            key = dedup_key(record)
            if not reason and key in keys:
                reason = "duplicata de título entre buscas; primeira versão mantida"
            if not reason:
                keys.add(key)
                extras.append(record | {"search_family": family})
                accepted += 1
            rows.append({
                "search_family": family, "openalex_id": record.get("openalex_id"),
                "title": record.get("title"), "document_type": record.get("document_type"),
                "included": not reason, "reason": reason,
            })
        histories.append({
            "provider": "OpenAlex", "query": payload["query"],
            "field": "title_and_abstract", "searched_on": payload["searched_on"],
            "count": payload["announced"], "downloaded": len(payload["records"]),
            "selected_new": accepted,
            "raw_file": f"searches/{family}.json",
            "screening_file": "searches/triagem_adicional.csv",
        })

    updated = normalize_dataframe(pd.concat([old_df, pd.DataFrame(extras)], ignore_index=True))
    # A pasta já contém os mapas e a busca inicial. Guarda um snapshot antes da
    # ampliação, inclusive se a exportação visual posterior falhar.
    backup = folder / "searches" / "antes_da_ampliacao.blicsa"
    if not backup.exists():
        shutil.copyfile(folder / "project.blicsa", backup)
    for family in payloads:
        shutil.copyfile(STAGING / f"{family}.json", folder / "searches" / f"{family}.json")
    fields = ("search_family", "openalex_id", "title", "document_type", "included", "reason")
    with (folder / "searches" / "triagem_adicional.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    config = state["config"] | {
        "research_context": (
            "Modelos de linguagem para textos de patentes: PatentBERT e alternativas, "
            "pré-treinamento mascarado, adaptação de domínio e tarefas de classificação, "
            "busca semântica e anterioridade. Consultas separadas e triagem auditável em searches/. "
            "Corpus exploratório: revisar manualmente antes do referencial teórico."
        ),
        "search_strategy": {"queries": histories},
    }
    snapshot = folder / "project.blicsa.tmp"
    save_blicsa_project(str(snapshot), updated, config, positions=None, G=None,
                        cluster_labels=None, searches=histories)
    snapshot.replace(folder / "project.blicsa")
    for search in histories[len(state.get("searches") or []):]:
        append_backlog(SLUG, "search", search)
    append_backlog(SLUG, "import", {"new": len(extras), "total": len(updated)})

    method_path = folder / "metodologia.json"
    method = json.loads(method_path.read_text(encoding="utf-8"))
    method["expansion"] = {
        "found_by_family": {name: data["announced"] for name, data in payloads.items()},
        "new_records": len(extras), "total_records": len(updated),
        "selected_by_family": dict(Counter(r["search_family"] for r in extras)),
        "reasons": dict(Counter(r["reason"] for r in rows if r["reason"])),
        "type_counts": dict(Counter(updated["document_type"])),
    }
    method_path.write_text(json.dumps(method, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(method["expansion"], ensure_ascii=False, indent=2))
    print("Agora gere novamente os mapas com exportar_mapas_rebusca.py --name patentbert")


if __name__ == "__main__":
    main()
