"""Animação temporal e camada artística do mapa (Fase 4).

Duas coisas moram aqui:

1. **Animação temporal** — o campo científico se formando ano a ano. As posições dos nós são
   FIXAS (o layout é calculado sobre o corpus completo); o que muda é presença, tamanho e cor.
   Sem isso a animação vira "sopa de nós saltando" e não se lê nada.
2. **Camada artística** — modo pôster neoplasticista (treemap onde área = peso do cluster) e
   os temas de renderização.

A renderização dos quadros é com PIL, não matplotlib: o quadro é um desenho de círculos,
linhas e texto, o PIL já é dependência do projeto e escreve GIF multi-quadro nativamente.
Sem dependência nova, e o mesmo código serve para o export de imagem e para a evidência.

Design system: canto zero, sem sombra, sem gradiente decorativo. A única rampa contínua
segue sendo a do overlay, onde o gradiente é informação.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from core.map_render import NO_DATA_COLOR, overlay_color, print_pattern_for

# Temas de renderização (mantendo o design system).
THEMES = {
    # papel: o padrão, fundo claro do app
    "paper": {"bg": (246, 244, 238), "ink": (20, 20, 20), "muted": (120, 120, 120)},
    # tinta: para projeção em sala escura
    "ink": {"bg": (20, 20, 20), "ink": (246, 244, 238), "muted": (150, 150, 150)},
    # impressão: alto contraste, preto e branco — clusters distinguíveis por PADRÃO
    "print": {"bg": (255, 255, 255), "ink": (0, 0, 0), "muted": (90, 90, 90)},
}

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Archivo.ttf"


def _font(tamanho: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(FONT_PATH), tamanho)
    except Exception:
        return ImageFont.load_default()


def _hex_to_rgb(cor: str) -> tuple[int, int, int]:
    h = str(cor).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, IndexError):
        return (120, 120, 120)


# ────────────────────────────── animação temporal ──────────────────────────────

@dataclass
class Frame:
    """Um quadro da linha do tempo."""
    year: int
    nodes: dict[str, dict] = field(default_factory=dict)   # nó → {size, color, occurrences}
    edges: list[tuple[str, str, float]] = field(default_factory=list)
    empty: bool = False                 # ano sem nenhum documento
    note: str = ""                      # aviso a exibir no quadro (chave i18n ou texto)

    @property
    def visible(self) -> set[str]:
        return set(self.nodes)


def timeline_frames(
    G,
    df=None,
    metric: str = "avg_year",
    cumulative: bool = True,
    edge_threshold: float = 0.0,
    theme: str = "paper",
) -> list[Frame]:
    """Quadros ano a ano a partir do grafo já montado.

    O nó entra no quadro do ano da sua PRIMEIRA ocorrência relevante e, daí em diante, cresce
    conforme acumula ocorrências (`cumulative=True`, o padrão — é o que mostra o campo se
    formando). Com `cumulative=False` cada quadro mostra só o recorte daquele ano.

    Ano sem nenhum documento vira um quadro VÁLIDO e vazio, com aviso — nunca um buraco na
    animação nem uma exceção.
    """
    anos_por_no: dict[str, int] = {}
    ocorr: dict[str, float] = {}
    for n, attrs in G.nodes(data=True):
        primeiro = attrs.get("first_year")
        if primeiro in (None, 0):
            # Sem ano de estreia, cai no ano médio — e, sem ele, o nó fica de fora da
            # linha do tempo (não se inventa uma data para ele).
            media = attrs.get("year_mean") or attrs.get("avg_year")
            primeiro = int(media) if media else None
        if primeiro:
            anos_por_no[n] = int(primeiro)
        ocorr[n] = float(attrs.get("occurrence", attrs.get("occurrences", 1)) or 1)

    if not anos_por_no:
        return []

    anos_corpus: set[int] = set()
    if df is not None and "year" in getattr(df, "columns", []):
        for v in df["year"]:
            try:
                y = int(v)
            except (TypeError, ValueError):
                continue
            if y > 0:
                anos_corpus.add(y)

    y_min = min(anos_por_no.values())
    y_max = max(anos_por_no.values())
    if anos_corpus:
        y_min = min(y_min, min(anos_corpus))
        y_max = max(y_max, max(anos_corpus))

    valores = [v for v in (G.nodes[n].get({"avg_year": "year_mean",
                                           "avg_citations": "citations_mean"}.get(metric, "occurrence"))
                           for n in G.nodes()) if v not in (None, 0)]
    vmin, vmax = (min(valores), max(valores)) if valores else (0.0, 1.0)

    tam_max = max(ocorr.values()) or 1.0
    quadros: list[Frame] = []

    for ano in range(int(y_min), int(y_max) + 1):
        if cumulative:
            presentes = {n for n, y in anos_por_no.items() if y <= ano}
        else:
            presentes = {n for n, y in anos_por_no.items() if y == ano}

        vazio = bool(anos_corpus) and ano not in anos_corpus
        f = Frame(year=ano, empty=(not presentes) or vazio)
        if f.empty and not presentes:
            f.note = "map.anim_year_empty"
            quadros.append(f)
            continue
        if vazio:
            f.note = "map.anim_year_no_docs"

        for n in presentes:
            attrs = G.nodes[n]
            if metric == "occurrences":
                bruto = ocorr[n]
            else:
                bruto = attrs.get({"avg_year": "year_mean",
                                   "avg_citations": "citations_mean"}[metric])
            valor = None if bruto in (None, 0) else float(bruto)
            f.nodes[n] = {
                "size": 3.0 + 17.0 * (ocorr[n] / tam_max),
                "color": attrs.get("color", "#1E4DA0"),
                "overlay_color": overlay_color(valor, vmin, vmax),
                "occurrences": ocorr[n],
                "cluster": int(attrs.get("group", 0) or 0),
            }

        for u, v, d in G.edges(data=True):
            if u in presentes and v in presentes:
                peso = float(d.get("weight", 1) or 1)
                if peso >= edge_threshold:
                    f.edges.append((u, v, peso))

        quadros.append(f)

    return quadros


def frames_share_positions(quadros: Sequence[Frame], positions: dict) -> bool:
    """Todos os quadros usam as MESMAS posições (layout fixo).

    É invariante do desenho: `timeline_frames` nunca devolve coordenadas, justamente para
    que não exista caminho onde um quadro mova um nó. Esta função confirma que todo nó
    visível em qualquer quadro tem posição no mapa fixo.
    """
    for f in quadros:
        for n in f.nodes:
            if n not in positions:
                return False
    return True


# ────────────────────────────── render de quadro ──────────────────────────────

def _projector(positions: dict, width: int, height: int, margin: int, footer: int):
    """Converte coordenada do grafo em pixel. Uma única projeção para TODOS os quadros —
    é o que garante que os nós não saltam entre quadros."""
    pts = [(float(x), float(y)) for x, y in positions.values()
           if math.isfinite(float(x)) and math.isfinite(float(y))]
    if not pts:
        pts = [(0.0, 0.0), (1.0, 1.0)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    span_x = (xmax - xmin) or 1.0
    span_y = (ymax - ymin) or 1.0

    def proj(n):
        x, y = positions.get(n, (0.0, 0.0))
        x = float(x) if math.isfinite(float(x)) else 0.0
        y = float(y) if math.isfinite(float(y)) else 0.0
        px = margin + (x - xmin) / span_x * (width - 2 * margin)
        py = margin + (1 - (y - ymin) / span_y) * (height - 2 * margin - footer)
        return px, py

    return proj


def render_frame(
    frame: Frame,
    positions: dict,
    width: int = 900,
    height: int = 650,
    theme: str = "paper",
    mode: str = "network",
    legend: dict | None = None,
    show_year: bool = True,
    max_labels: int = 18,
):
    """Desenha um quadro como imagem PIL."""
    from PIL import Image, ImageDraw

    cores = THEMES.get(theme, THEMES["paper"])
    footer = 70 if legend else 0
    img = Image.new("RGB", (width, height), cores["bg"])
    d = ImageDraw.Draw(img, "RGBA")
    proj = _projector(positions, width, height, 50, footer)

    # Arestas primeiro, bem apagadas (a informação são os nós).
    tinta = cores["ink"]
    for u, v, peso in frame.edges[:4000]:
        x1, y1 = proj(u)
        x2, y2 = proj(v)
        d.line([(x1, y1), (x2, y2)], fill=(*tinta, 26), width=1)

    # Nós, dos maiores para os menores (o maior fica por cima).
    ordenados = sorted(frame.nodes.items(), key=lambda kv: -kv[1]["size"])
    for n, info in ordenados:
        cx, cy = proj(n)
        r = float(info["size"])
        cor = info["overlay_color"] if mode == "overlay" else info["color"]
        rgb = _hex_to_rgb(cor)
        if theme == "print":
            # Preto e branco: o cluster é distinguível pelo PADRÃO, não pela cor.
            rgb = (255, 255, 255)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb, outline=tinta, width=1)
        if theme == "print":
            _hatch(d, cx, cy, r, print_pattern_for(info["cluster"]), tinta)

    # Rótulos dos maiores, com halo sólido (nunca sombra difusa).
    fonte = _font(13)
    for n, info in ordenados[:max_labels]:
        cx, cy = proj(n)
        r = float(info["size"])
        texto = str(n)[:28]
        tx, ty = cx, cy - r - 12
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            d.text((tx + dx, ty + dy), texto, font=fonte, fill=cores["bg"], anchor="mm")
        d.text((tx, ty), texto, font=fonte, fill=tinta, anchor="mm")

    if show_year:
        # Indicador grande do ano corrente, em Archivo, no canto.
        d.text((width - 28, 28), str(frame.year), font=_font(46), fill=tinta, anchor="ra")

    if frame.note:
        d.text((28, 28), _note_text(frame), font=_font(14), fill=cores["muted"], anchor="la")

    if legend:
        _draw_legend(d, legend, width, height, footer, cores)
    return img


def _note_text(frame: Frame) -> str:
    return {
        "map.anim_year_empty": f"{frame.year}: sem termos ainda",
        "map.anim_year_no_docs": f"{frame.year}: nenhum documento neste ano",
    }.get(frame.note, frame.note)


def _hatch(d, cx, cy, r, padrao: str, tinta):
    """Hachura chapada dentro do círculo — tema impressão."""
    passo = max(3, int(r / 2))
    caixa = [cx - r, cy - r, cx + r, cy + r]
    if padrao == "solid":
        d.ellipse(caixa, fill=tinta)
    elif padrao in ("hlines", "cross"):
        for y in range(int(cy - r), int(cy + r), passo):
            dx = math.sqrt(max(r * r - (y - cy) ** 2, 0))
            d.line([(cx - dx, y), (cx + dx, y)], fill=tinta, width=1)
    if padrao in ("vlines", "cross"):
        for x in range(int(cx - r), int(cx + r), passo):
            dy = math.sqrt(max(r * r - (x - cx) ** 2, 0))
            d.line([(x, cy - dy), (x, cy + dy)], fill=tinta, width=1)
    if padrao in ("diag", "diag-back"):
        sinal = 1 if padrao == "diag" else -1
        for k in range(-int(r), int(r) + 1, passo):
            d.line([(cx - r, cy + sinal * (k - r)), (cx + r, cy + sinal * (k + r))],
                   fill=tinta, width=1)
    if padrao == "dots":
        for yy in range(int(cy - r), int(cy + r), passo):
            for xx in range(int(cx - r), int(cx + r), passo):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    d.ellipse([xx - 1, yy - 1, xx + 1, yy + 1], fill=tinta)
    if padrao == "rings":
        for k in range(1, 4):
            rr = r * k / 3.0
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=tinta, width=1)


LEGEND_REQUIRED = ("query", "documents", "period", "method", "date")


def _draw_legend(d, legend: dict, width: int, height: int, footer: int, cores):
    """Legenda honesta: query, nº de documentos, período, método e data.

    Sem ela a imagem não é reproduzível nem citável — é o que um revisor de periódico cobra.
    """
    y0 = height - footer
    d.line([(0, y0), (width, y0)], fill=cores["ink"], width=2)
    linhas = [
        str(legend.get("query", "—")),
        f'{legend.get("documents", "—")} documentos · {legend.get("period", "—")} · '
        f'{legend.get("method", "—")}',
        str(legend.get("date", "—")),
    ]
    for i, linha in enumerate(linhas):
        d.text((18, y0 + 12 + i * 17), linha[:130],
               font=_font(13 if i == 0 else 11), fill=cores["ink"], anchor="la")


# ────────────────────────────── exports da animação ──────────────────────────────

def export_gif(imagens: Sequence, filepath: str, duration_ms: int = 700, loop: int = 0) -> str:
    """Grava GIF multi-quadro. O PIL faz isso nativamente — sem imageio nem ffmpeg."""
    if not imagens:
        raise ValueError("nenhum quadro para gravar")
    primeira, resto = imagens[0], list(imagens[1:])
    primeira.save(filepath, save_all=True, append_images=resto,
                  duration=max(20, int(duration_ms)), loop=int(loop), optimize=False)
    return filepath


def export_png_sequence(imagens: Sequence, pasta: str, prefixo: str = "quadro") -> list[str]:
    p = Path(pasta)
    p.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, img in enumerate(imagens):
        alvo = p / f"{prefixo}_{i:03d}.png"
        img.save(alvo)
        caminhos.append(str(alvo))
    return caminhos


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def export_mp4(imagens: Sequence, filepath: str, fps: int = 2,
               pasta_tmp: str | None = None) -> tuple[bool, str]:
    """MP4 via ffmpeg. Degrada com elegância: sem ffmpeg devolve (False, motivo).

    Nunca levanta por ausência do ffmpeg — o chamador segue e o GIF continua saindo.
    """
    if not ffmpeg_available():
        return False, ("ffmpeg não encontrado no sistema — MP4 pulado. "
                       "O GIF e a sequência de PNGs foram gerados normalmente.")
    import tempfile
    tmp = pasta_tmp or tempfile.mkdtemp(prefix="blicsa_anim_")
    export_png_sequence(imagens, tmp, "f")
    cmd = ["ffmpeg", "-y", "-framerate", str(max(1, int(fps))),
           "-i", str(Path(tmp) / "f_%03d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", filepath]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:
        return False, f"ffmpeg falhou: {e}"
    if r.returncode != 0:
        return False, f"ffmpeg retornou {r.returncode}: {r.stderr[-300:]}"
    return True, filepath


# ────────────────────────────── modo pôster (Mondrian) ──────────────────────────────

# Cores primárias do design system para os planos do pôster.
POSTER_COLORS = ["#DF3117", "#1E4DA0", "#F5BE00", "#F6F4EE", "#141414"]


def squarified_treemap(pesos: Sequence[float], width: float, height: float,
                       x0: float = 0.0, y0: float = 0.0) -> list[tuple[float, float, float, float]]:
    """Treemap: retângulos com área PROPORCIONAL ao peso, cobrindo o canvas inteiro.

    É o que faz o pôster ser uma visualização legítima e não enfeite: a área lida como
    tamanho do cluster. Algoritmo squarified (Bruls et al.), que favorece retângulos com
    proporção próxima do quadrado — no estilo neoplasticista isso importa, porque tiras
    finíssimas destruiriam a composição.
    """
    valores = [max(float(p), 0.0) for p in pesos]
    total = sum(valores)
    if not valores or total <= 0:
        return []

    area_total = float(width) * float(height)
    escalados = [v / total * area_total for v in valores]

    resultado: list[tuple[float, float, float, float]] = []
    x, y, w, h = float(x0), float(y0), float(width), float(height)
    restantes = list(escalados)

    def pior_proporcao(fila: list[float], lado: float) -> float:
        if not fila or lado <= 0:
            return float("inf")
        s = sum(fila)
        if s <= 0:
            return float("inf")
        maior, menor = max(fila), min(fila)
        return max((lado * lado * maior) / (s * s), (s * s) / (lado * lado * menor))

    while restantes:
        lado = min(w, h)
        fila: list[float] = [restantes.pop(0)]
        while restantes and pior_proporcao(fila + [restantes[0]], lado) <= pior_proporcao(fila, lado):
            fila.append(restantes.pop(0))

        soma = sum(fila)
        if lado == w:                       # empilha na horizontal
            altura_faixa = soma / w if w else 0.0
            cx = x
            for area in fila:
                largura = area / altura_faixa if altura_faixa else 0.0
                resultado.append((cx, y, largura, altura_faixa))
                cx += largura
            y += altura_faixa
            h -= altura_faixa
        else:                               # empilha na vertical
            largura_faixa = soma / h if h else 0.0
            cy = y
            for area in fila:
                altura = area / largura_faixa if largura_faixa else 0.0
                resultado.append((x, cy, largura_faixa, altura))
                cy += altura
            x += largura_faixa
            w -= largura_faixa

    return resultado


def render_poster(
    cluster_weights: dict[int, float],
    cluster_terms: dict[int, Sequence[str]] | None = None,
    cluster_labels: dict[int, str] | None = None,
    width: int = 1400,
    height: int = 1000,
    theme: str = "paper",
    legend: dict | None = None,
    title: str = "",
):
    """Pôster neoplasticista: planos retangulares chapados, linhas pretas estruturais.

    Não é enfeite — é um treemap: a ÁREA de cada plano é proporcional ao peso do cluster, e a
    leitura é imediata. Canto zero, sem sombra, sem gradiente.
    """
    from PIL import Image, ImageDraw

    cores = THEMES.get(theme, THEMES["paper"])
    footer = 80 if legend else 0
    topo = 70 if title else 0
    img = Image.new("RGB", (width, height), cores["bg"])
    d = ImageDraw.Draw(img)

    itens = sorted(cluster_weights.items(), key=lambda kv: -float(kv[1] or 0))
    itens = [(c, float(p)) for c, p in itens if float(p or 0) > 0]
    if not itens:
        d.text((width // 2, height // 2), "Nenhum dado para exibir",
               font=_font(24), fill=cores["ink"], anchor="mm")
        return img

    area_h = height - footer - topo
    rects = squarified_treemap([p for _, p in itens], width, area_h, 0, topo)

    for i, ((cluster, peso), (rx, ry, rw, rh)) in enumerate(zip(itens, rects)):
        cor = POSTER_COLORS[i % len(POSTER_COLORS)]
        rgb = _hex_to_rgb(cor)
        if theme == "print":
            rgb = (255, 255, 255)
        d.rectangle([rx, ry, rx + rw, ry + rh], fill=rgb)
        # Linhas pretas estruturais — a assinatura do neoplasticismo.
        d.rectangle([rx, ry, rx + rw, ry + rh], outline=cores["ink"], width=6)

        # Termos principais dentro do plano, em Archivo.
        termos = list((cluster_terms or {}).get(cluster, []))[:5]
        rotulo = (cluster_labels or {}).get(cluster, f"Cluster {cluster}")
        claro = sum(rgb) / 3 > 128
        texto_cor = (20, 20, 20) if claro else (246, 244, 238)
        if theme == "print":
            texto_cor = (0, 0, 0)

        px, py = rx + 18, ry + 16
        if rh > 46 and rw > 90:
            d.text((px, py), str(rotulo)[:26], font=_font(min(26, max(13, int(rh / 8)))),
                   fill=texto_cor, anchor="la")
            py += 30
            for t in termos:
                if py > ry + rh - 18:
                    break
                d.text((px, py), str(t)[:30], font=_font(13), fill=texto_cor, anchor="la")
                py += 17

    if title:
        d.text((24, 24), title[:70], font=_font(34), fill=cores["ink"], anchor="la")
    if legend:
        _draw_legend(d, legend, width, height, footer, cores)
    return img


def poster_area_report(cluster_weights: dict[int, float], width: int, height: int,
                       footer: int = 0, topo: int = 0) -> dict:
    """Confere que a área de cada plano é proporcional ao peso — a base do teste do pôster."""
    itens = [(c, float(p)) for c, p in
             sorted(cluster_weights.items(), key=lambda kv: -float(kv[1] or 0))
             if float(p or 0) > 0]
    if not itens:
        return {"rects": [], "total_area": 0.0, "canvas_area": 0.0, "errors": {}}

    area_h = height - footer - topo
    rects = squarified_treemap([p for _, p in itens], width, area_h, 0, topo)
    total_peso = sum(p for _, p in itens)
    canvas = float(width) * float(area_h)

    erros: dict[int, float] = {}
    soma_area = 0.0
    for (cluster, peso), (_, _, rw, rh) in zip(itens, rects):
        area = rw * rh
        soma_area += area
        esperado = peso / total_peso * canvas
        erros[cluster] = abs(area - esperado) / esperado if esperado else 0.0
    return {"rects": rects, "total_area": soma_area, "canvas_area": canvas, "errors": erros}
