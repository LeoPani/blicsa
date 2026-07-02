import argparse
import json
import sys
from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider

def main():
    parser = argparse.ArgumentParser(description="Headless search CLI for PyBibliomics")
    parser.add_argument("--provider", required=True, choices=["openalex", "crossref", "pubmed"], help="Search provider to use")
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument("--max", type=int, default=100, help="Maximum number of results")
    parser.add_argument("--out", required=True, help="Output JSON file path")
    parser.add_argument("--year-start", type=int, help="Filter: start year")
    parser.add_argument("--year-end", type=int, help="Filter: end year")
    parser.add_argument("--type", help="Filter: document type")
    parser.add_argument("--is-oa", action="store_true", default=None, help="Filter: open access only")
    parser.add_argument("--language", help="Filter: document language")

    args = parser.parse_args()

    # Select provider
    if args.provider == "openalex":
        provider = OpenAlexProvider()
    elif args.provider == "crossref":
        provider = CrossrefProvider()
    else:
        provider = PubMedProvider()

    filters = {}
    if args.year_start is not None:
        filters["year_start"] = args.year_start
    if args.year_end is not None:
        filters["year_end"] = args.year_end
    if args.type is not None:
        filters["type"] = args.type
    if args.is_oa is not None:
        filters["is_oa"] = args.is_oa
    if args.language is not None:
        filters["language"] = args.language

    print(f"Starting search on provider '{args.provider}' for query '{args.query}'...", file=sys.stderr)
    
    def progress(current, total):
        print(f"Fetched {current} / {total} records...", file=sys.stderr)

    results = []
    try:
        for record in provider.search(
            query=args.query,
            filters=filters,
            max_results=args.max,
            progress_cb=progress
        ):
            results.append(record)
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Search complete. Saving {len(results)} records to {args.out}...", file=sys.stderr)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Done.", file=sys.stderr)

if __name__ == "__main__":
    main()
