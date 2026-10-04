"""Importação de arquivos reais de cada base, campo a campo.

Os exemplos em `tests/fixtures/importacao/` imitam o que cada base exporta de verdade
(cabeçalhos, etiquetas, codificação, fim de linha), com os casos difíceis do mundo real:
BOM, Windows-1252, UTF-16, CRLF, aspas e `;` dentro de campos, registros sem DOI ou sem ano,
linhas de continuação, acentos em LaTeX. O guia para o usuário é `docs/GUIA-IMPORTACAO.md`.

Cada arquivo passa pelo mesmo caminho do app: `_auto_detect_format` escolhe o formato e o
leitor sai do mesmo mapa que `_load_worker` usa. Os testes no fim do arquivo passam pelo
`_load_worker` de verdade, com a janela.

Bugs que estes testes travam (auditoria de importação, 2026-10):

- I1  RIS: `ER  - ` (com hífen, como toda base grava) não fechava o registro; o arquivo
      inteiro virava UM registro, com os autores de todos somados.
- I2  RIS: editores (`A2`) entravam como coautores.
- I3  RIS do Scopus: citações e referências (no `N1`) eram ignoradas.
- I4  RIS e BibTeX salvos como `.txt` caíam no leitor do Scopus: registros "nan".
- I5  WoS etiquetado: um registro sem `PY` (Early Access) derrubava o arquivo inteiro.
- I6  WoS etiquetado: título e palavras-chave quebrados em duas linhas eram emendados com
      `; `, partindo o título e criando palavras-chave pela metade.
- I7  WoS tab-delimited real (sem linha `FN`) perdia o cabeçalho: todos os campos "nan".
      Aspas no título bagunçavam as colunas; o UTF-16 antigo nem era detectado.
- I8  BibTeX em Windows-1252 derrubava a importação; acentos LaTeX (`{\\'e}`) e chaves
      ficavam no texto; autores separados por `and` quebravam índice h e Sankey; os campos
      do BibTeX do Scopus (palavras-chave do autor, citações, referências, tipo) se perdiam.
- I9  OpenAlex JSON: autor sem nome derrubava o arquivo; `referenced_works` e `id` eram
      ignorados, então o JSON importado não fazia cocitação, acoplamento nem citação direta.
- I10 Crossref: o JSON de UM work (`/works/{doi}`) virava um registro vazio; autor
      institucional virava "; " sobrando; o rótulo "Abstract" entrava no resumo.
- I11 PubMed: o DOI saía errado (o `[pii]` da editora vinha junto); `*` do MeSH separava
      "*Humans" de "Humans".
- I12 Scopus CSV: "[No author name available]" virava um autor e "[No abstract available]"
      um resumo.
- I13 PDF: `.pdf` não era detectado, e todo PDF ganhava o ano 2024.
- I14 Detecção: "PT " em qualquer lugar do arquivo (ex.: "CONCEPT " num resumo) mandava
      um CSV do Scopus para o leitor do WoS.
"""

from __future__ import annotations

import csv
import io
import sys
import time
import types
from pathlib import Path

import pandas as pd
import pytest

from core.parsers import BibliometricParser

FIX = Path(__file__).resolve().parent / "fixtures" / "importacao"

#: Cópia do mapa de `_load_worker` em main.py. Um teste abaixo confere que os dois batem.
LOADERS = {
    "scopus": "load_scopus_csv", "wos": "load_wos_txt", "bibtex": "load_bibtex",
    "pubmed": "load_pubmed_medline", "openalex": "load_openalex_json",
    "crossref": "load_crossref_json", "ris": "load_ris", "pdf": "load_pdf",
    "blicsa": "load_blicsa_csv",
}


@pytest.fixture(scope="module")
def M():
    import main
    return main


def detectar(M, caminho) -> str:
    # `_auto_detect_format` não usa estado da janela: dá para chamar sem abrir a GUI.
    return M.BlicsaApp._auto_detect_format(None, str(caminho))


def importar(M, caminho) -> tuple[str, pd.DataFrame]:
    fmt = detectar(M, caminho)
    df = getattr(BibliometricParser(str(caminho)), LOADERS.get(fmt, "load_scopus_csv"))()
    return fmt, df


# ── Tabela de expectativas: arquivo → formato, nº de registros, campos do 1º registro ──

ESPERADO = {
    "scopus_export.csv": ("scopus", 4, {
        "authors": "Donthu N.; Kumar S.; Mukherjee D.; Pandey N.; Lim W.M.",
        "title": "How to conduct a bibliometric analysis: An overview and guidelines",
        "year": 2021, "source": "Journal of Business Research", "citations": 3105,
        "doi": "10.1016/j.jbusres.2021.04.070", "document_type": "review",
        "keywords": "Bibliometric analysis; Guidelines; Performance analysis; Science mapping"}),
    "scopus_excel_cp1252.csv": ("scopus", 2, {"year": 2021, "citations": 3105}),
    "scopus_um_registro.csv": ("scopus", 1, {"doi": "10.1016/j.jbusres.2021.04.070"}),
    "wos_plain_text.txt": ("wos", 4, {
        "authors": "Aria, M; Cuccurullo, C",
        "title": "bibliometrix: An R-tool for comprehensive science mapping analysis",
        "year": 2017, "source": "JOURNAL OF INFORMETRICS", "citations": 4210,
        "doi": "10.1016/j.joi.2017.08.007", "document_type": "article",
        "keywords": "Bibliometrics; Co-citation analysis; Science mapping; R package; "
                    "Knowledge structure"}),
    "wos_plain_text_crlf.txt": ("wos", 4, {"year": 2017, "citations": 4210}),
    "wos_tab_delimited.txt": ("wos", 3, {
        "authors": "Aria, M; Cuccurullo, C", "year": 2017, "citations": 4210,
        "keywords": "Bibliometrics; Co-citation analysis; Science mapping",
        "doi": "10.1016/j.joi.2017.08.007"}),
    "wos_tab_utf16.txt": ("wos", 1, {"year": 2017, "source": "JOURNAL OF INFORMETRICS"}),
    "scopus_export.bib": ("bibtex", 3, {
        "authors": "Donthu, Naveen; Kumar, Satish; Mukherjee, Debmalya; Pandey, Nitesh; "
                   "Lim, Weng Marc",
        "year": 2021, "citations": 3105, "document_type": "review",
        "keywords": "Bibliometric analysis; Guidelines; Performance analysis; Science mapping",
        "doi": "10.1016/j.jbusres.2021.04.070"}),
    "zotero_export.bib": ("bibtex", 3, {
        "authors": "van Eck, Nees Jan; Waltman, Ludo",
        "title": "Software survey: VOSviewer, a computer program for bibliometric mapping",
        "year": 2010, "source": "Scientometrics", "doi": "10.1007/s11192-009-0146-3",
        "keywords": "Bibliometric mapping, VOSviewer, Science mapping",
        "document_type": "article"}),
    "bibtex_cp1252.bib": ("bibtex", 1, {
        "authors": "Ribeiro, José; Araújo, Inês", "title": "Gestão de resíduos: uma revisão"}),
    "scopus_export.ris": ("ris", 2, {
        "authors": "Donthu, N.; Kumar, S.; Mukherjee, D.; Pandey, N.; Lim, W.M.",
        "year": 2021, "source": "Journal of Business Research", "citations": 3105,
        "doi": "10.1016/j.jbusres.2021.04.070", "document_type": "review"}),
    "zotero_export.ris": ("ris", 3, {
        "authors": "van Eck, Nees Jan; Waltman, Ludo", "year": 2010,
        "source": "Scientometrics", "keywords": "Bibliometric mapping; VOSviewer; Science mapping",
        "doi": "10.1007/s11192-009-0146-3", "document_type": "article"}),
    "mendeley_export.ris": ("ris", 2, {
        "authors": "Zupic, Ivan; Čater, Tomaž", "year": 2015,
        "source": "Organizational Research Methods", "doi": "10.1177/1094428114562629"}),
    "endnote_cp1252.txt": ("ris", 1, {
        "authors": "Araújo, Inês", "title": "Gestão pública e inovação", "year": 2017,
        "source": "Revista de Administração", "keywords": "gestão; inovação"}),
    "pubmed_export.nbib": ("pubmed", 3, {
        "authors": "Huang C; Wang Y; Li X",
        "title": "Clinical features of patients infected with 2019 novel coronavirus in "
                 "Wuhan, China.",
        "year": 2020, "source": "Lancet (London, England)",
        "doi": "10.1016/S0140-6736(20)30183-5", "document_type": "article"}),
    "pubmed_medline_crlf.txt": ("pubmed", 3, {"doi": "10.1016/S0140-6736(20)30183-5"}),
    "openalex_api.json": ("openalex", 3, {
        "authors": "Nees Jan van Eck; Ludo Waltman", "year": 2010, "source": "Scientometrics",
        "citations": 9876, "keywords": "Bibliometric mapping; VOSviewer",
        "abstract": "We present VOSviewer, a program.",
        "references": "https://openalex.org/W2096885696; https://openalex.org/W1979290264",
        "document_type": "article"}),
    "crossref_api_lista.json": ("crossref", 2, {
        "authors": "Donthu Naveen; Kumar Satish; Bibliometrics Working Group", "year": 2021,
        "citations": 3105, "abstract": "Bibliometric analysis is a popular and rigorous method.",
        "references": "10.1016/j.joi.2017.08.007; 10.1177/1094428114562629"}),
    "crossref_api_um_work.json": ("crossref", 1, {
        "authors": "van Eck Nees Jan; Waltman Ludo", "doi": "10.1007/s11192-009-0146-3",
        "citations": 9876, "source": "Scientometrics"}),
    "blicsa_corpus.csv": ("blicsa", 2, {
        "authors": "Nees Jan van Eck; Ludo Waltman", "year": 2010, "citations": 9876}),
}


def test_todo_fixture_tem_expectativa():
    """Arquivo novo na pasta sem linha em ESPERADO não seria testado em silêncio."""
    assert {p.name for p in FIX.iterdir() if not p.name.startswith(".")} == set(ESPERADO)


def test_fixtures_guardam_os_bytes_reais():
    """Se um checkout converter fim de linha ou codificação, os casos difíceis somem."""
    assert b"\r\n" in (FIX / "wos_plain_text_crlf.txt").read_bytes()
    assert (FIX / "wos_plain_text.txt").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (FIX / "wos_tab_utf16.txt").read_bytes().startswith(b"\xff\xfe")
    with pytest.raises(UnicodeDecodeError):
        (FIX / "bibtex_cp1252.bib").read_bytes().decode("utf-8")


def test_mapa_de_leitores_igual_ao_do_app():
    fonte = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    for fmt, metodo in LOADERS.items():
        assert f'"{fmt}":' in fonte and f'"{metodo}"' in fonte, (fmt, metodo)


@pytest.mark.parametrize("nome", sorted(ESPERADO))
def test_formato_detectado_registros_e_campos(M, nome):
    fmt_esperado, n, campos = ESPERADO[nome]
    fmt, df = importar(M, FIX / nome)
    assert fmt == fmt_esperado
    assert len(df) == n, f"{nome}: {len(df)} registros, esperado {n}"
    for coluna in ("authors", "title", "year", "source", "keywords", "abstract",
                   "citations", "doi", "references", "document_type"):
        assert coluna in df.columns, f"{nome}: falta a coluna {coluna}"
    # Nenhum leitor pode devolver o texto "nan" no lugar de um campo vazio.
    texto = df[["authors", "title", "source", "keywords", "doi"]].astype(str)
    assert not texto.isin(["nan", "None"]).any().any(), f"{nome}: 'nan' nos campos"
    primeiro = df.iloc[0]
    for campo, valor in campos.items():
        atual = primeiro[campo]
        if isinstance(valor, int):
            atual = int(atual)
        assert atual == valor, f"{nome}: {campo} = {atual!r}, esperado {valor!r}"


# ── I1-I4: RIS ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nome", ["scopus_export.ris", "zotero_export.ris",
                                  "mendeley_export.ris"])
def test_i1_ris_cada_registro_e_um_registro(nome):
    df = BibliometricParser(str(FIX / nome)).load_ris()
    assert len(df) >= 2
    assert df["title"].nunique() == len(df), "registros fundidos num só"
    # Nenhum registro herda autores do anterior.
    assert not any("Gonçalves" in a and "Donthu" in a for a in df["authors"])


def test_i1_ris_um_registro_e_sem_er_no_fim(tmp_path):
    arq = tmp_path / "x.ris"
    arq.write_text("TY  - JOUR\nAU  - Silva, A.\nTI  - Um\nPY  - 2020\nER  - \n"
                   "TY  - JOUR\nAU  - Souza, B.\nTI  - Dois\nPY  - 2021\n", encoding="utf-8")
    df = BibliometricParser(str(arq)).load_ris()
    assert df["title"].tolist() == ["Um", "Dois"]
    assert df["authors"].tolist() == ["Silva, A.", "Souza, B."]


def test_i2_ris_editor_nao_e_coautor():
    df = BibliometricParser(str(FIX / "zotero_export.ris")).load_ris()
    capitulo = df[df["title"].str.startswith("Bibliometria")].iloc[0]
    assert "Pereira" not in capitulo["authors"]
    assert capitulo["source"] == "Métricas da ciência"


def test_i3_ris_scopus_traz_citacoes_e_referencias():
    df = BibliometricParser(str(FIX / "scopus_export.ris")).load_ris()
    a, b = df.iloc[0], df.iloc[1]
    assert a["citations"] == 3105 and b["citations"] == 7
    # N1 em linhas separadas e N1 tudo junto: as duas grafias do Scopus.
    assert a["references"].startswith("Aria M., Cuccurullo C.")
    assert "Correspondence" not in a["references"]
    assert b["references"] == ("Ostrom E., Governing the commons, (1990); "
                               "Freire P., Pedagogia do oprimido, (1968)")
    assert b["document_type"] == "conference-paper"
    assert b["title"] == 'Catadores e "economia circular": cooperativas; políticas'


def test_i3_ris_resumo_em_varias_linhas(tmp_path):
    arq = tmp_path / "endnote.ris"
    arq.write_text("TY  - JOUR\nTI  - T\nAB  - Primeira linha do resumo\ncontinua aqui.\n"
                   "ER  - \n", encoding="utf-8")
    df = BibliometricParser(str(arq)).load_ris()
    assert df.iloc[0]["abstract"] == "Primeira linha do resumo continua aqui."


def test_i4_ris_e_bibtex_em_txt_sao_detectados(M, tmp_path):
    ris = tmp_path / "savedrecs.txt"
    ris.write_bytes((FIX / "zotero_export.ris").read_bytes())
    bib = tmp_path / "referencias.txt"
    bib.write_bytes((FIX / "zotero_export.bib").read_bytes())
    assert detectar(M, ris) == "ris"
    assert detectar(M, bib) == "bibtex"


# ── I5-I7: Web of Science ─────────────────────────────────────────────────────────

def test_i5_wos_early_access_sem_py_nao_derruba_o_arquivo():
    df = BibliometricParser(str(FIX / "wos_plain_text.txt")).load_wos_txt()
    early = df[df["doi"] == "10.1590/0034-761220250001"].iloc[0]
    assert early["year"] == 2026          # de EY
    assert early["document_type"] == "article"


def test_i6_wos_continuacao_de_texto_emenda_com_espaco():
    df = BibliometricParser(str(FIX / "wos_plain_text.txt")).load_wos_txt()
    assert df.iloc[1]["title"] == ('Catadores e "economia circular": cooperativas; políticas '
                                  "e ação coletiva no Brasil urbano contemporâneo")
    assert "Knowledge structure" in df.iloc[0]["keywords"].split("; ")
    # Listas continuam separadas por "; ".
    assert df.iloc[1]["authors"] == "Gonçalves, JM; Müller, H; Ñúñez, P"
    assert len(df.iloc[0]["references"].split("; ")) == 5


def test_i5_wos_anonimo_nao_e_autor():
    df = BibliometricParser(str(FIX / "wos_plain_text.txt")).load_wos_txt()
    assert "[Anonymous]" not in " ".join(df["authors"])


def test_i7_wos_tab_real_sem_fn_com_aspas():
    df = BibliometricParser(str(FIX / "wos_tab_delimited.txt")).load_wos_txt()
    assert df["title"].tolist()[1] == 'Catadores e "economia circular": cooperativas; políticas'
    assert df.iloc[1]["year"] == 2026     # PY vazio, ano do EA
    assert df.iloc[1]["abstract"] == 'Resumo com "aspas" e acentuação.'
    assert df.iloc[2]["authors"] == ""


def test_i7_wos_tab_antigo_com_linha_fn_continua_funcionando(tmp_path):
    arq = tmp_path / "wos.txt"
    arq.write_text("FN Thomson Reuters\nPT\tAU\tTI\tPY\tTC\nJ\tSilva, J\tT\t2020\t15\n",
                   encoding="utf-8")
    df = BibliometricParser(str(arq)).load_wos_txt()
    assert df.iloc[0]["title"] == "T" and df.iloc[0]["citations"] == 15


# ── I8: BibTeX ────────────────────────────────────────────────────────────────────

def test_i8_bibtex_acentos_latex_e_chaves():
    df = BibliometricParser(str(FIX / "scopus_export.bib")).load_bibtex()
    r = df.iloc[1]
    assert r["authors"] == "Gonçalves, João; Müller, Hans; José, André"
    assert r["title"] == "Catadores e economia circular: ação coletiva em São Paulo"
    assert r["abstract"] == "Resumo com acentos em LaTeX: ciência e política."
    assert r["citations"] == 7            # "cited By 7", grafia antiga do Scopus
    assert r["document_type"] == "conference-paper"
    assert r["keywords"] == "Economia circular; Cooperativas"   # author_keywords primeiro


def test_i8_bibtex_scopus_traz_referencias():
    df = BibliometricParser(str(FIX / "scopus_export.bib")).load_bibtex()
    refs = df.iloc[0]["references"].split("; ")
    assert len(refs) == 2 and refs[1].startswith("Zupic I.")


def test_i8_bibtex_and_entre_chaves_nao_separa_autor(tmp_path):
    arq = tmp_path / "x.bib"
    arq.write_text("@article{a, author = {{Barnes and Noble Group} and Silva, J.}, "
                   "title = {T}, year = {2020a}}", encoding="utf-8")
    df = BibliometricParser(str(arq)).load_bibtex()
    assert df.iloc[0]["authors"] == "Barnes and Noble Group; Silva, J."
    assert df.iloc[0]["year"] == 2020


def test_i8_bibtex_autores_no_indice_h():
    from core.matrix_builders import NetworkGenerator
    df = BibliometricParser(str(FIX / "zotero_export.bib")).load_bibtex()
    autores = {a for a, *_ in NetworkGenerator(df).get_author_hindex(50)}
    assert "van Eck, Nees Jan" in autores and "Waltman, Ludo" in autores
    assert not any(" and " in a for a in autores)


# ── I9-I10: OpenAlex e Crossref ───────────────────────────────────────────────────

def test_i9_openalex_autor_sem_nome_e_titulo_nulo():
    df = BibliometricParser(str(FIX / "openalex_api.json")).load_openalex_json()
    assert df.iloc[1]["authors"] == "João Gonçalves"
    assert df.iloc[2]["title"] == "Co-citation in the scientific literature"
    assert df.iloc[0]["openalex_id"] == "https://openalex.org/W2150220236"
    assert bool(df.iloc[0]["is_oa"]) is True


def test_i9_openalex_importado_gera_citacao_direta():
    from core.map_controls import viabilidade_tipo
    from core.matrix_builders import NetworkGenerator
    df = BibliometricParser(str(FIX / "openalex_api.json")).load_openalex_json()
    assert viabilidade_tipo(4, df) is None
    G = NetworkGenerator(df).build_direct_citation_network(min_citations=1)
    assert G.number_of_edges() >= 2


def test_i9_openalex_keywords_formato_2023(tmp_path):
    arq = tmp_path / "w.json"
    arq.write_text('[{"id": "W1", "title": "T", "keywords": [{"keyword": "science mapping",'
                   ' "score": 0.5}]}]', encoding="utf-8")
    df = BibliometricParser(str(arq)).load_openalex_json()
    assert df.iloc[0]["keywords"] == "science mapping"


def test_i10_crossref_um_work_e_autor_institucional():
    um = BibliometricParser(str(FIX / "crossref_api_um_work.json")).load_crossref_json()
    assert um.iloc[0]["title"].startswith("Software survey")
    lista = BibliometricParser(str(FIX / "crossref_api_lista.json")).load_crossref_json()
    assert not lista.iloc[0]["authors"].endswith(";")
    assert not lista.iloc[0]["abstract"].startswith("Abstract")


def test_json_com_bom_do_bloco_de_notas(tmp_path):
    arq = tmp_path / "works.json"
    arq.write_bytes((FIX / "openalex_api.json").read_bytes().decode("utf-8")
                    .encode("utf-8-sig"))
    df = BibliometricParser(str(arq)).load_openalex_json()
    assert len(df) == 3


# ── I11-I12: PubMed e Scopus ──────────────────────────────────────────────────────

def test_i11_pubmed_doi_e_mesh():
    df = BibliometricParser(str(FIX / "pubmed_export.nbib")).load_pubmed_medline()
    assert df["doi"].tolist() == ["10.1016/S0140-6736(20)30183-5",
                                  "10.1590/0102-311X00000021", ""]
    kws = df.iloc[0]["keywords"].split("; ")
    assert "Humans" in kws and not any(k.startswith("*") for k in kws)
    assert df.iloc[0]["abstract"].endswith("laboratory-confirmed infection.")
    assert df.iloc[1]["document_type"] == "review"


def test_i12_scopus_marcadores_nao_viram_dado():
    df = BibliometricParser(str(FIX / "scopus_export.csv")).load_scopus_csv()
    assert df.iloc[2]["authors"] == "" and df.iloc[2]["abstract"] == ""
    assert df.iloc[3]["year"] == 0          # no prelo, sem ano
    assert len(df.iloc[2]["references"].split("; ")) == 120
    assert df.iloc[1]["doi"] == "" and df.iloc[1]["citations"] == 0


def test_scopus_csv_sem_colunas_opcionais(tmp_path):
    """Usuário desmarcou quase tudo no diálogo de exportação do Scopus."""
    arq = tmp_path / "scopus.csv"
    arq.write_text("Title,Year,Source title\nT,2020,J\n", encoding="utf-8")
    df = BibliometricParser(str(arq)).load_scopus_csv()
    assert df.iloc[0]["authors"] == "" and df.iloc[0]["references"] == ""
    assert df.iloc[0]["citations"] == 0


# ── I13-I14: PDF e detecção ───────────────────────────────────────────────────────

def test_i13_pdf_detectado_sem_ano_inventado(M, tmp_path, monkeypatch):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")
    assert detectar(M, pdf) == "pdf"

    class _Pagina:
        def extract_text(self):
            return "Um artigo. https://doi.org/10.1016/j.joi.2017.08.007.\nTexto."

    class _Pdf:
        metadata = {"Title": "bibliometrix"}
        pages = [_Pagina()]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setitem(sys.modules, "pdfplumber",
                        types.SimpleNamespace(open=lambda *_a, **_k: _Pdf()))
    df = BibliometricParser(str(pdf)).load_pdf()
    r = df.iloc[0]
    assert r["year"] == 0
    assert r["doi"] == "10.1016/j.joi.2017.08.007"
    assert r["title"] == "bibliometrix"
    assert "document_type" in df.columns


def test_i14_scopus_com_concept_no_resumo_nao_vira_wos(M, tmp_path):
    arq = tmp_path / "scopus.csv"
    arq.write_text('Title,Year,Abstract\nT,2020,"A PROOF OF CONCEPT FOR VR SCRIPT"\n',
                   encoding="utf-8")
    # Sem "Authors" no cabeçalho: antes o "PT " de CONCEPT decidia pelo WoS.
    assert detectar(M, arq) != "wos"


def test_deteccao_existente_preservada(M):
    raiz = Path(__file__).resolve().parent.parent
    assert detectar(M, raiz / "exemplos" / "corpus_ficticio_scopus.csv") == "scopus"
    assert detectar(M, raiz / "exemplos" / "corpus_ficticio_wos.txt") == "wos"
    assert detectar(M, raiz / "docs" / "sample_dataset.csv") == "blicsa"


# ── Arquivos grandes (2000 registros) ─────────────────────────────────────────────

N_GRANDE = 2000


def _wos_grande() -> str:
    partes = ["﻿FN Clarivate Analytics Web of Science", "VR 1.0"]
    for i in range(N_GRANDE):
        partes += [
            "PT J", f"AU Autor{i}, A", f"   Coautor{i % 50}, B",
            f"TI Titulo numero {i} sobre mapeamento", "   cientifico",
            "SO JOURNAL X", "DE bibliometrics; science", "   mapping",
            f"PY {2000 + i % 25}" if i % 100 else "EY 2025", f"TC {i}",
            f"DI 10.5555/x{i}",
            f"CR Ref{i % 7} A, 2001, J, V1, P1", f"   Ref{(i + 1) % 7} B, 2002, J, V2, P2",
            "ER", ""]
    partes.append("EF")
    return "\r\n".join(partes)


def _ris_grande() -> str:
    partes = []
    for i in range(N_GRANDE):
        partes += ["TY  - JOUR", f"AU  - Autor{i}, A.", f"AU  - Coautor{i % 50}, B.",
                   f"TI  - Titulo {i}", f"PY  - {2000 + i % 25}", "KW  - bibliometrics",
                   "KW  - science mapping", f"DO  - 10.5555/r{i}", "ER  - ", ""]
    return "\r\n".join(partes)


def _scopus_grande() -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["Authors", "Title", "Year", "Source title", "Cited by", "DOI",
                "Abstract", "Author Keywords", "References", "Document Type"])
    for i in range(N_GRANDE):
        w.writerow([f"Autor{i} A.; Coautor{i % 50} B.", f'Titulo "{i}"; parte', 2000 + i % 25,
                    "Journal", i, f"10.5555/s{i}", "Resumo, com vírgula; e ponto e vírgula",
                    "bibliometrics; science mapping",
                    f"Ref{i % 7} A., T, J, (2001); Ref{(i + 1) % 7} B., T, J, (2002)",
                    "Article"])
    return buf.getvalue()


@pytest.mark.parametrize("nome,gerar,codificacao,fmt", [
    ("savedrecs.txt", _wos_grande, "utf-8", "wos"),
    ("scopus.ris", _ris_grande, "utf-8", "ris"),
    ("scopus.csv", _scopus_grande, "utf-8-sig", "scopus"),
])
def test_arquivo_com_2000_registros(M, tmp_path, nome, gerar, codificacao, fmt):
    arq = tmp_path / nome
    arq.write_bytes(gerar().encode(codificacao))
    inicio = time.perf_counter()
    detectado, df = importar(M, arq)
    duracao = time.perf_counter() - inicio
    assert detectado == fmt
    assert len(df) == N_GRANDE
    assert df["doi"].nunique() == N_GRANDE
    assert (df["year"] > 0).all()
    assert df.iloc[1999]["citations"] == (1999 if fmt != "ris" else 0)
    assert duracao < 30, f"{nome}: {duracao:.1f}s para {N_GRANDE} registros"
    if fmt == "wos":
        assert df.iloc[5]["title"] == "Titulo numero 5 sobre mapeamento cientifico"
        assert df.iloc[5]["keywords"] == "bibliometrics; science mapping"


# ── O que cada formato permite mapear ────────────────────────────────────────────

@pytest.mark.parametrize("nome,coautoria,referencias", [
    ("scopus_export.csv", True, True),
    ("wos_plain_text.txt", True, True),
    ("wos_tab_delimited.txt", True, True),
    ("scopus_export.bib", True, True),
    ("zotero_export.bib", True, False),
    ("scopus_export.ris", True, True),
    ("zotero_export.ris", True, False),
    ("pubmed_export.nbib", True, False),
    ("openalex_api.json", True, True),
    ("crossref_api_lista.json", True, True),
])
def test_viabilidade_dos_mapas_por_formato(M, nome, coautoria, referencias):
    """Base da tabela "qual mapa funciona com qual formato" do guia."""
    from core.map_controls import viabilidade_tipo
    _, df = importar(M, FIX / nome)
    assert (viabilidade_tipo(1, df) is None) is coautoria
    assert (viabilidade_tipo(2, df) is None) is referencias
    assert viabilidade_tipo(5, df) == "map.inviavel_sem_ipc"   # nenhuma base traz IPC


def test_cocitacao_com_wos_importado(M):
    from core.matrix_builders import NetworkGenerator
    _, df = importar(M, FIX / "wos_plain_text.txt")
    G = NetworkGenerator(df).build_cocitation_network(min_cocitations=1)
    assert G.number_of_nodes() >= 5


def test_citacao_direta_com_wos_importado(M):
    """WoS e Scopus casam a referência pelo sobrenome + ano (aproximado, ver o guia)."""
    from core.matrix_builders import NetworkGenerator
    _, df = importar(M, FIX / "wos_plain_text.txt")
    G = NetworkGenerator(df).build_direct_citation_network(min_citations=1)
    assert ("aria (2017)", "small (1973)") in G.edges()


# ── Pela janela: o mesmo caminho do botão "Carregar e Combinar" ──────────────────

@pytest.fixture(scope="module")
def app(M):
    mp = pytest.MonkeyPatch()
    caixas: list = []
    for nome in ("showinfo", "showwarning", "showerror"):
        mp.setattr(M.messagebox, nome, lambda *a, **k: caixas.append(a))
    mp.setattr(M.webbrowser, "open", lambda *a, **k: True)
    try:
        janela = M.BlicsaApp()
    except Exception as exc:
        mp.undo()
        pytest.skip(f"Tk indisponível: {exc}")
    janela._demo_no_browser = True
    janela.withdraw()
    janela._caixas = caixas
    yield janela
    for fn in (janela._on_app_close, janela.destroy):
        try:
            fn()
        except Exception:
            pass
    mp.undo()


@pytest.mark.parametrize("nome", [
    "scopus_export.csv", "wos_plain_text.txt", "wos_tab_delimited.txt", "scopus_export.bib",
    "zotero_export.ris", "endnote_cp1252.txt", "pubmed_export.nbib", "openalex_api.json",
    "crossref_api_um_work.json", "blicsa_corpus.csv",
])
def test_carga_pela_janela(app, nome):
    app._caixas.clear()
    app._file_paths = [str(FIX / nome)]
    app._file_formats = [app._auto_detect_format(str(FIX / nome))]
    app._load_worker()
    app.update()
    assert not app._caixas, f"{nome}: o app mostrou erro {app._caixas}"
    assert len(app._dataframe) == ESPERADO[nome][1]
