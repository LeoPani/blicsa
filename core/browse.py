"""Modo Navegação — contagem instantânea, paginação sob demanda e facetas.

A premissa do trabalho: **navegar e baixar são operações separadas**. O Web of Science mostra
"Results: 849" e "1 of 85" na hora porque não baixa nada além da página que você está vendo. O
app fazia o oposto — colhia os 319.300 registros antes de desenhar o primeiro card.

Aqui mora a parte testável dessa separação, sem UI:

* `BrowseSession` guarda query, filtros, ordenação e página, e sabe pedir UMA página por vez;
* as facetas vêm do `group_by` da API, que devolve contagens do **universo inteiro** sem
  baixar registro nenhum;
* cada requisição carrega um **token incremental**, e resposta de token velho é descartada —
  sem isso, uma busca lenta disparada antes sobrescreve o resultado da busca que o usuário
  acabou de fazer;
* um **cache LRU** de páginas evita rebater na API ao voltar uma página.

Provider que não suporta uma faceta **declara isso** (`FACETS` vazio), e a UI esconde o
filtro em vez de oferecer um controle que não funciona — foi exatamente essa a origem do
BUG-02, filtros que apareciam e não filtravam nada.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Sequence

# Rótulos i18n de cada faceta. A chave é a usada internamente; o valor é a chave do catálogo.
FACET_LABELS = {
    "type": "facet.type",
    "language": "facet.language",
    "publication_year": "facet.year",
    "is_oa": "facet.open_access",
    "source": "facet.source",
    "author": "facet.author",
}

# Ordenações oferecidas na UI → valor que vai para a API.
SORTS = ("relevance", "date_desc", "date_asc", "citations")

DEFAULT_PER_PAGE = 25
CACHE_PAGINAS = 12          # páginas mantidas no LRU


@dataclass
class FacetValue:
    key: str
    label: str
    count: int

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "count": self.count}


@dataclass
class Facet:
    field: str
    values: list[FacetValue] = field(default_factory=list)
    error: str = ""          # faceta que falhou: a lista continua, só sem ela
    error_key: str = ""      # chave i18n quando o erro tem mensagem própria
    #: Parâmetros da mensagem (ex.: `{fonte}` do 401). Sem isto, uma mensagem
    #: parametrizada chegaria à sidebar com a chave literal no lugar do valor.
    error_args: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error

    def as_dict(self) -> dict:
        return {"field": self.field, "error": self.error,
                "values": [v.as_dict() for v in self.values]}


@dataclass
class Page:
    """Uma página de resultados."""
    records: list[dict] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    token: int = 0
    error: str = ""
    #: Chave i18n do erro, quando ele tem uma mensagem própria (429 do OpenAlex, p.ex.).
    error_key: str = ""
    #: Parâmetros da mensagem de erro (ex.: nome da fonte), aplicados no `t()`.
    error_args: dict = field(default_factory=dict)
    #: Teto de resultados alcançáveis por paginação, declarado pelo provider. `0` = sem teto.
    browse_max: int = 0

    @property
    def pages(self) -> int:
        """Total de páginas que os resultados dariam, ignorando o teto da API."""
        if self.total <= 0:
            return 1
        return max(1, -(-self.total // max(1, self.per_page)))

    @property
    def navigable_pages(self) -> int:
        """Páginas que dá para ABRIR de verdade — é o número que o pager deve anunciar.

        Uma busca com 366.949 resultados dá 14.678 páginas de 25, mas o OpenAlex recusa
        além de 10.000 registros: só 400 existem. Anunciar 14.678 é prometer 14.278 páginas
        que devolvem erro — o total de resultados continua no cabeçalho, que é onde a
        informação honesta sobre o tamanho da busca pertence.
        """
        if self.browse_max <= 0:
            return self.pages
        teto = max(1, self.browse_max // max(1, self.per_page))
        return max(1, min(self.pages, teto))

    @property
    def clipped(self) -> bool:
        """Há resultados fora do alcance da paginação? Muda o rótulo do pager."""
        return self.navigable_pages < self.pages

    @property
    def empty(self) -> bool:
        return self.total == 0 and not self.records


def error_i18n_key(exc: Exception) -> str:
    """Chave i18n da mensagem de erro, quando o erro tem uma explicação própria.

    Erro de rede genérico não tem: a UI mostra o texto cru dentro do estado de erro. Já o
    limite de uso da API tem uma saída concreta (chave gratuita nos Ajustes), e mostrar
    "Failed to fetch https://api.openalex.org/works?per_page=25&mailto=..." em vez disso
    deixaria o usuário sem saber o que fazer.
    """
    chave = getattr(exc, "i18n_key", "")
    return str(chave) if chave else ""


def error_i18n_args(exc: Exception) -> dict:
    """Parâmetros da mensagem de erro, quando ela é parametrizada.

    O teto de paginação vale para OpenAlex e PubMed com a mesma explicação e a mesma saída;
    o que muda é o nome da fonte. Sem isto, a mensagem teria de nomear uma fonte só — e
    mentiria para a outra.
    """
    args = getattr(exc, "i18n_args", None)
    return dict(args) if isinstance(args, dict) else {}


def sort_to_api(sort: str) -> dict:
    """Ordenação da UI → filtros que os providers entendem.

    Nunca se ordena em memória: a página vem já ordenada da API, senão a ordenação só valeria
    dentro dos 25 registros da página corrente.
    """
    return {
        "relevance": {},
        "date_desc": {"sort": "date"},
        "date_asc": {"sort": "date", "order": "asc"},
        "citations": {"sort": "citations"},
    }.get(sort, {})


def supported_facets(provider) -> list[str]:
    """Facetas que o provider realmente suporta, na ordem de exibição."""
    disponiveis = getattr(provider, "FACETS", {}) or {}
    return [f for f in FACET_LABELS if f in disponiveis]


def build_filters(base: dict | None, ativos: dict[str, list[str]], sort: str = "relevance") -> dict:
    """Monta o dicionário de filtros a partir das facetas ativas.

    Semântica do Web of Science, e a que o usuário espera:
    * **OR dentro da mesma categoria** — marcar "Artigo" e "Capítulo" traz os dois;
    * **AND entre categorias** — "Artigo" + "inglês" traz artigos em inglês.

    O OR vira uma lista de valores no mesmo campo; quem monta a string da API é o provider.
    """
    filtros = dict(base or {})
    for campo, valores in (ativos or {}).items():
        vals = [v for v in valores if str(v).strip()]
        if not vals:
            continue
        if campo == "publication_year":
            filtros["year_values"] = list(vals)
        elif campo == "is_oa":
            filtros["is_oa"] = str(vals[0]).lower() in ("true", "1", "sim", "yes")
        else:
            filtros[campo] = vals[0] if len(vals) == 1 else list(vals)
    filtros.update(sort_to_api(sort))
    return filtros


class BrowseSession:
    """Estado de uma navegação: query, filtros, facetas ativas, ordenação e página.

    Não conhece Tk: quem chama passa um `on_page`/`on_facets` e decide como desenhar. Assim
    a sessão inteira é testável sem abrir janela.
    """

    def __init__(self, provider, query: str = "", base_filters: dict | None = None,
                 per_page: int = DEFAULT_PER_PAGE):
        self.provider = provider
        self.query = query
        self.base_filters = dict(base_filters or {})
        self.per_page = max(1, int(per_page))
        # Teto de paginação do provider (0 = sem teto). Viaja em cada `Page` para o pager
        # anunciar só o que existe.
        self.browse_max = int(getattr(provider, "BROWSE_MAX_RESULTS", 0) or 0)
        self.sort = "relevance"
        self.active_facets: dict[str, list[str]] = {}
        self.page = 1
        self.total = 0
        self.facets: dict[str, Facet] = {}

        self._token = 0
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple, Page] = OrderedDict()

    # ── token: só a última query vence ──────────────────────────────────
    def next_token(self) -> int:
        """Novo token para a requisição que está saindo agora."""
        with self._lock:
            self._token += 1
            return self._token

    def is_current(self, token: int) -> bool:
        """A resposta que chegou ainda é a que interessa?

        Uma busca ampla disparada antes pode responder DEPOIS de uma busca estreita disparada
        depois. Sem esta checagem, a lista mostra o resultado errado — e o usuário não tem
        como saber que está olhando a resposta da query anterior.
        """
        with self._lock:
            return token == self._token

    # ── estado da consulta ──────────────────────────────────────────────
    def current_filters(self) -> dict:
        return build_filters(self.base_filters, self.active_facets, self.sort)

    def filters_excluding(self, campo: str) -> dict:
        """Filtros correntes SEM o da própria categoria.

        É como o "Refine Results" do WoS funciona, e é o que mantém a lista utilizável: se a
        faceta "Tipo" aplicasse o próprio filtro, marcar "Artigo" faria "Capítulo de livro"
        desaparecer da sidebar — e o usuário não teria como trocar de opção sem antes
        remover o chip. Os filtros das OUTRAS categorias continuam valendo, então as
        contagens seguem coerentes com o resto do refinamento.
        """
        outros = {k: v for k, v in self.active_facets.items() if k != campo}
        return build_filters(self.base_filters, outros, self.sort)

    def cache_key(self, page: int) -> tuple:
        f = self.current_filters()
        return (self.query, tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                                         for k, v in f.items())),
                int(page), int(self.per_page))

    def toggle_facet(self, campo: str, valor: str) -> bool:
        """Liga/desliga um valor de faceta. Devolve True se ficou ativo."""
        atuais = self.active_facets.setdefault(campo, [])
        v = str(valor)
        if v in atuais:
            atuais.remove(v)
            if not atuais:
                self.active_facets.pop(campo, None)
            ativo = False
        else:
            atuais.append(v)
            ativo = True
        self.page = 1               # trocar filtro sempre volta para a página 1
        return ativo

    def clear_facet(self, campo: str, valor: str | None = None):
        """Remove um chip. Sem valor, limpa a categoria inteira."""
        if valor is None:
            self.active_facets.pop(campo, None)
        elif campo in self.active_facets:
            self.active_facets[campo] = [v for v in self.active_facets[campo] if v != str(valor)]
            if not self.active_facets[campo]:
                self.active_facets.pop(campo, None)
        self.page = 1

    def clear_all_facets(self):
        self.active_facets.clear()
        self.page = 1

    def set_sort(self, sort: str):
        if sort not in SORTS:
            raise ValueError(f"ordenação inválida: {sort!r}")
        self.sort = sort
        self.page = 1

    def chips(self) -> list[dict]:
        """Filtros ativos, para os chips do cabeçalho."""
        saida = []
        for campo, valores in self.active_facets.items():
            for v in valores:
                rotulo = v
                faceta = self.facets.get(campo)
                if faceta:
                    for fv in faceta.values:
                        if fv.key == v:
                            rotulo = fv.label
                            break
                saida.append({"field": campo, "key": v, "label": rotulo})
        return saida

    # ── busca de página ─────────────────────────────────────────────────
    def fetch_page(self, page: int | None = None, cancel_event=None,
                   use_cache: bool = True) -> Page:
        """Uma página. Não acumula nada além do cache LRU.

        Levanta nada: erro vira `Page.error`, para a UI mostrar o estado de erro com botão de
        tentar de novo em vez de engolir a falha.
        """
        if page is not None:
            self.page = max(1, int(page))
        token = self.next_token()

        chave = self.cache_key(self.page)
        if use_cache and chave in self._cache:
            self._cache.move_to_end(chave)
            cacheada = self._cache[chave]
            # Página do cache também precisa do token corrente, senão a UI a descarta.
            return Page(records=cacheada.records, total=cacheada.total, page=cacheada.page,
                        per_page=cacheada.per_page, token=token,
                        browse_max=self.browse_max)

        try:
            registros, total = self.provider.browse(
                self.query, self.current_filters(), page=self.page,
                per_page=self.per_page, cancel_event=cancel_event)
        except Exception as e:
            # `total` do estado anterior vai junto: no teto de paginação o usuário precisa
            # continuar vendo quantos resultados existem — é o que dá sentido à sugestão de
            # refinar a busca ou importar tudo.
            return Page(page=self.page, per_page=self.per_page, token=token,
                        total=self.total, error=str(e), error_key=error_i18n_key(e),
                        error_args=error_i18n_args(e), browse_max=self.browse_max)

        self.total = int(total or 0)
        p = Page(records=list(registros), total=self.total, page=self.page,
                 per_page=self.per_page, token=token, browse_max=self.browse_max)
        self._cache[chave] = p
        self._cache.move_to_end(chave)
        while len(self._cache) > CACHE_PAGINAS:
            self._cache.popitem(last=False)
        return p

    def cached_pages(self) -> int:
        return len(self._cache)

    def invalidate_cache(self):
        self._cache.clear()

    # ── facetas ─────────────────────────────────────────────────────────
    def fetch_facets(self, campos: Sequence[str] | None = None, top: int = 10,
                     cancel_event=None, paralelo: bool = True) -> dict[str, Facet]:
        """Contagens por faceta sobre o universo da busca.

        **Em paralelo** por padrão: são 6 requisições independentes, e em série somam ~5s —
        tempo em que a sidebar fica um retângulo branco vazio ao lado de uma lista já pronta.
        Em paralelo custa o tempo da mais lenta, ~1s. O custo em créditos é o mesmo (1 por
        faceta); o que muda é só a espera.

        Faceta que falha **não derruba a listagem**: entra com `error` preenchido e a UI mostra
        o resto. Perder uma faceta é um aborrecimento; perder a lista por causa dela seria um
        defeito.
        """
        alvos = list(campos) if campos else supported_facets(self.provider)
        if not alvos:
            self.facets = {}
            return {}

        def uma(campo: str) -> tuple[str, Facet]:
            try:
                # `filters_excluding`: a faceta não aplica o próprio filtro, senão marcar um
                # valor apaga os outros da lista e trava o usuário na escolha que ele fez.
                brutos = self.provider.facet(campo, self.query, self.filters_excluding(campo),
                                             top=top, cancel_event=cancel_event)
                return campo, Facet(
                    field=campo,
                    values=[FacetValue(str(b["key"]), str(b.get("label") or b["key"]),
                                       int(b.get("count", 0) or 0)) for b in brutos])
            except Exception as e:
                return campo, Facet(field=campo, error=str(e), error_key=error_i18n_key(e),
                                    error_args=error_i18n_args(e))

        if paralelo and len(alvos) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(6, len(alvos))) as pool:
                pares = list(pool.map(uma, alvos))
        else:
            pares = [uma(c) for c in alvos]

        # Ordem de exibição estável, independente de quem respondeu primeiro.
        por_campo = dict(pares)
        resultado = {c: por_campo[c] for c in alvos if c in por_campo}
        self.facets = resultado
        return resultado


def validate_query(query: str) -> tuple[bool, str]:
    """Query utilizável? Devolve (ok, chave i18n do erro)."""
    if not str(query or "").strip():
        return False, "search.error_empty_query"
    return True, ""


def format_count(n: int) -> str:
    """319300 → "319.300" (separador de milhar do pt_BR, como no relatório da busca)."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"
