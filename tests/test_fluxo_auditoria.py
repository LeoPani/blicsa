"""Atritos de fluxo encontrados na Auditoria 1, Fase 2.

Dois defeitos, os dois silenciosos — o app não quebrava, ele entregava a coisa errada sem
avisar:

1. **Trocar de idioma devolvia o usuário à tela de boas-vindas.** `_refresh_language` destrói
   tudo e remonta o layout, e a tela de boas-vindas é um `place()` por cima de tudo que
   `_switch_tab` não remove. A aba embaixo continuava certa; o usuário via "novo projeto /
   abrir projeto" com o corpus dele invisível atrás.

2. **Import do Web of Science etiquetado devolvia zero registros.** O `.txt` do WoS vem em
   dois sabores e o parser só lia o tab-delimited. Nenhum erro, nenhum aviso: corpus vazio.
"""

import pathlib
import tempfile

import pytest

from core.parsers import BibliometricParser

RAIZ = pathlib.Path(__file__).resolve().parent.parent

#: Export *plain text* do WoS: cabeçalho FN/VR, `TAG valor`, continuação com três espaços,
#: `ER` fecha o registro, `EF` fecha o arquivo.
WOS_ETIQUETADO = (
    "FN Clarivate Analytics Web of Science\nVR 1.0\n"
    "PT J\nAU Silva, J\n   Costa, M\nTI Waste picking in Brazil\nSO WASTE MANAGEMENT\n"
    "DE waste; informality\nAB Um resumo com acento: ação.\nPY 2020\nTC 15\nDI 10.1/abc\n"
    "CR Freire P, 1968, PEDAGOGIA\n   Ostrom E, 1990, GOVERNING\nER\n\n"
    "PT J\nAU Dias, S\nTI Cooperatives\nSO HABITAT INTL\nDE cooperative\nPY 2011\nTC 40\nER\n\nEF\n"
)

WOS_TAB = ("FN Thomson Reuters\nPT\tAU\tTI\tSO\tDE\tAB\tPY\tTC\tDI\n"
           "J\tSilva, J\tWaste picking\tWASTE MGMT\twaste\tResumo\t2020\t15\t10.1/abc\n")


def _arquivo(conteudo: str, nome: str = "wos.txt") -> str:
    alvo = pathlib.Path(tempfile.mkdtemp()) / nome
    alvo.write_text(conteudo, encoding="utf-8")
    return str(alvo)


# ── Import do Web of Science ─────────────────────────────────────────────────────

def test_wos_etiquetado_e_lido():
    """O formato que a interface do WoS oferece primeiro, e que devolvia corpus vazio."""
    df = BibliometricParser(_arquivo(WOS_ETIQUETADO)).load_wos_txt()

    assert len(df) == 2, "o export etiquetado do WoS voltou a ser lido como zero registros"
    primeiro = df.iloc[0]
    assert primeiro["title"] == "Waste picking in Brazil"
    assert primeiro["year"] == 2020
    assert primeiro["citations"] == 15
    assert primeiro["keywords"] == "waste; informality"
    assert primeiro["source"] == "WASTE MANAGEMENT"


def test_wos_etiquetado_junta_linhas_de_continuacao():
    """Autores e referências ocupam várias linhas, indentadas com três espaços. Ignorá-las
    perderia o segundo autor de todo artigo em coautoria — silenciosamente."""
    df = BibliometricParser(_arquivo(WOS_ETIQUETADO)).load_wos_txt()

    assert df.iloc[0]["authors"] == "Silva, J; Costa, M"
    assert "Freire" in df.iloc[0]["references"] and "Ostrom" in df.iloc[0]["references"]


def test_wos_tab_delimited_continua_funcionando():
    """A correção não pode ter trocado um formato pelo outro."""
    df = BibliometricParser(_arquivo(WOS_TAB)).load_wos_txt()
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Waste picking"


def test_cabecalho_do_arquivo_nao_vira_registro():
    """`FN` e `VR` são metadados do arquivo, não campos de registro.

    O modo de falha aparece num arquivo **sem nenhum registro** — busca que não retornou
    nada, ou download interrompido antes do primeiro `PT`. Sem tratar o cabeçalho, ele fica
    no acumulador e o `if atual` do final o transforma num registro fantasma: o usuário
    importa um arquivo vazio e recebe "1 registro" com todos os campos em branco.

    A primeira versão deste teste conferia que nenhum título saía vazio no arquivo COM
    registros, e passava com ou sem a correção — `FN` e `VR` não estão entre as colunas
    exportadas, então nunca chegavam à tabela. Quem apontou foi `scripts/reinject_ia_ux.py`.
    """
    so_cabecalho = "FN Clarivate Analytics Web of Science\nVR 1.0\nEF\n"
    # Direto no parser etiquetado, e não por `load_wos_txt`: um arquivo só com cabeçalho não
    # tem linha `PT `, então a detecção o manda para o caminho TSV e a guarda nunca seria
    # exercitada. Testar pelo caminho "mais realista" teria passado sem verificar nada.
    df = BibliometricParser(_arquivo(so_cabecalho))._load_wos_etiquetado()
    assert len(df) == 0, "o cabeçalho do arquivo virou um registro em branco"

    completo = BibliometricParser(_arquivo(WOS_ETIQUETADO)).load_wos_txt()
    assert not completo["title"].eq("").any(), "registro sem título no arquivo completo"


def test_ultimo_registro_sem_ER_nao_e_descartado():
    """Arquivo truncado no download é comum. Perder o último registro em silêncio seria a
    mesma classe de defeito que esta correção resolve."""
    sem_fim = WOS_ETIQUETADO.replace("PY 2011\nTC 40\nER\n\nEF\n", "PY 2011\nTC 40\n")
    df = BibliometricParser(_arquivo(sem_fim)).load_wos_txt()
    assert len(df) == 2, "o registro sem `ER` foi descartado"


def test_deteccao_nao_confunde_os_dois_formatos():
    etiquetado = BibliometricParser(_arquivo(WOS_ETIQUETADO))
    tabular = BibliometricParser(_arquivo(WOS_TAB, "wos_tab.txt"))
    assert etiquetado._wos_e_etiquetado() is True
    assert tabular._wos_e_etiquetado() is False


# ── A tela de boas-vindas não pode voltar sozinha ────────────────────────────────

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


def _boas_vindas_na_frente(janela) -> bool:
    frame = getattr(janela, "_welcome_frame", None)
    return frame is not None and frame.winfo_manager() == "place"


def test_boas_vindas_aparecem_na_primeira_abertura(app):
    assert _boas_vindas_na_frente(app), "usuário novo precisa da tela de escolha"


def test_trocar_de_idioma_nao_devolve_o_usuario_ao_inicio(app):
    """O atrito medido: usuário no corpus, troca o idioma, e a tela de boas-vindas volta
    por cima — com a aba certa embaixo, invisível. Clicar em 'novo projeto' dali entraria
    no fluxo de criação por cima do trabalho aberto."""
    app._dispensa_boas_vindas()
    app._switch_tab("corpus")
    app.update_idletasks()

    app._refresh_language()
    app.update_idletasks()

    assert not _boas_vindas_na_frente(app), "a tela de boas-vindas voltou sozinha"
    assert app._current_tab_key == "corpus", "a aba não foi preservada"


def test_idioma_trocado_duas_vezes_continua_fora_do_caminho(app):
    app._dispensa_boas_vindas()
    app._switch_tab("corpus")
    for _ in range(2):
        app._refresh_language()
        app.update_idletasks()
    assert not _boas_vindas_na_frente(app)


def test_sem_dispensar_a_tela_ela_sobrevive_a_troca_de_idioma(app):
    """O contraponto: quem ainda **não** escolheu um caminho tem de continuar vendo a
    escolha depois de trocar o idioma. A correção não pode ter virado 'nunca mostrar'."""
    assert _boas_vindas_na_frente(app)
    app._refresh_language()
    app.update_idletasks()
    assert _boas_vindas_na_frente(app), "a tela sumiu para quem ainda não escolheu nada"
