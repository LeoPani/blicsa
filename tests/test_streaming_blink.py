"""`ui/streaming.py` — a resposta do Blink aparecendo na tela sem piscar e sem travar.

O laço antigo fazia, **por token recebido**, um `after(0, ...)` que apagava o balão inteiro
(`delete("1.0", "end")`), reparsava o Markdown do texto todo, remedia a altura e rolava a
conversa. Três defeitos de uma vez: pisca, é quadrático, e satura o laço de eventos do Tk a
ponto de a janela parar de responder — que é por que não dava para voltar para outra janela
enquanto o Blink escrevia.

Os três têm testes aqui, e são testes de PROPRIEDADE, não de aparência: quantos `after` o
fluxo agenda, se algum trecho já desenhado é reescrito, e onde ele deixa a fronteira entre o
definitivo e o provisório. Aparência não dá para afirmar num teste; estas três dão, e são as
causas do que se via na tela.
"""

import pytest

from ui.streaming import _fronteira_estavel


# ── Onde termina o que já pode ser desenhado em definitivo ──────────────────────

def test_sem_linha_completa_nada_e_definitivo():
    """O primeiro pedaço quase nunca traz uma quebra de linha."""
    assert _fronteira_estavel("Uma respos") == 0


def test_a_linha_em_construcao_fica_de_fora():
    """Ela ainda pode virar título, item de lista ou negrito no próximo pedaço.

    Formatá-la agora e reformatá-la depois é exatamente o piscar que se quer evitar.
    """
    texto = "Primeira linha inteira.\nsegunda pela met"
    assert _fronteira_estavel(texto) == len("Primeira linha inteira.\n")


def test_bloco_de_codigo_aberto_recua_a_fronteira():
    """Dentro da cerca nada é interpretado — meia cerca desenharia o conteúdo como prosa.

    E é justamente dentro da cerca que vem a string de busca proposta.
    """
    texto = 'Segue a string:\n```\n("machine learning" OR x)\n'
    assert _fronteira_estavel(texto) == len("Segue a string:\n")


def test_bloco_de_codigo_fechado_libera_tudo():
    texto = 'Segue:\n```\n("machine learning")\n```\n'
    assert _fronteira_estavel(texto) == len(texto)


def test_tabela_encostada_no_fim_espera_as_linhas_que_faltam():
    """A largura das colunas só se conhece depois de ver TODAS as linhas.

    Desenhar metade e acrescentar o resto sairia com duas larguras na mesma tabela — e
    tabela é o formato em que o modelo devolve comparação de métricas, então sai muito.
    """
    texto = "Comparação:\n| base | total |\n| --- | --- |\n"
    assert _fronteira_estavel(texto) == len("Comparação:\n")


def test_tabela_seguida_de_prosa_ja_e_definitiva():
    texto = "| a | b |\n| --- | --- |\n| 1 | 2 |\n\nFim da tabela.\n"
    assert _fronteira_estavel(texto) == len(texto)


def test_a_fronteira_nunca_anda_para_tras():
    """Se andasse, o desenho já feito teria de ser apagado — o piscar de volta.

    Percorre um texto realista caractere a caractere, como o stream de fato chega.
    """
    texto = ("# Análise\n\nTrês frentes:\n\n- primeira\n- segunda\n\n"
             "| base | total |\n| --- | --- |\n| OpenAlex | 4722 |\n\n"
             'Segue a string:\n\n```\n("machine learning" OR "deep learning") AND x\n```\n')
    anterior = 0
    for i in range(len(texto) + 1):
        atual = _fronteira_estavel(texto[:i])
        assert atual >= anterior, f"a fronteira recuou em {i}: {anterior} → {atual}"
        anterior = atual


# ── O fluxo: um temporizador, não um por token ──────────────────────────────────

class _AppFalso:
    """Um `after` que enfileira em vez de executar, para o teste controlar os quadros.

    Executar na hora faria o fluxo se reagendar dentro de si mesmo até estourar a pilha —
    e esconderia justamente o que se quer medir, que é QUANTAS vezes ele agenda.
    """

    def __init__(self):
        self.fila = []
        self.agendamentos = 0

    def after(self, _ms, cb):
        self.agendamentos += 1
        self.fila.append(cb)

    def quadro(self):
        """Roda um quadro pendente. Devolve False quando não havia nenhum."""
        if not self.fila:
            return False
        self.fila.pop(0)()
        return True

    def rodar_ate_parar(self, limite=200):
        n = 0
        while self.quadro() and n < limite:
            n += 1
        return n


class _CaixaFalsa:
    """O mínimo de `CTkTextbox` que o fluxo usa, guardando o que foi escrito e apagado.

    O que este duble **não** modela: a quebra de linha final obrigatória do `Text` do Tk, e
    o efeito dela nos índices. Foi exatamente ali que o desenho incremental errou de
    primeira — `delete(marca, "end")` comia essa quebra, o conteúdo subia uma linha e a
    cauda saía DUPLICADA na tela —, e aqui passava dos dois jeitos. Emular a regra num duble
    seria emular também o defeito; quem guarda essa parte é
    `tests/test_layout_blink.py::test_o_streaming_monta_a_resposta_inteira_no_balao`, contra
    um `CTkTextbox` de verdade.

    O que ele modela é o resto: os índices são os do Tk (`"1.0"` é o começo, e
    `index("end-1c")` devolve string), porque trocá-los por inteiros esconderia a mesma
    família de erro num lugar diferente.
    """

    def __init__(self):
        self.texto = ""
        self.apagados = 0
        self.inserido_em_markdown = []

    def configure(self, **_kw):
        pass

    @staticmethod
    def _pos(indice):
        return 0 if indice == "1.0" else int(indice)

    def index(self, _onde):
        return str(len(self.texto))

    def delete(self, inicio, _fim):
        corte = self._pos(inicio)
        if len(self.texto) > corte:
            self.apagados += 1
        self.texto = self.texto[:corte]

    def insert(self, _onde, texto, *_a, **_kw):
        self.texto += texto


@pytest.fixture
def fluxo():
    from ui.streaming import FluxoDeResposta

    app = _AppFalso()
    caixa = _CaixaFalsa()

    def abrir():
        return caixa, lambda: None

    def markdown(cx, trecho):
        cx.inserido_em_markdown.append(trecho)
        cx.insert("end", trecho)

    f = FluxoDeResposta(app, abrir, markdown, intervalo_ms=0)
    return f, app, caixa


def test_cem_tokens_nao_viram_cem_agendamentos(fluxo):
    """Era um `after(0, ...)` por token: centenas de callbacks na fila do Tk, cada um com
    dois `update_idletasks`. O laço de eventos saturava e a janela parava de responder.

    Aqui o worker só acumula; quem agenda é o temporizador, um de cada vez.
    """
    f, app, _ = fluxo
    for i in range(100):
        f.escrever(f"palavra{i} ")
    assert app.agendamentos == 1, "voltou a agendar um quadro por token"


def test_o_texto_completo_chega_inteiro_a_tela(fluxo):
    f, app, caixa = fluxo
    for pedaco in ("# Título\n", "corpo da ", "resposta\n", "fim"):
        f.escrever(pedaco)
        app.rodar_ate_parar()
    f.concluir()
    app.rodar_ate_parar()

    assert caixa.texto == "# Título\ncorpo da resposta\nfim"


def test_trecho_ja_definitivo_nao_e_reparsado(fluxo):
    """O reparse do texto INTEIRO a cada pedaço é o que fazia a resposta longa chegar cada
    vez mais devagar — n tokens reparsando n caracteres.

    Cada trecho entra no Markdown uma vez só, e emendado dá o texto original.
    """
    f, app, caixa = fluxo
    texto = "# Título\n\nprimeiro parágrafo\n\nsegundo parágrafo\n"
    for ch in texto:
        f.escrever(ch)
        app.rodar_ate_parar()
    f.concluir()
    app.rodar_ate_parar()

    assert "".join(caixa.inserido_em_markdown) == texto
    assert len(caixa.inserido_em_markdown) < len(texto), "reparsou por caractere"


def test_concluir_desenha_a_cauda_que_ficou_sem_quebra_de_linha(fluxo):
    """O modelo termina sem `\\n` com frequência. Sem este passo a última linha ficaria
    para sempre como texto simples, sem o negrito e sem o bloco de código."""
    f, app, caixa = fluxo
    f.escrever("uma linha só, sem quebra no fim")
    app.rodar_ate_parar()
    assert caixa.inserido_em_markdown == []

    f.concluir()
    app.rodar_ate_parar()
    assert caixa.inserido_em_markdown == ["uma linha só, sem quebra no fim"]


def test_o_fluxo_para_de_agendar_quando_acaba(fluxo):
    """Um temporizador que se reagenda sozinho para sempre é um vazamento por resposta."""
    f, app, _ = fluxo
    f.escrever("resposta\n")
    f.concluir()
    app.rodar_ate_parar()

    assert app.fila == []


def test_balao_destruido_no_meio_nao_derruba_o_worker(fluxo):
    """Trocar de idioma reconstrói a tela inteira, e o stream continua chegando.

    O worker é uma thread de rede: uma exceção dentro do quadro mataria o `for chunk in
    stream` e deixaria a resposta pela metade no histórico da conversa.
    """
    f, app, caixa = fluxo

    def explodir(*_a, **_kw):
        raise RuntimeError("invalid command name .!ctktextbox")

    caixa.insert = explodir
    f.escrever("texto\n")
    app.rodar_ate_parar()

    f.escrever("mais texto\n")
    f.concluir()
    assert app.fila == [], "seguiu agendando quadros sobre um balão morto"
