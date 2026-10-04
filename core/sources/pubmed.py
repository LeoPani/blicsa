import urllib.parse
import json
import logging
import re
from typing import Iterator, Dict, Any, Optional, Callable
from core.sources.base import SearchProvider, PaginationLimitError
from core.document_types import normalize_document_type

logger = logging.getLogger("PubMedProvider")

# PubMed usa códigos ISO 639-2 ([LA]); o app envia ISO 639-1 (pt, en...).
_ISO639_1_TO_2 = {
    "pt": "por", "en": "eng", "fr": "fre", "es": "spa", "de": "ger",
    "it": "ita", "ru": "rus", "zh": "chi", "ja": "jpn", "ko": "kor",
}


def _pubmed_lang_code(code: str) -> Optional[str]:
    """Converte ISO 639-1 -> 639-2 para o filtro [LA] do PubMed.
    Aceita também um 639-2 já válido. Desconhecido -> None (não aplicar filtro)."""
    c = str(code).strip().lower()
    if c in _ISO639_1_TO_2:
        return _ISO639_1_TO_2[c]
    if c in _ISO639_1_TO_2.values():
        return c
    return None


#: Registros por EFetch. O NCBI aceita bem lotes grandes vindos do histórico; 200 equilibra
#: número de requisições (3/s sem chave) e tamanho de resposta.
PUBMED_EFETCH_BATCH = 200

#: Teto DURO do PubMed por busca, medido contra a API em 2026-08-04.
#:
#: `usehistory=y` + WebEnv **não** o remove — foi a hipótese testada e refutada. Palavras do
#: próprio NCBI ao pedir `retstart=10000` com histórico válido:
#:
#:   "'retstart' cannot be larger than 9998. For PubMed, ESearch can only retrieve the first
#:    9,999 records matching the query. To obtain more than 9,999 PubMed records, consider
#:    using EDirect..."
#:
#: Reproduzível: `retstart=9950&retmax=50` devolve 49 registros; `retstart=10000` devolve 400.
#: O histórico continua valendo a pena (uma ESearch só, sem trafegar lista de PMIDs), mas o
#: teto é da API. O que o app pode garantir é que ele **não seja silencioso**.
PUBMED_MAX_FETCHABLE = 9_999


def pubmed_api_key() -> str:
    """Chave do NCBI, se o usuário tiver configurado uma na aba de Credenciais.

    Opcional: sem ela o NCBI permite 3 requisições por segundo por IP; com ela, 10. Não
    muda o que é acessível, muda a velocidade — e o app já respeita o teto com
    `rate_limit_delay`.
    """
    try:
        from core.settings import get_credencial
        return get_credencial("pubmed").strip()
    except Exception:
        return ""


class PubMedProvider(SearchProvider):
    DISPLAY_NAME = "PubMed"
    #: Teto da paginação do ESearch (`retstart + retmax` <= 10.000 no NCBI). Vale só para a
    #: navegação: a importação usa `usehistory=y` + EFetch e alcança o conjunto inteiro.
    BROWSE_MAX_RESULTS = 10_000

    def __init__(self, *a, api_key: str | None = None, **kw):
        super().__init__(*a, **kw)
        # `None` = ler das Credenciais a cada instância; string vazia = sem chave (o padrão).
        self.api_key = pubmed_api_key() if api_key is None else str(api_key or "")

    def fetch_url(self, url: str, *a, **kw) -> str:
        """Anexa a chave do NCBI, quando houver, a QUALQUER requisição deste provider.

        Um ponto só, como no OpenAlex: o PubMed monta URL em seis lugares (`count`,
        `browse`, `search`, `_pmids_sem_historico`, esearch e efetch), e repetir o parâmetro
        em cada um é como as duas chamadas soltas do `main.py` acabaram sem chave nenhuma.
        """
        if self.api_key and "api_key=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}api_key={urllib.parse.quote(self.api_key)}"
        return super().fetch_url(url, *a, **kw)

    def count(self, query: str, filters: Optional[Dict[str, Any]] = None, cancel_event=None) -> int:
        """Total de resultados (esearchresult.count) com retmax=0 — request barata.

        Usa o MESMO `term` da importação (`_term`). Antes montava o seu, sem ano
        só-inicial/só-final nem acesso aberto, e a contagem do aviso de volume divergia do
        que a importação depois baixava.
        """
        term = self._term(query, filters)
        params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 0}
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
        data = json.loads(self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=0.35))
        return int(data.get("esearchresult", {}).get("count", 0))

    # O PubMed não tem `group_by`; as facetas ficariam mentindo na UI (origem do BUG-02).
    FACETS: Dict[str, str] = {}

    def _term(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """Monta o `term` do E-utilities a partir da query + filtros.

        Fonte ÚNICA do termo para `count`, `browse` e `search`. Antes eram três cópias e só a
        do `search` tratava ano só-inicial/só-final e acesso aberto: na navegação, preencher
        só o "ano inicial" ou marcar "acesso aberto" era ignorado em silêncio, e o total
        mostrado não era o da importação (auditoria das bases, 2026-10).
        """
        partes = [query.strip()] if query.strip() else []
        f = filters or {}
        if f.get("year_start") and f.get("year_end"):
            partes.append(f"({f['year_start']}:{f['year_end']}[DP])")
        elif f.get("year_start"):
            partes.append(f"({f['year_start']}:3000[DP])")
        elif f.get("year_end"):
            partes.append(f"(1800:{f['year_end']}[DP])")
        if f.get("type"):
            partes.append(f"({f['type']}[PT])")
        if f.get("is_oa"):
            partes.append("free full text[SB]")
        if f.get("language"):
            la = _pubmed_lang_code(f["language"])
            if la:
                partes.append(f"{la}[LA]")
            else:
                logger.warning(
                    f"Idioma '{f['language']}' sem mapeamento ISO 639-2; "
                    f"filtro de idioma NÃO aplicado no PubMed (evita zero silencioso)."
                )
        return " AND ".join(partes) if partes else "all[Filter]"

    def _parse_medline(self, texto: str) -> list[Dict[str, Any]]:
        """MEDLINE cru → lista de dicionários por tag (mesmo parser do `search`)."""
        registros, atual, tag_atual = [], {}, None
        for linha in texto.splitlines():
            if not linha.strip():
                if atual:
                    registros.append(atual)
                    atual, tag_atual = {}, None
                continue
            m = re.match(r"^([A-Z0-9]{2,4})\s*-\s*(.*)$", linha)
            if m:
                tag, valor = m.group(1), m.group(2).strip()
                tag_atual = tag
                atual[tag] = (atual[tag] + "; " + valor) if tag in atual else valor
            elif tag_atual and linha.startswith("      "):
                atual[tag_atual] = atual.get(tag_atual, "") + " " + linha.strip()
        if atual:
            registros.append(atual)
        return registros

    def _pmids_sem_historico(self, term: str, retstart: int, retmax: int,
                             sort_value: str = "", cancel_event=None,
                             rate_limit_delay: float = 0.35) -> list:
        """Fatia de PMIDs pela ESearch comum, para quando o histórico não estiver disponível.

        Caminho degradado e assumidamente limitado: `retstart + retmax` não passa de 10.000
        no NCBI. Existe para a importação não morrer se o `usehistory` falhar — e quem chama
        já registrou em `stop_reason` que o teto voltou a valer.
        """
        params = {"db": "pubmed", "term": term, "retmode": "json",
                  "retmax": int(retmax), "retstart": int(retstart)}
        if sort_value:
            params["sort"] = sort_value
        url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
               + urllib.parse.urlencode(params))
        try:
            dados = json.loads(self.fetch_url(url, cancel_event=cancel_event,
                                              rate_limit_delay=rate_limit_delay))
        except Exception as e:
            logger.error(f"[PubMed] ESearch sem histórico falhou: {e}")
            return []
        return list(dados.get("esearchresult", {}).get("idlist", []) or [])

    def _record_from_medline(self, r: Dict[str, Any]) -> Dict[str, Any]:
        kw = r.get("MH", r.get("OT", r.get("KW", "")))
        dp = r.get("DP", r.get("DA", "0"))
        m_ano = re.search(r"\b(19|20)\d{2}\b", dp)
        # O DOI pode estar no LID ou só no AID (o LID às vezes traz apenas o [pii]). Antes só
        # o LID era olhado e, sem "[doi]" nele, o texto inteiro do LID virava o DOI:
        # "S0140-6736(20)30183-5 [pii]" ia para o campo `doi`, quebrando link, exportação e a
        # deduplicação por DOI entre bases (auditoria das bases, 2026-10).
        m_doi = None
        for tag in ("LID", "AID"):
            m_doi = re.search(r"(\S+)\s+\[doi\]", r.get(tag, "") or "")
            if m_doi:
                break
        return {
            "authors": r.get("AU", r.get("FAU", "")),
            "title": r.get("TI", ""),
            "year": int(m_ano.group()) if m_ano else 0,
            "source": r.get("JT", r.get("TA", "")),
            "document_type": normalize_document_type(r.get("PT", "")),
            "keywords": kw,
            "abstract": r.get("AB", ""),
            "citations": 0,
            "doi": m_doi.group(1) if m_doi else "",
            "references": "",
            "origin": "PubMed",
            "language": r.get("LA", ""),
            "is_oa": False,
            "oa_url": "",
        }

    def browse(self, query: str, filters: Optional[Dict[str, Any]] = None,
               page: int = 1, per_page: int = 25, sort: Optional[str] = None, cancel_event=None):
        """Uma página via ESearch(retstart) + EFetch do lote. Devolve (registros, total)."""
        por_pagina = max(1, min(100, int(per_page)))
        pagina = max(1, int(page))
        if self.BROWSE_MAX_RESULTS and pagina * por_pagina > self.BROWSE_MAX_RESULTS:
            raise PaginationLimitError(self.BROWSE_MAX_RESULTS, pagina, por_pagina,
                                       self.DISPLAY_NAME)
        inicio = max(0, (pagina - 1) * por_pagina)
        params = {"db": "pubmed", "term": self._term(query, filters), "retmode": "json",
                  "retmax": por_pagina, "retstart": inicio}
        if ((filters or {}).get("sort") or sort) == "date":
            params["sort"] = "pub_date"
        url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
               + urllib.parse.urlencode(params))
        dados = json.loads(self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=0.35))
        res = dados.get("esearchresult", {})
        total = int(res.get("count", 0) or 0)
        ids = res.get("idlist", []) or []
        if not ids:
            return [], total

        efetch = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
                  + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids),
                                            "retmode": "text", "rettype": "medline"}))
        texto = self.fetch_url(efetch, cancel_event=cancel_event, rate_limit_delay=0.35)
        return [self._record_from_medline(r) for r in self._parse_medline(texto)], total

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event = None
    ) -> Iterator[Dict[str, Any]]:
        # PubMed Rate Limit: max 3 requests per second
        rate_limit_delay = 0.35
        
        # 1. Build term — mesma fonte que `count` e `browse`.
        term = self._term(query, filters)

        # BUG-A: rastreio de parada.
        self.stop_reason = None
        self.stop_error = False
        self.pages_fetched = 0
        # Total REAL da base (esearchresult.count), independente do retmax pedido.
        self.total_available = 0

        # 2. ESearch COM HISTÓRICO (usehistory=y).
        #
        # A versão anterior pedia `retmax=max_results` e ficava com a lista de PMIDs na mão.
        # O NCBI corta `retmax` em 10.000: uma importação de 25.000 voltava com 10.000 **e
        # nenhum aviso** — o mesmo teto silencioso que o OpenAlex tinha. Com `usehistory=y` o
        # servidor guarda o conjunto inteiro e devolve `WebEnv` + `QueryKey`; o EFetch pagina
        # por `retstart` sobre esse conjunto, sem teto.
        #
        # `retmax=0` porque os PMIDs deixaram de ser necessários: quem os lê agora é o
        # próprio EFetch, direto do histórico. A requisição fica barata e traz só a contagem.
        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        esearch_params = {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "usehistory": "y",
            "retmax": 0,
            "retstart": 0
        }
        # Ordenação server-side (PubMed não tem citações; 'date' → pub_date, resto = relevância).
        if (filters or {}).get("sort") == "date":
            esearch_params["sort"] = "pub_date"
        
        query_str = urllib.parse.urlencode(esearch_params)
        url = f"{esearch_url}?{query_str}"
        
        try:
            raw_data = self.fetch_url(url, cancel_event=cancel_event, rate_limit_delay=rate_limit_delay)
            esearch_data = json.loads(raw_data)
        except Exception as e:
            self.stop_reason = f"erro de rede na ESearch: {e}"
            self.stop_error = True
            logger.error(f"[PubMed] parou: {self.stop_reason}")
            return

        res = esearch_data.get("esearchresult", {})
        total_results = int(res.get("count", 0) or 0)
        self.total_available = total_results
        # O NCBI devolve as chaves em minúsculas no retmode=json.
        webenv = str(res.get("webenv") or "")
        query_key = str(res.get("querykey") or res.get("query_key") or "")

        if not total_results:
            self.stop_reason = "exauriu (sem resultados)"
            logger.info(f"[PubMed] parou: {self.stop_reason}")
            return

        alvo = min(int(max_results), total_results)

        # Teto DURO da API (ver PUBMED_MAX_FETCHABLE). Truncar aqui é inevitável; truncar
        # CALADO é que era o defeito. O motivo NÃO é gravado agora: se a colheita parar antes
        # por outro motivo (rede, histórico expirado), esse motivo é mais específico e tem de
        # prevalecer. A decisão fica no fim; aqui só marca a bandeira.
        self.truncated_by_api = False
        if alvo > PUBMED_MAX_FETCHABLE:
            self.truncated_by_api = True
            alvo = PUBMED_MAX_FETCHABLE
            logger.warning(f"[PubMed] teto da API: {PUBMED_MAX_FETCHABLE} de {total_results} "
                           f"registros — o NCBI não entrega mais que isso por busca")

        # 3. EFetch paginado sobre o histórico do servidor.
        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        batch_size = PUBMED_EFETCH_BATCH
        count_fetched = 0
        retstart = 0

        # PMIDs que a própria ESearch já devolveu. Com `usehistory=y` e `retmax=0` vêm vazios
        # (é o esperado), mas se vierem, usá-los evita repetir a pergunta ao servidor.
        ids_conhecidos = list(res.get("idlist", []) or [])

        if not (webenv and query_key):
            # Sem histórico não há como passar dos 10.000. Colher o que der é melhor do que
            # falhar, mas o motivo da parada tem que dizer isso — truncar em silêncio é
            # exatamente o defeito que esta reescrita elimina.
            # `or` para não apagar o motivo do teto duro, que já é a consequência visível.
            self.stop_reason = self.stop_reason or (
                "histórico do PubMed indisponível (sem WebEnv/QueryKey): "
                "o NCBI limita a 10.000 registros sem ele")
            logger.warning(f"[PubMed] {self.stop_reason}")
            alvo = min(alvo, 10_000)

        while count_fetched < alvo:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Search cancelled by user")

            efetch_params = {
                "db": "pubmed",
                "retmode": "text",
                "rettype": "medline",
                "retstart": retstart,
                "retmax": min(batch_size, alvo - count_fetched),
            }
            if webenv and query_key:
                efetch_params["WebEnv"] = webenv
                efetch_params["query_key"] = query_key
            else:
                # Caminho degradado: usa os PMIDs que a ESearch já trouxe e, só quando eles
                # acabam, refaz a ESearch pedindo a próxima fatia.
                ids = ids_conhecidos[retstart:retstart + efetch_params["retmax"]]
                if not ids:
                    ids = self._pmids_sem_historico(
                        term, retstart, efetch_params["retmax"],
                        sort_value=esearch_params.get("sort", ""),
                        cancel_event=cancel_event, rate_limit_delay=rate_limit_delay)
                if not ids:
                    self.stop_reason = self.stop_reason or "exauriu (sem mais PMIDs)"
                    break
                efetch_params.pop("retstart", None)
                efetch_params.pop("retmax", None)
                efetch_params["id"] = ",".join(ids)

            url = f"{efetch_url}?{urllib.parse.urlencode(efetch_params)}"
            self.pages_fetched += 1
            try:
                medline_text = self.fetch_url(url, cancel_event=cancel_event,
                                              rate_limit_delay=rate_limit_delay)
            except Exception as e:
                self.stop_reason = f"erro de rede na EFetch (lote {self.pages_fetched}): {e}"
                self.stop_error = True
                logger.error(f"[PubMed] parou: {self.stop_reason}")
                break

            brutos = self._parse_medline(medline_text)
            if not brutos:
                # Lote vazio antes do alvo: o conjunto acabou (ou o histórico expirou).
                # Sem esta saída o `retstart` não avançaria e o laço giraria para sempre.
                self.stop_reason = self.stop_reason or "exauriu (histórico sem mais registros)"
                break

            for r in brutos:
                if count_fetched >= alvo:
                    break
                yield self._record_from_medline(r)
                count_fetched += 1

            retstart += len(brutos)
            if progress_cb:
                progress_cb(count_fetched, alvo)

        if self.stop_reason is None:
            if self.truncated_by_api and count_fetched >= alvo:
                # Só quando o teto foi de fato o que interrompeu. A trilha nomeia o NCBI
                # para não se confundir com um limite que o usuário tenha pedido.
                self.stop_reason = ("teto do PubMed: 9.999 registros por busca "
                                    "(limite do NCBI)")
            else:
                # Compara com o LIMITE PEDIDO, não com `alvo`: pedir 25.000 numa base de 450
                # e receber 450 é a base ter acabado, não um limite atingido. `alvo` já é o
                # menor dos dois, então usá-lo faria todo fim de conjunto virar "atingiu
                # limite".
                self.stop_reason = ("atingiu limite" if count_fetched >= int(max_results)
                                    else "exauriu (todos os PMIDs)")
        logger.info(f"[PubMed] parou: {self.stop_reason} · lotes={self.pages_fetched} "
                    f"· registros={count_fetched} · disponíveis={self.total_available}")
