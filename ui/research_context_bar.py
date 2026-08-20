"""Campo do contexto de pesquisa do projeto, com exemplo e indicador de "está ativo".

**Não usa amarelo.** O amarelo do design system significa "isto foi gerado por IA" (ver
`docs/inventario-ia.md`), e este campo é o oposto: é o que o **usuário** escreveu. Marcá-lo de
amarelo diria à pessoa que uma máquina redigiu o enquadramento da própria pesquisa dela. O
indicador é azul — o token de estado da aplicação.

Duas decisões que parecem detalhe e não são:

1. **O exemplo é placeholder, não valor inicial.** Um exemplo pré-preenchido de verdade seria
   enviado ao modelo por quem não reparasse nele, e o Blink passaria a responder sobre
   cooperativas de catadores para alguém que estuda semicondutores. `valor()` devolve string
   vazia enquanto o exemplo estiver na tela — é o invariante que o teste guarda.

2. **O exemplo é concreto.** "Descreva sua pesquisa" não ensina nada; um exemplo que mostra
   um termo sendo desambiguado ("'informalidade' aqui é sociologia do trabalho, não direito
   tributário") ensina o que vale a pena escrever ali.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from core.i18n import t
from core.research_context import LIMITE_CONTEXTO, esta_ativo, normalizar
from ui.design_tokens import BLUE, INK, MUTED, WHITE_CARD

#: Altura do campo em linhas de texto. Três cabe um parágrafo curto sem empurrar o chat para
#: fora da tela — e contexto que não cabe em três linhas provavelmente é longo demais.
ALTURA_CAMPO = 66

#: A partir desta fração do teto, o contador aparece. Antes disso ele é ruído; depois, é
#: aviso — o campo corta em LIMITE_CONTEXTO e cortar em silêncio seria pior.
FRACAO_AVISO = 0.8


class ResearchContextBar(ctk.CTkFrame):
    """Rótulo + indicador + campo de texto. Guarda o valor do projeto ativo.

    `on_change` é chamado a cada edição — quem cria a barra decide o que fazer (tipicamente:
    marcar o projeto como sujo para salvar depois).
    """

    def __init__(self, master, valor: str = "", on_change: Callable[[str], None] | None = None):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self._mostrando_exemplo = False
        self._indicador_aceso = False
        self._monta()
        self.definir(valor)

    # ── construção ────────────────────────────────────────────────────────
    def _monta(self):
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, 4))
        self._cabecalho = cabecalho

        self.rotulo = ctk.CTkLabel(cabecalho, text=t("ai.contexto_titulo"),
                                   font=ctk.CTkFont(size=13, weight="bold"),
                                   text_color=INK, anchor="w")
        self.rotulo.pack(side="left")

        # Recolher/expandir. O contexto é escrito UMA vez e depois só relido: mantê-lo
        # aberto custa ~120px de altura em toda conversa, e a altura é o que falta no chat.
        self.alternar = ctk.CTkButton(
            cabecalho, text="▾", width=26, height=22, corner_radius=0,
            fg_color="transparent", text_color=INK, hover_color="#e0e0e0",
            font=ctk.CTkFont(size=12), command=self.alternar_recolhido)
        self.alternar.pack(side="left", padx=(6, 0))

        # Resumo de uma linha, visível só quando recolhido: recolher para esconder o que
        # está indo junto em toda resposta seria trocar espaço por opacidade.
        self.resumo = ctk.CTkLabel(cabecalho, text="", font=ctk.CTkFont(size=11),
                                   text_color=MUTED, anchor="w")

        # Indicador de "o contexto está indo junto em toda resposta". Azul, nunca amarelo.
        self.indicador = ctk.CTkLabel(cabecalho, text=t("ai.contexto_ativo"),
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      fg_color=BLUE, text_color=WHITE_CARD,
                                      corner_radius=0, padx=6)

        self.contador = ctk.CTkLabel(cabecalho, text="", font=ctk.CTkFont(size=11),
                                     text_color=MUTED)
        self.contador.pack(side="right")

        self.campo = ctk.CTkTextbox(self, height=ALTURA_CAMPO, corner_radius=0,
                                    border_width=2, border_color=INK, fg_color=WHITE_CARD,
                                    text_color=INK, font=ctk.CTkFont(size=12), wrap="word")
        self.campo.pack(fill="x")
        self.campo.bind("<FocusIn>", self._ao_focar)
        self.campo.bind("<FocusOut>", self._ao_desfocar)
        self.campo.bind("<KeyRelease>", self._ao_editar)

        self.ajuda = ctk.CTkLabel(self, text=t("ai.contexto_ajuda"),
                                  font=ctk.CTkFont(size=11), text_color=MUTED,
                                  justify="left", anchor="w", wraplength=680)
        self.ajuda.pack(anchor="w", fill="x", pady=(4, 0))

        #: Estado inicial: aberto quando não há contexto (é quando ele precisa ser escrito),
        #: recolhido quando já há (é quando ele só precisa ser conferido).
        self._recolhido = False

    # ── recolher ──────────────────────────────────────────────────────────
    def alternar_recolhido(self):
        self.definir_recolhido(not self._recolhido)

    def definir_recolhido(self, recolhido: bool):
        """Recolhe para uma linha, ou reabre o campo inteiro."""
        self._recolhido = bool(recolhido)
        if self._recolhido:
            self.campo.pack_forget()
            self.ajuda.pack_forget()
            self.contador.pack_forget()
            self.resumo.pack(side="left", fill="x", expand=True, padx=(10, 0))
            self.alternar.configure(text="▸")
        else:
            self.resumo.pack_forget()
            self.campo.pack(fill="x")
            self.ajuda.pack(anchor="w", fill="x", pady=(4, 0))
            self.contador.pack(side="right")
            self.alternar.configure(text="▾")
        self._atualizar_resumo()

    def esta_recolhido(self) -> bool:
        return self._recolhido

    def _atualizar_resumo(self):
        """Uma linha com o começo do contexto — ou o convite, quando ainda não há nenhum."""
        texto = self.valor()
        if texto:
            uma_linha = " ".join(texto.split())
            self.resumo.configure(text=uma_linha[:90] + ("…" if len(uma_linha) > 90 else ""))
        else:
            self.resumo.configure(text=t("ai.contexto_vazio_resumo"))

    # ── valor ─────────────────────────────────────────────────────────────
    def valor(self) -> str:
        """O contexto REAL — string vazia enquanto o exemplo estiver na tela.

        É o invariante que impede o texto de exemplo de viajar para o modelo como se fosse a
        pesquisa do usuário.
        """
        if self._mostrando_exemplo:
            return ""
        return normalizar(self.campo.get("1.0", "end"))

    def definir(self, texto: object):
        """Carrega o valor vindo do projeto. Vazio volta a mostrar o exemplo."""
        texto = normalizar(texto)
        self.campo.delete("1.0", "end")
        if texto:
            self._mostrando_exemplo = False
            self.campo.insert("1.0", texto)
            self.campo.configure(text_color=INK)
        else:
            self._mostrar_exemplo()
        self._atualizar_indicador()
        # Projeto que já tem contexto abre recolhido: ele foi escrito uma vez e a partir daí
        # só precisa ser conferido. Sem contexto, abre aberto — é quando há o que escrever.
        if hasattr(self, "_recolhido"):
            self.definir_recolhido(bool(texto))

    # ── exemplo (placeholder) ─────────────────────────────────────────────
    def _mostrar_exemplo(self):
        self._mostrando_exemplo = True
        self.campo.delete("1.0", "end")
        self.campo.insert("1.0", t("ai.contexto_placeholder"))
        self.campo.configure(text_color=MUTED)

    def _ao_focar(self, _e=None):
        if self._mostrando_exemplo:
            self._mostrando_exemplo = False
            self.campo.delete("1.0", "end")
            self.campo.configure(text_color=INK)

    def _ao_desfocar(self, _e=None):
        if not self._mostrando_exemplo and not normalizar(self.campo.get("1.0", "end")):
            self._mostrar_exemplo()
        self._atualizar_indicador()

    # ── reações ───────────────────────────────────────────────────────────
    def _ao_editar(self, _e=None):
        self._atualizar_indicador()
        self._atualizar_resumo()
        if self.on_change:
            self.on_change(self.valor())

    def _atualizar_indicador(self):
        # Estado próprio em vez de `winfo_ismapped()`: fora do laço principal do Tk o widget
        # ainda não foi mapeado, `ismapped()` devolve falso e o `pack` era refeito a cada
        # tecla. O booleano diz o que a barra decidiu, não o que o Tk já desenhou.
        ativo = esta_ativo(self.valor())
        if ativo and not self._indicador_aceso:
            self.indicador.pack(side="left", padx=(8, 0))
            self._indicador_aceso = True
        elif not ativo and self._indicador_aceso:
            self.indicador.pack_forget()
            self._indicador_aceso = False

        # Cortar em silêncio seria pior do que avisar: o usuário digitou e não veria sumir.
        bruto = "" if self._mostrando_exemplo else self.campo.get("1.0", "end").strip()
        if len(bruto) >= LIMITE_CONTEXTO * FRACAO_AVISO:
            self.contador.configure(text=f"{len(bruto)}/{LIMITE_CONTEXTO}")
        else:
            self.contador.configure(text="")
