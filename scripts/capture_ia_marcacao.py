#!/usr/bin/env python3
"""As três capturas da marcação de IA, com chamada REAL ao modelo.

**Sem mock, e sem texto de mentira.** O ponto das evidências é mostrar a marcação sobre o que
o modelo de fato escreveu: um texto colado à mão numa caixa provaria que a caixa existe, não
que ela envolve a saída do modelo. Se a chave não estiver configurada, o script recusa em vez
de gerar uma imagem que parece boa.

Captura por `CGWindowID` (`capture_window.py`) e validação por `check_evidence_privacy` — as
mesmas regras do resto do repositório, pelos mesmos motivos (uma captura antiga gravou a tela
inteira do autor).

O corpus vem do CSV de exemplo do repositório, e não de uma busca online: a captura precisa
ser refazível daqui a um ano com o mesmo conteúdo. O que é real aqui é a **chamada ao
modelo**, que é o que a evidência afirma.

Uso:
    python3 scripts/capture_ia_marcacao.py chat
    python3 scripts/capture_ia_marcacao.py insights
    python3 scripts/capture_ia_marcacao.py clusters
    python3 scripts/capture_ia_marcacao.py todas
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.capture_window import CapturaError, captura  # noqa: E402

CSV_EXEMPLO = RAIZ / "docs" / "sample_dataset.csv"
DESTINO = RAIZ / "docs" / "evidence"

#: Contexto de pesquisa usado nas capturas. Serve a dois propósitos: acender o indicador da
#: Fase 3 na imagem e provar que ele acompanha a resposta.
CONTEXTO = ("Reviso a literatura de mapeamento bibliométrico para o capítulo de métodos de "
            "uma tese. Interessa o que distingue as ferramentas entre si, não a história "
            "da cientometria.")

#: Curta de propósito: o selo "IA" fica no TOPO do bloco, e uma resposta de meia tela empurra
#: o selo para fora do quadro. A evidência precisa mostrar faixa **e** selo juntos.
PERGUNTA = ("Em no máximo duas frases curtas, o que distingue VOSviewer de CiteSpace? "
            "Sem introdução.")

#: Teto de espera por resposta do modelo. Estourar é FALHA, não motivo para capturar o que
#: estiver na tela: uma captura do indicador pulsando não é evidência de marcação.
TIMEOUT_MODELO = 120


class FalhaCaptura(RuntimeError):
    pass


def _exige_chave():
    from core.settings import get_api_key

    if not (get_api_key() or "").strip():
        raise FalhaCaptura(
            "sem chave de IA configurada. Estas capturas exigem chamada real ao modelo — "
            "exporte GROQ_API_KEY ou configure a chave nos Ajustes. NÃO há modo mock.")


def _app_com_corpus():
    """Sobe o app real com o corpus de exemplo e o contexto de pesquisa preenchido."""
    import importlib.util

    import pandas as pd

    spec = importlib.util.spec_from_file_location("main", str(RAIZ / "main.py"))
    main_mod = importlib.util.module_from_spec(spec)
    sys.modules["main"] = main_mod
    spec.loader.exec_module(main_mod)

    # Evidência em pt_BR, independentemente do idioma que o usuário deixou salvo — as outras
    # imagens de `docs/evidence` estão em pt_BR e uma mistura tornaria a série ilegível.
    # `load_locales` NÃO grava no settings: o idioma do app de quem roda o script fica intacto
    # (`set_lang` é que persiste, e não é chamado aqui).
    from core import i18n
    i18n.load_locales("pt_BR")

    app = main_mod.BlicsaApp()
    app.geometry("1280x860")

    # Gerar o mapa abre o Sigma no navegador padrão, que rouba o foco e faz `ativa_app()`
    # falhar — a captura então recusa (corretamente) por não achar a janela do app. O mesmo
    # sinalizador que o `--demo-search` usa desliga isso.
    app._demo_no_browser = True

    # A tela de boas-vindas é um frame por cima de TUDO (`place` com relwidth=1), e
    # `_switch_tab` não a remove — só os botões dela removem. Sem isto, a captura sai da
    # tela de boas-vindas com a conversa acontecendo atrás, invisível.
    if getattr(app, "_welcome_frame", None) is not None:
        app._welcome_frame.place_forget()
    app._dataframe = pd.DataFrame(pd.read_csv(CSV_EXEMPLO))
    app._research_context = CONTEXTO
    barra = getattr(app, "_research_context_bar", None)
    if barra is not None:
        barra.definir(CONTEXTO)
    app._refresh_corpus_tab()
    app.update()
    return app


def _espera(cond, timeout=TIMEOUT_MODELO, oque="condição"):
    """Espera fora da thread da UI. Estourar levanta — nunca captura mesmo assim."""
    limite = time.time() + timeout
    while time.time() < limite:
        try:
            if cond():
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise FalhaCaptura(f"tempo esgotado esperando {oque} ({timeout}s)")


def _texto_enviar() -> str:
    from core.i18n import t

    return t("blink.enviar")


def _acha_botao(raiz, texto):
    """Botão pelo RÓTULO visível, percorrendo a árvore de widgets.

    Vale mais que guardar uma referência no `main.py` só para o teste: o script encontra o
    mesmo botão que o usuário clica, e some junto com ele se a tela mudar.
    """
    import customtkinter as ctk

    for filho in raiz.winfo_children():
        if isinstance(filho, ctk.CTkButton) and filho.cget("text") == texto:
            return filho
        achado = _acha_botao(filho, texto)
        if achado is not None:
            return achado
    return None


def _mapa(app):
    """Gera o mapa e espera o grafo existir — pré-requisito de clusters e insights."""
    app.after(0, lambda: (app._min_occ_var.set(1), app._run_mapping()))
    _espera(lambda: getattr(app, "_generator", None) is not None
            and getattr(app._generator, "G", None) is not None
            and app._generator.G.number_of_nodes() > 0,
            timeout=180, oque="a geração do mapa")


# ── as três capturas ──────────────────────────────────────────────────────────────

def cap_chat(app) -> tuple[Path, str]:
    """Resposta real do Blink no chat: faixa amarela + selo IA + indicador de contexto."""
    app.after(0, lambda: app._switch_tab("home"))
    _espera(lambda: getattr(app, "_research_chat_input_main", None) is not None,
            timeout=20, oque="a tela do Blink")
    time.sleep(1.0)

    def _perguntar():
        campo = app._research_chat_input_main
        campo.delete(0, "end")
        campo.insert(0, PERGUNTA)
        # Acionar o BOTÃO, não `event_generate("<Return>")` no campo: `CTkEntry.bind`
        # repassa o binding ao `tkinter.Entry` interno, e o evento gerado no wrapper não
        # chega lá. A primeira versão deste script "enviava" a pergunta sem enviar nada, e
        # a falha aparecia 120s depois como tempo esgotado.
        botao = _acha_botao(app._blink_chat_container, _texto_enviar())
        if botao is None:
            raise FalhaCaptura("botão de enviar não encontrado na tela do Blink")
        botao.invoke()

    antes = len(app._research_messages)
    app.after(0, _perguntar)
    # A thread do chat acrescenta a fala do assistente SÓ quando o stream termina.
    _espera(lambda: len(app._research_messages) > antes + 1
            and app._research_messages[-1]["role"] == "assistant"
            and app._research_messages[-1]["content"].strip(),
            oque="a resposta do modelo no chat")
    time.sleep(1.5)   # último quadro do stream desenhado

    def _rolar_ate_o_selo():
        """Põe o TOPO da resposta no quadro: é onde fica o selo "IA".

        O chat rola sozinho para o fim durante o stream, e o fim de uma resposta longa deixa
        de fora justamente o selo — a captura mostraria a faixa amarela sem o rótulo textual,
        que é metade da convenção.
        """
        hist = app._research_chat_history_main
        hist.update_idletasks()
        filhos = [f for f in hist.winfo_children() if f.winfo_height() > 1]
        if not filhos:
            return
        altura = max(hist.winfo_height(), 1)
        hist._parent_canvas.yview_moveto(max(0.0, (filhos[-1].winfo_y() - 12) / altura))

    app.after(0, _rolar_ate_o_selo)
    time.sleep(1.0)
    return DESTINO / "ia_marcacao_chat.png", "Blicsa"


def cap_insights(app) -> tuple[Path, str]:
    """Diálogo de insights (Sankey): o ponto que estava SEM marcação até esta rodada."""
    _mapa(app)
    app.after(0, lambda: threading.Thread(target=app._ai_sankey_worker, daemon=True).start())

    def _dialogo():
        for w in app.winfo_children():
            try:
                if "Insights de IA" in str(w.title()):
                    return w
            except Exception:
                continue
        return None

    _espera(lambda: _dialogo() is not None,
            oque="o diálogo de insights com a resposta do modelo")
    time.sleep(1.5)

    # O diálogo nasce atrás da janela principal. Sem trazê-lo à frente, `screencapture -l`
    # grava a janela obstruída — e o conteúdo que a evidência precisa mostrar fica coberto.
    def _erguer():
        dlg = _dialogo()
        if dlg is not None:
            dlg.lift()
            dlg.attributes("-topmost", True)
            # `-alpha` explícito: o CTkToplevel sobe com fade-in no macOS, e a captura
            # pegava a janela translúcida no meio da animação — a evidência saía lavada,
            # com o texto quase ilegível.
            dlg.attributes("-alpha", 1.0)
            dlg.focus_force()
            dlg.update_idletasks()

    app.after(0, _erguer)
    time.sleep(3.0)
    # Título próprio: `encontra_janela` pega a MAIOR janela que casa, e a principal é maior
    # que o diálogo. Casar pelo título é o que garante que a foto é do diálogo.
    return DESTINO / "ia_marcacao_insights.png", "Insights de IA"


def cap_clusters(app) -> tuple[Path, str]:
    """Rótulos de cluster nomeados pelo modelo, com o selo `[IA]` na célula."""
    _mapa(app)
    app.after(0, lambda: threading.Thread(target=app._label_clusters_worker,
                                          daemon=True).start())
    _espera(lambda: bool(app._cluster_labels) and bool(app._cluster_label_origins),
            oque="os rótulos de cluster do modelo")

    def _mostrar():
        # "analises": a Treeview de rankings vive no tabview `_tv_analises`, que é filho
        # dessa aba. A primeira versão pedia "viz" — chave que não existe — e a evidência
        # saía com o painel em branco. Ver tests/test_navegacao_abas.py.
        app._switch_tab("analises")
        app._tv_analises.set("Rankings")
        app._rank_var.set("clusters")
        app._show_ranking()

    app.after(0, _mostrar)
    time.sleep(2.0)
    return DESTINO / "ia_marcacao_clusters.png", "Blicsa"


MODOS = {"chat": cap_chat, "insights": cap_insights, "clusters": cap_clusters}


def roda(modo: str) -> int:
    _exige_chave()
    app = _app_com_corpus()
    resultado = {"codigo": 1}

    def _trabalho():
        try:
            destino, titulo = MODOS[modo](app)
            caminho = captura(destino, titulo=titulo)
            from scripts.check_evidence_privacy import analisa

            rel = analisa(caminho.read_bytes(), str(caminho.relative_to(RAIZ)))
            print(f"OK  {caminho.name} · {rel['dimensoes']} · papel {rel['papel']:.1%} · "
                  f"{rel['veredito']} · {rel['motivo']}")
            resultado["codigo"] = 0 if rel["veredito"] != "REPROVADA" else 1
        except (FalhaCaptura, CapturaError) as e:
            print(f"FALHOU [{modo}]: {e}", file=sys.stderr)
        except Exception as e:                                   # pragma: no cover
            import traceback
            traceback.print_exc()
            print(f"FALHOU [{modo}]: {e}", file=sys.stderr)
        finally:
            app.after(0, app.quit)

    threading.Thread(target=_trabalho, daemon=True).start()
    app.mainloop()
    try:
        app.destroy()
    except Exception:
        pass
    return resultado["codigo"]


def main() -> int:
    modo = sys.argv[1] if len(sys.argv) > 1 else "todas"
    if modo == "todas":
        # Um processo por captura: o app fica em estados incompatíveis entre elas (diálogo
        # modal aberto, aba trocada), e reaproveitar a instância trocaria confiabilidade por
        # alguns segundos.
        import subprocess
        pior = 0
        for m in MODOS:
            r = subprocess.call([sys.executable, __file__, m], cwd=str(RAIZ),
                                env=os.environ.copy())
            pior = max(pior, r)
        return pior
    if modo not in MODOS:
        print(f"modo desconhecido: {modo} (use {', '.join(MODOS)} ou 'todas')",
              file=sys.stderr)
        return 2
    return roda(modo)


if __name__ == "__main__":
    sys.exit(main())
