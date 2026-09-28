"""`core/strings_por_base.py` — a string do Blink traduzida para cada uma das três bases.

O defeito que estes testes guardam é o "a string sugerida costuma não dar resultado": uma
string só, mandada igual para as três, e cada uma quebrando de um jeito. Os números nos
docstrings foram medidos contra as APIs reais, com
`("machine learning" OR "deep learning") AND bibliometric` como referência (83.693 obras no
OpenAlex).

Aqui não há Tk nem rede: a tradução é determinística, e é onde estão os casos difíceis. Os
testes de tela ficam em `tests/test_layout_blink.py`.
"""

import pytest

from core.strings_por_base import (BASES, adaptar, normalizar, traduzir)

CANONICA = '("machine learning" OR "deep learning") AND bibliometric'


def _para(bruto, base):
    return adaptar(bruto, base).string


def _notas(bruto, base):
    return adaptar(bruto, base).notas


# ── O que quebra CADA base ──────────────────────────────────────────────────────

def test_curinga_sai_no_openalex_porque_a_busca_inteira_falha():
    """`bibliometric*` no `filter=default.search:` devolve **HTTP 400**, não "poucos".

    É a diferença que importa: uma string ruim devolve resultado ruim, e esta não devolve
    resultado nenhum. Sem o `*`, o mesmo tema mediu 4.722 obras.
    """
    saida = _para('(bibliometric* OR scientometric*) AND "machine learning"', "openalex")
    assert "*" not in saida
    assert "curinga_removido" in _notas('bibliometric*', "openalex")


def test_curinga_fica_no_pubmed_que_e_a_unica_das_tres_que_o_entende():
    assert "*" in _para('(bibliometric* OR scientometric*) AND ml', "pubmed")


def test_virgula_sai_do_openalex_porque_e_o_separador_de_filtros_da_api():
    """`filter=default.search:machine learning, deep learning` = HTTP 400.

    A vírgula não é escolha de estilo: o provider monta a busca DENTRO do parâmetro
    `filter=`, e é lá que a vírgula separa um filtro do próximo.
    """
    assert "," not in _para("machine learning, deep learning", "openalex")
    assert "virgula_removida" in _notas("a, b", "openalex")


def test_sintaxe_de_scopus_sai_das_tres_preservando_os_termos():
    """`TITLE-ABS-KEY(...)` derrubou o PubMed de 1.310 registros para **1**.

    O E-utilities procura "TITLE-ABS-KEY" como se fosse palavra do texto. Apagar até o `)`
    levaria junto os termos, que é justamente o que interessa — por isso o envoltório sai e
    o conteúdo fica.
    """
    for base in BASES:
        saida = _para('TITLE-ABS-KEY("machine learning" AND bibliometric)', base)
        assert "TITLE-ABS-KEY" not in saida
        assert "machine learning" in saida
        assert "bibliometric" in saida


def test_sintaxe_de_web_of_science_tambem_sai():
    assert "TS=" not in _para('TS=("machine learning" AND bibliometrics)', "openalex")


def test_marcador_de_campo_sai_do_openalex_e_fica_no_pubmed():
    """`"machine learning"[tiab]` derrubou o OpenAlex de 83.693 para 72; no PubMed é válido."""
    assert "[tiab]" not in _para('"machine learning"[tiab] AND bibliometrics', "openalex")
    assert "[tiab]" in _para('"machine learning"[tiab] AND bibliometrics', "pubmed")


# ── O Crossref, que não tem booleano ────────────────────────────────────────────

def test_crossref_recebe_termos_porque_a_api_apaga_os_operadores():
    """Não é simplificação nossa: `CrossrefProvider` apaga AND/OR/NOT e os parênteses.

    E as aspas a própria Crossref ignora — medido, com e sem aspas dá o mesmo total e os
    mesmos três primeiros resultados.
    """
    saida = _para(CANONICA, "crossref")
    assert "AND" not in saida and "OR" not in saida
    assert "(" not in saida and '"' not in saida
    assert "machine learning" in saida and "bibliometric" in saida


def test_crossref_descarta_o_ramo_negado_em_vez_de_procurar_por_ele():
    """Com o `NOT` apagado pela API, `NOT review` viraria "procure por review".

    Medido: a string bruta com `NOT (review OR editorial)` devolvia em PRIMEIRO lugar "A
    Scientometric **Review** of Machine Learning...". A negação é a única parte da string
    cujo sentido se inverte ao ser achatada — descartar é a leitura fiel.
    """
    saida = _para(f'{CANONICA} NOT (review OR editorial)', "crossref")
    assert "review" not in saida.lower()
    assert "editorial" not in saida.lower()
    assert "machine learning" in saida
    assert "negacao_descartada" in _notas(f"{CANONICA} NOT review", "crossref")


def test_crossref_nao_repete_termo_que_aparece_duas_vezes():
    saida = _para('("big data" OR "big data") AND "big data"', "crossref")
    assert saida.lower().count("big data") == 1


def test_crossref_corta_a_lista_longa_de_termos():
    """Sem booleano, cada palavra a mais só dilui o ranking."""
    bruta = " OR ".join(f"termo{i}" for i in range(30))
    adaptacao = adaptar(bruta, "crossref")
    assert len(adaptacao.string.split()) == 12
    assert "termos_cortados" in adaptacao.notas


# ── Higiene comum às três ───────────────────────────────────────────────────────

def test_booleano_em_minuscula_sobe_para_maiuscula():
    """Em minúscula não é operador: vira palavra, e o mesmo tema caiu de 83.693 p/ 31.823."""
    assert _para('("a" or "b") and c', "openalex") == '("a" OR "b") AND c'


def test_booleano_dentro_de_aspas_nao_e_operador_e_nao_sobe():
    """`"drug and alcohol"` é o nome do que se procura, não uma conjunção."""
    assert '"drug and alcohol"' in _para('"drug and alcohol" AND policy', "openalex")


def test_virgula_dentro_de_aspas_no_openalex():
    """Mesmo dentro de aspas a vírgula quebra o `filter=` — mas o aviso tem de aparecer."""
    adaptacao = adaptar('"Rio de Janeiro, Brazil" AND dengue', "openalex")
    assert "," not in adaptacao.string
    assert "virgula_removida" in adaptacao.notas


def test_aspas_tortas_viram_retas():
    assert _para('(“machine learning” OR “deep learning”) AND x', "openalex") == \
        '("machine learning" OR "deep learning") AND x'


def test_parentese_sem_par_sai():
    """Resposta cortada pelo limite de tokens produz isso, e um `(` sobrando é 400."""
    adaptacao = adaptar('((a OR b) AND (c OR d)', "openalex")
    assert adaptacao.string.count("(") == adaptacao.string.count(")")
    assert "parenteses_equilibrados" in adaptacao.notas


def test_aspa_aberta_e_nunca_fechada_e_fechada():
    assert normalizar('"machine learning AND x')[0].count('"') % 2 == 0


def test_operador_pendurado_no_fim_sai():
    """`"machine learning" AND` mediu 3.633.511 — não dá erro, descarta a restrição em silêncio."""
    adaptacao = adaptar('"machine learning" AND', "openalex")
    assert adaptacao.string == '"machine learning"'
    assert "operador_solto" in adaptacao.notas


def test_operador_grudado_no_parentese_sai():
    assert _para('(AND "machine learning") AND x', "openalex") == '("machine learning") AND x'


def test_parenteses_ficam_porque_mudam_a_conta():
    """Sem eles a precedência muda: o mesmo tema pulou de 83.693 para 898.824."""
    assert _para(CANONICA, "openalex") == CANONICA


# ── Contrato do módulo ──────────────────────────────────────────────────────────

def test_traduzir_devolve_as_tres_na_ordem_do_seletor():
    assert [a.base for a in traduzir(CANONICA)] == list(BASES)


def test_string_vazia_nao_gera_adaptacao_nenhuma():
    """O Blink também responde pergunta que não é sobre busca."""
    assert traduzir("") == []
    assert traduzir("   ") == []


def test_string_limpa_atravessa_sem_nota_nenhuma():
    """Nota é aviso de conserto: string boa não pode carregar aviso."""
    for base in ("openalex", "pubmed"):
        assert adaptar(CANONICA, base).notas == []


@pytest.mark.parametrize("base", BASES)
def test_nenhuma_base_recebe_quebra_de_linha(base):
    """A string vai para um `CTkEntry` de uma linha, e daí para uma URL."""
    assert "\n" not in _para('("a" OR\n "b") AND c', base)
