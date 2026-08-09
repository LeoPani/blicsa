"""Mensagens de erro de projeto: traduzidas, sem jargão de biblioteca — Etapa 4, item 9.

O que o usuário via, com a interface em francês, ao abrir um CSV renomeado para `.blicsa`:

> *File is not a zip file*

Em inglês fixo, vindo do `zipfile`. E no arquivo sem manifesto, pior:

> *There is no item named 'manifest.json' in the archive*

Nomeando um arquivo interno do formato, que o usuário não sabe que existe. Nenhum traceback
chegava à tela — o erro era capturado — mas o conteúdo não dizia o que houve nem o que fazer.

Os testes vão pelo **método que o botão chama**, e conferem o que o `messagebox` recebeu.
"""

import gzip
import json
import zipfile
from pathlib import Path

import pytest

from core import i18n
from core.project import diagnosticar_projeto

IDIOMAS = ("pt_BR", "en", "fr")

#: Cada falha real, com o arquivo que a provoca. Não é lista teórica: os cinco primeiros
#: foram reproduzidos na Auditoria 1, Fase 2, §5.
CASOS = {
    "zip truncado": lambda p: p.write_bytes(b"PK\x03\x04lixo"),
    "csv renomeado": lambda p: p.write_text("a,b,c\n1,2,3\n", encoding="utf-8"),
    "sem manifesto": lambda p: _zip(p, {"config.json": "{}"}),
    "manifesto inválido": lambda p: _zip(p, {"manifest.json": "{{{"}),
    "dataset corrompido": lambda p: _zip(p, {"manifest.json": json.dumps({"version": "1.0"}),
                                             "dataset.json.gz": "não é gzip"}),
}


def _zip(caminho: Path, arquivos: dict[str, str]):
    with zipfile.ZipFile(caminho, "w") as z:
        for nome, conteudo in arquivos.items():
            z.writestr(nome, conteudo)


@pytest.fixture(autouse=True)
def restaura_idioma():
    anterior = i18n.get_lang()
    yield
    i18n.load_locales(anterior)


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


# ── O diagnóstico ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nome", sorted(CASOS))
def test_cada_falha_tem_diagnostico_proprio(nome, tmp_path):
    """Diagnóstico genérico para tudo seria o mesmo problema com outra roupa."""
    from core.project import load_blicsa_project

    alvo = tmp_path / "p.blicsa"
    CASOS[nome](alvo)
    with pytest.raises(Exception) as capturado:
        load_blicsa_project(str(alvo))

    chave = diagnosticar_projeto(capturado.value)
    assert chave != "projeto.erro_desconhecido", f"{nome} caiu no diagnóstico genérico"
    assert chave.startswith("projeto.erro_")


def test_os_diagnosticos_sao_distintos_entre_si(tmp_path):
    """Se todos devolvessem a mesma chave, os testes acima passariam sem valer nada."""
    from core.project import load_blicsa_project

    chaves = set()
    for nome, monta in CASOS.items():
        alvo = tmp_path / f"{nome.replace(' ', '_')}.blicsa"
        monta(alvo)
        try:
            load_blicsa_project(str(alvo))
        except Exception as e:
            chaves.add(diagnosticar_projeto(e))
    assert len(chaves) >= 3, f"diagnósticos pouco específicos: {chaves}"


@pytest.mark.parametrize("erro,esperado", [
    (zipfile.BadZipFile("x"), "projeto.erro_nao_e_blicsa"),
    (KeyError("manifest.json"), "projeto.erro_incompleto"),
    (FileNotFoundError(2, "no such file"), "projeto.erro_sumiu"),
    (PermissionError(13, "denied"), "projeto.erro_permissao"),
    (MemoryError(), "projeto.erro_memoria"),
    (OSError(28, "No space left on device"), "projeto.erro_disco_cheio"),
    (OSError(30, "Read-only file system"), "projeto.erro_somente_leitura"),
    (ValueError("qualquer outra"), "projeto.erro_desconhecido"),
])
def test_mapeamento_de_cada_tipo(erro, esperado):
    """A ordem importa: `FileNotFoundError` e `PermissionError` são `OSError`, e disco cheio
    é `OSError` genérico com `errno`. Do específico para o geral."""
    assert diagnosticar_projeto(erro) == esperado


# ── O que chega à tela ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("idioma", IDIOMAS)
@pytest.mark.parametrize("nome", sorted(CASOS))
def test_a_mensagem_sai_traduzida_e_sem_jargao(nome, idioma, app, monkeypatch, tmp_path):
    """Caminho real: `_load_project_gui` → `load_blicsa_project` → `_erro_de_projeto`."""
    i18n.load_locales(idioma)
    alvo = tmp_path / "p.blicsa"
    CASOS[nome](alvo)

    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kw: str(alvo))
    mostrados: list[tuple[str, str]] = []
    monkeypatch.setattr("tkinter.messagebox.showerror",
                        lambda titulo, msg, *a, **k: mostrados.append((str(titulo), str(msg))))
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    app._load_project_gui()
    app.update()

    assert mostrados, f"{nome} em {idioma}: nenhuma mensagem foi mostrada"
    titulo, mensagem = mostrados[0]

    assert "Traceback" not in mensagem
    for jargao in ("zip file", "manifest.json", "Errno", "JSONDecodeError", "KeyError",
                   "gzip", "BadZipFile"):
        assert jargao not in mensagem, f"{nome} em {idioma}: jargão na tela → {mensagem!r}"
    assert len(mensagem) > 30, f"mensagem curta demais para orientar: {mensagem!r}"
    assert mensagem == i18n.t(diagnosticar_projeto(
        _erro_de(str(alvo))), ), "a mensagem não veio do catálogo"


def _erro_de(caminho: str) -> BaseException:
    from core.project import load_blicsa_project

    try:
        load_blicsa_project(caminho)
    except Exception as e:
        return e
    raise AssertionError("o arquivo abriu — a fixture não provoca falha")


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_falha_ao_salvar_tambem_e_traduzida(idioma, app, monkeypatch, tmp_path):
    i18n.load_locales(idioma)
    monkeypatch.setattr("tkinter.filedialog.asksaveasfilename",
                        lambda **kw: str(tmp_path / "nao" / "existe" / "p.blicsa"))
    mostrados = []
    monkeypatch.setattr("tkinter.messagebox.showerror",
                        lambda titulo, msg, *a, **k: mostrados.append(str(msg)))
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    app._active_project = None

    app._save_project_gui()
    app.update()

    assert mostrados, "salvar em caminho inválido não avisou nada"
    assert "Errno" not in mostrados[0] and "Traceback" not in mostrados[0]
    assert mostrados[0] == i18n.t("projeto.erro_sumiu")


# ── Paridade e tradução de verdade ───────────────────────────────────────────────

def test_toda_chave_de_diagnostico_existe_nos_tres_catalogos():
    """Chave ausente faz `t()` devolver a própria chave, e o usuário lê
    `projeto.erro_corrompido` na tela."""
    raiz = Path(__file__).resolve().parent.parent
    chaves = _chaves_de_diagnostico()

    for idioma in IDIOMAS:
        catalogo = json.loads((raiz / f"locales/{idioma}.json").read_text(encoding="utf-8"))
        faltando = sorted(chaves - set(catalogo))
        assert not faltando, f"{idioma} sem: {faltando}"


def test_as_mensagens_sao_traduzidas_de_fato():
    """Catálogo com a frase copiada do português passaria em tudo acima e entregaria
    português ao usuário francês."""
    raiz = Path(__file__).resolve().parent.parent
    catalogos = {i: json.loads((raiz / f"locales/{i}.json").read_text(encoding="utf-8"))
                 for i in IDIOMAS}

    copiadas = [c for c in _chaves_de_diagnostico()
                if len({catalogos[i][c] for i in IDIOMAS}) < 3]
    assert not copiadas, f"mensagens idênticas em dois ou mais catálogos: {copiadas}"


def _chaves_de_diagnostico() -> set[str]:
    """Extraídas da **fonte real** de `core/project.py`, não de uma lista fixa aqui.

    Lista fixa envelhece em silêncio: quem acrescentar um diagnóstico novo não lembraria de
    acrescentá-lo ao teste, e a chave só faltaria na tela do usuário francês.
    """
    import ast

    raiz = Path(__file__).resolve().parent.parent
    fonte = (raiz / "core/project.py").read_text(encoding="utf-8")
    chaves = {n.value for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and n.value.startswith("projeto.erro_")}
    assert len(chaves) >= 8, f"poucas chaves extraídas: {chaves}"
    return chaves


def test_o_detalhe_tecnico_vai_para_o_log_e_nao_some(app, monkeypatch, tmp_path, caplog):
    """Tirar o jargão da tela não pode virar perder a informação: quem mantém o programa
    precisa do tipo e da mensagem originais."""
    alvo = tmp_path / "p.blicsa"
    CASOS["csv renomeado"](alvo)
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kw: str(alvo))
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    with caplog.at_level("INFO"):
        app._load_project_gui()
        app.update()

    registrado = caplog.text
    assert "BadZipFile" in registrado, "o detalhe técnico não foi para o log"
    assert "projeto.erro_nao_e_blicsa" in registrado, "o log não diz qual diagnóstico saiu"
