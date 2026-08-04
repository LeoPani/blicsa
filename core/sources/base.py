import time
import urllib.request
import urllib.parse
import json
import logging
from collections import OrderedDict
from typing import Iterator, Callable, Dict, Any, Optional

logger = logging.getLogger("SearchProvider")


class RateLimitError(IOError):
    """Limite de uso da API atingido (HTTP 429 depois de esgotar os retries).

    Subclasse de IOError de propósito: quem já tratava erro de rede genérico continua
    funcionando, e quem quiser dar a mensagem específica pega este tipo.
    """

    #: Chave i18n da mensagem que a UI deve exibir.
    i18n_key = "search.error_rate_limit"

    def __init__(self, url: str = ""):
        super().__init__("limite de uso da API atingido (HTTP 429)")
        self.url = url


class PaginationLimitError(IOError):
    """Fronteira de paginação da API no modo navegação (`page` × `per_page`).

    Não é erro de rede nem culpa do usuário: é um teto da API. O OpenAlex recusa
    `page × per_page > 10.000` — navegar além disso é impossível **por paginação**, mas o
    conjunto inteiro continua acessível pela importação, que usa cursor e não tem teto.

    Por isso a mensagem precisa ser específica: um erro genérico ou uma página em branco
    deixaria o usuário achando que os resultados acabaram, quando existem milhares.
    """

    #: Chave i18n da mensagem que a UI deve exibir.
    i18n_key = "browse.error_page_limit"

    def __init__(self, limite: int = 0, page: int = 0, per_page: int = 0, fonte: str = ""):
        super().__init__(
            f"paginação limitada a {limite} resultados "
            f"(página {page} × {per_page} por página excede o teto)")
        self.limite = int(limite)
        self.page = int(page)
        self.per_page = int(per_page)
        self.fonte = str(fonte or "")
        #: Parâmetros da mensagem. OpenAlex e PubMed têm o mesmo teto e a mesma saída
        #: (importar em vez de navegar); só o nome da fonte muda.
        self.i18n_args = {"fonte": self.fonte}

# Identidade única do app nas APIs (OpenAlex/Crossref pedem um mailto de contato).
MAILTO = "blicsa.app@gmail.com"

# Teto do cache de respostas por provider (LRU).
CACHE_MAX_ENTRIES = 50

class SearchProvider:
    #: Teto de resultados alcançáveis pela paginação por `page` (modo navegação).
    #: `0` = sem teto conhecido. Quem tem teto declara o seu e a navegação avisa ao chegar
    #: lá, em vez de devolver erro genérico ou página em branco.
    BROWSE_MAX_RESULTS = 0

    #: Nome da fonte como aparece para o usuário nas mensagens.
    DISPLAY_NAME = ""

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
        ultimo_http = None
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
                    ultimo_http = e.code
                else:
                    raise e
            except Exception as e:
                logger.warning(f"Error requesting {url}: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
                retries -= 1
        # 429 esgotado não é "erro de rede genérico": é o teto de uso da API. Levantar um
        # tipo próprio deixa a UI dizer o que fazer (chave gratuita nos Ajustes) em vez de
        # mostrar "Failed to fetch https://api.openalex.org/works?per_page=25&mailto=..."
        if ultimo_http == 429:
            raise RateLimitError(url)
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
