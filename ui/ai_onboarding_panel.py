"""Convite do Blink para a aba de Credenciais.

Era uma SEGUNDA implementação do mesmo fluxo: três passos, campo, teste de conexão e
gravação, tudo duplicado do que hoje vive em `ui/credentials_tab.py`. Duas implementações
da mesma tarefa divergem — foi assim que o campo dos Ajustes ficou sem teste de conexão
enquanto o do Blink tinha, e que o campo que de fato alimentava as chamadas de IA (o da
barra de parâmetros do mapa) ficou sem os dois.

Agora é o que sempre deveria ter sido: uma explicação curta e um botão que leva ao lugar
onde a credencial se configura. Aparece **no lugar do chat** quando não há chave; um erro
no meio da conversa seria pior, porque o usuário perguntaria por que a IA não responde em
vez de saber o que fazer.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from core.i18n import t
from ui.design_tokens import INK, MUTED, RED, RED_HOV, WHITE_CARD


class AIOnboardingPanel(ctk.CTkFrame):
    """Convite curto + botão que abre a aba de Credenciais.

    `on_ir_para_credenciais` é quem sabe trocar de aba (o app). `on_saved` continua no
    construtor por compatibilidade com quem já criava o painel, mas o salvamento não
    acontece mais aqui.
    """

    def __init__(self, master, on_saved: Callable[[], None] | None = None,
                 on_ir_para_credenciais: Callable[[], None] | None = None):
        super().__init__(master, fg_color="transparent")
        self.on_saved = on_saved
        self.on_ir_para_credenciais = on_ir_para_credenciais
        self._monta()

    def _monta(self):
        ctk.CTkLabel(self, text=t("ai.onboarding_title"),
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=INK).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(self, text=t("blink.sem_chave"), font=ctk.CTkFont(size=13),
                     text_color=MUTED, justify="left", wraplength=680,
                     anchor="w").pack(anchor="w", fill="x", pady=(0, 20))

        ctk.CTkButton(self, text=t("blink.ir_credenciais"), width=260, height=44,
                      corner_radius=0, fg_color=RED, hover_color=RED_HOV,
                      text_color=WHITE_CARD, font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._ir).pack(anchor="w")

    def _ir(self):
        if self.on_ir_para_credenciais:
            self.on_ir_para_credenciais()
