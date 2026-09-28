"""Aba de Credenciais: fonte única das chaves do Blicsa.

Substitui três lugares que faziam a mesma coisa de três jeitos — o painel de onboarding do
Blink, a seção de IA dos Ajustes e o campo "Chave API" cru na barra de parâmetros do mapa.
Aquele último era o que de fato alimentava as chamadas, e era justamente o que não tinha
teste de conexão nem link de criação.

Um `BlocoCredencial` por slot, todos com o mesmo contrato: explicação, link de criação,
campo mascarado, teste de conexão real e diagnóstico específico. **Só credencial provada
inválida (401/403) deixa de ser gravada**: falha de rede, franquia esgotada ou erro
passageiro do provedor não dizem nada sobre a chave, e descartá-la nesses casos fazia o
app perder o que o usuário acabara de colar.

Vocabulário visual neoplasticista do app: blocos chapados, canto zero, sem sombra e sem
gradiente, cores de `ui/design_tokens.py`. Nunca amarelo, que no design system significa
"conteúdo gerado por IA" (ver docs/inventario-ia.md).
"""

from __future__ import annotations

import threading
import webbrowser
from typing import Callable

import customtkinter as ctk

from core.credenciais import CREDENCIAIS, PROVEDORES_IA, deve_gravar, mascarar
from core.i18n import t
from ui.design_tokens import BLUE, INK, MUTED, PAPER, RED, RED_HOV, WHITE_CARD

#: Cor do quadrado de cada bloco, na ordem do registro. Mesma paleta dos passos do
#: onboarding, para quem vem de lá reconhecer a tela.
PLANOS = (RED, BLUE, INK)


class BlocoCredencial(ctk.CTkFrame):
    """Um slot: título, explicação, link de criação, campo, teste e estado."""

    def __init__(self, master, credencial, plano, on_change: Callable[[], None] | None = None):
        super().__init__(master, fg_color=WHITE_CARD, corner_radius=0,
                         border_width=2, border_color=INK)
        self.credencial = credencial
        self.plano = plano
        self.on_change = on_change
        self._campo = None
        self._resultado = None
        self._estado = None
        self._botao_salvar = None
        self._botao_remover = None
        self._provedor_var = None
        self._monta()
        self._atualizar_estado()

    # ── construção ────────────────────────────────────────────────────────
    def _monta(self):
        faixa = ctk.CTkFrame(self, fg_color=self.plano, corner_radius=0, width=8)
        faixa.pack(side="left", fill="y")
        faixa.pack_propagate(False)

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(side="left", fill="both", expand=True, padx=16, pady=14)

        linha_tit = ctk.CTkFrame(corpo, fg_color="transparent")
        linha_tit.pack(fill="x")
        ctk.CTkLabel(linha_tit, text=t(self.credencial.titulo_i18n),
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=INK).pack(side="left")
        selo = t("cred.obrigatoria") if self.credencial.id == "ai" else t("cred.opcional")
        ctk.CTkLabel(linha_tit, text=f"  ({selo})", font=ctk.CTkFont(size=11),
                     text_color=MUTED).pack(side="left")

        ctk.CTkLabel(corpo, text=t(self.credencial.explicacao_i18n),
                     font=ctk.CTkFont(size=12), text_color=MUTED, justify="left",
                     wraplength=620, anchor="w").pack(anchor="w", fill="x", pady=(4, 10))

        # Provedor selecionável: só a IA tem mais de um. O link de criação acompanha a
        # escolha, senão o botão mandaria quem escolheu OpenAI para o console do Groq.
        if self.credencial.provedores:
            linha_prov = ctk.CTkFrame(corpo, fg_color="transparent")
            linha_prov.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(linha_prov, text=t("cred.provedor"), font=ctk.CTkFont(size=12),
                         text_color=INK).pack(side="left", padx=(0, 8))
            # Abre no provedor ATIVO, não no primeiro da lista. O combo sempre voltava a
            # "groq" a cada montagem da aba: quem usava a OpenAI reabria o Blicsa vendo
            # "groq" selecionado e a chave da OpenAI descrita como inexistente.
            from core.settings import provedor_ia
            inicial = provedor_ia()
            if inicial not in self.credencial.provedores:
                inicial = next(iter(self.credencial.provedores))
            self._provedor_var = ctk.StringVar(value=inicial)
            ctk.CTkComboBox(linha_prov, values=list(self.credencial.provedores),
                            variable=self._provedor_var, width=170, height=30,
                            corner_radius=0, border_width=2, border_color=INK,
                            button_color=INK, fg_color=WHITE_CARD, text_color=INK,
                            command=self._on_provedor).pack(side="left")

        linha = ctk.CTkFrame(corpo, fg_color="transparent")
        linha.pack(fill="x")

        ctk.CTkButton(linha, text=t("cred.criar"), width=130, height=36, corner_radius=0,
                      fg_color=WHITE_CARD, text_color=INK, border_width=2, border_color=INK,
                      hover_color=PAPER, font=ctk.CTkFont(size=12),
                      command=self._abrir_criacao).pack(side="left", padx=(0, 10))

        self._campo = ctk.CTkEntry(
            linha, placeholder_text=self.credencial.placeholder or "…",
            placeholder_text_color=MUTED, show="•", height=36, corner_radius=0,
            border_width=2, border_color=INK, fg_color=WHITE_CARD, text_color=INK,
            font=ctk.CTkFont(size=13))
        self._campo.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._campo.bind("<Return>", lambda _e: self._testar_e_salvar())

        self._botao_salvar = ctk.CTkButton(
            linha, text=t("cred.testar"), width=150, height=36, corner_radius=0,
            fg_color=RED, hover_color=RED_HOV, text_color=WHITE_CARD,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._testar_e_salvar)
        self._botao_salvar.pack(side="left")

        rodape = ctk.CTkFrame(corpo, fg_color="transparent")
        rodape.pack(fill="x", pady=(10, 0))
        self._estado = ctk.CTkLabel(rodape, text="", font=ctk.CTkFont(size=12),
                                    text_color=MUTED, anchor="w")
        self._estado.pack(side="left")
        self._botao_remover = ctk.CTkButton(
            rodape, text=t("cred.remover"), width=100, height=28, corner_radius=0,
            fg_color=WHITE_CARD, text_color=INK, border_width=2, border_color=INK,
            hover_color=PAPER, font=ctk.CTkFont(size=12), command=self._remover)
        self._botao_remover.pack(side="right")

        self._resultado = ctk.CTkLabel(corpo, text="", font=ctk.CTkFont(size=12),
                                       text_color=INK, justify="left", wraplength=620,
                                       anchor="w")
        self._resultado.pack(anchor="w", fill="x", pady=(8, 0))

    # ── ações ─────────────────────────────────────────────────────────────
    def _url_criacao(self) -> str:
        if self._provedor_var is not None:
            escolhido = self._provedor_var.get()
            if escolhido in PROVEDORES_IA:
                return PROVEDORES_IA[escolhido][0]
        return self.credencial.url_criacao

    def _abrir_criacao(self):
        webbrowser.open(self._url_criacao())

    def _provedor_selecionado(self) -> str | None:
        """Provedor do combo, ou None nos slots que não têm provedor (OpenAlex, PubMed)."""
        return self._provedor_var.get() if self._provedor_var is not None else None

    def _on_provedor(self, escolhido: str):
        """Trocar no combo troca o provedor ATIVO e passa a mostrar a chave DELE.

        Cada provedor tem seu próprio slot no cofre, então alternar não apaga mais a chave
        do anterior: configura-se Groq e OpenAI uma vez cada e troca-se à vontade. A troca
        é persistida na hora porque a escolha só valia dentro da sessão — no reinício o app
        voltava ao Groq e mandava a chave guardada para o endpoint errado.

        `set_config_ia` sem URL nem modelo é deliberado: zera os dois para o preset do
        provedor novo, senão a URL base do anterior ficaria para trás.
        """
        from core.settings import set_config_ia

        set_config_ia(escolhido)
        self._mostrar("", INK)
        self._atualizar_estado()
        if self.on_change:
            self.on_change()

    def _testar_e_salvar(self):
        """Testa contra o provedor antes de gravar. Credencial que não conecta não é salva."""
        chave = (self._campo.get() or "").strip()
        self._botao_salvar.configure(state="disabled")
        self._mostrar("…", INK)

        def _trabalho():
            r = self._executar_teste(chave)
            self.after(0, lambda: self._concluir(r, chave))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _executar_teste(self, chave: str):
        """Isolado para o teste poder trocar só a rede, mantendo o resto do caminho."""
        if self._provedor_var is not None:
            escolhido = self._provedor_var.get()
            if escolhido in PROVEDORES_IA:
                _, base_url, modelo = PROVEDORES_IA[escolhido]
                return self.credencial.testar(chave, base_url=base_url, modelo=modelo)
        return self.credencial.testar(chave)

    def _concluir(self, resultado, chave: str):
        """Grava tudo que o teste não provou inválido, e diz em qual dos dois casos está.

        A regra antiga era "credencial que não conecta não é gravada", e ela descartava a
        chave também quando o teste falhava por wi-fi caído, franquia esgotada (429) ou
        erro passageiro do provedor. O usuário colava a chave, via a mensagem vermelha,
        fechava o app — e ela sumia, porque nunca havia chegado ao cofre. Só 401/403 é
        prova de chave errada; o resto é o mundo, não a credencial.
        """
        self._botao_salvar.configure(state="normal")
        if not deve_gravar(resultado):
            self._mostrar(t(resultado.chave_i18n), RED)
            return
        self.credencial.gravar(chave, self._provedor_selecionado())
        if resultado.ok:
            self._mostrar(t(resultado.chave_i18n, modelo=resultado.modelo), BLUE)
        else:
            # Guardada sem confirmação: o diagnóstico continua sendo o do teste, mas o
            # usuário precisa saber que a chave NÃO se perdeu.
            self._mostrar(t("cred.salva_sem_confirmar", motivo=t(resultado.chave_i18n)), INK)
        self._campo.delete(0, "end")
        self._atualizar_estado()
        if self.on_change:
            self.on_change()

    def _remover(self):
        self.credencial.gravar("", self._provedor_selecionado())
        self._mostrar("", INK)
        self._atualizar_estado()
        if self.on_change:
            self.on_change()

    def _atualizar_estado(self):
        atual = (self.credencial.valor(self._provedor_selecionado()) or "").strip()
        # A credencial NUNCA aparece inteira: capturas de tela dos Ajustes viram
        # documentação, e uma chave legível numa imagem é uma chave comprometida.
        self._estado.configure(text=t("cred.ativa", chave=mascarar(atual)) if atual
                               else t("cred.nenhuma"))
        self._botao_remover.configure(state="normal" if atual else "disabled")

    def _mostrar(self, texto: str, cor: str):
        if self._resultado is not None:
            self._resultado.configure(text=texto, text_color=cor)


class CredentialsTab(ctk.CTkFrame):
    """Os três blocos, numa coluna rolável.

    `on_change` avisa o app que uma credencial mudou, para ele sincronizar a sessão — a
    mesma exigência da Fase 1: salvar ou remover vale na hora, sem reiniciar.
    """

    def __init__(self, master, on_change: Callable[[], None] | None = None):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.blocos: dict = {}

        ctk.CTkLabel(self, text=t("cred.titulo"),
                     font=ctk.CTkFont(size=30, weight="bold"),
                     text_color=INK).pack(anchor="w", padx=40, pady=(24, 6))
        ctk.CTkLabel(self, text=t("cred.intro"), font=ctk.CTkFont(size=13),
                     text_color=MUTED, justify="left", wraplength=680,
                     anchor="w").pack(anchor="w", fill="x", padx=40, pady=(0, 18))

        coluna = ctk.CTkScrollableFrame(self, fg_color="transparent")
        coluna.pack(fill="both", expand=True, padx=40, pady=(0, 24))

        for i, cred in enumerate(CREDENCIAIS):
            bloco = BlocoCredencial(coluna, cred, PLANOS[i % len(PLANOS)],
                                    on_change=self.on_change)
            bloco.pack(fill="x", pady=(0, 14))
            self.blocos[cred.id] = bloco

    def atualizar(self):
        """Relê o cofre. Usado quando algo fora da aba muda uma credencial.

        Ressincroniza o combo de provedor antes de reler: o provedor ativo também se troca
        pela barra de parâmetros do mapa, e um combo defasado aqui mostraria a chave de um
        provedor com o nome de outro.
        """
        from core.settings import provedor_ia

        ativo = provedor_ia()
        for bloco in self.blocos.values():
            if bloco._provedor_var is not None and ativo in bloco.credencial.provedores:
                bloco._provedor_var.set(ativo)
            bloco._atualizar_estado()
