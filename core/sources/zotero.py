
import urllib.parse
import json
import logging
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider

logger = logging.getLogger("ZoteroProvider")

class ZoteroProvider(SearchProvider):
    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        # Zotero user ID can be passed in query. e.g. "475425"
        user_id = query.strip()
        if not user_id.isdigit():
            user_id = "475425" # default public library
            
        base_url = f"https://api.zotero.org/users/{user_id}/items?format=json&limit={min(100, max_results)}"
        import urllib.request
        try:
            req = urllib.request.Request(base_url, headers={'User-Agent': 'Blicsa'})
            with urllib.request.urlopen(req) as res:
                data = json.loads(res.read().decode('utf-8'))
                for i, item in enumerate(data):
                    if cancel_event and cancel_event.is_set(): break
                    d = item.get("data", {})
                    creators = [c.get("lastName", "") + ", " + c.get("firstName", "") for c in d.get("creators", []) if "lastName" in c]
                    yield {
                        "doi": d.get("DOI", ""),
                        "title": d.get("title", "No Title"),
                        "authors": "; ".join(creators),
                        "year": d.get("date", "")[:4] if d.get("date") else None,
                        "source": d.get("publicationTitle", ""),
                        "abstract": d.get("abstractNote", ""),
                        "citations": 0
                    }
                    if progress_cb: progress_cb(i+1, len(data))
        except Exception as e:
            logger.error(f"Zotero API error: {e}")
