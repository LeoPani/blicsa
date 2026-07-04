import threading
import pandas as pd
import hashlib
from unittest.mock import patch, MagicMock
from core.sources.openalex import OpenAlexProvider

def test_api_pagination_and_dedupe():
    mock_responses = []
    total_items = 260
    
    def build_page(start, count, next_cursor):
        return {
            "meta": {"count": total_items, "next_cursor": next_cursor},
            "results": [
                {
                    "title": f"Title {i} {hashlib.md5(str(i).encode()).hexdigest()*3}",
                    "doi": f"10.1234/{i}",
                    "publication_year": 2023,
                    "authorships": [{"author": {"display_name": f"Author {i}"}}],
                } for i in range(start, start + count)
            ]
        }
        
    mock_responses = [
        build_page(0, 100, "cursor_1"),
        build_page(100, 100, "cursor_2"),
        build_page(200, 60, None)
    ]
    
    with patch("core.sources.base.SearchProvider.fetch_url") as mock_fetch:
        import json
        mock_fetch.side_effect = [json.dumps(r) for r in mock_responses]
        
        provider = OpenAlexProvider()
        fetched_results = []
        
        for record in provider.search("test query", max_results=1000):
            fetched_results.append(record)
            
        assert len(fetched_results) == 260

    df = pd.DataFrame(fetched_results)
    df = pd.concat([df, df.head(10)], ignore_index=True)
    assert len(df) == 270
    
    from core.harmonization import fuzzy_deduplicate_papers
    df_deduped = fuzzy_deduplicate_papers(df)
    
    assert len(df_deduped) == 260
