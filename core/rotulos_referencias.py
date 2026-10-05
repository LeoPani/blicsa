"""Rótulos legíveis para referências do OpenAlex no mapa de cocitação.

No OpenAlex as referências de um artigo são IDs (`https://openalex.org/W2741809807`), e o
mapa de cocitação mostrava esses códigos como rótulo dos nós: inútil para quem lê. Aqui os
IDs que viraram nós são resolvidos para "Sobrenome (ano)", em lotes de 50 por consulta,
com cache em disco (`~/Blicsa/cache/rotulos_openalex.json`) para não perguntar de novo.

Sem internet, ou se o OpenAlex falhar, o mapa sai com o rótulo curto de antes: o rótulo é
melhoria, nunca motivo para o mapa não abrir.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Optional

log = logging.getLogger("blicsa")

_TRAVA = threading.Lock()
#: Versão do formato do rótulo. Entradas antigas ("Gregor e outro (2013)") são refeitas.
VERSAO = 2


def caminho_cache() -> Path:
    return Path.home() / "Blicsa" / "cache" / "rotulos_openalex.json"


def _ler_cache(caminho: Path) -> dict:
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_cache(caminho: Path, dados: dict) -> None:
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        os.replace(tmp, caminho)
    except OSError as exc:
        log.warning("[Rótulos] cache não gravado: %s", exc)


def id_openalex(valor) -> str:
    m = re.fullmatch(r"\s*(?:https?://openalex\.org/)?(W\d+)\s*", str(valor or ""), re.I)
    return m.group(1).upper() if m else ""


def rotulos(ids: Iterable[str], obter: Optional[Callable[[str], Optional[dict]]] = None, *,
            mailto: str = "blicsa.app@gmail.com", cache: Optional[Path] = None,
            cancelar=None) -> dict[str, str]:
    """{W…: "Sobrenome (ano)"} para os IDs que o OpenAlex conhece. Nunca levanta por rede."""
    from core.artigos_conectados import _Cliente, rotulo, sobrenome
    ids = [i for i in dict.fromkeys(id_openalex(x) for x in ids) if i]
    if not ids:
        return {}
    cache = cache or caminho_cache()
    with _TRAVA:
        conhecidos = _ler_cache(cache)
    faltam = [i for i in ids if not (isinstance(conhecidos.get(i), dict)
                                     and conhecidos[i].get("v") == VERSAO)]
    if faltam:
        if obter is None and os.environ.get("BLICSA_SEM_REDE"):
            pass                                   # testes: nunca consultar a rede de verdade
        elif obter is None:
            try:
                from core.artigos_conectados import obter_padrao
                obter, mailto = obter_padrao()
            except Exception as exc:
                log.warning("[Rótulos] OpenAlex indisponível: %s", exc)
                obter = None
        if obter is not None:
            novos = {}

            def guardar(i, w):
                novos[i] = {"v": VERSAO, "rotulo": rotulo(w), "sobrenome": sobrenome(w),
                            "ano": w.get("publication_year"),
                            "titulo": str(w.get("title") or w.get("display_name") or "")}
            try:
                cli = _Cliente(obter, mailto, cancelar)
                for w in cli.em_lote(faltam):
                    i = id_openalex(w.get("id"))
                    if i:
                        guardar(i, w)
                # O filtro em lote não devolve obras que o OpenAlex fundiu com outra (o código
                # antigo continua nas referências). A consulta direta segue o redirecionamento.
                # Visto ao vivo em 04/10: "W2962739339" no mapa de cocitação.
                for i in [x for x in faltam if x not in novos][:40]:
                    w = cli.obra(i)
                    if w:
                        guardar(i, w)
                    else:
                        # O OpenAlex respondeu e não conhece: guarda isso para não perguntar
                        # de novo a cada mapa. (Falha de rede levanta e não chega aqui.)
                        novos[i] = {"v": VERSAO, "rotulo": "", "desconhecido": True}
            except InterruptedError:
                raise
            except Exception as exc:
                log.warning("[Rótulos] consulta ao OpenAlex falhou: %s", exc)
            if novos:
                with _TRAVA:
                    conhecidos = _ler_cache(cache)
                    conhecidos.update(novos)
                    _gravar_cache(cache, conhecidos)
    out = {i: conhecidos[i]["rotulo"] for i in ids
           if isinstance(conhecidos.get(i), dict) and conhecidos[i].get("rotulo")}
    # "Silva et al. (2020)" duas vezes vira "(2020a)" e "(2020b)", como nas normas de citação.
    repetidos = Counter(out.values())
    letras: Counter = Counter()
    for i in sorted(out, key=lambda x: int(x[1:])):
        r = out[i]
        if repetidos[r] > 1 and r.endswith(")"):
            letras[r] += 1
            out[i] = f"{r[:-1]}{chr(96 + letras[r])})"
    return out


def aplicar_no_grafo(G, obter=None, *, tempo_max: float = 15.0, **kw) -> int:
    """Troca o rótulo dos nós que são IDs do OpenAlex. Devolve quantos foram trocados.

    A consulta roda numa thread com tempo máximo: sem internet, o provider tenta de novo
    com espera crescente, e o mapa não pode ficar esperando isso. Se passar do tempo, o
    mapa sai com os rótulos curtos (e o que chegar depois fica no cache para a próxima).
    """
    alvo = {n: id_openalex(n) for n in G.nodes if id_openalex(n)}
    if not alvo:
        return 0
    resultado: dict = {}

    def consultar():
        try:
            resultado.update(rotulos(alvo.values(), obter, **kw))
        except Exception as exc:          # noqa: BLE001 — rótulo nunca derruba o mapa
            log.warning("[Rótulos] %s", exc)
    th = threading.Thread(target=consultar, daemon=True, name="rotulos_openalex")
    th.start()
    th.join(tempo_max)
    if th.is_alive():
        log.info("[Rótulos] OpenAlex demorou mais de %.0f s; mapa sai com rótulos curtos", tempo_max)
        return 0
    titulos = _ler_cache(kw.get("cache") or caminho_cache())
    trocados = 0
    for n, i in alvo.items():
        if i in resultado:
            G.nodes[n]["label"] = resultado[i]
            titulo = (titulos.get(i) or {}).get("titulo")
            if titulo:
                G.nodes[n]["title"] = f"<b>{resultado[i]}</b><br>{titulo}"
            trocados += 1
    return trocados
