"""Modo Importação — download em massa explícito, honesto e cancelável.

O par do `core/browse.py`: navegar é barato e instantâneo; **baixar é uma decisão do
usuário**, tomada com o número real na frente.

Decisões do Leonardo que este módulo implementa:

* **limite vazio = ilimitado** (padrão). Quem quer o corpus inteiro tem direito a ele;
* mas acima de `LIMIAR_AVISO` registros aparece um **aviso com o número real e a estimativa
  de tempo**, com três saídas — baixar tudo, limitar, cancelar. Nunca baixar 300 mil por
  acidente, nunca proibir quem quer de verdade;
* **cancelar preserva o que já veio**, e a trilha diz que foi interrompido;
* a trilha final é completa: encontrados, baixados, após deduplicação e filtrados por idioma.

Tudo aqui é testável sem UI: a decisão de avisar, a estimativa de tempo, o progresso e a
trilha são funções puras ou objetos sem Tk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

# Acima disto, perguntar antes de baixar. Não é um teto: é uma confirmação.
LIMIAR_AVISO = 10_000
# Sugestão oferecida no diálogo quando o volume é grande.
LIMITE_SUGERIDO = 10_000


@dataclass
class VolumeDecision:
    """O que a UI deve fazer antes de começar a baixar."""
    warn: bool                 # mostrar o diálogo?
    total: int                 # nº real de registros encontrados
    suggested_limit: int       # o que o botão "Limitar" aplicaria
    eta_seconds: float | None  # estimativa para baixar tudo, se houver taxa conhecida

    def as_dict(self) -> dict:
        return {"warn": self.warn, "total": self.total,
                "suggested_limit": self.suggested_limit, "eta_seconds": self.eta_seconds}


def decide_volume(total: int, limite: int | None, taxa_por_segundo: float | None = None,
                  limiar: int = LIMIAR_AVISO) -> VolumeDecision:
    """Avisar antes de baixar?

    Avisa quando o que SERÁ baixado passa do limiar. Um limite pequeno num universo enorme
    não precisa de aviso — o usuário já limitou.
    """
    total = max(0, int(total or 0))
    efetivo = total if limite in (None, 0) else min(total, int(limite))
    eta = (efetivo / taxa_por_segundo) if (taxa_por_segundo and taxa_por_segundo > 0) else None
    return VolumeDecision(warn=efetivo > int(limiar), total=total,
                          suggested_limit=min(LIMITE_SUGERIDO, total) or LIMITE_SUGERIDO,
                          eta_seconds=eta)


def parse_limit(texto: str | int | None) -> int | None:
    """Campo Limite → nº ou None (ilimitado).

    Vazio, espaço, "0" e lixo viram None = ilimitado, que é o padrão pedido. Negativo também:
    não existe "baixar -5".
    """
    if texto is None:
        return None
    if isinstance(texto, int):
        return texto if texto > 0 else None
    s = str(texto).strip()
    if not s:
        return None
    try:
        n = int(float(s.replace(".", "").replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


class RateEstimator:
    """Taxa de download medida, para a estimativa de tempo ao vivo.

    Usa uma janela deslizante das últimas amostras: as primeiras páginas costumam ser mais
    lentas (conexão fria) e arrastariam a estimativa para cima o download inteiro.
    """

    def __init__(self, janela: int = 8, relogio: Callable[[], float] = time.monotonic):
        self.janela = max(2, int(janela))
        self._relogio = relogio
        self._marcas: list[tuple[float, int]] = []      # (instante, acumulado)

    def update(self, baixados: int):
        self._marcas.append((self._relogio(), int(baixados)))
        if len(self._marcas) > self.janela:
            self._marcas.pop(0)

    @property
    def rate(self) -> float | None:
        """Registros por segundo, ou None enquanto não houver amostra suficiente."""
        if len(self._marcas) < 2:
            return None
        (t0, n0), (t1, n1) = self._marcas[0], self._marcas[-1]
        dt = t1 - t0
        dn = n1 - n0
        if dt <= 0 or dn <= 0:
            return None
        return dn / dt

    def eta(self, restantes: int) -> float | None:
        r = self.rate
        if not r or restantes <= 0:
            return 0.0 if restantes <= 0 else None
        return restantes / r


def format_eta(segundos: float | None) -> str:
    """Segundos → "~28 min" / "~45 s" / "—" quando não dá para saber."""
    if segundos is None:
        return "—"
    s = max(0.0, float(segundos))
    if s < 90:
        return f"~{int(round(s))} s"
    minutos = s / 60.0
    if minutos < 90:
        return f"~{int(round(minutos))} min"
    return f"~{minutos / 60.0:.1f} h"


@dataclass
class ImportProgress:
    """Estado do download, para a barra e o rótulo de tempo."""
    downloaded: int = 0
    target: int = 0            # 0 = desconhecido/ilimitado
    eta_seconds: float | None = None
    cancelled: bool = False

    @property
    def fraction(self) -> float:
        """Fração em [0,1]. Nunca passa de 1 nem fica negativa.

        Com alvo desconhecido devolve 0.0 — a barra fica indeterminada em vez de mentir uma
        porcentagem inventada.
        """
        if self.target <= 0:
            return 0.0
        return max(0.0, min(1.0, self.downloaded / self.target))

    @property
    def percent(self) -> int:
        return int(round(self.fraction * 100))


class ImportJob:
    """Acompanha um download em massa: progresso monotônico, cancelamento e trilha.

    Não faz rede: recebe os lotes de quem faz. Assim o job inteiro é testável com um
    gerador sintético, inclusive os casos de erro e cancelamento.
    """

    def __init__(self, total_encontrado: int, limite: int | None = None,
                 relogio: Callable[[], float] = time.monotonic):
        self.total_encontrado = max(0, int(total_encontrado or 0))
        self.limite = parse_limit(limite)
        self.alvo = self.total_encontrado if self.limite is None else min(
            self.total_encontrado, self.limite)
        self._baixados = 0
        self.cancelado = False
        self.erro_rede = ""
        self.deduplicados = 0
        self.filtrados_idioma = 0
        self._estimador = RateEstimator(relogio=relogio)

    # ── progresso ───────────────────────────────────────────────────────
    @property
    def baixados(self) -> int:
        return self._baixados

    def advance(self, n: int):
        """Soma ao progresso. Nunca regride nem passa do alvo.

        São DUAS guardas contra regressão, e cada uma sozinha já resolve — o `if n <= 0` e o
        `max(...)`. Isso é proposital (barra de progresso é barata e regride feio na tela),
        mas está anotado porque a matriz de reinjeção mostrou que remover UMA delas não
        derruba teste nenhum: quem for simplificar precisa saber que a outra está segurando.
        """
        if n <= 0:
            return
        novo = self._baixados + int(n)
        if self.alvo > 0:
            novo = min(novo, self.alvo)          # não passa do alvo
        self._baixados = max(self._baixados, novo)   # não regride
        self._estimador.update(self._baixados)

    def progress(self) -> ImportProgress:
        restantes = max(0, self.alvo - self._baixados) if self.alvo else 0
        return ImportProgress(downloaded=self._baixados, target=self.alvo,
                              eta_seconds=self._estimador.eta(restantes),
                              cancelled=self.cancelado)

    def cancel(self):
        """Cancela preservando o que já veio."""
        self.cancelado = True

    @property
    def reached_limit(self) -> bool:
        return self.alvo > 0 and self._baixados >= self.alvo

    # ── consumo dos lotes ───────────────────────────────────────────────
    def consume(self, lotes: Iterable[Sequence[dict]],
                on_batch: Callable[[list], None] | None = None) -> list[dict]:
        """Consome lotes até o alvo, o cancelamento ou o fim.

        Devolve os registros acumulados. Em cancelamento devolve o PARCIAL — jogar fora o que
        já foi baixado seria punir quem desistiu de esperar.
        """
        acumulado: list[dict] = []
        for lote in lotes:
            if self.cancelado:
                break
            if self.alvo > 0 and self._baixados >= self.alvo:
                break
            restante = (self.alvo - self._baixados) if self.alvo > 0 else len(lote)
            pedaco = list(lote)[:max(0, restante)]
            if not pedaco:
                break
            acumulado.extend(pedaco)
            self.advance(len(pedaco))
            if on_batch:
                on_batch(pedaco)
        return acumulado

    # ── trilha ──────────────────────────────────────────────────────────
    def trail(self, *, after_dedup: int | None = None) -> str:
        """Trilha completa e honesta.

        "Encontrados N · baixados M · após deduplicação K · filtrados por idioma X", com o
        aviso de interrupção quando houver. A regra herdada das rodadas anteriores: o usuário
        nunca se pergunta onde os resultados foram.
        """
        partes = [f"Encontrados {_fmt(self.total_encontrado)}",
                  f"baixados {_fmt(self._baixados)}"]
        if self.limite and self.total_encontrado > self._baixados:
            partes[-1] += f" de {_fmt(self.limite)} (limite)"
        if after_dedup is not None and after_dedup != self._baixados:
            partes.append(f"após deduplicação {_fmt(after_dedup)}")
            self.deduplicados = self._baixados - int(after_dedup)
        if self.filtrados_idioma:
            partes.append(f"filtrados por idioma {_fmt(self.filtrados_idioma)}")
        trilha = " · ".join(partes)
        if self.cancelado:
            trilha += " · ⚠ cancelado pelo usuário — resultados parciais"
        if self.erro_rede:
            trilha += (f" · ⚠ interrompido por erro de rede — resultados parciais "
                       f"({self.erro_rede[:60]})")
        return trilha


def _fmt(n: int) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def merge_without_duplicates(existentes: Sequence[dict], novos: Sequence[dict],
                             chaves: Sequence[str] = ("doi", "title")) -> tuple[list[dict], int]:
    """Junta novos registros ao corpus sem repetir o que já está lá.

    Reimportar a mesma query é comum — o usuário refina um filtro e importa de novo. Sem esta
    junção o corpus dobraria de tamanho a cada rodada. Compara por DOI (quando há) e, na
    falta dele, pelo título normalizado.
    """
    def assinatura(r: dict) -> tuple:
        doi = str(r.get("doi") or "").strip().lower().replace("https://doi.org/", "")
        if doi:
            return ("doi", doi)
        titulo = " ".join(str(r.get("title") or "").lower().split())
        return ("titulo", titulo)

    vistos = {assinatura(r) for r in existentes}
    saida = list(existentes)
    ignorados = 0
    for r in novos:
        a = assinatura(r)
        if a in vistos or a == ("titulo", ""):
            ignorados += 1
            continue
        vistos.add(a)
        saida.append(r)
    return saida, ignorados
