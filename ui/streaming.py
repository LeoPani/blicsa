"""A resposta do Blink aparecendo na tela enquanto o modelo escreve.

O jeito antigo era, **a cada pedaço recebido**, `after(0, ...)` com `delete("1.0", "end")` +
`insert_markdown(texto_inteiro)` + remedida de altura + rolagem. Três consequências, todas
visíveis:

1. **Pisca.** Apagar e reescrever o balão inteiro sessenta vezes por resposta é sessenta
   apagões. O texto sumia e voltava, e a altura pulava a cada vez que um cabeçalho ou uma
   tabela entrava — o "modo como a IA escreve" que o usuário reclamou.
2. **Trava o aplicativo.** Um `after(0, ...)` por token enfileira centenas de callbacks, e
   cada um chama `update_idletasks` duas vezes (uma para medir a altura, outra para medir a
   região de rolagem). O laço de eventos do Tk fica saturado: a janela para de responder,
   e no macOS uma janela que não responde não devolve o foco. Era por isso que não dava
   para voltar para outra janela enquanto o Blink escrevia.
3. **É quadrático.** Reparsar `n` caracteres a cada um dos `n` tokens; numa resposta longa,
   a última metade chega visivelmente mais devagar que a primeira.

Aqui o desenho é outro: o worker só **acumula** (barato, sem Tk), e um único temporizador
repinta em cadência fixa, **acrescentando** ao que já está desenhado em vez de refazer
tudo. Um `after` no total, não um por token.

O que já foi desenhado nunca é tocado de novo, e o que ainda pode mudar — a linha que o
modelo está escrevendo, uma tabela pela metade, um bloco de código sem a cerca de
fechamento — fica numa "cauda" provisória, redesenhada como texto simples até virar
definitiva. É o que dá o efeito de máquina de escrever sem o piscar.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

log = logging.getLogger("blicsa")

#: Cadência do repinte. 70ms ≈ 14 quadros por segundo: rápido o bastante para ler como
#: texto sendo escrito, espaçado o bastante para o laço de eventos do Tk atender clique,
#: rolagem e troca de janela entre um quadro e outro. O valor antigo, na prática, era zero.
INTERVALO_MS = 70

#: Distância do fim (em fração da barra de rolagem) dentro da qual a conversa ainda é
#: considerada "no fim". Quem rolou para cima para reler algo não é arrastado de volta.
MARGEM_DE_FIM = 0.02


def _fronteira_estavel(texto: str) -> int:
    """Até onde o texto já pode ser desenhado com Markdown **em definitivo**.

    O parser é por linha, com dois blocos que só se leem inteiros: a tabela (a largura das
    colunas depende de TODAS as linhas) e o bloco cercado por ``` (o que está dentro sai
    literal). Desenhar qualquer um deles pela metade e depois acrescentar o resto sairia
    torto — colunas de larguras diferentes na mesma tabela, meia linha fora do bloco.

    Devolve o índice do primeiro caractere que ainda NÃO é definitivo.
    """
    corte = texto.rfind("\n") + 1
    if corte <= 0:
        # Nem uma linha completa ainda: tudo é provisório.
        return 0

    prefixo = texto[:corte]

    # Cerca ímpar = bloco de código aberto. Recua para antes da cerca que o abriu.
    if prefixo.count("```") % 2:
        abertura = prefixo.rfind("```")
        corte = min(corte, prefixo.rfind("\n", 0, abertura) + 1)
        prefixo = texto[:corte]

    # Tabela encostada no fim do prefixo: pode ainda ganhar linhas no próximo pedaço.
    linhas = prefixo.split("\n")
    if linhas and linhas[-1] == "":
        linhas.pop()
    i = len(linhas)
    while i > 0 and _e_linha_de_tabela(linhas[i - 1]):
        i -= 1
    if i < len(linhas):
        corte = len("\n".join(linhas[:i]))
        corte = corte + 1 if corte else 0

    return max(corte, 0)


def _e_linha_de_tabela(linha: str) -> bool:
    """Mesma regra de `core.markdown_parser`, repetida para não importar Tk aqui."""
    t = linha.strip()
    return t.startswith("|") and t.count("|") >= 2


class FluxoDeResposta:
    """Um balão do Blink sendo preenchido enquanto o modelo responde.

    Uso, do lado do worker (thread de rede):

        fluxo = FluxoDeResposta(app, abrir_balao, inserir_markdown, rolar)
        for pedaco in stream:
            fluxo.escrever(pedaco)
        fluxo.concluir()

    `escrever` e `concluir` são as ÚNICAS entradas chamadas de fora da thread da interface,
    e as duas só encostam no buffer, sob trava. Todo Tk acontece no temporizador, que roda
    na thread da interface — a regra que o laço antigo respeitava por acidente (via
    `after(0, ...)`) e que aqui é estrutural.
    """

    def __init__(self, app, abrir_balao: Callable, inserir_markdown: Callable,
                 rolar: Optional[Callable] = None, no_fim: Optional[Callable] = None,
                 intervalo_ms: int = INTERVALO_MS):
        self._app = app
        self._abrir_balao = abrir_balao
        self._inserir_markdown = inserir_markdown
        self._rolar = rolar
        #: Medido ANTES de escrever, nunca depois: escrever empurra o fim para baixo e a
        #: conversa deixa de estar "no fim" no instante seguinte à inserção. Perguntar
        #: depois responderia sempre "não" e a rolagem nunca acompanharia.
        self._no_fim = no_fim
        self._intervalo = intervalo_ms

        self._trava = threading.Lock()
        self._buffer: List[str] = []
        self._encerrado = False

        self._caixa = None
        self._remedir = None
        self._desenhado = 0          # caracteres já escritos em definitivo
        self._fim_estavel = "1.0"    # índice Tk onde a cauda provisória começa
        self._agendado = False
        self._cancelado = False
        self._ultimo_tamanho = -1    # -1 e não 0: o primeiro quadro sempre desenha
        self._finalizado = False

    # ── Chamado da thread do worker ─────────────────────────────────────────────

    @property
    def texto(self) -> str:
        """Tudo que chegou até agora. Seguro de ler de qualquer thread."""
        with self._trava:
            return "".join(self._buffer)

    def escrever(self, pedaco: str):
        """Acumula um pedaço e garante que o temporizador está de pé. Não desenha nada."""
        if not pedaco:
            return
        with self._trava:
            self._buffer.append(pedaco)
        self._garantir_temporizador()

    def concluir(self):
        """Fim do stream: um último repinte, agora com a cauda virando definitiva."""
        self._encerrado = True
        self._garantir_temporizador()

    def cancelar(self):
        """Desiste do repinte — a tela em que o balão vivia não existe mais."""
        self._cancelado = True

    # ── Só na thread da interface, daqui para baixo ─────────────────────────────

    def _garantir_temporizador(self):
        if self._agendado or self._cancelado:
            return
        self._agendado = True
        try:
            self._app.after(0, self._quadro)
        except Exception:
            # App fechando: `after` numa raiz destruída levanta TclError, e não há tela
            # onde desenhar de qualquer forma.
            self._agendado = False
            self._cancelado = True

    def _quadro(self):
        self._agendado = False
        if self._cancelado:
            return

        texto = self.texto
        terminou = self._encerrado

        # Modelo que engasga, rede que segura o pacote: entre um pedaço e outro passam
        # quadros com NADA de novo. Redesenhar mesmo assim seria voltar a apagar e reinserir
        # a cauda quatorze vezes por segundo sem que o texto tenha mudado — de graça, e no
        # laço de eventos que a correção existe para desafogar.
        if len(texto) != self._ultimo_tamanho or (terminou and not self._finalizado):
            try:
                self._desenhar(texto, definitivo=terminou)
            except Exception as ex:
                # Balão destruído no meio do stream (troca de idioma reconstrói a tela
                # inteira): o worker continua, mas não há mais onde escrever. Desistir em
                # SILÊNCIO seria transformar qualquer erro de desenho em "a resposta parou
                # no meio" sem rastro — o registro é o que separa a tela que sumiu de um
                # defeito aqui dentro.
                log.info("[Blink] desenho do fluxo interrompido: %s: %s",
                         type(ex).__name__, ex)
                self._cancelado = True
                return
            self._ultimo_tamanho = len(texto)
            self._finalizado = terminou

        # `len(self.texto)` relido: um pedaço pode ter chegado DURANTE o desenho, e sair
        # agora deixaria o fim da resposta fora da tela para sempre.
        if terminou and len(texto) == len(self.texto):
            return
        self._agendado = True
        try:
            self._app.after(self._intervalo, self._quadro)
        except Exception:
            self._agendado = False
            self._cancelado = True

    def _desenhar(self, texto: str, definitivo: bool):
        if not texto and not definitivo:
            return
        if self._caixa is None:
            self._caixa, self._remedir = self._abrir_balao()
            if self._caixa is None:
                self._cancelado = True
                return

        # `_fronteira_estavel` só cresce (o texto só cresce, e o recuo por bloco aberto
        # nunca passa do que já era definitivo), então `max` aqui é cinto e suspensório:
        # desenhar duas vezes o mesmo trecho duplicaria texto na tela.
        corte = max(self._desenhado,
                    len(texto) if definitivo else _fronteira_estavel(texto))

        acompanhar = True
        if self._no_fim is not None:
            try:
                acompanhar = bool(self._no_fim())
            except Exception:
                acompanhar = True

        caixa = self._caixa
        caixa.configure(state="normal")

        # A cauda provisória some inteira: ela é o único trecho que pode mudar.
        #
        # **`"end-1c"`, nunca `"end"`.** Um `Text` do Tk mantém uma quebra de linha final
        # obrigatória, e `"end"` fica DEPOIS dela: apagar até ali come essa quebra, o
        # conteúdo sobe uma linha e o índice guardado passa a apontar para outro lugar.
        # Medido: com `"end"` a cauda não era apagada e saía duplicada na tela
        # ("Três frentes Três frentes aparecem no corpus"); com `"end-1c"` a ida e volta é
        # exata. Foi o teste contra um `CTkTextbox` de verdade que pegou — o duble de
        # `tests/test_streaming_blink.py` não tem quebra obrigatória e passava dos dois
        # jeitos.
        caixa.delete(self._fim_estavel, "end-1c")

        if corte > self._desenhado:
            self._inserir_markdown(caixa, texto[self._desenhado:corte])
            self._desenhado = corte
            self._fim_estavel = caixa.index("end-1c")

        cauda = texto[self._desenhado:]
        if cauda:
            # Sem Markdown de propósito: a linha em construção ainda pode virar título,
            # item de lista ou negrito quando o próximo pedaço chegar, e formatá-la duas
            # vezes com resultados diferentes é justamente o piscar que se quer evitar.
            caixa.insert("end-1c", cauda)

        caixa.configure(state="disabled")

        if self._remedir is not None:
            self._remedir()
        if self._rolar is not None and acompanhar:
            self._rolar()


def perto_do_fim(canvas, margem: float = MARGEM_DE_FIM) -> bool:
    """A conversa está no fim (ou quase)? Quem rolou para cima fica onde está.

    Rolar à força enquanto a pessoa relê um trecho acima é arrancar a leitura dela da tela a
    cada 70ms — pior do que a rolagem não acompanhar.
    """
    try:
        _, fim = canvas.yview()
        return fim >= 1.0 - margem
    except Exception:
        return True
