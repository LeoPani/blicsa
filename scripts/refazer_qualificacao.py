"""Refaz as três buscas iniciais e as vertentes extras de PatentBERT no OpenAlex.

As respostas normalizadas ficam em ~/Blicsa/rebusca-2026-09-17/ antes de
qualquer importação. `--name all` executa só as três buscas iniciais; as
consultas adicionais precisam ser selecionadas pelo nome e pré-visualizadas.
Uma busca incompleta termina com erro explícito.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.sources.openalex import OpenAlexProvider


QUERIES = {
    "patentbert": (
        '(patent OR patents) AND (BERT OR transformer OR "large language model" OR LLM) '
        'AND (classification OR retrieval OR "prior art" OR search)'
    ),
    "dsr-pi": (
        '("design science research" OR "design science") AND '
        '("technology transfer" OR "intellectual property" OR patent OR '
        '"innovation management")'
    ),
    "grace-period": (
        '(patent OR patents) AND '
        '("grace period" OR "novelty grace period" OR "prior disclosure")'
    ),
}

# O projeto PatentBERT é um eixo de pesquisa, não uma exigência de citar o
# modelo de Lee e Hsiang. As consultas adicionais cobrem métodos e aplicações
# que a primeira string (limitada a classificação/recuperação) poderia perder.
# Rodar separadamente permite auditar a contribuição de cada vertente.
PATENT_EXTRA_QUERIES = {
    "patent-masked": (
        '(patent OR patents OR "prior art") AND '
        '("masked language model" OR "masked language modeling" OR '
        '"masked language modelling" OR "masked pretraining" OR '
        '"masked pre-training")'
    ),
    "patent-adaptation": (
        '(patent OR patents OR "prior art") AND '
        '("domain-adaptive pretraining" OR "domain adaptive pretraining" OR '
        '"continued pretraining" OR "patent language model" OR '
        '"patent-specific language model")'
    ),
    "patent-semantic": (
        '(patent OR patents OR "prior art") AND '
        '("semantic similarity" OR "sentence embedding" OR '
        '"dense retrieval" OR "document embedding") AND '
        '(BERT OR transformer OR "language model")'
    ),
}

ALL_QUERIES = QUERIES | PATENT_EXTRA_QUERIES


def download(name: str, query: str, output_dir: Path,
             preview: bool = False) -> dict:
    provider = OpenAlexProvider()
    filters = {"fields": [("abstract", query)]}  # título e resumo, não texto completo
    announced = provider.count("", filters=filters)
    print(f"{name}: {announced} encontrados", flush=True)
    if preview:
        examples, _ = provider.browse("", filters=filters, per_page=10,
                                      sort="citations")
        for record in examples:
            print(f"  {record['year']} [{record['citations']}] {record['title']}",
                  flush=True)
        return {"name": name, "query": query, "announced": announced}
    if announced > 5000:
        raise RuntimeError(
            f"Busca {name} ampla demais ({announced}): revisar a string antes de "
            "baixar tudo ou segmentar por período. Nada foi importado."
        )
    records = list(provider.search("", filters=filters, max_results=announced + 200,
                                   progress_cb=lambda done, total: print(
                                       f"{name}: {done}/{total}", flush=True)))
    if provider.stop_error or len(records) < announced:
        raise RuntimeError(
            f"Busca incompleta em {name}: {len(records)}/{announced}; "
            f"motivo={provider.stop_reason}"
        )
    payload = {
        "name": name,
        "query": query,
        "search_field": "title_and_abstract",
        "source": "OpenAlex",
        "searched_on": date.today().isoformat(),
        "announced": announced,
        "downloaded": len(records),
        "pages": provider.pages_fetched,
        "stop_reason": provider.stop_reason,
        "records": records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{name}.json"
    tmp = output_dir / f"{name}.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    print(f"{name}: salvo em {target}", flush=True)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path.home() / "Blicsa" / "rebusca-2026-09-17")
    parser.add_argument("--name", choices=(*ALL_QUERIES, "all"), default="all")
    parser.add_argument("--preview", action="store_true",
                        help="mostra contagem e amostra antes de baixar")
    args = parser.parse_args()
    names = QUERIES if args.name == "all" else {args.name: ALL_QUERIES[args.name]}
    for name, query in names.items():
        download(name, query, args.output_dir, preview=args.preview)


if __name__ == "__main__":
    main()
