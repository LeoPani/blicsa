"""Cria três projetos Blicsa a partir das buscas auditáveis da qualificação."""

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

from core.project import (append_backlog, create_project, normalize_dataframe,
                          project_dir, save_blicsa_project)


STAGING = Path.home() / "Blicsa" / "rebusca-2026-09-17"
PROJECT_NAMES = {
    "patentbert": "Qualificação 2026 — PatentBERT (rebusca)",
    "dsr-pi": "Qualificação 2026 — DSR e PI (rebusca)",
    "grace-period": "Qualificação 2026 — Grace Period (rebusca)",
}
SCHOLARLY_TYPES = {
    "article", "review", "conference-paper", "book", "book-chapter",
    "dissertation", "preprint", "report",
}
PREFERRED_TYPES = {
    "article": 4, "review": 4, "conference-paper": 3,
    "book": 3, "book-chapter": 3, "dissertation": 2,
    "preprint": 1, "report": 1,
}

MEDICAL_PATENT = re.compile(
    r"patent ductus|ductus arterios|\bpda\b|preterm infant|neonat|"
    r"ibuprofen|indomethacin|echocardi|pediatric|paediatric"
)
STRONG_IP = re.compile(
    r"intellectual property|patent application|patent document|patent text|"
    r"patent classification|patent search|patent citation|patent landscape|"
    r"patent database|patent office|patent law|patent analys|\bpatents\b|"
    r"prior art|invention|inventor|patent claim|patent filing|\bcpc\b|\bipc\b"
)


def screening_reason(name: str, record: dict) -> str:
    """Critérios conservadores; registros rejeitados continuam no JSON da busca."""
    if record.get("document_type") not in SCHOLARLY_TYPES:
        return "tipo fora do corpus bibliográfico"
    if "zenodo" in str(record.get("source") or "").casefold():
        return "repositório Zenodo: revisão manual necessária"

    title = str(record.get("title") or "").casefold()
    abstract = str(record.get("abstract") or "").casefold()
    text = f"{title} {abstract}"

    if name in {"patentbert", "grace-period"}:
        if MEDICAL_PATENT.search(text) and not STRONG_IP.search(text):
            return "homonímia médica: patent ductus arteriosus, sem propriedade intelectual"

    if name == "patentbert":
        patents = re.compile(r"patent(?!ed\b)|prior art")
        ai = re.compile(
            r"bert|transformer|large language model|\bllm\b|language model|"
            r"natural language processing|deep learning|generative ai|artificial intelligence"
        )
        focused = ((bool(patents.search(title)) or len(patents.findall(abstract)) >= 2)
                   and (bool(ai.search(title)) or bool(ai.search(abstract))))
    elif name == "dsr-pi":
        dsr = re.compile(r"design.science")
        domain = re.compile(
            r"technology transfer|intellectual property|patent|"
            r"innovation management|intellectual capital|innovation ecosyst"
        )
        focused = (
            (bool(dsr.search(title))
             and (bool(domain.search(title)) or bool(domain.search(abstract))))
            or (bool(domain.search(title)) and bool(dsr.search(abstract)))
        )
    else:
        grace = re.compile(r"grace period|prior disclosure")
        patent = re.compile(r"patent|novelty|invention")
        focused = (
            (bool(grace.search(title))
             and (bool(patent.search(title)) or bool(patent.search(abstract))))
            or (bool(patent.search(title)) and bool(grace.search(abstract)))
        )
    return "" if focused else "tema central pouco explícito no título/resumo"


def dedup_key(record: dict) -> str:
    raw = str(record.get("title") or "").replace("\\n", " ").replace("\\t", " ")
    title = re.sub(r"[^a-z0-9]+", " ", raw.casefold()).strip()
    return title or str(record.get("openalex_id") or record.get("doi") or "")


def metadata_score(record: dict) -> tuple:
    return (
        PREFERRED_TYPES.get(str(record.get("document_type")), 0),
        bool(record.get("abstract")), bool(record.get("references")),
        bool(record.get("doi")), int(record.get("citations") or 0),
    )


def build_one(name: str) -> dict:
    source = STAGING / f"{name}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = payload["records"]
    if len(records) < payload["announced"]:
        raise RuntimeError(f"Busca incompleta: {source}")

    initial_reasons = [screening_reason(name, record) for record in records]
    best_by_title: dict[str, int] = {}
    for index, (record, reason) in enumerate(zip(records, initial_reasons)):
        if reason:
            continue
        key = dedup_key(record)
        previous = best_by_title.get(key)
        if previous is None or metadata_score(record) > metadata_score(records[previous]):
            best_by_title[key] = index
    keep = set(best_by_title.values())
    selected = [record for index, record in enumerate(records) if index in keep]
    selected_df = normalize_dataframe(pd.DataFrame(selected))

    slug = create_project(PROJECT_NAMES[name])
    folder = project_dir(slug)
    shutil.copyfile(source, folder / "searches" / "consulta_openalex_completa.json")
    with (folder / "searches" / "triagem.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("openalex_id", "title", "year", "document_type", "source",
                         "included", "reason"))
        for index, record in enumerate(records):
            reason = initial_reasons[index]
            if not reason and index not in keep:
                reason = "duplicata de título; versão com mais metadados mantida"
            writer.writerow((record.get("openalex_id"), record.get("title"),
                             record.get("year"), record.get("document_type"),
                             record.get("source"), index in keep, reason))

    search = {
        "provider": "OpenAlex", "query": payload["query"],
        "field": "title_and_abstract", "searched_on": payload["searched_on"],
        "count": payload["announced"], "downloaded": len(records),
        "selected": len(selected),
        "raw_file": "searches/consulta_openalex_completa.json",
        "screening_file": "searches/triagem.csv",
    }
    config = {
        "name": PROJECT_NAMES[name],
        "research_context": (
            "Rebusca para seminário de qualificação. Corpus exploratório selecionado "
            "por tema explícito em título/resumo, tipo bibliográfico e deduplicação de título. "
            "A consulta integral e a triagem estão na pasta searches; revisar manualmente "
            "antes de usar em síntese ou referencial teórico."
        ),
        "search_strategy": search,
    }
    save_blicsa_project(str(folder / "project.blicsa"), selected_df, config,
                        positions=None, G=None, cluster_labels=None,
                        searches=[search])
    append_backlog(slug, "search", search)
    append_backlog(slug, "import", {"selected": len(selected), "source": "OpenAlex"})
    append_backlog(slug, "dedup", {"removed": sum(
        not reason and index not in keep
        for index, reason in enumerate(initial_reasons))})

    reasons = Counter(reason for reason in initial_reasons if reason)
    result = {
        "slug": slug, "name": PROJECT_NAMES[name], "downloaded": len(records),
        "selected": len(selected), "excluded": dict(reasons),
        "duplicates_removed": sum(not reason and index not in keep
                                  for index, reason in enumerate(initial_reasons)),
        "types": dict(Counter(record.get("document_type") or "unknown"
                              for record in selected)),
        "with_references": sum(bool(record.get("references")) for record in selected),
    }
    (folder / "metodologia.json").write_text(
        json.dumps(result | {"query": payload["query"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    missing = [name for name in PROJECT_NAMES if not (STAGING / f"{name}.json").exists()]
    if missing:
        raise SystemExit(f"Buscas faltantes: {', '.join(missing)}")
    for name in PROJECT_NAMES:
        build_one(name)


if __name__ == "__main__":
    main()
