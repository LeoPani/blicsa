"""Corpus adversariais para a bateria de mapas — Auditoria 1, Fase 1.

Não é um arquivo de teste: é a **fonte de dados** que a bateria (`tests/test_mapas_adversariais.py`)
e o executor da matriz (`scripts/audit_mapas.py`) compartilham. Ficar num lugar só é o que
impede o relatório de auditar um corpus e o teste de guardar outro.

Cada caso existe por um modo de falha conhecido de pipeline de grafo, não por variedade:

- **1 documento** e **grafo desconexo** quebram layout por força (ForceAtlas2 divide por
  distância entre componentes) e modularidade (Louvain sobre componente isolado).
- **mesmo ano** e **sem ano** são os dois extremos do overlay: variância zero faz `vmax - vmin`
  virar zero, e ausência total faz a métrica inteira ser `None`. Os dois já produziram divisão
  por zero em bibliotecas de mapa.
- **frequências iguais** tira o desempate de qualquer ordenação por peso; **termo dominante**
  faz o oposto, com um nó cuja escala esmaga os outros.
- **5.000 documentos** é o volume declarado na documentação do projeto.
- **caracteres difíceis** cobre o que passa por JSON, por rótulo de canvas e por nome de
  arquivo de export ao mesmo tempo.
- **abstracts vazios** é o corpus que produz grafo vazio — o caso em que o mapa precisa dizer
  "sem dados" em vez de abrir em branco (foi bug real, `docs/RELATORIO-MEGAPROMPT.md`).
- **grafias de autor** é o caso em que o grafo mente sem quebrar: três nós para uma pessoa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import networkx as nx
import pandas as pd

COLUNAS = ["authors", "title", "year", "source", "keywords", "abstract",
           "citations", "doi", "references", "origin", "language", "is_oa", "oa_url"]


def _df(linhas: list[dict]) -> pd.DataFrame:
    """DataFrame com o schema completo do Blicsa, faltando nada.

    Preencher as colunas ausentes aqui — e não em cada caso — é o que garante que uma falha
    da bateria seja do mapa, e não de um `KeyError` de fixture incompleta.
    """
    base = {"authors": "", "title": "", "year": 2020, "source": "Rev. Teste",
            "keywords": "", "abstract": "", "citations": 0, "doi": "",
            "references": "", "origin": "teste", "language": "en",
            "is_oa": False, "oa_url": ""}
    return pd.DataFrame([{**base, **linha} for linha in linhas], columns=COLUNAS)


# ── Construtores de grafo ────────────────────────────────────────────────────────

def _coocorrencia(campo: str = "keywords", min_ocorrencia: int = 1):
    def constroi(gen):
        return gen.build_keyword_cooccurrence(min_occurrence=min_ocorrencia, field=campo)
    return constroi


def _coautoria(min_publicacoes: int = 1):
    def constroi(gen):
        return gen.build_coauthorship_network(min_publications=min_publicacoes)
    return constroi


@dataclass(frozen=True)
class Caso:
    nome: str
    descricao: str
    df: pd.DataFrame
    constroi: Callable
    #: O que este caso existe para provar. Vai para a coluna "o que testa" do relatório.
    alvo: str


# ── Os casos ─────────────────────────────────────────────────────────────────────

def _um_documento() -> pd.DataFrame:
    return _df([{"title": "Estudo único", "keywords": "reciclagem;informalidade;cooperativa",
                 "authors": "Silva, J.", "year": 2020, "citations": 5,
                 "abstract": "recycling informality cooperative work"}])


def _dois_desconexos(componentes: int = 2) -> pd.DataFrame:
    """N documentos sem um único termo em comum → N componentes isoladas."""
    linhas = []
    for i in range(componentes):
        termos = ";".join(f"termo{i}x{j}" for j in range(3))
        linhas.append({"title": f"Documento {i}", "keywords": termos,
                       "authors": f"Autor{i}, A.", "year": 2000 + i, "citations": i})
    return _df(linhas)


def _mesmo_ano() -> pd.DataFrame:
    linhas = []
    for i in range(20):
        linhas.append({"title": f"Artigo {i}", "keywords": "residuos;politica;urbano",
                       "authors": f"Autor{i % 4}, B.", "year": 2020, "citations": i})
    return _df(linhas)


def _sem_ano() -> pd.DataFrame:
    """`year=0` é como o Blicsa grava "não sei" — ver `_metric(zero_is_missing=True)`."""
    linhas = []
    for i in range(12):
        linhas.append({"title": f"Sem ano {i}", "keywords": "residuos;politica;urbano",
                       "authors": f"Autor{i % 3}, C.", "year": 0, "citations": i})
    return _df(linhas)


def _frequencias_iguais() -> pd.DataFrame:
    """Cada termo exatamente 4 vezes: nenhuma ordenação por peso tem desempate."""
    termos = ["alpha", "beta", "gamma", "delta", "epsilon"]
    linhas = []
    for i in range(4):
        for t in termos:
            linhas.append({"title": f"{t} {i}", "keywords": ";".join(termos),
                           "authors": "Autor, D.", "year": 2015 + i, "citations": 10})
    return _df(linhas)


def _termo_dominante() -> pd.DataFrame:
    """Um termo em 100% dos documentos, os outros em 1 cada."""
    linhas = []
    for i in range(30):
        linhas.append({"title": f"Dominante {i}", "keywords": f"dominante;raro{i}",
                       "authors": f"Autor{i}, E.", "year": 2010 + (i % 10), "citations": i})
    return _df(linhas)


def _cinco_mil() -> pd.DataFrame:
    """5.000 documentos, vocabulário de 200 termos — o volume declarado na documentação."""
    linhas = []
    for i in range(5000):
        kws = ";".join(f"t{(i + k) % 200}" for k in range(4))
        linhas.append({"title": f"Doc {i}", "keywords": kws,
                       "authors": f"A{i % 500}, F.", "year": 1990 + (i % 35),
                       "citations": i % 97})
    return _df(linhas)


def _caracteres_dificeis() -> pd.DataFrame:
    """Acento, emoji, aspas, barra invertida, quebra de linha, `<script>` e 600 caracteres.

    Tudo isso atravessa JSON, rótulo de canvas e nome de arquivo de export no mesmo caminho.
    """
    longo = "termo-muito-longo-" + ("x" * 600)
    dificeis = [
        "ação & reação", "café", "naïve", "日本語", "🌍 clima", 'aspas "duplas"',
        "barra\\invertida", "quebra\nlinha", "<script>alert(1)</script>", longo,
        "tab\tinterno", "emoji-composto 👩‍🔬", "acentos ÀÉÎÕÜ", "ponto.e;ponto",
    ]
    linhas = []
    for i in range(8):
        kws = ";".join(dificeis[(i + k) % len(dificeis)] for k in range(4))
        linhas.append({"title": f"Difícil {i} — {dificeis[i % len(dificeis)]}",
                       "keywords": kws, "authors": f"Ávila-Núñez, J{i}.",
                       "year": 2018 + (i % 3), "citations": i * 3,
                       "abstract": "resumo com 🌍 emoji e acentuação: ação, café, naïve."})
    return _df(linhas)


def _abstracts_vazios() -> pd.DataFrame:
    """Extração pelo campo `abstracts` sobre abstracts todos vazios → grafo vazio."""
    linhas = []
    for i in range(10):
        linhas.append({"title": f"Sem resumo {i}", "abstract": "", "keywords": "",
                       "authors": f"Autor{i}, G.", "year": 2019, "citations": 0})
    return _df(linhas)


def _autores_grafias() -> pd.DataFrame:
    """A mesma pessoa em três grafias. O grafo não quebra — ele mente, com três nós."""
    grafias = ["Silva, J.", "Silva, João", "SILVA J", "da Silva, J.", "Silva, J"]
    linhas = []
    for i, g in enumerate(grafias * 3):
        linhas.append({"title": f"Coautoria {i}", "authors": f"{g};Costa, M.",
                       "keywords": "residuos;politica", "year": 2015 + (i % 5),
                       "citations": i})
    return _df(linhas)


CASOS: list[Caso] = [
    Caso("um_documento", "corpus com 1 documento", _um_documento(),
         _coocorrencia(), "layout e clusterização com grafo mínimo"),
    Caso("dois_desconexos", "2 documentos sem termos em comum", _dois_desconexos(2),
         _coocorrencia(), "ForceAtlas2/Louvain/densidade com 2 componentes"),
    Caso("dez_desconexos", "10 componentes isoladas", _dois_desconexos(10),
         _coocorrencia(), "o mesmo com 10 componentes"),
    Caso("mesmo_ano", "todos os documentos do mesmo ano", _mesmo_ano(),
         _coocorrencia(), "overlay com variância zero (vmax == vmin)"),
    Caso("sem_ano", "nenhum documento com ano", _sem_ano(),
         _coocorrencia(), "overlay com a métrica inteiramente ausente"),
    Caso("frequencias_iguais", "todos os termos com a mesma frequência", _frequencias_iguais(),
         _coocorrencia(), "escala de tamanho sem amplitude"),
    Caso("termo_dominante", "um termo dominante, o resto raro", _termo_dominante(),
         _coocorrencia(), "escala esmagada por um outlier"),
    Caso("cinco_mil", "5.000 documentos", _cinco_mil(),
         _coocorrencia(min_ocorrencia=20), "volume declarado na documentação"),
    Caso("caracteres_dificeis", "acentos, emoji, aspas, 600 caracteres", _caracteres_dificeis(),
         _coocorrencia(), "JSON, rótulo de canvas e nome de export"),
    Caso("abstracts_vazios", "corpus só com abstracts vazios", _abstracts_vazios(),
         _coocorrencia(campo="abstracts"), "grafo vazio — o mapa precisa dizer 'sem dados'"),
    Caso("autores_grafias", "autores repetidos em grafias diferentes", _autores_grafias(),
         _coautoria(), "grafo que mente sem quebrar"),
]

POR_NOME = {c.nome: c for c in CASOS}


def monta(caso: Caso, iteracoes: int = 60) -> tuple[nx.Graph, dict]:
    """Grafo + posições, pelo mesmo caminho que a interface usa.

    `iteracoes` baixo de propósito: a bateria roda 11 casos × 3 modos e o que se verifica
    aqui é robustez, não convergência. Os testes de determinismo fixam o valor que usam.
    """
    from core.matrix_builders import NetworkGenerator
    from core.visualizer import compute_fa2_layout

    gen = NetworkGenerator(caso.df)
    G = caso.constroi(gen)
    if G.number_of_nodes():
        gen.apply_clustering()
        gen.compute_overlay_scores()
    pos = compute_fa2_layout(G, iterations=iteracoes)
    return G, pos
