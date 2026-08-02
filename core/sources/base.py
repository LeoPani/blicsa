import time
import urllib.request
import urllib.parse
import json
import logging
from collections import OrderedDict
from typing import Iterator, Callable, Dict, Any, Optional

logger = logging.getLogger("SearchProvider")

# Identidade única do app nas APIs (OpenAlex/Crossref pedem um mailto de contato).
MAILTO = "blicsa.app@gmail.com"

# Teto do cache de respostas por provider (LRU).
CACHE_MAX_ENTRIES = 50

class SearchProvider:
    def __init__(self, mailto: str = MAILTO, cache: Optional[Dict[str, Any]] = None):
        self.mailto = mailto
        self.cache: OrderedDict = OrderedDict(cache or {})
        self.last_request_time = 0.0
        # Orçamento informado pela API (ver _capture_rate_limit). Vazio até a 1ª resposta.
        self.rate_limit: Dict[str, Any] = {}

    def _cache_get(self, url: str) -> Optional[str]:
        if url in self.cache:
            self.cache.move_to_end(url)
            return self.cache[url]
        return None

    def _cache_put(self, url: str, data: str):
        self.cache[url] = data
        self.cache.move_to_end(url)
        while len(self.cache) > CACHE_MAX_ENTRIES:
            self.cache.popitem(last=False)

    def _capture_rate_limit(self, headers):
        """Guarda o orçamento de requisições que a API informa nos headers.

        O OpenAlex passou a devolver um modelo de CRÉDITOS: `X-RateLimit-Limit` por dia,
        `X-RateLimit-Credits-Used` por requisição e `X-RateLimit-Remaining`. Medido neste
        projeto: página custa 10 créditos, `group_by` custa 1, e o teto sem chave é 1.000/dia.
        Não bloqueia nem cobra nada — só deixa o número disponível para a UI avisar quando
        estiver acabando, em vez de o usuário descobrir com um 429 no meio de uma busca.
        """
        try:
            def _num(chave):
                v = headers.get(chave)
                return float(v) if v not in (None, "") else None

            restante = _num("X-RateLimit-Remaining")
            if restante is None:
                return
            self.rate_limit = {
                "remaining": restante,
                "limit": _num("X-RateLimit-Limit"),
                "used_by_last": _num("X-RateLimit-Credits-Used"),
                "reset_seconds": _num("X-RateLimit-Reset"),
                "remaining_usd": _num("X-RateLimit-Remaining-USD"),
            }
        except Exception:
            pass          # header ausente ou malformado nunca pode derrubar a requisição

    def fetch_url(self, url: str, headers: Optional[Dict[str, str]] = None, cancel_event = None, rate_limit_delay: float = 0.0, no_cache: bool = False) -> str:
        # Check cache (no_cache=True para paginação por cursor de scroll que REPETE a URL,
        # p.ex. Crossref — cachear devolveria a mesma página e travaria a paginação).
        if not no_cache:
            cached = self._cache_get(url)
            if cached is not None:
                return cached

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
                    self._capture_rate_limit(response.headers)
                    if not no_cache:
                        self._cache_put(url, data)
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
