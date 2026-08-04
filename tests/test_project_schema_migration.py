"""Retrocompatibilidade de `.blicsa` salvos por versões antigas do app.

O defeito, observado numa sessão real: abrir um projeto antigo e mandar calcular a rede
imprimia `[ERRO] 'keywords'` — uma mensagem de uma palavra só, sem dizer que o problema era o
arquivo, muito menos qual coluna faltava. A causa é um `KeyError`: `matrix_builders` acessa
`df["keywords"]` direto, e um `.blicsa` de julho não tem essa coluna.

O gancho de migração existia em `core/project.py` desde sempre, com o comentário "Insert
migrations here if schema ever changes". O schema mudou; o gancho continuou vazio.

As fixtures reproduzem os DOIS formatos encontrados em disco (`scripts/` não gera nada em
tempo de teste — são arquivos commitados, do jeito que chegariam de um usuário):

* `projeto_schema_1_0.blicsa`  — manifest "1.0" de 14/07, cinco colunas;
* `projeto_schema_v3_so_titulo.blicsa` — manifest 3 de 30/07, só `title`. É o caso que
  quebrou de verdade, e o que prova que **o número da versão não serve para decidir se
  migra**: ele diz "3", mais novo que o "1.0", e tem menos colunas.
"""

import gzip
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from core import matrix_builders as mb
from core.project import (COLUNAS_NUMERICAS, SCHEMA_REGISTRO, load_blicsa_project,
                          normalize_dataframe)

FIXTURES = Path(__file__).parent / "fixtures"
ANTIGO = FIXTURES / "projeto_schema_1_0.blicsa"
SO_TITULO = FIXTURES / "projeto_schema_v3_so_titulo.blicsa"


def _colunas_cruas(caminho: Path) -> set[str]:
    """Colunas que o arquivo REALMENTE tem, sem passar pela normalização."""
    with zipfile.ZipFile(caminho) as z:
        regs = json.loads(gzip.decompress(z.read("dataset.json.gz")))
    return set().union(*[set(r) for r in regs]) if regs else set()


# ── As fixtures são mesmo antigas? ────────────────────────────────────────────────

def test_fixtures_sao_de_schema_antigo_de_verdade():
    """Guarda contra a fixture envelhecer para o schema novo e o teste virar vácuo.

    Se alguém regravar estes arquivos com o app atual, eles passam a ter todas as colunas e
    todos os testes abaixo continuam verdes **sem testar nada**."""
    cruas_1_0 = _colunas_cruas(ANTIGO)
    assert cruas_1_0 == {"authors", "citations", "doi", "title", "year"}, cruas_1_0
    assert "keywords" not in cruas_1_0, "a fixture 1.0 não pode ter keywords"

    cruas_v3 = _colunas_cruas(SO_TITULO)
    assert cruas_v3 == {"title"}, cruas_v3

    with zipfile.ZipFile(SO_TITULO) as z:
        assert json.loads(z.read("manifest.json"))["version"] == 3, (
            "a fixture existe para provar que versão MAIOR não significa schema completo")


# ── Carga: o arquivo antigo chega normalizado ─────────────────────────────────────

@pytest.mark.parametrize("caminho", [ANTIGO, SO_TITULO], ids=["schema_1_0", "v3_so_titulo"])
def test_projeto_antigo_carrega_com_schema_completo(caminho):
    df = load_blicsa_project(str(caminho))["df"]
    faltando = [c for c in SCHEMA_REGISTRO if c not in df.columns]
    assert not faltando, f"colunas ausentes depois da carga: {faltando}"


@pytest.mark.parametrize("caminho", [ANTIGO, SO_TITULO], ids=["schema_1_0", "v3_so_titulo"])
def test_calculo_de_rede_nao_levanta_keyerror(caminho):
    """O sintoma original, nos três campos que a UI oferece."""
    df = load_blicsa_project(str(caminho))["df"]
    for campo in ("keywords", "titles", "titles_abstracts"):
        mb._extract_term_lists(df, campo, {}, None)   # não pode levantar


@pytest.mark.parametrize("caminho", [ANTIGO, SO_TITULO], ids=["schema_1_0", "v3_so_titulo"])
def test_filtro_de_periodo_funciona(caminho):
    """`df["year"] >= n` compara com int: se a coluna vier ausente ou como texto, estoura."""
    df = load_blicsa_project(str(caminho))["df"]
    assert str(df["year"].dtype).startswith("int"), df["year"].dtype
    recortado = df[(df["year"] >= 2000) & (df["year"] <= 2030)]
    assert isinstance(recortado, pd.DataFrame)


def test_dados_existentes_sobrevivem_a_normalizacao():
    """O outro lado da guarda: preencher o que falta não pode mexer no que já existe."""
    df = load_blicsa_project(str(ANTIGO))["df"]
    assert list(df["title"]) == ["Bibliometric mapping of innovation systems",
                                 "Co-word analysis in regional studies"]
    assert list(df["year"]) == [2019, 2021]
    assert list(df["citations"]) == [12, 3]
    assert df.loc[0, "authors"] == "Silva A; Costa B"
    # E o que foi preenchido tem que ser vazio, não lixo.
    assert list(df["keywords"]) == ["", ""]
    assert list(df["is_oa"]) == [False, False]


# ── `normalize_dataframe` isolada ─────────────────────────────────────────────────

def test_colunas_extras_sao_preservadas():
    """Projetos de julho têm `language_source`. Normalizar não é podar."""
    df = normalize_dataframe(pd.DataFrame([{"title": "T", "language_source": "detectado"}]))
    assert df.loc[0, "language_source"] == "detectado"
    assert "keywords" in df.columns


def test_is_oa_em_texto_vira_booleano_correto():
    """JSON antigo grava "false" como string — e `bool("false")` é True.

    Sem a conversão, todo registro de projeto antigo apareceria como Open Access."""
    df = normalize_dataframe(pd.DataFrame([
        {"title": "A", "is_oa": "false"}, {"title": "B", "is_oa": "true"},
        {"title": "C", "is_oa": False},   {"title": "D", "is_oa": True},
    ]))
    assert list(df["is_oa"]) == [False, True, False, True]


def test_ano_como_texto_ou_lixo_vira_numero():
    df = normalize_dataframe(pd.DataFrame([
        {"title": "A", "year": "2019"}, {"title": "B", "year": "s.d."},
        {"title": "C", "year": None},   {"title": "D", "year": 2024},
    ]))
    assert list(df["year"]) == [2019, 0, 0, 2024]
    assert str(df["year"].dtype).startswith("int")


def test_nan_em_campo_de_texto_nao_vira_a_palavra_nan():
    """`str(float("nan"))` é "nan": sem tratamento, a UI mostraria "nan" como se fosse dado."""
    df = normalize_dataframe(pd.DataFrame([{"title": "A", "authors": None},
                                           {"title": "B", "authors": "Silva A"}]))
    assert list(df["authors"]) == ["", "Silva A"]


def test_dataframe_vazio_ganha_o_schema():
    """Busca sem resultado também passa por código que faz `df["year"]`."""
    df = normalize_dataframe(pd.DataFrame())
    assert set(SCHEMA_REGISTRO).issubset(df.columns)
    assert len(df) == 0
    for coluna in COLUNAS_NUMERICAS:
        assert str(df[coluna].dtype).startswith("int")


def test_dataframe_ja_completo_nao_e_alterado():
    """Idempotência: o caminho normal (projeto novo) não pode ser tocado."""
    original = pd.DataFrame([{**SCHEMA_REGISTRO, "title": "T", "year": 2020, "citations": 5}])
    resultado = normalize_dataframe(original.copy())
    pd.testing.assert_frame_equal(resultado[list(SCHEMA_REGISTRO)],
                                  original[list(SCHEMA_REGISTRO)], check_dtype=False)


# ── Versão mínima do Python: README, badge e CI têm que concordar ─────────────────

def test_versao_minima_do_python_e_consistente():
    """A divergência custou um CI vermelho de 21/07 a 03/08 sem ninguém notar.

    O README anunciava "Python 3.10+", a matriz do CI incluía 3.10, e quatro pins do
    `requirements-core.txt` (numpy, pandas, scipy, networkx) declaram `requires-python
    >=3.11`. O build morria em `Install dependencies` — antes de rodar teste algum, o que
    fazia a falha parecer sempre a mesma e sempre de outra coisa.
    """
    import re

    raiz = Path(__file__).parent.parent
    readme = (raiz / "README.md").read_text(encoding="utf-8")
    ci = (raiz / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    badge = re.search(r"badge/Python-(\d+)\.(\d+)%2B", readme)
    assert badge, "badge de versão do Python sumiu do README"
    badge_ver = (int(badge.group(1)), int(badge.group(2)))

    texto = re.search(r"\*\*Python (\d+)\.(\d+)\+\*\* is required", readme)
    assert texto, "a frase de versão mínima sumiu do README"
    texto_ver = (int(texto.group(1)), int(texto.group(2)))

    matriz = re.search(r'python-version:\s*\[([^\]]+)\]', ci)
    assert matriz, "matriz de versões sumiu do CI"
    versoes = [tuple(int(x) for x in v.strip().strip('"\' ').split("."))
               for v in matriz.group(1).split(",")]
    menor_ci = min(versoes)

    assert badge_ver == texto_ver, f"badge {badge_ver} ≠ texto {texto_ver} no README"
    assert menor_ci == badge_ver, (
        f"o CI testa a partir de {menor_ci} mas o README promete {badge_ver} — "
        "uma das duas afirmações está mentindo")
    assert menor_ci >= (3, 11), (
        f"os pins de numpy/pandas/scipy/networkx exigem >=3.11; a matriz mínima é {menor_ci}")


# ── Item 3: a normalização cobre TODOS os formatos já produzidos ──────────────────

def test_normalizacao_cobre_os_tres_formatos_conhecidos(tmp_path):
    """v1.0 (14/07), v3 (30/07, alheio ao app) e o formato atual, no mesmo teste.

    O `v3` não é uma evolução do `1.0`: nenhum código deste repositório escreve
    `version: 3` nem `app: "Blicsa"`, e os dois arquivos com esse manifesto têm o mesmo
    carimbo redondo (`10:00:00`), enquanto o app grava `time.strftime`. São artefatos de um
    script avulso. Entram aqui porque **existem em disco de usuário** e precisam abrir.
    """
    import networkx as nx
    from core.project import CURRENT_MANIFEST_VERSION, save_blicsa_project

    atual = tmp_path / "formato_atual.blicsa"
    save_blicsa_project(
        str(atual),
        pd.DataFrame([{**SCHEMA_REGISTRO, "title": "Atual", "year": 2025, "citations": 3}]),
        {"name": "Atual"}, {"n": (0.0, 0.0)}, nx.Graph([("a", "b")]), {0: "C0"}, [])

    casos = [(ANTIGO, "1.0"), (SO_TITULO, 3), (atual, CURRENT_MANIFEST_VERSION)]
    for caminho, versao_esperada in casos:
        with zipfile.ZipFile(caminho) as z:
            assert json.loads(z.read("manifest.json"))["version"] == versao_esperada, caminho.name
        df = load_blicsa_project(str(caminho))["df"]
        faltando = [c for c in SCHEMA_REGISTRO if c not in df.columns]
        assert not faltando, f"{caminho.name}: faltam {faltando}"
        # E o dado tem que ser utilizável, não só presente.
        mb._extract_term_lists(df, "keywords", {}, None)
        assert str(df["year"].dtype).startswith("int")


def test_manifesto_do_app_e_sempre_a_versao_corrente(tmp_path):
    """O número gravado tem que sair de `CURRENT_MANIFEST_VERSION`, não de um literal solto."""
    import networkx as nx
    from core.project import CURRENT_MANIFEST_VERSION, save_blicsa_project

    destino = tmp_path / "p.blicsa"
    save_blicsa_project(str(destino), pd.DataFrame([{"title": "T"}]), {}, None,
                        nx.Graph(), None, None)
    with zipfile.ZipFile(destino) as z:
        m = json.loads(z.read("manifest.json"))
    assert m["version"] == CURRENT_MANIFEST_VERSION
    assert m["app"] == "PyBibliomics Blicsa", "o app nunca escreve app='Blicsa'"


# ── Item 4: os acessos a df["year"] em main.py estão guardados ────────────────────

def test_acessos_a_year_em_main_estao_guardados():
    """`main.py` monta DataFrame por caminhos que NÃO passam pela normalização de projeto
    (importação de arquivo, resultado de busca). Cada `df["year"]` precisa da sua guarda.

    Foi assim que o cálculo de rede morria com "[ERRO] 'keywords'": acesso direto a coluna
    que podia não existir. O mesmo risco vale para `year`, e este teste impede que um acesso
    novo entre sem guarda."""
    import re

    linhas = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8").splitlines()
    desprotegidos = []
    for i, linha in enumerate(linhas):
        codigo = linha.split("#", 1)[0]          # comentário não é acesso
        if not re.search(r'df\["year"\]', codigo):
            continue
        janela = "\n".join(linhas[max(0, i - 8):i])
        if not re.search(r'"year"\s+in\s+df\.columns|\btem_ano\b', janela):
            desprotegidos.append(i + 1)

    assert not desprotegidos, (
        f"acesso a df[\"year\"] sem guarda nas linhas {desprotegidos} de main.py — "
        'preceda com `if "year" in df.columns`')
