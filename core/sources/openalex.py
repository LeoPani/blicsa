import urllib.parse
import urllib.error
import json
import logging
import re
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import AuthError, PaginationLimitError, RateLimitError, SearchProvider
from core.document_types import normalize_document_type

logger = logging.getLogger("OpenAlexProvider")

def openalex_api_key() -> str:
    """Chave do OpenAlex, se o usuário tiver configurado uma nos Ajustes.

    Opcional, mas não mais um detalhe. O OpenAlex descontinuou o *polite pool* em fevereiro
    de 2026: o `mailto` continua sendo enviado como identificação de boa prática, e medido
    lado a lado ele já não muda franquia nenhuma. O que separa os dois patamares hoje é a
    chave — cerca de 1.000 créditos por dia sem ela, cerca de 10.000 com ela.

    Vazia por padrão, e o app funciona assim. Uma página de busca custa 10 créditos, então
    sem chave dá algo como 100 páginas por dia.
    """
    try:
        from core.settings import get_credencial
        return get_credencial("openalex").strip()
    except Exception:
        return ""


class OpenAlexProvider(SearchProvider):
    DISPLAY_NAME = "OpenAlex"
    #: Teto da paginação por `page` na API: `page × per_page` não pode passar de 10.000.
    #: Vale **só para a navegação**; a importação usa cursor e alcança o conjunto inteiro.
    BROWSE_MAX_RESULTS = 10_000

    _FIELD_MAP = {
        "title":    "title.search",
        "author":   "authorships.author.display_name.search",
        "abstract": "title_and_abstract.search",
        "all":      "default.search",
    }

    @staticmethod
    def _ou(valor) -> str:
        """Valor de faceta → sintaxe do OpenAlex.

        Lista vira `a|b|c`, que é **OR dentro do mesmo campo**; campos diferentes são
        separados por vírgula, que é AND. É a semântica do "Refine Results" do Web of
        Science e a que o usuário espera ao marcar duas caixas da mesma categoria.
        """
        if isinstance(valor, (list, tuple, set)):
            return "|".join(str(v) for v in valor if str(v).strip())
        return str(valor)

    def __init__(self, *a, api_key: str | None = None, **kw):
        super().__init__(*a, **kw)
        # `None` = ler dos Ajustes a cada instância; string vazia = sem chave (o padrão).
        self.api_key = openalex_api_key() if api_key is None else str(api_key or "")

    def fetch_url(self, url: str, *a, **kw) -> str:
        """Anexa a chave da API, quando houver, a QUALQUER requisição deste provider.

        Um único ponto em vez de repetir o parâmetro nos cinco lugares que montam URL — e
        `get_by_doi`, `count`, `facet`, `browse` e `search` passam todos por aqui.
        """
        if self.api_key and "api_key=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}api_key={urllib.parse.quote(self.api_key)}"
        return super().fetch_url(url, *a, **kw)

    def _oa_filter(self, query: str, filters: Optional[Dict[str, Any]]) -> str:
        """Valor de `filter=` a partir de filtros padrão + busca por campo (busca avançada)."""
        f = filters or {}
        fp = []
        # Anos escolhidos na faceta (lista de valores) têm precedência sobre a faixa.
        if f.get("year_values"):
            fp.append(f"publication_year:{self._ou(f['year_values'])}")
        elif f.get("year_start") and f.get("year_end"):
            fp.append(f"publication_year:{f['year_start']}-{f['year_end']}")
        elif f.get("year_start"):
            fp.append(f"publication_year:>{int(f['year_start']) - 1}")
        elif f.get("year_end"):
            fp.append(f"publication_year:<{int(f['year_end']) + 1}")
        if f.get("type"):
            fp.append(f"type:{self._ou(f['type'])}")
        if f.get("is_oa") is not None:
            fp.append(f"is_oa:{str(f['is_oa']).lower()}")
        if f.get("language"):
            fp.append(f"language:{self._ou(f['language'])}")
        if f.get("source"):
            fp.append(f"primary_location.source.id:{self._ou(f['source'])}")
        if f.get("author"):
            fp.append(f"authorships.author.id:{self._ou(f['author'])}")
        # Linhas de busca avançada por campo (ANDadas via vírgula no OpenAlex).
        for field, value in (f.get("fields") or []):
            v = str(value).strip()
            if v:
                fp.append(f"{self._FIELD_MAP.get(field, 'default.search')}:{v}")
        if query and query.strip():
            fp.append(f"default.search:{query.strip()}")
        return ",".join(fp)

    #: Campos que `_normalize_work` usa (o resto da obra não é lido na importação).
    CAMPOS_IMPORTACAO = ("id,doi,title,publication_year,authorships,keywords,concepts,"
                         "abstract_inverted_index,cited_by_count,referenced_works,"
                         "primary_location,open_access,type,language")
    #: Teto da paginação numerada do OpenAlex (page × per_page). Acima, só cursor.
    LIMITE_PAGINACAO = 10_000
    #: Páginas pedidas ao mesmo tempo (o OpenAlex aceita 10 pedidos por segundo).
    PAGINAS_PARALELAS = 4

    def _search_paginas(self, base_url, params, max_results, progress_cb, cancel_event):
        """Importação por páginas numeradas, 4 de cada vez, entregues EM ORDEM.

        A página 1 vem sozinha (traz o total); as demais saem em paralelo. Uma página que
        falha encerra a importação ali, com o mesmo `stop_reason`/`stop_error` do cursor:
        o que já chegou fica, e a trilha de contagem diz onde parou.
        """
        import math
        from concurrent.futures import ThreadPoolExecutor

        params = {k: v for k, v in params.items() if k != "cursor"}
        per_page = int(params.get("per_page") or 200)
        count_fetched = 0

        def pagina(n):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Search cancelled by user")
            q = dict(params, page=n)
            return json.loads(self.fetch_url(f"{base_url}?{urllib.parse.urlencode(q)}",
                                              cancel_event=cancel_event))

        self.pages_fetched = 1
        try:
            data = pagina(1)
        except InterruptedError:
            self.stop_reason = "cancelado"
            raise
        except Exception as e:
            self.stop_reason = f"erro de rede na página 1: {e}"
            self.stop_error = True
            logger.error(f"[OpenAlex] parou: {self.stop_reason}")
            return
        results = data.get("results", []) or []
        total = int((data.get("meta") or {}).get("count", len(results)) or 0)
        self.total_available = total
        alvo = min(max_results, total)
        if not results:
            self.stop_reason = "exauriu (sem resultados)"
            logger.info(f"[OpenAlex] parou: {self.stop_reason} · páginas=1 · registros=0")
            return
        # A ordem por relevância pode mudar um pouco entre pedidos de páginas diferentes:
        # na verificação ao vivo (04/10), 2 de 3000 vieram repetidos. Repetido é descartado
        # e, no fim, mais páginas completam o que faltou.
        vistos: set = set()

        def novos(lote):
            for w in lote:
                chave = w.get("id") or id(w)
                if chave in vistos:
                    continue
                vistos.add(chave)
                yield w

        for w in list(novos(results))[:alvo]:
            yield self._normalize_work(w)
            count_fetched += 1
        if progress_cb and total:
            progress_cb(count_fetched, alvo)

        n_paginas = min(math.ceil(alvo / per_page), self.LIMITE_PAGINACAO // per_page)
        if n_paginas > 1 and count_fetched < alvo:
            ex = ThreadPoolExecutor(max_workers=self.PAGINAS_PARALELAS)
            try:
                futuros = [ex.submit(pagina, n) for n in range(2, n_paginas + 1)]
                for n, fut in enumerate(futuros, start=2):
                    if cancel_event and cancel_event.is_set():
                        self.stop_reason = "cancelado"
                        raise InterruptedError("Search cancelled by user")
                    try:
                        dados = fut.result()
                    except InterruptedError:
                        self.stop_reason = "cancelado"
                        raise
                    except Exception as e:
                        self.stop_reason = f"erro de rede na página {n}: {e}"
                        self.stop_error = True
                        logger.error(f"[OpenAlex] parou: {self.stop_reason}")
                        break
                    self.pages_fetched = n
                    lote = dados.get("results", []) or []
                    if not lote:
                        self.stop_reason = "exauriu (sem resultados)"
                        break
                    for w in novos(lote):
                        if count_fetched >= alvo:
                            break
                        yield self._normalize_work(w)
                        count_fetched += 1
                    if progress_cb:
                        progress_cb(count_fetched, alvo)
                    if count_fetched >= alvo:
                        break
            finally:
                ex.shutdown(wait=False, cancel_futures=True)
            # Completa o que os repetidos tiraram, página a página, dentro do teto da API.
            extra = n_paginas + 1
            while (not self.stop_error and self.stop_reason is None and count_fetched < alvo
                   and extra * per_page <= self.LIMITE_PAGINACAO):
                try:
                    dados = pagina(extra)
                except InterruptedError:
                    self.stop_reason = "cancelado"
                    raise
                except Exception as e:
                    self.stop_reason = f"erro de rede na página {extra}: {e}"
                    self.stop_error = True
                    break
                self.pages_fetched = extra
                lote = dados.get("results", []) or []
                if not lote:
                    break
                for w in novos(lote):
                    if count_fetched >= alvo:
                        break
                    yield self._normalize_work(w)
                    count_fetched += 1
                extra += 1
        if self.stop_reason is None:
            self.stop_reason = ("atingiu limite" if count_fetched >= max_results
                                else "fim dos resultados")
        logger.info(f"[OpenAlex] parou: {self.stop_reason} · páginas={self.pages_fetched} · "
                    f"registros={count_fetched}")

    def _normalize_work(self, w: Dict[str, Any]) -> Dict[str, Any]:
        authors = "; ".join(
            a.get("author", {}).get("display_name", "")
            for a in w.get("authorships", []) if a.get("author", {}).get("display_name"))
        # Os conceitos legados são categorias hierárquicas amplas (incluem, por exemplo,
        # "Computer science" em quase todo artigo de IA). OpenAlex fornece keywords mais
        # específicas; só recorrer aos conceitos quando a resposta antiga não as trouxer.
        keyword_items = w.get("keywords") or w.get("concepts") or []
        kws = "; ".join(
            item.get("display_name", "")
            for item in keyword_items
            if isinstance(item, dict) and item.get("display_name")
        )
        abstract = w.get("abstract", "") or ""
        if not abstract and w.get("abstract_inverted_index"):
            inv = w["abstract_inverted_index"]
            word_pos = [(pos, word) for word, positions in inv.items() for pos in positions]
            abstract = " ".join(wd for _, wd in sorted(word_pos))
        src = ""
        if w.get("primary_location") and w["primary_location"].get("source"):
            src = w["primary_location"]["source"].get("display_name", "") or ""
        oa_info = w.get("open_access", {})
        return {
            "authors": authors, "title": w.get("title", "") or "",
            "openalex_id": str(w.get("id") or ""),
            "year": int(w.get("publication_year") or 0), "source": src, "keywords": kws,
            "document_type": normalize_document_type(w.get("type")),
            "abstract": abstract, "citations": int(w.get("cited_by_count", 0)),
            "doi": w.get("doi", "") or "", "references": "; ".join(w.get("referenced_works", [])),
            "origin": "OpenAlex", "language": str(w.get("language") or ""),
            "is_oa": bool(oa_info.get("is_oa", False)), "oa_url": str(oa_info.get("oa_url") or ""),
        }

    def get_by_doi(self, doi: str, cancel_event=None) -> Optional[Dict[str, Any]]:
        """Lookup EXATO de um registro pelo DOI, via endpoint canônico do OpenAlex
        (/works/https://doi.org/{doi}), já normalizado por _normalize_work.
        Retorna None se não achar. Não é a busca textual "doi:..." (que é errada:
        vira full-text e pode trazer o paper errado ou nada)."""
        raw = (doi or "").strip()
        if not raw:
            return None
        # Normaliza qualquer forma para o DOI nu (10.xxxx/yyyy).
        for prefix in ("https://doi.org/", "http://doi.org/",
                       "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
            if raw.lower().startswith(prefix):
                raw = raw[len(prefix):]
                break
        raw = raw.strip().strip("/")
        if not raw:
            return None
        url = f"https://api.openalex.org/works/https://doi.org/{raw}?mailto={self.mailto}"
        try:
            data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        except (AuthError, RateLimitError):
            # "DOI não encontrado" e "sua chave foi recusada" são situações diferentes com
            # ações opostas, e devolver None para as duas apagava a segunda: quem chamasse
            # via extensão ou pela biblioteca de seminais via "não identificado pela API"
            # para TODAS as referências, sem nunca saber que o problema era a credencial.
            raise
        except Exception as e:
            logger.warning(f"[OpenAlex] get_by_doi falhou para '{raw}': {e}")
            return None
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return self._normalize_work(data)

    def get_by_id(self, work_id: str, cancel_event=None) -> Optional[Dict[str, Any]]:
        """Resolve um identificador W do OpenAlex exatamente, sem busca textual.

        Referências de resultados OpenAlex contêm apenas ``https://openalex.org/W...``.
        Interpretar esse código com IA inventava autores e títulos; a consulta exata entrega
        os metadados correspondentes ou ``None`` se não houver registro.
        """
        match = re.fullmatch(r"(?:https?://openalex\.org/)?(W\d+)",
                             str(work_id or "").strip(), flags=re.I)
        if not match:
            return None
        url = f"https://api.openalex.org/works/{match.group(1).upper()}?mailto={self.mailto}"
        try:
            data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        except (AuthError, RateLimitError):
            raise
        except Exception as e:
            logger.warning("[OpenAlex] get_by_id falhou para %s: %s", match.group(1), e)
            return None
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return self._normalize_work(data)

    def count(self, query: str, filters: Optional[Dict[str, Any]] = None, cancel_event=None) -> int:
        """Total de resultados numa ÚNICA request barata (nada é baixado)."""
        params: Dict[str, Any] = {"per_page": 1, "mailto": self.mailto}
        flt = self._oa_filter(query, filters)
        if flt:
            params["filter"] = flt
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        return int(data.get("meta", {}).get("count", 0))

    # Facetas suportadas: campo do `group_by` → chave usada na UI. É o equivalente ao
    # "Refine Results" do Web of Science, e a graça é que cada chamada devolve a contagem do
    # UNIVERSO INTEIRO sem baixar um registro sequer.
    FACETS = {
        "type": "type",
        "language": "language",
        "publication_year": "publication_year",
        "is_oa": "open_access.is_oa",
        "source": "primary_location.source.id",
        "author": "authorships.author.id",
    }

    def facet(self, campo: str, query: str, filters: Optional[Dict[str, Any]] = None,
              top: int = 10, cancel_event=None) -> list[dict]:
        """Contagens de uma faceta sobre o universo da busca, via `group_by`.

        Devolve [{"key", "label", "count"}], já cortado no top-N e sem a categoria
        "unknown" (que o OpenAlex devolve para registros sem o campo e só polui a sidebar).
        """
        gb = self.FACETS.get(campo)
        if not gb:
            raise ValueError(f"faceta não suportada pelo OpenAlex: {campo!r}")
        # SEM `per_page`: uma resposta de `group_by` não traz `results` (medido: results=0,
        # custo 1 crédito com ou sem o parâmetro), mas `per_page=1` TRUNCA a lista de grupos
        # para um só — a sidebar mostraria "Artigo (29.730)" e mais nada. Custou uma medição
        # ao vivo para aparecer, porque a captura de tela usava facetas sintéticas.
        params: Dict[str, Any] = {"group_by": gb, "mailto": self.mailto}
        flt = self._oa_filter(query, filters)
        if flt:
            params["filter"] = flt
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        saida = []
        for g in data.get("group_by", []):
            chave = g.get("key")
            if chave in (None, "unknown", ""):
                continue
            saida.append({"key": str(chave),
                          "label": str(g.get("key_display_name") or chave),
                          "count": int(g.get("count", 0) or 0)})
        saida.sort(key=lambda d: (-d["count"], d["label"]))
        return saida[:max(1, int(top))]

    def browse(self, query: str, filters: Optional[Dict[str, Any]] = None,
               page: int = 1, per_page: int = 25, sort: Optional[str] = None, cancel_event=None):
        """Paginação BÁSICA pulável (tipo Scopus): devolve (records_da_página, total).
        Não colhe tudo — só a página pedida. Navega os primeiros 10.000 do OpenAlex.

        Além de `BROWSE_MAX_RESULTS` a API recusa a requisição: levanta
        `PaginationLimitError` **antes** de gastar a chamada, porque o teto é conhecido e
        gastar crédito para receber um 400 previsível não ajuda ninguém. A importação
        (`search`) usa cursor e não tem esse teto.
        """
        pp = max(1, min(200, per_page))
        pg = max(1, page)
        if self.BROWSE_MAX_RESULTS and pg * pp > self.BROWSE_MAX_RESULTS:
            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pg, pp, self.DISPLAY_NAME)
        params: Dict[str, Any] = {"per_page": pp, "page": pg, "mailto": self.mailto}
        flt = self._oa_filter(query, filters)
        if flt:
            params["filter"] = flt
        # "date" com order=asc vira publication_date:asc — é o "mais antigo primeiro" da UI.
        f = filters or {}
        chave_sort = f.get("sort") or sort
        direcao = "asc" if str(f.get("order", "")).lower() == "asc" else "desc"
        oa_sort = {"citations": f"cited_by_count:{direcao}",
                   "date": f"publication_date:{direcao}"}.get(chave_sort)
        if oa_sort:
            params["sort"] = oa_sort
        url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
        try:
            data = json.loads(self.fetch_url(url, cancel_event=cancel_event))
        except urllib.error.HTTPError as e:
            # Rede de segurança para o dia em que o teto da API mudar e o pré-cheque acima
            # ficar defasado: o 400 de paginação vira a MESMA mensagem explicativa, nunca um
            # erro genérico. Só o 400; qualquer outro código continua subindo como está.
            if e.code == 400:
                raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pg, pp, self.DISPLAY_NAME) from e
            raise
        total = int(data.get("meta", {}).get("count", 0))
        records = [self._normalize_work(w) for w in data.get("results", [])]
        return records, total

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        base_url = "https://api.openalex.org/works"

        params: Dict[str, Any] = {
            "per_page": min(200, max_results),
            "cursor": "*",
            "mailto": self.mailto
        }

        import re
        q_str = query.strip()
        extra_fields = []

        # Sintaxe legada do Query Builder (TITLE()/AUTHOR()/...) vira busca por campo.
        if re.search(r'(TITLE|AUTHOR|YEAR|TITLE-ABS-KEY)\(', q_str):
            year_vals = []
            for match in re.finditer(r'(TITLE-ABS-KEY|TITLE|AUTHOR|YEAR)\("?([^")]+)"?\)', q_str):
                field, val = match.groups()
                val = val.strip()
                if field == "TITLE":
                    extra_fields.append(("title", val))
                elif field == "AUTHOR":
                    extra_fields.append(("author", val))
                elif field == "TITLE-ABS-KEY":
                    extra_fields.append(("all", val))
                elif field == "YEAR":
                    year_vals.append(val)
            q_str = ""
            if year_vals and not (filters or {}).get("year_start"):
                filters = dict(filters or {})
                filters["year_start"] = filters["year_end"] = year_vals[0]

        if extra_fields:
            filters = dict(filters or {})
            filters["fields"] = list(filters.get("fields") or []) + extra_fields

        flt = self._oa_filter(q_str, filters)
        if flt:
            params["filter"] = flt

        # Ordenação server-side ("relevance" = padrão do OpenAlex, sem param).
        oa_sort = {"citations": "cited_by_count:desc",
                   "date": "publication_date:desc"}.get((filters or {}).get("sort"))
        if oa_sort:
            params["sort"] = oa_sort

        count_fetched = 0
        total_results = None
        # BUG-A: rastreio explícito do motivo de parada (nada de parada silenciosa).
        self.stop_reason = None
        self.stop_error = False
        self.pages_fetched = 0
        # Total REAL da base (meta.count), independente do limite de download. O progress_cb
        # recebe min(limite, total) porque é alvo de barra de progresso — usar aquele valor
        # como "Encontrados" escondia do usuário que existiam mais resultados.
        self.total_available = 0

        # Só os campos que `_normalize_work` lê: a resposta cai de ~15 para ~1,7 MB por 1000.
        params["select"] = self.CAMPOS_IMPORTACAO
        if max_results <= self.LIMITE_PAGINACAO and self.PAGINAS_PARALELAS > 1:
            # Até 10.000 (o teto da paginação numerada do OpenAlex): páginas em paralelo.
            # Medido em 04/10 na internet do autor: 1000 registros de 18,1 s para 5,5 s, mesmos IDs.
            yield from self._search_paginas(base_url, params, max_results, progress_cb,
                                            cancel_event)
            return

        while count_fetched < max_results:
            if cancel_event and cancel_event.is_set():
                self.stop_reason = "cancelado"
                raise InterruptedError("Search cancelled by user")

            query_str = urllib.parse.urlencode(params)
            url = f"{base_url}?{query_str}"

            self.pages_fetched += 1
            try:
                # fetch_url já faz 3 tentativas com backoff 1s/2s/4s antes de levantar.
                raw_data = self.fetch_url(url, cancel_event=cancel_event)
                data = json.loads(raw_data)
            except Exception as e:
                self.stop_reason = f"erro de rede na página {self.pages_fetched}: {e}"
                self.stop_error = True
                logger.error(f"[OpenAlex] parou: {self.stop_reason}")
                break

            results = data.get("results", [])
            meta = data.get("meta", {})
            
            if total_results is None:
                total_results = meta.get("count", len(results))
                self.total_available = int(total_results or 0)

            if not results:
                self.stop_reason = "exauriu (sem resultados)"
                break

            for w in results:
                if count_fetched >= max_results:
                    break
                yield self._normalize_work(w)
                count_fetched += 1

            if progress_cb and total_results:
                progress_cb(count_fetched, min(max_results, total_results))

            next_cursor = meta.get("next_cursor")
            if not next_cursor or next_cursor == params.get("cursor"):
                self.stop_reason = "cursor encerrado (fim dos resultados)"
                break
            params["cursor"] = next_cursor

        if self.stop_reason is None:
            self.stop_reason = "atingiu limite"
        logger.info(f"[OpenAlex] parou: {self.stop_reason} · páginas={self.pages_fetched} · registros={count_fetched}")
