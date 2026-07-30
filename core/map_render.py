"""Cálculos puros das três visualizações do mapa (network / overlay / densidade).

Fica em Python — e não só no JS — por dois motivos: é testável sem navegador, e os mesmos
números alimentam o modo pôster, a animação e os exports de imagem (Fase 4). O `map.js` recebe
a paleta e os parâmetros já resolvidos daqui via `graph.json`, então JS e Python nunca podem
divergir na escala de cor: existe uma única fonte da verdade.

Design system: canto zero, sem sombra, sem gradiente decorativo. A **barra de cor do overlay**
é a única escala contínua permitida, porque ali o gradiente é informação (ano/citações), não
enfeite.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

# ── Paleta do overlay ─────────────────────────────────────────────────────────────
# Azul → verde → amarelo, como o VOSviewer. Frio = antigo/baixo, quente = recente/alto.
# Interpolada em RGB entre paradas fixas; é a única rampa contínua da UI.
OVERLAY_PALETTE: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (30, 77, 160)),    # #1E4DA0 azul (INK azul do design system)
    (0.50, (122, 158, 126)),  # #7A9E7E verde
    (1.00, (245, 190, 0)),    # #F5BE00 amarelo
)

# Cinza neutro para nó SEM dado da métrica. Honestidade > estética: não se pinta de azul
# (que significaria "mais antigo") o nó que simplesmente não tem ano.
NO_DATA_COLOR = "#B0B0B0"


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def normalize_metric(value: float | None, vmin: float, vmax: float) -> float | None:
    """Põe `value` em [0,1] dentro da faixa. `None` entra, `None` sai (= sem dado).

    Quando `vmax == vmin` (todos os valores iguais — corpus de um único ano, o mesmo bug do
    slider) devolve 0.5: o meio da escala. Não divide por zero e não mente dizendo que o
    valor é o mínimo.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    span = float(vmax) - float(vmin)
    if span <= 0:
        return 0.5
    return _clamp01((v - float(vmin)) / span)


def overlay_color(value: float | None, vmin: float, vmax: float) -> str:
    """Cor hexadecimal do nó no overlay. `None` → cinza de "sem dado"."""
    t = normalize_metric(value, vmin, vmax)
    if t is None:
        return NO_DATA_COLOR
    return color_at(t)


def color_at(t: float) -> str:
    """Cor da rampa na posição `t` ∈ [0,1] (interpolação linear entre as paradas)."""
    t = _clamp01(float(t))
    stops = OVERLAY_PALETTE
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            rgb = tuple(round(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
            return "#%02X%02X%02X" % rgb
    return "#%02X%02X%02X" % stops[-1][1]


def overlay_scale(values: Iterable[float | None], ticks: int = 3) -> dict:
    """Configuração da barra de gradiente: faixa, rótulos e contagem de "sem dado".

    `ticks` é o número de marcas numéricas (3 = extremos + meio, como o VOSviewer).
    """
    validos = []
    sem_dado = 0
    for v in values:
        if v is None:
            sem_dado += 1
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            sem_dado += 1
            continue
        if math.isnan(f) or math.isinf(f):
            sem_dado += 1
            continue
        validos.append(f)

    if not validos:
        return {"min": None, "max": None, "ticks": [], "stops": _palette_stops(),
                "no_data": sem_dado, "uniform": False}

    vmin, vmax = min(validos), max(validos)
    uniform = vmax == vmin
    n = max(2, int(ticks))
    if uniform:
        # Todos iguais: uma marca só, e a UI avisa que a escala não discrimina.
        marcas = [{"t": 0.5, "value": vmin}]
    else:
        marcas = [{"t": i / (n - 1), "value": vmin + (vmax - vmin) * i / (n - 1)}
                  for i in range(n)]
    return {"min": vmin, "max": vmax, "ticks": marcas, "stops": _palette_stops(),
            "no_data": sem_dado, "uniform": uniform}


def _palette_stops() -> list[dict]:
    return [{"t": t, "color": "#%02X%02X%02X" % rgb} for t, rgb in OVERLAY_PALETTE]


# ── Densidade ─────────────────────────────────────────────────────────────────────

def density_grid(
    positions: Sequence[tuple[float, float]],
    weights: Sequence[float] | None = None,
    cols: int = 32,
    rows: int = 32,
    radius: float = 0.15,
    bounds: tuple[float, float, float, float] | None = None,
) -> dict:
    """Mapa de calor por kernel gaussiano sobre uma grade regular.

    Igual ao VOSviewer, a densidade é **relativa ao recorte** (`bounds`): dar zoom recalcula,
    porque a pergunta é "onde há concentração *nesta vista*". O `map.js` chama a versão JS
    desta mesma conta ao mudar a câmera; aqui fica a referência testável e a que alimenta os
    exports de imagem.

    Args:
        positions: pares (x, y) dos nós.
        weights: peso de cada nó (ocorrências). None = todos 1.
        cols, rows: resolução da grade.
        radius: raio do kernel em fração da diagonal do recorte.
        bounds: (xmin, ymin, xmax, ymax). None = calculado dos pontos.

    Returns:
        {"grid": [[float]], "cols", "rows", "bounds", "max"} com a grade normalizada em [0,1].
    """
    pts = [(float(x), float(y)) for x, y in positions
           if not (math.isnan(float(x)) or math.isnan(float(y))
                   or math.isinf(float(x)) or math.isinf(float(y)))]
    cols = max(1, int(cols))
    rows = max(1, int(rows))

    if not pts:
        return {"grid": [[0.0] * cols for _ in range(rows)], "cols": cols, "rows": rows,
                "bounds": (0.0, 0.0, 1.0, 1.0), "max": 0.0}

    w = list(weights) if weights is not None else [1.0] * len(pts)
    if len(w) < len(pts):
        w = w + [1.0] * (len(pts) - len(w))

    if bounds is None:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        # Ponto único (ou linha degenerada): abre uma janela mínima em vez de dividir por zero.
        if xmax - xmin <= 0:
            xmin, xmax = xmin - 0.5, xmax + 0.5
        if ymax - ymin <= 0:
            ymin, ymax = ymin - 0.5, ymax + 0.5
    else:
        xmin, ymin, xmax, ymax = (float(b) for b in bounds)
        if xmax - xmin <= 0:
            xmax = xmin + 1.0
        if ymax - ymin <= 0:
            ymax = ymin + 1.0

    largura, altura = xmax - xmin, ymax - ymin
    diagonal = math.hypot(largura, altura) or 1.0
    sigma = max(float(radius), 1e-6) * diagonal
    dois_sigma2 = 2.0 * sigma * sigma
    corte = (3.0 * sigma) ** 2          # além de 3σ a contribuição é desprezível

    grid = [[0.0] * cols for _ in range(rows)]
    for (px, py), peso in zip(pts, w):
        try:
            pw = float(peso)
        except (TypeError, ValueError):
            pw = 1.0
        if math.isnan(pw) or math.isinf(pw):
            pw = 1.0
        for r in range(rows):
            cy = ymin + altura * (r + 0.5) / rows
            dy2 = (cy - py) ** 2
            if dy2 > corte:
                continue
            linha = grid[r]
            for c in range(cols):
                cx = xmin + largura * (c + 0.5) / cols
                d2 = dy2 + (cx - px) ** 2
                if d2 <= corte:
                    linha[c] += pw * math.exp(-d2 / dois_sigma2)

    pico = max((v for linha in grid for v in linha), default=0.0)
    if pico > 0:
        grid = [[v / pico for v in linha] for linha in grid]
    return {"grid": grid, "cols": cols, "rows": rows,
            "bounds": (xmin, ymin, xmax, ymax), "max": pico}


def density_peaks(grade: dict, limiar: float = 0.5) -> list[tuple[int, int]]:
    """Células que são máximos locais acima do limiar — usado para testar aglomerados."""
    g = grade["grid"]
    rows, cols = len(g), len(g[0]) if g else 0
    picos: list[tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            v = g[r][c]
            if v < limiar:
                continue
            local_max = True
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols and g[rr][cc] > v:
                        local_max = False
                        break
                if not local_max:
                    break
            if local_max:
                picos.append((r, c))
    return picos


# ── Contraste da paleta de clusters ───────────────────────────────────────────────

def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """Luminância relativa (WCAG 2.1)."""
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (0.2126 * _srgb_to_linear(r) + 0.7152 * _srgb_to_linear(g)
            + 0.0722 * _srgb_to_linear(b))


def contrast_ratio(a: str, b: str) -> float:
    """Razão de contraste WCAG entre duas cores (1.0 = idênticas, 21.0 = preto/branco)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def _to_lab(hex_color: str) -> tuple[float, float, float]:
    """sRGB → CIE L*a*b* (iluminante D65), para distância perceptual."""
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (_srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: str, b: str) -> float:
    """Distância perceptual CIE76 entre duas cores. ΔE ≳ 20 = claramente distinguíveis.

    É a métrica certa para cores CATEGÓRICAS lado a lado (clusters vizinhos). A razão de
    contraste WCAG (`contrast_ratio`) mede luminância, para texto sobre fundo: dois tons de
    matiz bem diferente e luminância parecida — vermelho e roxo, p.ex. — dão razão ~1.1 e
    ainda assim se distinguem à vista. Usar WCAG para julgar a paleta de clusters reprovaria
    uma paleta perfeitamente legível; usar ΔE para texto sobre fundo faria o oposto.
    """
    la, lb = _to_lab(a), _to_lab(b)
    return math.sqrt(sum((la[i] - lb[i]) ** 2 for i in range(3)))


def palette_contrast_report(palette: Sequence[str]) -> dict:
    """Distinguibilidade entre TODOS os pares da paleta de clusters.

    Reporta ΔE (a métrica que decide, para cores categóricas) e a razão WCAG junto, por
    referência. O pior par é o que define a legibilidade do mapa.
    """
    pares = []
    for i in range(len(palette)):
        for j in range(i + 1, len(palette)):
            a, b = palette[i], palette[j]
            pares.append({"a": a, "b": b,
                          "delta_e": round(delta_e(a, b), 1),
                          "ratio": round(contrast_ratio(a, b), 2)})
    por_de = sorted(pares, key=lambda p: p["delta_e"])
    por_wcag = sorted(pares, key=lambda p: p["ratio"])
    return {"pairs": por_de,
            "min_delta_e": por_de[0]["delta_e"] if por_de else 0.0,
            "worst_pair": (por_de[0]["a"], por_de[0]["b"]) if por_de else None,
            "min_ratio": por_wcag[0]["ratio"] if por_wcag else 0.0,
            "worst_wcag_pair": (por_wcag[0]["a"], por_wcag[0]["b"]) if por_wcag else None}


# ── Padrões de preenchimento (tema "impressão", Fase 4) ───────────────────────────
# Clusters têm de continuar distinguíveis em preto e branco: cada um ganha um padrão, não só
# uma cor. Definido aqui porque o mesmo mapa alimenta o canvas e o export.
PRINT_PATTERNS: tuple[str, ...] = (
    "solid", "hlines", "vlines", "diag", "diag-back", "cross", "dots", "rings",
)


def print_pattern_for(cluster: int) -> str:
    """Padrão de preenchimento do cluster no tema impressão (cíclico e determinístico)."""
    return PRINT_PATTERNS[int(cluster) % len(PRINT_PATTERNS)]
