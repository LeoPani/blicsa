#!/usr/bin/env python3
"""Capturas dos três modos do mapa sobre corpus adversariais — Auditoria 1, Fase 1.

**Mapa de verdade, não figura de teste.** Monta o corpus pelo mesmo caminho do app
(`NetworkGenerator` → ForceAtlas2 → `export_sigma_json`), serve pelo mesmo servidor local
confinado, abre o mesmo `map_template.html` no `pywebview` e captura a janela por
`CGWindowID` — a mesma cadeia que produziu `mapa_network.png` na rodada dos mapas, e o mesmo
motivo (uma captura antiga gravou a tela inteira do autor, ver `1a33124`).

Cada imagem passa por `check_evidence_privacy` inline: `git ls-files` só enxerga arquivo já
rastreado, então a auditoria do repositório não veria uma captura recém-criada.

    python3 scripts/capture_mapas_adversariais.py                # os três corpus padrão
    python3 scripts/capture_mapas_adversariais.py dez_desconexos # um só
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from corpus_adversarial import POR_NOME, monta  # noqa: E402
from core.i18n import get_map_i18n  # noqa: E402
from core.local_server import prepare_serve_dir, start_server  # noqa: E402
from core.sigma_exporter import export_sigma_json  # noqa: E402
from scripts.capture_window import CapturaError, captura  # noqa: E402

DESTINO = RAIZ / "docs" / "evidence"

#: Três corpus escolhidos por contraste visual, não por variedade: componentes separadas,
#: um nó que esmaga a escala, e rótulos que testam a tipografia do canvas.
CORPUS = ["dez_desconexos", "termo_dominante", "caracteres_dificeis"]

#: `data-mode` das abas do `map_template.html`. Os três modos leem o MESMO payload.
MODOS = ["network", "overlay", "density"]

TITULO_JANELA = "Blicsa — auditoria de mapas"


def _publica(nome_caso: str, serve_dir: Path) -> dict:
    """Gera graph.json e i18n.json no diretório servido. Devolve o meta do payload."""
    G, pos = monta(POR_NOME[nome_caso], iteracoes=400)
    destino = serve_dir / "assets" / "graph.json"
    payload = export_sigma_json(G, pos, str(destino))

    with open(serve_dir / "assets" / "i18n.json", "w", encoding="utf-8") as f:
        json.dump(get_map_i18n(), f, ensure_ascii=False)
    return payload["meta"]


def _clica_aba(janela, modo: str) -> str:
    """Clica a aba do modo na página, e devolve o modo que o JS diz estar ativo.

    **Clique de verdade, não `state.mode = x`.** Forçar a variável interna pularia o
    `setMode`, que é quem redesenha o canvas, mostra a legenda e liga a densidade — a
    captura sairia com a aba certa marcada e o desenho da aba anterior.

    A primeira versão trocava de aba por AppleScript (Tab + Enter) e **duas das três
    capturas saíam idênticas**: `overlay` e `density` com a mesma assinatura de pixels. Um
    veredito visual em cima daquilo teria auditado a mesma imagem duas vezes.
    """
    janela.evaluate_js(f'document.getElementById("tab-{modo}").click()')
    time.sleep(1.2)
    return janela.evaluate_js("state.mode")


def main() -> int:
    casos = sys.argv[1:] or CORPUS
    desconhecidos = [c for c in casos if c not in POR_NOME]
    if desconhecidos:
        print(f"corpus desconhecido: {desconhecidos}. Disponíveis: {sorted(POR_NOME)}")
        return 2

    serve_dir = prepare_serve_dir(RAIZ)
    porta, servidor = start_server(serve_dir)
    print(f"servidor local em 127.0.0.1:{porta} · servindo {serve_dir}\n")

    falhas: list[str] = []
    geradas: list[Path] = []
    url = f"http://127.0.0.1:{porta}/assets/map_template.html"

    def roteiro(janela):
        """Roda numa thread do pywebview, com a janela já viva."""
        try:
            for caso in casos:
                meta = _publica(caso, serve_dir)
                janela.load_url(url)          # recarrega com o graph.json do caso
                print(f"── {caso}: {meta['nodes_total']} nós · {meta['edges_total']} arestas "
                      f"· {len(meta['clusters'])} clusters")

                # CONFERIR o que está na tela antes de fotografar. Sem isto o script gravou
                # `dez_desconexos_density.png` com o mapa do corpus SEGUINTE: o `load_url`
                # devolve na hora e o `graph.json` chega do cache, então uma espera fixa
                # fotografa o que sobrou da iteração anterior. Uma captura rotulada errado é
                # pior do que captura nenhuma — ela vira linha de tabela num relatório.
                esperado = meta["nodes_total"]
                for _ in range(40):
                    time.sleep(0.5)
                    try:
                        if janela.evaluate_js("typeof graph !== 'undefined' && graph.order") == esperado:
                            break
                    except Exception:
                        pass
                else:
                    falhas.append(f"{caso}: o mapa na tela nunca chegou a {esperado} nós")
                    print(f"   [FALHA] mapa na tela não bate com o corpus ({esperado} nós)")
                    continue
                time.sleep(3)                 # WebGL e rótulos assentam depois do grafo

                for modo in MODOS:
                    ativo = _clica_aba(janela, modo)
                    if ativo != modo:
                        falhas.append(f"{caso}/{modo}: aba não trocou (ativo={ativo!r})")
                        print(f"   [FALHA] {modo:8s} aba não trocou (ativo={ativo!r})")
                        continue
                    alvo = DESTINO / f"auditoria_mapa_{caso}_{modo}.png"
                    # Repetição por CORRIDA DE FOCO, não por resultado ruim: a janela some da
                    # lista do Quartz por um instante enquanto o canvas de densidade
                    # rasteriza, e `encontra_janela` levanta. O que **não** se repete é uma
                    # captura que saiu — validação reprovada continua sendo falha definitiva.
                    ultimo: Exception | None = None
                    for tentativa in range(3):
                        try:
                            captura(alvo, titulo=TITULO_JANELA)
                            geradas.append(alvo)
                            print(f"   [OK  ] {modo:8s} → {alvo.name}"
                                  + (f"  (tentativa {tentativa + 1})" if tentativa else ""))
                            ultimo = None
                            break
                        except CapturaError as e:
                            ultimo = e
                            time.sleep(1.5)
                    if ultimo is not None:
                        falhas.append(f"{caso}/{modo}: {ultimo}")
                        print(f"   [FALHA] {modo:8s} {ultimo}")
        finally:
            janela.destroy()

    import webview  # noqa: E402  (só aqui: importar cedo abre display em ambiente headless)

    # Nasce em branco de propósito. Criando-a já apontada para o mapa, a janela carregava o
    # `graph.json` que tivesse sobrado da execução ANTERIOR, e o primeiro corpus da lista era
    # sempre fotografado com os dados de outro — foi assim que
    # `dez_desconexos_density.png` saiu mostrando o corpus de caracteres difíceis.
    janela = webview.create_window(TITULO_JANELA, "about:blank", width=1200, height=800)
    try:
        webview.start(roteiro, janela)
    finally:
        servidor.shutdown()

    # As imagens precisam ser DIFERENTES entre si. Duas capturas idênticas com nomes de modos
    # diferentes é o defeito que a versão por AppleScript produzia — e passaria despercebido
    # em qualquer conferência que só olhasse se o arquivo existe.
    import hashlib

    from PIL import Image

    assinaturas: dict[str, list[str]] = {}
    for caminho in geradas:
        with Image.open(caminho) as im:
            chave = hashlib.sha256(im.convert("RGB").resize((64, 48)).tobytes()).hexdigest()
        assinaturas.setdefault(chave, []).append(caminho.name)
    repetidas = [nomes for nomes in assinaturas.values() if len(nomes) > 1]
    for grupo in repetidas:
        falhas.append(f"capturas idênticas entre si: {grupo}")
        print(f"   [FALHA] imagens idênticas: {grupo}")

    if falhas:
        print(f"\n{len(falhas)} problema(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print(f"\n{len(geradas)} capturas geradas em {DESTINO}, todas distintas entre si")
    return 0


if __name__ == "__main__":
    sys.exit(main())
