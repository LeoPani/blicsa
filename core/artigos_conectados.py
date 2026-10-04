"""Explorar a partir de um artigo: o grafo de artigos parecidos (à la Connected Papers).

Dado um ou mais artigos de partida, monta o grafo dos ~40 artigos mais parecidos com eles,
usando os dados abertos do OpenAlex. Semelhança é a mesma ideia do Connected Papers e da
bibliometria clássica:

* **acoplamento bibliográfico**: dois artigos que citam as mesmas obras tratam de assuntos
  próximos (Kessler, 1963);
* **cocitação**: dois artigos citados juntos pelos mesmos trabalhos também (Small, 1973).

Os dois são normalizados pelo cosseno de Salton (número de compartilhados dividido pela
raiz do produto dos tamanhos), para que um artigo com 300 referências não pareça parecido
com tudo. A soma dos dois cossenos é a semelhança; citação direta entre os dois soma um
pequeno bônus.

Além do grafo, duas listas:

* **obras anteriores** (Prior works): as obras mais citadas pelos artigos do grafo, que não
  estão nele. Tendem a ser os clássicos em que esse grupo se apoia;
* **obras derivadas** (Derivative works): trabalhos que citam muitos artigos do grafo.
  Tendem a ser revisões e o estado da arte posterior.

Diferenças em relação ao Connected Papers, por decisão:

* O conjunto de candidatos é local: referências do artigo de partida, os mais citados entre
  os que o citam, e os `related_works` do próprio OpenAlex. O Connected Papers examina
  ~50 mil artigos do Semantic Scholar; aqui são algumas centenas, e por isso o cálculo é
  aberto e auditável, e roda em segundos sem conta.
* O resultado pode virar corpus do Blicsa (o Connected Papers só exporta lista).

A rede entra por `obter(url) -> dict` (injetável); os testes rodam offline.
"""

from __future__ import annotations

import math
import re
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import networkx as nx

API = "https://api.openalex.org/works"
LOTE = 50                     # IDs por pedido no filtro openalex_id:W1|W2|...
MAX_CITANTES = 200            # artigos que citam a semente, por semente (os mais citados)
N_PADRAO = 40                 # o Connected Papers mostra ~40-50: mais que isso vira borrão
BONUS_CITACAO_DIRETA = 0.1


class ErroExplorar(Exception):
    """Mensagem já escrita para o usuário (vai direto para a tela)."""


# ── Identificadores ─────────────────────────────────────────────────────────────────
def id_curto(valor) -> str:
    m = re.search(r"\b(W\d+)\b", str(valor or ""), re.IGNORECASE)
    return m.group(1).upper() if m else ""


def doi_de(valor) -> str:
    m = re.search(r"10\.\d{4,9}/\S+", str(valor or ""))
    return m.group(0).rstrip(".;,)") if m else ""


def interpretar_entrada(texto: str) -> list[str]:
    """Aceita DOIs, links doi.org, IDs/links do OpenAlex, um por linha ou separados por
    espaço, vírgula ou ponto e vírgula. Devolve referências prontas para `/works/<ref>`."""
    refs, vistos = [], set()
    for parte in re.split(r"[\s,;]+", str(texto or "")):
        parte = parte.strip()
        if not parte:
            continue
        w = id_curto(parte) if "openalex" in parte.lower() or re.fullmatch(r"[Ww]\d+", parte) else ""
        d = "" if w else doi_de(parte)
        ref = w or (f"https://doi.org/{d}" if d else "")
        if ref and ref.lower() not in vistos:
            vistos.add(ref.lower())
            refs.append(ref)
    return refs


# ── Rótulos ─────────────────────────────────────────────────────────────────────────
def sobrenome(work: dict) -> str:
    for a in work.get("authorships") or []:
        nome = str(((a or {}).get("author") or {}).get("display_name") or "").strip()
        if nome:
            return nome.split(",")[0].strip() if "," in nome else nome.split()[-1]
    return ""


def rotulo(work: dict) -> str:
    sn = sobrenome(work) or (str(work.get("title") or work.get("display_name") or "?")[:25])
    ano = work.get("publication_year")
    n = len([a for a in (work.get("authorships") or []) if a])
    etal = " et al." if n > 2 else (" e outro" if n == 2 else "")
    return f"{sn}{etal} ({ano})" if ano else f"{sn}{etal}"


def _refs(work: dict) -> set[str]:
    return {id_curto(r) for r in (work.get("referenced_works") or []) if id_curto(r)}


def _cos(compartilhados: int, a: int, b: int) -> float:
    return compartilhados / math.sqrt(a * b) if compartilhados and a and b else 0.0


# ── Resultado ───────────────────────────────────────────────────────────────────────
@dataclass
class Exploracao:
    sementes: list[str]                       # IDs W das sementes
    obras: dict[str, dict]                    # W → obra do OpenAlex (todas que vimos)
    grafo: nx.Graph
    semelhanca: dict[str, float]              # W → semelhança com as sementes
    anteriores: list[tuple[str, int]] = field(default_factory=list)   # (W, nº de citantes no grafo)
    derivadas: list[tuple[str, int]] = field(default_factory=list)    # (W, nº de obras do grafo citadas)
    pedidos: int = 0
    avisos: list[str] = field(default_factory=list)

    def obras_do_grafo(self) -> list[dict]:
        return [self.obras[n] for n in self.grafo.nodes if n in self.obras]


# ── Rede ────────────────────────────────────────────────────────────────────────────
class _Cliente:
    def __init__(self, obter: Callable[[str], Optional[dict]], mailto: str, cancelar=None):
        self._obter = obter
        self.mailto = mailto
        self.cancelar = cancelar
        self.pedidos = 0

    def get(self, caminho: str, **params) -> Optional[dict]:
        if self.cancelar is not None and self.cancelar.is_set():
            raise InterruptedError
        params["mailto"] = self.mailto
        url = f"{API}{caminho}?{urllib.parse.urlencode(params, safe=':|,/')}"
        self.pedidos += 1
        return self._obter(url)

    def obra(self, ref: str) -> Optional[dict]:
        if ref.startswith("https://doi.org/"):
            caminho = "/" + ref                     # /works/https://doi.org/10.x/y
        else:
            caminho = "/" + id_curto(ref)
        dados = self.get(caminho)
        return dados if isinstance(dados, dict) and dados.get("id") else None

    def em_lote(self, ids: Iterable[str]) -> list[dict]:
        ids = [i for i in dict.fromkeys(id_curto(x) for x in ids) if i]
        out = []
        for k in range(0, len(ids), LOTE):
            bloco = ids[k:k + LOTE]
            dados = self.get("", filter="openalex_id:" + "|".join(bloco), per_page=LOTE)
            out.extend((dados or {}).get("results") or [])
        return out

    def citantes(self, ids: list[str], quantos: int) -> list[dict]:
        """Os `quantos` trabalhos mais citados que citam QUALQUER um de `ids`."""
        out = []
        for k in range(0, len(ids), LOTE):
            bloco = ids[k:k + LOTE]
            pagina, faltam = 1, quantos
            while faltam > 0:
                pp = min(200, faltam)
                dados = self.get("", filter="cites:" + "|".join(bloco),
                                 sort="cited_by_count:desc", per_page=pp, page=pagina)
                res = (dados or {}).get("results") or []
                out.extend(res)
                faltam -= len(res)
                if len(res) < pp:
                    break
                pagina += 1
        return out


def obter_padrao(api_key: str | None = None):
    """`obter` que usa o provider do app (chave da API, limites, cache e retry)."""
    import json
    from core.sources.openalex import OpenAlexProvider
    prov = OpenAlexProvider(api_key=api_key)

    def obter(url: str) -> Optional[dict]:
        return json.loads(prov.fetch_url(url))
    return obter, prov.mailto


# ── Cálculo ─────────────────────────────────────────────────────────────────────────
def _semelhanca(a: str, b: str, refs: dict[str, set], citado_por: dict[str, set]) -> float:
    ra, rb = refs.get(a, set()), refs.get(b, set())
    ca, cb = citado_por.get(a, set()), citado_por.get(b, set())
    s = _cos(len(ra & rb), len(ra), len(rb)) + _cos(len(ca & cb), len(ca), len(cb))
    if b in ra or a in rb:
        s += BONUS_CITACAO_DIRETA
    return s


def explorar(entrada: str | list[str], obter: Callable[[str], Optional[dict]], *,
             mailto: str = "blicsa.app@gmail.com", n: int = N_PADRAO, cancelar=None,
             ao_progresso: Optional[Callable[[str], None]] = None) -> Exploracao:
    refs_entrada = interpretar_entrada(entrada) if isinstance(entrada, str) else list(entrada)
    if not refs_entrada:
        raise ErroExplorar("sem_entrada")
    cli = _Cliente(obter, mailto, cancelar)
    avisar = ao_progresso or (lambda _m: None)
    obras: dict[str, dict] = {}

    def guardar(ws):
        for w in ws or []:
            i = id_curto((w or {}).get("id"))
            if i:
                obras[i] = w

    # 1. Sementes
    avisar("sementes")
    sementes, nao_achados = [], []
    for ref in refs_entrada[:10]:
        w = cli.obra(ref)
        if w:
            guardar([w])
            sementes.append(id_curto(w["id"]))
        else:
            nao_achados.append(ref)
    if not sementes:
        raise ErroExplorar("nao_achado")

    # 2. Candidatos: referências, citantes e related_works de cada semente
    avisar("citantes")
    citantes = cli.citantes(sementes, MAX_CITANTES * len(sementes))
    guardar(citantes)
    avisar("referencias")
    faltam = set()
    for s in sementes:
        faltam |= _refs(obras[s])
        faltam |= {id_curto(r) for r in obras[s].get("related_works") or []}
    faltam -= set(obras)
    guardar(cli.em_lote(sorted(faltam)))

    candidatos = (set(obras) - set(sementes))
    # Quem cita quem, dentro do que conhecemos (é a base da cocitação local)
    refs = {i: _refs(w) for i, w in obras.items()}
    citado_por: dict[str, set] = {}
    for i, rs in refs.items():
        for r in rs:
            citado_por.setdefault(r, set()).add(i)

    # 3. Os N mais parecidos com as sementes
    avisar("calculando")
    sem = {c: sum(_semelhanca(c, s, refs, citado_por) for s in sementes) for c in candidatos}
    escolhidos = [c for c, v in sorted(sem.items(), key=lambda kv: (-kv[1],
                  -(obras[kv[0]].get("cited_by_count") or 0), kv[0])) if v > 0][:n]
    nos = sementes + escolhidos

    G = nx.Graph()
    for i in nos:
        w = obras[i]
        cit = int(w.get("cited_by_count") or 0)
        ano = int(w.get("publication_year") or 0)
        G.add_node(i, label=rotulo(w), title=str(w.get("title") or w.get("display_name") or ""),
                   size=math.log1p(cit) + 1, citations_mean=cit, citations_sum=cit,
                   year_mean=ano, first_year=ano, occurrence=1,
                   semente=i in sementes, semelhanca=round(sem.get(i, 0.0), 4),
                   doi=str(w.get("doi") or ""))
    # Arestas: semelhança par a par; cada nó fica com as suas 6 ligações mais fortes, para o
    # mapa mostrar estrutura e não um novelo (o Connected Papers faz o mesmo tipo de corte).
    pares = {}
    for k, a in enumerate(nos):
        for b in nos[k + 1:]:
            v = _semelhanca(a, b, refs, citado_por)
            if v > 0:
                pares[(a, b)] = v
    melhores: dict[str, list] = {}
    for (a, b), v in pares.items():
        melhores.setdefault(a, []).append((v, b))
        melhores.setdefault(b, []).append((v, a))
    for a, lista in melhores.items():
        for v, b in sorted(lista, reverse=True)[:6]:
            G.add_edge(a, b, weight=round(v, 4))
    # Ninguém fica solto: liga cada nó isolado à semente mais parecida.
    for c in escolhidos:
        if G.degree(c) == 0:
            s = max(sementes, key=lambda s: _semelhanca(c, s, refs, citado_por))
            G.add_edge(c, s, weight=round(max(_semelhanca(c, s, refs, citado_por), 0.01), 4))
    # Um grafo só: cada grupo desligado das sementes ganha uma ponte pelo seu nó mais parecido
    # com elas. Sem isso o layout empurra os grupos para longe e o mapa vira ilhas soltas.
    principal = nx.node_connected_component(G, sementes[0])
    for comp in [c for c in nx.connected_components(G) if not (c & principal)]:
        melhor = max(comp, key=lambda c: (sem.get(c, 0.0), c))
        s = max(sementes, key=lambda s: _semelhanca(melhor, s, refs, citado_por))
        G.add_edge(melhor, s, weight=round(max(_semelhanca(melhor, s, refs, citado_por), 0.01), 4))
        principal |= comp
    from core.matrix_builders import CLUSTER_PALETTE
    try:
        from networkx.algorithms.community import louvain_communities
        comunidades = louvain_communities(G, weight="weight", seed=42)
    except Exception:
        comunidades = [set(G)]
    for k, com in enumerate(sorted(comunidades, key=len, reverse=True)):
        for i in com:
            G.nodes[i]["group"] = k
            G.nodes[i]["color"] = CLUSTER_PALETTE[k % len(CLUSTER_PALETTE)]

    # 4. Obras anteriores: as mais citadas pelo grafo, fora dele
    conta_ant = Counter(r for i in nos for r in refs.get(i, set()) if r not in G)
    anteriores = [(r, k) for r, k in conta_ant.most_common(30) if k >= 2][:15]
    # 5. Obras derivadas: quem cita muitos artigos do grafo, fora dele
    avisar("derivadas")
    deriv = cli.citantes(nos, 200)
    guardar(deriv)
    conta_der = Counter()
    for w in deriv:
        i = id_curto(w.get("id"))
        if i and i not in G:
            k = len(_refs(w) & set(nos))
            if k >= 2:
                conta_der[i] = k
    derivadas = sorted(conta_der.items(), key=lambda kv: (-kv[1],
                       -(obras[kv[0]].get("cited_by_count") or 0)))[:15]
    faltam = [r for r, _ in anteriores if r not in obras]
    if faltam:
        guardar(cli.em_lote(faltam))

    ex = Exploracao(sementes, obras, G, sem, anteriores, derivadas, cli.pedidos)
    if nao_achados:
        ex.avisos.append("nao_achados:" + ", ".join(nao_achados))
    return ex


def para_registros(ex: Exploracao, ids: Iterable[str]) -> list[dict]:
    """Obras escolhidas → registros do corpus, no mesmo formato da busca do OpenAlex."""
    from core.sources.openalex import OpenAlexProvider
    norm = OpenAlexProvider.__new__(OpenAlexProvider)   # _normalize_work não usa estado
    return [norm._normalize_work(ex.obras[i]) for i in ids if i in ex.obras]


def completar_ids(df, obter: Callable[[str], Optional[dict]], *, mailto: str = "blicsa.app@gmail.com",
                  cancelar=None, ao_progresso: Optional[Callable[[int, int], None]] = None) -> int:
    """Preenche `openalex_id` pelo DOI, em lotes de 50 (projetos montados antes de o Blicsa
    guardar o código). Altera `df` no lugar; devolve quantos foram preenchidos."""
    if "openalex_id" not in df.columns:
        df["openalex_id"] = ""
    vazio = df["openalex_id"].fillna("").astype(str).str.strip() == ""
    dois = {}
    for idx in df.index[vazio]:
        d = doi_de(df.at[idx, "doi"] if "doi" in df.columns else "")
        if d:
            dois.setdefault(d.lower(), []).append(idx)
    lista = sorted(dois)
    cli = _Cliente(obter, mailto, cancelar)
    feitos = 0
    for k in range(0, len(lista), LOTE):
        bloco = lista[k:k + LOTE]
        dados = cli.get("", filter="doi:" + "|".join(bloco), per_page=LOTE)
        for w in (dados or {}).get("results") or []:
            d = doi_de(w.get("doi")).lower()
            for idx in dois.get(d, []):
                df.at[idx, "openalex_id"] = str(w.get("id") or "")
                feitos += 1
        if ao_progresso:
            ao_progresso(min(k + LOTE, len(lista)), len(lista))
    return feitos
