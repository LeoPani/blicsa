"""Controles de qualidade do mapa — a parte testável, fora da UI.

O guia do VOSviewer é explícito: a diferença entre um mapa ruim e um bom está nos parâmetros,
não no desenho. Este módulo concentra as operações que os controles disparam, para que possam
ser testadas sem abrir janela:

* `recluster` — muda a resolução SEM refazer o layout (é o ponto do passo 14 do guia: 1.0 →
  1.20 muda de 3 para 4 clusters, e o mapa tem de continuar o mesmo mapa);
* `MapParams` — o conjunto de parâmetros que define o mapa, serializável para o `.blicsa`;
* `export_svg` — vetor de verdade para publicação (o canvas do Sigma é WebGL e só dá raster);
* `parse_cluster_labels` — leitura tolerante da resposta da IA.
"""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

import networkx as nx

from core.map_render import overlay_color, print_pattern_for
from core.matrix_builders import CLUSTER_PALETTE, _apply_clustering, _color_nodes

# Faixa da resolução exposta na UI (o guia usa 1.0 como padrão e 1.20 no exemplo).
RESOLUTION_MIN, RESOLUTION_DEFAULT, RESOLUTION_MAX = 0.5, 1.0, 2.0


# ────────────────────────────── reclusterizar ──────────────────────────────

def recluster(G: nx.Graph, resolution: float = RESOLUTION_DEFAULT,
              algorithm: str = "louvain") -> dict[str, int]:
    """Recalcula os clusters do grafo EXISTENTE, sem tocar em posições nem em arestas.

    É o que separa "ajustar a resolução" de "gerar o mapa de novo": o layout custa segundos
    e, pior, muda o desenho inteiro — o usuário perderia a referência visual a cada ajuste.
    Aqui só o atributo `group` (e a cor derivada) muda.
    """
    if G.number_of_nodes() == 0:
        return {}
    res = max(RESOLUTION_MIN, min(RESOLUTION_MAX, float(resolution)))
    partition = _apply_clustering(G, algorithm=algorithm, resolution=res)
    _color_nodes(G, partition)
    return partition


def cluster_sizes(G: nx.Graph) -> dict[int, int]:
    """{cluster: nº de nós}, ordenado por tamanho decrescente."""
    contagem: dict[int, int] = {}
    for _, grupo in G.nodes(data="group"):
        if grupo is None:
            continue
        contagem[int(grupo)] = contagem.get(int(grupo), 0) + 1
    return dict(sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0])))


# ────────────────────────────── parâmetros ──────────────────────────────

@dataclass
class MapParams:
    """Tudo que define o mapa. Persistido no `.blicsa` para o projeto reabrir igual."""
    fields: str = "keywords"            # keywords | title_abstract | both
    method: str = "auto"                # auto | spacy | nltk | ngram
    binary_count: bool = True           # contagem binária por documento (padrão VOSviewer)
    min_occurrences: int = 3
    resolution: float = RESOLUTION_DEFAULT
    algorithm: str = "louvain"
    attraction: float = 1.0             # ForceAtlas2 — o guia sugere 1 quando há sobreposição
    repulsion: float = 0.0              # …e 0 de repulsão no mesmo caso
    max_edges: int = 0                  # 0 = sem teto
    excluded_terms: list[str] = field(default_factory=list)
    thesaurus_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "MapParams":
        """Reconstrói tolerando dicionário parcial, chaves a mais e tipos errados.

        Projeto salvo por uma versão anterior não tem os campos novos; um `.blicsa` editado à
        mão pode ter lixo. Em nenhum dos casos o projeto pode deixar de abrir.
        """
        d = d or {}
        base = cls()
        for k, tipo_padrao in base.to_dict().items():
            if k not in d:
                continue
            v = d[k]
            try:
                if isinstance(tipo_padrao, bool):
                    setattr(base, k, bool(v))
                elif isinstance(tipo_padrao, int) and not isinstance(tipo_padrao, bool):
                    setattr(base, k, int(v))
                elif isinstance(tipo_padrao, float):
                    setattr(base, k, float(v))
                elif isinstance(tipo_padrao, list):
                    setattr(base, k, [str(x) for x in (v or [])])
                else:
                    setattr(base, k, str(v))
            except (TypeError, ValueError):
                pass          # valor inválido → mantém o padrão, sem quebrar a abertura
        base.resolution = max(RESOLUTION_MIN, min(RESOLUTION_MAX, base.resolution))
        base.min_occurrences = max(1, base.min_occurrences)
        return base


def allowed_terms_from(termos: Iterable[str], excluidos: Iterable[str]) -> set[str]:
    """Termos que sobrevivem à lista de exclusão da tabela revisável (passo 13 do guia)."""
    fora = {str(t).strip().lower() for t in (excluidos or []) if str(t).strip()}
    return {str(t) for t in termos if str(t).strip().lower() not in fora}


# ────────────────────────────── rótulos de cluster ──────────────────────────────

def parse_cluster_labels(raw: str) -> dict[int, str]:
    """Lê "0: Rótulo" linha a linha, ignorando tudo que não casar.

    A IA às vezes devolve preâmbulo, markdown ou JSON em vez das linhas pedidas. Nenhum desses
    casos pode derrubar a rotulagem: o que der para aproveitar é aproveitado, o resto é
    ignorado. Resposta totalmente malformada devolve dicionário vazio — nunca exceção.
    """
    labels: dict[int, str] = {}
    if not raw or not isinstance(raw, str):
        return labels

    # Caminho alternativo: a IA devolveu JSON {"0": "Rótulo"}.
    texto = raw.strip()
    if texto.startswith("{"):
        try:
            dados = json.loads(texto)
            for k, v in dados.items():
                try:
                    labels[int(k)] = str(v).strip()
                except (TypeError, ValueError):
                    continue
            if labels:
                return labels
        except json.JSONDecodeError:
            pass

    for linha in texto.splitlines():
        # Tira ênfase markdown em QUALQUER posição antes de casar: a IA escreve
        # "- **0**: Rótulo", e limpar só o começo da linha deixaria o "**" grudado no número.
        limpa = re.sub(r"[*_`]", "", linha)
        limpa = re.sub(r"^[\s\-#>]+", "", limpa)            # bullet e citação
        m = re.match(r"^(\d+)\s*[:\-–]\s*(.+)$", limpa)
        if m:
            rotulo = m.group(2).strip().strip("*_`\"' ")
            if rotulo:
                labels[int(m.group(1))] = rotulo
    return labels


def apply_cluster_labels(G: nx.Graph, labels: dict[int, str]) -> int:
    """Grava o rótulo do cluster nos nós. Devolve quantos nós foram afetados."""
    n = 0
    for node, grupo in list(G.nodes(data="group")):
        if grupo is None:
            continue
        rotulo = labels.get(int(grupo))
        if rotulo:
            G.nodes[node]["cluster_label"] = rotulo
            n += 1
    return n


# ────────────────────────────── export SVG ──────────────────────────────

def export_svg(
    G: nx.Graph,
    positions: dict,
    filepath: str,
    width: int = 1600,
    height: int = 1200,
    mode: str = "network",
    metric: str = "avg_year",
    theme: str = "paper",
    legend: dict | None = None,
    max_edges: int = 2000,
) -> str:
    """Escreve o mapa como SVG — vetor de verdade, para publicação.

    O canvas do Sigma é WebGL e só exporta raster; um periódico pede vetor. Aqui o mesmo grafo
    e as MESMAS posições viram SVG, com as mesmas regras de cor dos outros modos.

    `legend` é o dicionário da legenda honesta (query, nº de documentos, período, método,
    data) — sem ele a imagem não é reproduzível nem citável.
    """
    fundo, tinta = ("#F6F4EE", "#141414")
    if theme == "ink":
        fundo, tinta = ("#141414", "#F6F4EE")
    elif theme == "print":
        fundo, tinta = ("#FFFFFF", "#000000")

    nos = list(G.nodes())
    if nos:
        xs = [float(positions.get(n, (0, 0))[0]) for n in nos]
        ys = [float(positions.get(n, (0, 0))[1]) for n in nos]
        xs = [x for x in xs if math.isfinite(x)] or [0.0]
        ys = [y for y in ys if math.isfinite(y)] or [0.0]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    else:
        xmin, xmax, ymin, ymax = 0.0, 1.0, 0.0, 1.0
    span_x = (xmax - xmin) or 1.0
    span_y = (ymax - ymin) or 1.0
    margem = 60
    rodape = 90 if legend else 0

    def px(n):
        x, y = positions.get(n, (0.0, 0.0))
        x = float(x) if math.isfinite(float(x)) else 0.0
        y = float(y) if math.isfinite(float(y)) else 0.0
        cx = margem + (x - xmin) / span_x * (width - 2 * margem)
        # y do SVG cresce para baixo; inverte para o mapa não sair espelhado.
        cy = margem + (1 - (y - ymin) / span_y) * (height - 2 * margem - rodape)
        return cx, cy

    tamanhos = [float(G.nodes[n].get("size", 10) or 10) for n in nos] or [10.0]
    s_min, s_max = min(tamanhos), max(tamanhos)
    s_span = (s_max - s_min) or 1.0

    valores = [G.nodes[n].get({"avg_year": "year_mean",
                               "avg_citations": "citations_mean"}.get(metric, "occurrence"))
               for n in nos]
    validos = [float(v) for v in valores
               if v is not None and not (isinstance(v, float) and math.isnan(v)) and float(v) != 0]
    vmin, vmax = (min(validos), max(validos)) if validos else (0.0, 1.0)

    partes: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{fundo}"/>',
    ]

    if theme == "print":
        # Clusters distinguíveis SEM cor: cada um ganha um padrão de preenchimento.
        partes.append("<defs>")
        for c in sorted({int(g or 0) for _, g in G.nodes(data="group")}):
            partes.append(_pattern_def(f"pat{c}", print_pattern_for(c)))
        partes.append("</defs>")

    arestas = sorted(G.edges(data=True), key=lambda e: float(e[2].get("weight", 1) or 1),
                     reverse=True)
    if max_edges:
        arestas = arestas[:max_edges]
    if arestas and mode != "density":
        pesos = [float(d.get("weight", 1) or 1) for _, _, d in arestas]
        w_min, w_span = min(pesos), (max(pesos) - min(pesos)) or 1.0
        partes.append(f'<g stroke="{tinta}" stroke-opacity="0.10" fill="none">')
        for u, v, d in arestas:
            x1, y1 = px(u)
            x2, y2 = px(v)
            esp = 0.2 + 1.6 * ((float(d.get("weight", 1) or 1) - w_min) / w_span)
            partes.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke-width="{esp:.2f}"/>')
        partes.append("</g>")

    for n in nos:
        cx, cy = px(n)
        attr = G.nodes[n]
        raio = 3 + 14 * ((float(attr.get("size", 10) or 10) - s_min) / s_span)
        if mode == "overlay":
            bruto = attr.get({"avg_year": "year_mean",
                              "avg_citations": "citations_mean"}.get(metric, "occurrence"))
            valor = None if (bruto is None or float(bruto or 0) == 0) else float(bruto)
            cor = overlay_color(valor, vmin, vmax)
        elif theme == "print":
            cor = f"url(#pat{int(attr.get('group', 0) or 0)})"
        else:
            cor = attr.get("color", CLUSTER_PALETTE[0])
        partes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{raio:.1f}" fill="{cor}" '
                      f'stroke="{tinta}" stroke-width="0.8"/>')

    # Rótulos por último, para ficarem por cima dos nós.
    partes.append(f'<g font-family="Archivo, Inter, sans-serif" font-size="12" '
                  f'font-weight="600" fill="{tinta}" text-anchor="middle">')
    for n in sorted(nos, key=lambda k: float(G.nodes[k].get("size", 10) or 10), reverse=True)[:120]:
        cx, cy = px(n)
        raio = 3 + 14 * ((float(G.nodes[n].get("size", 10) or 10) - s_min) / s_span)
        rotulo = html.escape(str(G.nodes[n].get("label", n)))[:40]
        partes.append(f'<text x="{cx:.1f}" y="{cy - raio - 4:.1f}">{rotulo}</text>')
    partes.append("</g>")

    if legend:
        partes.append(_legend_svg(legend, width, height, rodape, fundo, tinta))

    partes.append("</svg>")
    svg = "\n".join(partes)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg)
    return svg


def _pattern_def(pid: str, tipo: str) -> str:
    """Padrão de preenchimento do tema impressão (hachuras chapadas, sem gradiente)."""
    traco = '<path stroke="#000000" stroke-width="1.2" fill="none" d="%s"/>'
    corpo = {
        "solid": '<rect width="8" height="8" fill="#000000"/>',
        "hlines": traco % "M0,2 H8 M0,6 H8",
        "vlines": traco % "M2,0 V8 M6,0 V8",
        "diag": traco % "M0,8 L8,0",
        "diag-back": traco % "M0,0 L8,8",
        "cross": traco % "M0,4 H8 M4,0 V8",
        "dots": '<circle cx="4" cy="4" r="1.6" fill="#000000"/>',
        "rings": '<circle cx="4" cy="4" r="2.4" fill="none" stroke="#000000" stroke-width="1.2"/>',
    }.get(tipo, '<rect width="8" height="8" fill="#000000"/>')
    return (f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="8" height="8">'
            f'<rect width="8" height="8" fill="#FFFFFF"/>{corpo}</pattern>')


LEGEND_FIELDS = ("query", "documents", "period", "method", "date")


def _legend_svg(legend: dict, width: int, height: int, rodape: int,
                fundo: str, tinta: str) -> str:
    """Legenda honesta: sem ela a imagem não é reproduzível nem citável por um revisor."""
    y0 = height - rodape
    linhas = [
        f'{legend.get("query", "—")}',
        (f'{legend.get("documents", "—")} documentos · {legend.get("period", "—")} · '
         f'{legend.get("method", "—")}'),
        f'{legend.get("date", "—")}',
    ]
    partes = [f'<g><line x1="0" y1="{y0}" x2="{width}" y2="{y0}" stroke="{tinta}" '
              f'stroke-width="2"/>',
              f'<g font-family="Archivo, Inter, sans-serif" fill="{tinta}" font-size="13">']
    for i, linha in enumerate(linhas):
        peso = "700" if i == 0 else "400"
        partes.append(f'<text x="20" y="{y0 + 26 + i * 20}" font-weight="{peso}">'
                      f'{html.escape(str(linha))}</text>')
    partes.append("</g></g>")
    return "\n".join(partes)


def build_legend(query: str, documents: int, period: str, method: str, date: str) -> dict:
    """Monta a legenda obrigatória dos exports."""
    return {"query": query or "—", "documents": int(documents or 0),
            "period": period or "—", "method": method or "—", "date": date or "—"}
