"""`core/uso_de_ia.py` — o registro de cada chamada de IA que a pesquisa fez.

O defeito de partida: o app tinha onze pontos chamando o modelo e **nenhum** gravava nada.
O único contador que existia, `blink_usage`, era incrementado dentro de `_legacy_diary`, que
só roda quando o usuário faz uma BUSCA — contava buscas e chamava de uso do Blink. Quem
fosse declarar o uso de IA no artigo teria de reconstruir tudo de memória.

O que estes testes guardam não é a contagem: é a **classificação**. A declaração que vai
para a revista precisa dizer se a saída do modelo entrou no resultado (os rótulos de cluster
vão para a figura publicada) ou se ela só aconselhou, e essas duas coisas não podem se
confundir.
"""

import pytest

from core.uso_de_ia import (ACAO, ACONSELHA, DESCREVE, INTERPRETA, PONTOS, evento,
                            eventos_de_ia, houve_interpretacao, natureza,
                            provedor_do_endereco, resumir)


def _linha(ponto, modelo="m", provedor="Groq", uso=None, erro="", ts="2026-01-01T10:00:00"):
    return {"ts": ts, "action": ACAO,
            "detail": evento(ponto, modelo, provedor, uso=uso, erro=erro)}


def _uso(entrada, saida):
    return {"prompt_tokens": entrada, "completion_tokens": saida,
            "total_tokens": entrada + saida}


# ── A classificação, que é o ponto do módulo ────────────────────────────────────

def test_rotulo_de_cluster_e_o_unico_que_entra_no_resultado():
    """E é por isso que ele é o mais grave: o nome vai para a figura que o artigo publica.

    Quem lê o artigo vê um rótulo temático sem saber que quem o escreveu foi um modelo de
    linguagem. Nenhum outro ponto tem essa propriedade hoje.
    """
    assert natureza("rotulos_de_cluster") == INTERPRETA
    assert [p for p, n in PONTOS.items() if n == INTERPRETA] == ["rotulos_de_cluster"]


def test_o_chat_apenas_aconselha():
    """Não entra no resultado — mas entra na cadeia de decisão, e por isso é registrado."""
    assert natureza("blink_chat") == ACONSELHA
    assert natureza("assistente_de_busca") == ACONSELHA


def test_ponto_desconhecido_e_registrado_em_vez_de_perdido():
    """Perder o registro é pior do que errar a classificação.

    Um ponto de IA novo que ninguém lembrou de cadastrar tem de aparecer no relatório assim
    mesmo; o teste estrutural abaixo é que cobra o cadastro.
    """
    assert natureza("ponto_que_ainda_nao_existe") == DESCREVE
    assert resumir([_linha("ponto_que_ainda_nao_existe")])["chamadas"] == 1


def test_houve_interpretacao_separa_os_dois_tipos_de_declaracao():
    """Um artigo com rótulos escritos por IA declara uma coisa; um sem, outra."""
    assert not houve_interpretacao([_linha("blink_chat"), _linha("insights_do_corpus")])
    assert houve_interpretacao([_linha("blink_chat"), _linha("rotulos_de_cluster")])


# ── Tokens: ausência não é zero ─────────────────────────────────────────────────

def test_chamada_sem_medida_nao_conta_como_zero():
    """Provedor que não conta, chamada cortada e resposta sem o campo caem todos aqui.

    Somar como zero faria o relatório afirmar um consumo que ninguém mediu — e um total de
    1.000 tokens em 30 chamadas das quais 29 não mediram nada pareceria o consumo da
    pesquisa inteira.
    """
    r = resumir([_linha("blink_chat", uso=_uso(100, 50)),
                 _linha("blink_chat"),
                 _linha("blink_chat")])
    assert r["tokens"]["total"] == 150
    assert r["sem_medida"] == 2
    assert r["chamadas"] == 3


def test_consumo_separado_por_modelo():
    """A pesquisa pode trocar de modelo no meio; a declaração nomeia os dois."""
    r = resumir([_linha("blink_chat", modelo="a", uso=_uso(10, 5)),
                 _linha("blink_chat", modelo="b", uso=_uso(20, 10))])
    assert r["por_modelo"]["a"]["total"] == 15
    assert r["por_modelo"]["b"]["total"] == 30
    assert r["tokens"]["total"] == 45


def test_evento_sem_medida_nao_carrega_chave_de_tokens():
    """Gravar `tokens: {0,0,0}` faria o backlog registrar uma medida que não houve."""
    assert "tokens" not in evento("blink_chat", "m", "Groq")
    assert "tokens" in evento("blink_chat", "m", "Groq", uso=_uso(1, 1))


# ── Falhas ──────────────────────────────────────────────────────────────────────

def test_a_chamada_que_falhou_tambem_e_uso_de_ia():
    """Ela entrou na cadeia de decisão da pesquisa e some se só o sucesso for gravado."""
    r = resumir([_linha("blink_chat"), _linha("blink_chat", erro="429 rate limit")])
    assert r["chamadas"] == 2
    assert r["falhas"] == 1


def test_a_mensagem_de_erro_e_truncada():
    """Um traceback inteiro no backlog engorda um arquivo que é lido a cada relatório."""
    assert len(evento("blink_chat", "m", "Groq", erro="x" * 5000)["erro"]) <= 300


# ── Provedor ────────────────────────────────────────────────────────────────────

def test_o_provedor_vem_do_ENDERECO_e_nao_do_nome_do_modelo():
    """`openai/gpt-oss-120b` roda no Groq. Declarar "OpenAI" por causa do prefixo do nome
    seria dizer errado à revista quem processou os dados."""
    assert provedor_do_endereco("https://api.groq.com/openai/v1") == "Groq"


@pytest.mark.parametrize("url,esperado", [
    ("https://api.openai.com/v1", "OpenAI"),
    ("http://localhost:11434/v1", "local"),
    ("https://openrouter.ai/api/v1", "OpenRouter"),
    ("", ""),
])
def test_provedores_conhecidos(url, esperado):
    assert provedor_do_endereco(url) == esperado


def test_endereco_desconhecido_devolve_o_host_e_nao_uma_incognita():
    """Num relatório de método o host É a informação — quem lê sabe reconhecê-lo."""
    assert provedor_do_endereco("https://api.exemplo.com.br/v1") == "api.exemplo.com.br"


# ── Convivência com o backlog que já existia ────────────────────────────────────

def test_so_as_linhas_de_ia_sao_lidas():
    """O backlog é compartilhado com busca, importação, dedup, análise e exportação."""
    backlog = [{"action": "search", "detail": {}}, _linha("blink_chat"),
               {"action": "import", "detail": {}}]
    assert len(eventos_de_ia(backlog)) == 1
    assert resumir(backlog)["chamadas"] == 1


def test_backlog_vazio_nao_levanta():
    r = resumir([])
    assert r["chamadas"] == 0 and r["tokens"]["total"] == 0 and r["provedores"] == []


# ── Guarda estrutural ───────────────────────────────────────────────────────────

def test_todo_ponto_cadastrado_aparece_no_app():
    """O cadastro e o código não podem divergir em nenhuma das duas direções.

    Ponto no cadastro sem chamador é entrada morta que polui o relatório; chamador sem
    cadastro é chamada classificada por omissão. As duas se pegam aqui.
    """
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    faltando = [p for p in PONTOS if f'"{p}"' not in fonte]
    assert not faltando, f"pontos cadastrados que ninguém chama: {faltando}"


def test_nenhum_ponto_constroi_o_analista_por_fora_do_registro():
    """`AIAnalyst(...)` na mão é uma chamada de IA que não vai para o relatório.

    Era assim nos onze pontos, e é o defeito que este módulo existe para fechar. O caminho
    único é `_uso_de_ia`, que grava no `finally` — inclusive quando a chamada estoura.
    """
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    assert "AIAnalyst(api_key" not in fonte, (
        "algum ponto voltou a construir o analista direto, sem passar pelo registro de uso")
