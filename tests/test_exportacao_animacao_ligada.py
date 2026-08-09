"""Exportação de animação e pôster ligada à interface — Etapa 3.

`core/map_animation.py` eram 543 linhas com 22 testes e **nenhum chamador**: importado só
por `tests/`. A linha do tempo interativa do `map.js` continuava funcionando; o que não
existia era levar o resultado para fora do app — GIF para apresentação, PNG para artigo,
pôster para impressão.

Estes testes vão pelo **método do botão**, não pelas funções do módulo. As funções já tinham
22 testes e mesmo assim o recurso não existia para o usuário — é precisamente a distinção que
o levantamento em `docs/CODIGO-SEM-CHAMADOR.md` registra.
"""

from pathlib import Path

import pandas as pd
import pytest

CORPUS = pd.DataFrame([
    {"title": f"Artigo {i}", "keywords": "residuos;politica;urbano", "authors": "Silva, J",
     "year": 2015 + (i % 6), "citations": i} for i in range(18)
])

SEM_ANO = pd.DataFrame([
    {"title": f"Artigo {i}", "keywords": "residuos;politica", "authors": "Silva, J",
     "year": 0, "citations": i} for i in range(6)
])


@pytest.fixture
def app():
    import main as blicsa

    try:
        janela = blicsa.BlicsaApp()
    except Exception:
        pytest.skip("sem display para inicializar Tk")
    janela.withdraw()
    janela.update_idletasks()
    yield janela
    janela.destroy()


@pytest.fixture
def sem_thread(monkeypatch):
    """`Thread(...).start()` roda o alvo na hora — ver a mesma fixture em
    `tests/test_analise_seminal_ligada.py` para o porquê (`after` de outra thread exige o
    `mainloop`, que o teste não roda)."""
    import main as blicsa

    class ThreadSincrona:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._alvo, self._args = target, args
            self._kwargs = kwargs or {}

        def start(self):
            self._alvo(*self._args, **self._kwargs)

    monkeypatch.setattr(blicsa.threading, "Thread", ThreadSincrona)


def _com_mapa(app, df=CORPUS):
    """Deixa o app no estado em que o usuário estaria: corpus carregado e mapa gerado."""
    from core.matrix_builders import NetworkGenerator
    from core.visualizer import compute_fa2_layout

    gen = NetworkGenerator(df)
    G = gen.build_keyword_cooccurrence(min_occurrence=1)
    gen.apply_clustering()
    gen.compute_overlay_scores()
    app._dataframe = df
    app._graph = G
    app._positions = compute_fa2_layout(G, iterations=20)
    return app


# ── O fio que faltava ────────────────────────────────────────────────────────────

def test_botao_exporta_gif_com_varios_quadros(app, monkeypatch, sem_thread, tmp_path):
    alvo = tmp_path / "animacao.gif"
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", lambda **kw: str(alvo))
    _com_mapa(app)

    app._export_map_animation()
    app.update()

    assert alvo.exists() and alvo.stat().st_size > 0, "o GIF não foi gravado"

    from PIL import Image

    with Image.open(alvo) as im:
        assert getattr(im, "n_frames", 1) > 1, "o GIF saiu com um quadro só"


def test_botao_exporta_poster(app, monkeypatch, tmp_path):
    alvo = tmp_path / "poster.png"
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", lambda **kw: str(alvo))
    _com_mapa(app)

    app._export_map_poster()

    assert alvo.exists() and alvo.stat().st_size > 0
    from PIL import Image

    with Image.open(alvo) as im:
        assert im.size[0] > 200 and im.size[1] > 200


def test_extensao_png_vira_sequencia_de_quadros(app, monkeypatch, sem_thread, tmp_path):
    """O formato sai da extensão escolhida no diálogo — quem digita `.png` quer a sequência."""
    alvo = tmp_path / "quadro.png"
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", lambda **kw: str(alvo))
    _com_mapa(app)

    app._export_map_animation()
    app.update()

    gerados = sorted(tmp_path.glob("quadro*.png"))
    assert len(gerados) > 1, f"esperava uma sequência, saiu {[p.name for p in gerados]}"


def test_os_dois_botoes_estao_na_tela(app):
    """Guarda contra o método existir e o botão não — que era o estado do módulo inteiro."""
    comandos = set()

    def varre(widget):
        for filho in widget.winfo_children():
            cmd = getattr(filho, "_command", None)
            if cmd is not None:
                comandos.add(getattr(cmd, "__name__", ""))
            varre(filho)

    varre(app)
    assert "_export_map_animation" in comandos, "nenhum botão exporta a animação"
    assert "_export_map_poster" in comandos, "nenhum botão exporta o pôster"


# ── Estados em que o usuário chega ───────────────────────────────────────────────

def test_sem_mapa_avisa_e_nao_abre_dialogo(app, monkeypatch):
    abriu = []
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename",
                        lambda **kw: abriu.append("abriu") or "")
    avisos = []
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    app._graph, app._positions = None, {}

    app._export_map_animation()
    app._export_map_poster()

    assert len(avisos) == 2, "exportar sem mapa devia avisar nas duas vezes"
    assert not abriu, "abriu o diálogo de arquivo sem ter o que exportar"


def test_corpus_sem_ano_explica_em_vez_de_gerar_arquivo_vazio(app, monkeypatch, sem_thread,
                                                              tmp_path):
    """A animação é uma linha do tempo. Sem ano nenhum ela não existe — e o usuário precisa
    saber que o problema é o corpus, não o app."""
    alvo = tmp_path / "a.gif"
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", lambda **kw: str(alvo))
    infos = []
    monkeypatch.setattr("tkinter.messagebox.showinfo",
                        lambda titulo, msg, *a, **k: infos.append(msg))
    _com_mapa(app, SEM_ANO)

    app._export_map_animation()
    app.update()
    app.update()

    assert infos, "corpus sem ano passou em silêncio"
    assert "ano" in infos[0].lower() or "year" in infos[0].lower() or "année" in infos[0].lower()
    assert not alvo.exists(), "gravou um arquivo sem quadro nenhum"


def test_cancelar_o_dialogo_nao_faz_nada(app, monkeypatch, sem_thread):
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", lambda **kw: "")
    _com_mapa(app)

    app._export_map_animation()   # não pode levantar
    app._export_map_poster()
    app.update()


def test_sem_ffmpeg_grava_gif_no_lugar_do_mp4(app, monkeypatch, sem_thread, tmp_path):
    """`export_mp4` devolve `(False, motivo)` sem ffmpeg, por projeto. O app não pode recusar
    o pedido inteiro por causa de um binário ausente."""
    import core.map_animation as anim

    monkeypatch.setattr(anim, "ffmpeg_available", lambda: False)
    alvo = tmp_path / "video.mp4"
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename", lambda **kw: str(alvo))
    avisos = []
    monkeypatch.setattr("tkinter.messagebox.showwarning",
                        lambda titulo, msg, *a, **k: avisos.append(msg))
    _com_mapa(app)

    app._export_map_animation()
    app.update()

    assert (tmp_path / "video.gif").exists(), "sem ffmpeg, nada foi entregue"
    assert avisos, "o usuário não foi avisado de que recebeu GIF em vez de MP4"


def test_o_modulo_de_animacao_tem_chamador_fora_dos_testes():
    """A condição que motivou esta etapa, afirmada diretamente: se voltar a ser importado
    só por `tests/`, este teste falha."""
    import ast

    raiz = Path(__file__).resolve().parent.parent
    fontes = [raiz / "main.py"] + list((raiz / "ui").glob("*.py")) + \
             [p for p in (raiz / "core").glob("*.py") if p.name != "map_animation.py"]

    for caminho in fontes:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and (no.module or "").endswith("map_animation"):
                return
    pytest.fail("core/map_animation.py voltou a ser importado só por testes")
