"""`core/string_de_busca.py` — achar na resposta do Blink a string de busca proposta.

O assistente de busca é instruído a terminar a análise com "uma nova string completa e
pronta para copiar e colar", e copiar e colar era o que sobrava para o usuário: selecionar
dentro de um `CTkTextbox` desabilitado, ir para a aba de Importação e colar. O botão que
faz esse caminho depende inteiramente desta extração — e os dois modos de errar têm custos
opostos: não achar tira o botão da tela, achar errado joga lixo no campo de busca e devolve
zero resultado sem o usuário entender por quê.

Os testes de UI ficam em `tests/test_layout_blink.py`; aqui é só a extração, que é onde
estão os casos difíceis e o que dá para exercitar sem abrir janela.
"""

import pytest

from core.string_de_busca import extrair_string_de_busca

STRING = '("machine learning" OR "deep learning") AND bibliometrics'


# ── Os três níveis de confiança ──────────────────────────────────────────────────

def test_bloco_cercado(caplog=None):
    resposta = f"Aqui vai a sugestão:\n\n```\n{STRING}\n```\n\nEspero ter ajudado."
    assert extrair_string_de_busca(resposta) == STRING


def test_bloco_cercado_com_linguagem_na_cerca():
    """O modelo escreve ```text e ```python o tempo todo; a cerca não é conteúdo."""
    assert extrair_string_de_busca(f"```text\n{STRING}\n```") == STRING


def test_codigo_inline():
    assert extrair_string_de_busca(f"Sugiro `{STRING}` para o seu caso.") == STRING


def test_linha_solta_sem_marcacao_nenhuma():
    assert extrair_string_de_busca(f"Nova string de busca: {STRING}") == STRING


# ── Qual candidata, quando há mais de uma ────────────────────────────────────────

def test_vale_a_ultima_e_nao_a_primeira():
    """A análise cita a string ATUAL antes de propor a nova.

    Pegar a primeira devolveria ao usuário exatamente a string que ele já tem — o botão
    apareceria, ele clicaria, e nada mudaria.
    """
    resposta = (f"Sua string atual é:\n```\n(\"data\") AND antiga\n```\n"
                f"Sugiro trocar por:\n```\n{STRING}\n```")
    assert extrair_string_de_busca(resposta) == STRING


# ── O que NÃO pode virar string de busca ─────────────────────────────────────────

def test_prosa_com_booleano_nao_e_string_de_busca():
    """"Use AND para restringir" é frase que o Blink escreve toda hora.

    Aplicá-la no campo de busca daria zero resultado, e o usuário não teria como saber
    que o culpado foi o botão.
    """
    assert extrair_string_de_busca("Use AND para restringir o escopo da sua busca.") == ""


def test_resposta_sem_string_nenhuma():
    """O Blink também responde pergunta que não é sobre busca: o botão não deve aparecer."""
    assert extrair_string_de_busca("Os clusters temáticos indicam três frentes.") == ""


def test_resposta_inteira_nao_passa_por_string():
    """Teto de tamanho: sem ele, um parágrafo com aspas e AND viraria candidata."""
    enorme = '("a" OR "b") AND ' + "palavra " * 500
    assert extrair_string_de_busca(enorme) == ""


# ── Adversarial: nada pode levantar ──────────────────────────────────────────────

@pytest.mark.parametrize("resposta", [
    "", "   ", "\n\n", None, "```", "```\n", "``` ```", "`", "()", '""',
    "AND", "AND OR NOT", "a" * 5000, "\x00", "🌍 AND (\"emoji\")",
])
def test_entrada_adversarial_nao_levanta(resposta):
    """A resposta vem de um modelo: pode vir truncada em qualquer ponto."""
    assert isinstance(extrair_string_de_busca(resposta), str)


def test_bloco_sem_fechamento_ainda_entrega_a_string():
    """Resposta cortada pelo limite de tokens deixa a cerca aberta.

    É justamente o caso em que a string está no fim e o usuário mais quer o botão.
    """
    assert extrair_string_de_busca(f"Segue:\n```\n{STRING}") == STRING


def test_bloco_de_varias_linhas_vira_uma_string():
    """O modelo quebra string longa em várias linhas; o campo de busca é de uma linha só."""
    quebrada = '("machine learning"\nOR "deep learning")\nAND bibliometrics'
    assert extrair_string_de_busca(f"```\n{quebrada}\n```") == STRING


def test_rotulo_nao_entra_na_string():
    """"Nova string: (...)" — o rótulo no campo de busca daria zero resultado."""
    assert extrair_string_de_busca(f"```\nNova string: {STRING}\n```") == STRING
