"""Painel de onboarding da chave de IA, no vocabulário visual neoplasticista do app.

Blocos chapados, canto zero, sem sombra e sem gradiente. A numeração dos passos é preta sobre
plano de cor; o corpo de cada passo fica sobre o branco de card. As cores saem todas de
`ui/design_tokens.py` — nenhum literal hexadecimal aqui.

Aparece **no lugar do chat** quando não há chave configurada. Um erro no meio da conversa
seria pior: o usuário perguntaria por que a IA não responde em vez de saber o que fazer.
"""

from __future__ import annotations

import threading
import webbrowser
from typing import Callable

import customtkinter as ctk

from ai.onboarding import URL_CONSOLE_GROQ, mascarar, testar_chave
from core.i18n import t
from ui.design_tokens import BLUE, INK, MUTED, PAPER, RED, RED_HOV, WHITE_CARD

#: Cores dos planos de cada passo. Nunca amarelo: o amarelo do design system significa
#: "conteúdo gerado por IA" e usá-lo aqui diluiria o sinal (ver docs/inventario-ia.md).
PLANOS_PASSOS = (RED, BLUE, INK)


class AIOnboardingPanel(ctk.CTkFrame):
    """Três passos + campo da chave + resultado do teste de conexão.

    `on_saved` é chamado quando a chave é validada e gravada — quem cria o painel decide o
    que fazer (tipicamente: destruir o painel e montar o chat).
    """

    def __init__(self, master, on_saved: Callable[[], None] | None = None):
        super().__init__(master, fg_color="transparent")
        self.on_saved = on_saved
        self._campo_chave: ctk.CTkEntry | None = None
        self._resultado: ctk.CTkLabel | None = None
        self._botao_salvar: ctk.CTkButton | None = None
        self._monta()

    # ── construção ────────────────────────────────────────────────────────
    def _monta(self):
        ctk.CTkLabel(self, text=t("ai.onboarding_title"),
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=INK).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(self, text=t("ai.onboarding_intro"), font=ctk.CTkFont(size=13),
                     text_color=MUTED, justify="left", wraplength=680,
                     anchor="w").pack(anchor="w", fill="x", pady=(0, 20))

        self._passo(1, t("ai.step1"), botao=(t("ai.step1_button"), self._abrir_console))
        self._passo(2, t("ai.step2"))
        corpo3 = self._passo(3, t("ai.step3"))

        linha = ctk.CTkFrame(corpo3, fg_color="transparent")
        linha.pack(fill="x", pady=(10, 0))

        self._campo_chave = ctk.CTkEntry(
            linha, placeholder_text="gsk_…", placeholder_text_color=MUTED,
            show="•", height=38, corner_radius=0, border_width=2, border_color=INK,
            fg_color=WHITE_CARD, text_color=INK, font=ctk.CTkFont(size=13))
        self._campo_chave.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._campo_chave.bind("<Return>", lambda _e: self._testar_e_salvar())

        self._botao_salvar = ctk.CTkButton(
            linha, text=t("ai.step3_button"), width=170, height=38, corner_radius=0,
            fg_color=RED, hover_color=RED_HOV, text_color=WHITE_CARD,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._testar_e_salvar)
        self._botao_salvar.pack(side="left")

        self._resultado = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13),
                                       text_color=INK, justify="left", wraplength=680,
                                       anchor="w")
        self._resultado.pack(anchor="w", fill="x", pady=(16, 0))

    def _passo(self, numero: int, titulo: str, botao: tuple[str, Callable] | None = None):
        """Um passo: quadrado numerado no plano de cor + corpo sobre o card branco."""
        bloco = ctk.CTkFrame(self, fg_color=WHITE_CARD, corner_radius=0,
                             border_width=2, border_color=INK)
        bloco.pack(fill="x", pady=(0, 12))

        quadrado = ctk.CTkFrame(bloco, fg_color=PLANOS_PASSOS[numero - 1], corner_radius=0,
                                width=46, height=46)
        quadrado.pack(side="left", padx=0, pady=0, fill="y")
        quadrado.pack_propagate(False)
        ctk.CTkLabel(quadrado, text=str(numero), font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=WHITE_CARD if numero != 3 else PAPER).pack(expand=True)

        corpo = ctk.CTkFrame(bloco, fg_color="transparent")
        corpo.pack(side="left", fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(corpo, text=titulo, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=INK, anchor="w").pack(anchor="w")

        if botao:
            texto, comando = botao
            ctk.CTkButton(corpo, text=texto, width=200, height=34, corner_radius=0,
                          fg_color=WHITE_CARD, text_color=INK, border_width=2,
                          border_color=INK, hover_color=PAPER,
                          font=ctk.CTkFont(size=13), command=comando).pack(anchor="w",
                                                                          pady=(10, 0))
        return corpo

    # ── ações ─────────────────────────────────────────────────────────────
    def _abrir_console(self):
        webbrowser.open(URL_CONSOLE_GROQ)

    def _testar_e_salvar(self):
        """Testa contra o provedor antes de gravar. Chave que não conecta não é salva."""
        chave = (self._campo_chave.get() or "").strip()
        self._botao_salvar.configure(state="disabled")
        self._mostrar("…", INK)

        def _trabalho():
            r = testar_chave(chave)
            self.after(0, lambda: self._concluir(r, chave))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _concluir(self, resultado, chave: str):
        self._botao_salvar.configure(state="normal")
        if not resultado.ok:
            self._mostrar(t(resultado.chave_i18n), RED)
            return

        from core.settings import set_api_key
        set_api_key(chave)
        # A partir daqui a chave só aparece mascarada — inclusive em captura de tela.
        self._mostrar(f"{t('ai.key_ok', modelo=resultado.modelo)}  ·  "
                      f"{t('ai.key_saved', chave=mascarar(chave))}", BLUE)
        self._campo_chave.delete(0, "end")
        if self.on_saved:
            self.after(700, self.on_saved)

    def _mostrar(self, texto: str, cor: str):
        if self._resultado is not None:
            self._resultado.configure(text=texto, text_color=cor)
