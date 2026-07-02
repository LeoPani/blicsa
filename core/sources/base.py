import time
import urllib.request
import urllib.parse
import json
import logging
from typing import Iterator, Callable, Dict, Any, Optional

logger = logging.getLogger("SearchProvider")

class SearchProvider:
    def __init__(self, mailto: str = "pybibliomics@example.com", cache: Optional[Dict[str, Any]] = None):
        self.mailto = mailto
        self.cache = cache if cache is not None else {}
        self.last_request_time = 0.0

    def fetch_url(self, url: str, headers: Optional[Dict[str, str]] = None, cancel_event = None, rate_limit_delay: float = 0.0) -> str:
        # Check cache
        if url in self.cache:
            return self.cache[url]

        headers = headers or {}
        if "User-Agent" not in headers:
            headers["User-Agent"] = f"Blicsa/1.0 (mailto:{self.mailto})"

        # Rate limiting
        if rate_limit_delay > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < rate_limit_delay:
                time.sleep(rate_limit_delay - elapsed)

        retries = 3
        backoff = 1.0
        while retries > 0:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Search cancelled by user")
            
            try:
                self.last_request_time = time.time()
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = response.read().decode("utf-8", errors="replace")
                    self.cache[url] = data
                    return data
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    logger.warning(f"HTTP {e.code} received. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                    retries -= 1
                else:
                    raise e
            except Exception as e:
                logger.warning(f"Error requesting {url}: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
                retries -= 1
        raise IOError(f"Failed to fetch {url} after retries")

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        raise NotImplementedError
