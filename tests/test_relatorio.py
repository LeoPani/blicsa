"""`core/relatorio.py` — o documento que se anexa ao artigo, montado do que o projeto gravou.

Três coisas que estes testes guardam, porque as três já podem estar erradas em silêncio:

* **A declaração muda conforme o que houve.** Um texto fixo com lacunas diria a mesma coisa
  para uma pesquisa sem IA nenhuma e para uma cujos rótulos de cluster foram escritos por um
  modelo — e é exatamente essa distinção que a exigência da revista quer ver.
* **A string do relatório é a que FOI para a API.** Ela passa pelo tradutor de
  `core/strings_por_base.py` e pelo `_effective_query`, e sai diferente da que o usuário
  digitou. Publicar a digitada faria a busca não reproduzir o número.
* **Ausência não é zero.** Encontrados não medidos viram travessão, não `0`.

Sem Tk e sem rede: a montagem é aritmética sobre o backlog. A tela está em
`tests/test_aba_relatorio.py`.
"""

import json

import pytest

from core.relatorio import (buscas, cobertura, declaracao_de_uso, fluxo_de_registros,
                            montar, para_json, para_markdown)
from core.uso_de_ia import ACAO, evento


@pytest.fixture(autouse=True)
def em_portugues():
    """O relatório é texto: sem catálogo carregado, as asserções comparariam chaves cruas."""
    from core.i18n import load_locales
    load_locales("pt_BR")


def _ia(ponto, uso=None, erro="", modelo="openai/gpt-oss-120b"):
    return {"ts": "2026-01-01T10:00:00", "action": ACAO,
            "detail": evento(ponto, modelo, "Groq", uso=uso, erro=erro)}


def _busca(**d):
    base = {"provider": "openalex", "query": "digitada", "query_interpretada": "enviada",
            "filters": {}, "encontrados": 100, "baixados": 50, "stop_reason": ""}
    base.update(d)
    return {"ts": "2026-01-01T09:00:00", "action": "search", "detail": base}


# ── A declaração de uso ─────────────────────────────────────────────────────────

def test_sem_ia_a_declaracao_diz_que_nao_houve():
    """Não é ausência de texto: é uma afirmação, e algumas revistas a exigem por escrito."""
    texto = declaracao_de_uso(montar([_busca()]))
    assert "Nenhuma ferramenta" in texto


def test_com_rotulos_de_cluster_a_declaracao_diz_que_a_ia_entrou_no_resultado():
    texto = declaracao_de_uso(montar([_ia("rotulos_de_cluster")]))
    assert "incorporada ao resultado" in texto
    assert "Nomeação de clusters" in texto


def test_so_com_chat_a_declaracao_diz_que_a_saida_nao_integrou_os_dados():
    """A distinção que separa uso consultivo de uso que produz resultado."""
    texto = declaracao_de_uso(montar([_ia("blink_chat")]))
    assert "sem que sua saída integrasse os dados" in texto
    assert "incorporada ao resultado" not in texto


def test_a_declaracao_nomeia_os_pontos_em_vez_de_descreve_los_por_escrito():
    """Frase fixa sobre "os clusters" passaria a mentir no dia do segundo ponto do tipo."""
    from core.uso_de_ia import INTERPRETA, PONTOS

    assert [p for p, n in PONTOS.items() if n == INTERPRETA] == ["rotulos_de_cluster"], (
        "surgiu outro ponto que entra no resultado — confira se a declaração o nomeia")


def test_a_declaracao_sempre_fecha_dizendo_o_que_a_ia_NAO_fez():
    """É a frase que o editor procura. Sem ela a declaração lista atividades e deixa em
    aberto a única pergunta que interessa."""
    for backlog in ([_ia("blink_chat")], [_ia("rotulos_de_cluster")]):
        assert "responsabilidade dos autores" in declaracao_de_uso(montar(backlog))


def test_a_declaracao_nomeia_o_provedor_e_o_modelo():
    texto = declaracao_de_uso(montar([_ia("blink_chat")], versao="2.0.0"))
    assert "openai/gpt-oss-120b" in texto and "Groq" in texto and "2.0.0" in texto


# ── A cadeia de busca ───────────────────────────────────────────────────────────

def test_a_string_publicada_e_a_que_foi_para_a_api():
    """O que o usuário digita passa pelo tradutor por base e pelo `_effective_query`.

    Um leitor que tentasse refazer a busca com a string digitada não chegaria ao mesmo
    número — e não teria como saber por quê.
    """
    b = buscas([_busca(query='TITLE-ABS-KEY("ml")', query_interpretada='"ml" AND biblio')])[0]
    assert b["string_enviada"] == '"ml" AND biblio'
    assert b["string"] == 'TITLE-ABS-KEY("ml")'


def test_a_digitada_aparece_no_markdown_so_quando_difere():
    """Repeti-la idêntica encheria o relatório de ruído em toda busca comum."""
    igual = para_markdown(montar([_busca(query="x", query_interpretada="x")]))
    assert "String digitada" not in igual

    diferente = para_markdown(montar([_busca(query="x", query_interpretada="y")]))
    assert "String digitada" in diferente


def test_busca_sem_medida_sai_com_travessao_e_nao_com_zero():
    """`0 encontrados` é uma afirmação — "a base não tem nada". Ausência de medida não é."""
    md = para_markdown(montar([_busca(encontrados=None, baixados=None)]))
    assert "— encontrados" in md
    assert "0 encontrados" not in md


def test_projeto_sem_busca_diz_isso_em_vez_de_deixar_a_secao_vazia():
    assert "Nenhuma busca registrada" in para_markdown(montar([_ia("blink_chat")]))


# ── O fluxo de registros ────────────────────────────────────────────────────────

def test_o_corpus_final_sai_do_ultimo_import_e_nao_de_uma_subtracao():
    """Somar e subtrair daria um número plausível e errado sempre que houvesse importação
    de arquivo local, que não passa por busca nenhuma."""
    backlog = [_busca(encontrados=500, baixados=200),
               {"ts": "1", "action": "import", "detail": {"registros": 200, "total_corpus": 200}},
               {"ts": "2", "action": "import", "detail": {"registros": 80, "total_corpus": 280}}]
    f = fluxo_de_registros(backlog)
    assert f["encontrados"] == 500 and f["baixados"] == 200
    assert f["importados"] == 280 and f["corpus_final"] == 280


def test_dedup_cancelado_nao_conta_como_duplicata_removida():
    """A tela de dedup deixa recusar. Contar o que foi recusado inflaria o fluxograma."""
    backlog = [{"ts": "1", "action": "dedup", "detail": {"pares": 9, "aplicado": False}},
               {"ts": "2", "action": "dedup", "detail": {"pares": 4, "aplicado": True}}]
    assert fluxo_de_registros(backlog)["duplicatas_removidas"] == 4


def test_varias_buscas_somam():
    backlog = [_busca(encontrados=10, baixados=5), _busca(encontrados=20, baixados=7)]
    f = fluxo_de_registros(backlog)
    assert f["encontrados"] == 30 and f["baixados"] == 12


# ── A cobertura do corpus ───────────────────────────────────────────────────────

@pytest.fixture
def corpus():
    import pandas as pd
    return pd.DataFrame({
        "title": list("abcd"), "year": [2019, 2021, 0, 2023],
        "abstract": ["x", "", "y", "z"], "references": ["r", "", "", "r"],
        "doi": ["10.1/a", "10.1/b", "", "10.1/d"], "keywords": ["k", "k", "", ""],
        "origin": ["openalex", "openalex", "crossref", "pubmed"],
        "is_oa": [True, False, True, True]})


def test_o_ano_zero_do_schema_nao_vira_inicio_do_periodo(corpus):
    """`0` é o vazio de `SCHEMA_REGISTRO`, não uma data — e todo relatório diria que a
    pesquisa começa no ano zero."""
    c = cobertura(corpus)
    assert c["ano_min"] == 2019 and c["ano_max"] == 2023


def test_preenchimento_por_campo(corpus):
    """Um corpus com 30% de resumos não sustenta coocorrência de termos, e um sem
    referências não sustenta acoplamento nem cocitação. Hoje isso se descobre quando o mapa
    sai ralo."""
    c = cobertura(corpus)
    assert c["com_resumo"] == 75.0
    assert c["com_referencias"] == 50.0
    assert c["com_doi"] == 75.0


def test_bases_de_origem_contadas(corpus):
    assert cobertura(corpus)["bases"] == {"openalex": 2, "crossref": 1, "pubmed": 1}


def test_corpus_ausente_nao_levanta():
    """A aba abre com o projeto recém-criado, antes de qualquer importação."""
    assert cobertura(None)["registros"] == 0


def test_coluna_que_falta_conta_como_zero_e_nao_estoura():
    """`.blicsa` de versão antiga não tem todas as colunas do schema."""
    import pandas as pd
    c = cobertura(pd.DataFrame({"title": ["a"]}))
    assert c["registros"] == 1 and c["com_resumo"] == 0.0


# ── As saídas ───────────────────────────────────────────────────────────────────

def test_o_json_leva_a_declaracao_ja_montada():
    """Quem processar o suplemento não deveria ter de reimplementar as regras de redação."""
    d = json.loads(para_json(montar([_ia("rotulos_de_cluster")])))
    assert "incorporada ao resultado" in d["declaracao_de_uso_de_ia"]


def test_o_json_e_valido_com_o_relatorio_completo(corpus):
    d = json.loads(para_json(montar([_busca(), _ia("blink_chat")], projeto="P",
                                    versao="2.0.0", contexto="ctx", df=corpus)))
    assert d["projeto"] == "P" and d["corpus"]["registros"] == 4


def test_tabela_sem_linha_nao_vira_cabecalho_solto():
    md = para_markdown(montar([]))
    assert "| Modelo |" not in md


def test_o_cano_da_tabela_markdown_e_escapado():
    """Uma string de busca com `|` quebraria a tabela em colunas fantasmas."""
    md = para_markdown(montar([_ia("blink_chat", modelo="mod|elo")]))
    assert r"mod\|elo" in md


def test_o_markdown_traz_as_seis_secoes(corpus):
    md = para_markdown(montar([_busca(), _ia("blink_chat")], projeto="P", versao="2.0.0",
                              contexto="ctx", df=corpus))
    for secao in ("Declaração de uso de IA", "Cadeia de busca", "Fluxo de registros",
                  "Cobertura e limites do corpus", "Ambiente", "Contexto da pesquisa"):
        assert f"## {secao}" in md, f"faltou a seção {secao}"


def test_sem_contexto_a_secao_de_contexto_nao_aparece():
    """Cabeçalho sobre um bloco vazio é pior do que a ausência do bloco."""
    assert "## Contexto da pesquisa" not in para_markdown(montar([]))


def test_o_ambiente_registra_a_versao_do_blicsa():
    """Reprodutibilidade material: o resultado depende da versão que o produziu."""
    md = para_markdown(montar([], versao="2.0.0"))
    assert "Blicsa 2.0.0" in md


# ── PDF (extra opcional) ────────────────────────────────────────────────────────

def test_o_pdf_sai_com_o_relatorio_completo(tmp_path, corpus):
    from core.relatorio_pdf import disponivel, gerar

    if not disponivel():
        pytest.skip("extra de PDF ausente (pip install -r requirements-pdf.txt)")
    destino = tmp_path / "relatorio.pdf"
    gerar(montar([_busca(), _ia("rotulos_de_cluster")], projeto="P", versao="2.0.0",
                 df=corpus), str(destino))
    assert destino.exists() and destino.stat().st_size > 1000


def test_o_pdf_sobrevive_a_caractere_de_marcacao_na_string_de_busca(tmp_path):
    """`ano<2020` e `A&B` são queries plausíveis, e o `Paragraph` do reportlab lê `<` e `&`
    como marcação: sem escapar, o PDF inteiro deixa de sair por causa de um caractere."""
    from core.relatorio_pdf import disponivel, gerar

    if not disponivel():
        pytest.skip("extra de PDF ausente")
    destino = tmp_path / "r.pdf"
    gerar(montar([_busca(query_interpretada='ano<2020 AND "A&B" AND x>1')],
                 projeto="P & <Q>"), str(destino))
    assert destino.exists()


def test_sem_o_extra_a_mensagem_ensina_o_comando(monkeypatch):
    """`ModuleNotFoundError: reportlab` na cara do usuário não ensina nada."""
    from core import relatorio_pdf

    monkeypatch.setattr(relatorio_pdf, "disponivel", lambda: False)
    assert "requirements-pdf.txt" in relatorio_pdf.ReportlabAusente().args[0]
