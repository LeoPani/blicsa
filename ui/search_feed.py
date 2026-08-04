import customtkinter as ctk
import pandas as pd
from typing import Callable, Optional, List
from collections import Counter
import threading
import time

from core.i18n import t

PAPER = "#F6F4EE"
INK = "#141414"
RED = "#DF3117"
BLUE = "#1E4DA0"
WHITE = "#FFFFFF"

class SkeletonCard(ctk.CTkFrame):
    """
    A placeholder skeleton loading card with pulse animation to indicate
    that data is currently being fetched or processed.
    """
    def __init__(self, master):
        super().__init__(master, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.grid_columnconfigure(0, weight=1)
        
        self.title_skel = ctk.CTkFrame(self, fg_color="#E0E0E0", height=20, corner_radius=0)
        self.title_skel.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        self.title_skel.configure(width=300)
        
        self.meta_skel = ctk.CTkFrame(self, fg_color="#E0E0E0", height=14, corner_radius=0)
        self.meta_skel.grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self.meta_skel.configure(width=200)

        self.abs_skel = ctk.CTkFrame(self, fg_color="#E0E0E0", height=30, corner_radius=0)
        self.abs_skel.grid(row=2, column=0, padx=12, pady=(4, 12), sticky="ew")
        
        self._pulse_state = 0
        self._animating = True
        self._animate()

    def _animate(self):
        if not self._animating: return
        # Dois tons chapados alternados em passo discreto (sem shimmer/gradiente).
        colors = ["#E0E0E0", "#EDEDED"]
        color = colors[self._pulse_state % len(colors)]
        self.title_skel.configure(fg_color=color)
        self.meta_skel.configure(fg_color=color)
        self.abs_skel.configure(fg_color=color)
        self._pulse_state += 1
        self.after(500, self._animate)

    def stop(self):
        self._animating = False

def record_key(record: dict) -> str:
    """Identidade ESTÁVEL de um registro, para a seleção sobreviver à troca de página.

    A seleção original era por índice na lista em memória — o que funcionava enquanto tudo
    estava carregado de uma vez. Com paginação, "índice 3" é um registro na página 1 e outro
    na página 2, e a seleção do usuário migraria para registros que ele nunca marcou.

    DOI quando existe; senão título normalizado + ano, que é o que resta para distinguir.
    """
    doi = str(record.get("doi") or "").strip().lower()
    for prefixo in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefixo):
            doi = doi[len(prefixo):]
    doi = doi.strip("/")
    if doi:
        return f"doi:{doi}"
    titulo = " ".join(str(record.get("title") or "").lower().split())
    ano = str(record.get("year") or "")
    return f"t:{titulo}|{ano}"


def truncate_source_name(name: str, limit: int = 22) -> str:
    """Encurta o nome de uma fonte para a sidebar, com reticências.

    Dois cuidados: o parêntese da CONTAGEM que vem depois ("… (305)") nunca pode ser
    partido, e o corte não pode deixar um parêntese ABERTO do próprio nome pendurado —
    "LA Referencia (Red Federal…" viraria "LA Referencia (Red Fe… (305)", que lê como
    parêntese cortado no meio. Nesse caso o trecho entre parênteses sai inteiro.
    """
    s = (name or "").strip()
    if len(s) <= limit:
        return s
    cut = s[:limit - 1].rstrip()
    if cut.count("(") > cut.count(")"):
        cut = cut[:cut.rfind("(")].rstrip()
    return (cut or s[:limit - 1].rstrip()) + "…"


class ArticleCard(ctk.CTkFrame):
    """
    A UI card representing a single bibliometric record/article.
    Provides a checkbox for selection and displays title, year,
    citations, authors, source, and a truncated abstract.
    """
    def __init__(self, master, record: dict, on_toggle: Callable[[bool, int], None], index: int):
        super().__init__(master, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.record = record
        self.on_toggle = on_toggle
        self.index = index
        self._selected = True

        # A sobra de largura vai para a coluna do CONTEÚDO (2), não para a do checkbox (1).
        # Com o peso na 1, a coluna do checkbox esticava e empurrava o texto para a direita
        # por uma distância que dependia do conteúdo de cada card — os títulos começavam em
        # x diferentes (variação medida: 532px), com um vão branco no meio do card.
        self.grid_columnconfigure(2, weight=1)
        
        # Left edge bar — height=1 evita a altura default 200px do CTkFrame (que reservava
        # um vão branco gigante); com sticky="ns" a barra estica ao conteúdo real do card.
        self.left_bar = ctk.CTkFrame(self, width=6, height=1, fg_color=WHITE, corner_radius=0)
        self.left_bar.grid(row=0, column=0, rowspan=5, sticky="ns")
        
        # Checkbox
        self.cb = ctk.CTkCheckBox(
            self, text="", width=24, corner_radius=0, 
            border_color=INK, fg_color=RED, hover_color=RED,
            command=self._on_check
        )
        self.cb.select()
        self.cb.grid(row=0, column=1, rowspan=4, padx=(8, 4), pady=12, sticky="nw")
        
        # Badges & Title — height=1 pelo mesmo motivo do left_bar: um CTkFrame sem altura
        # explícita assume a default de 200px do CTkFrame, e um registro SEM badge nenhum
        # (sem ano/citações/OA/idioma) reservava esses 200px de branco no topo do card.
        # Segue sempre gridado: vazio ele custa 1px e mantém o respiro de topo do card.
        title_frame = ctk.CTkFrame(self, fg_color="transparent", height=1)
        title_frame.grid(row=0, column=2, padx=(4, 12), pady=(12, 2), sticky="ew")
        title_frame.grid_columnconfigure(3, weight=1)

        year = record.get("year", "")
        if year:
            ctk.CTkLabel(title_frame, text=str(year), fg_color=INK, text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            
        cites = record.get("citations", 0)
        if cites > 0:
            ctk.CTkLabel(title_frame, text=f"★ {cites}", fg_color="#F5BE00", text_color=INK, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            
        if record.get("is_oa"):
            ctk.CTkLabel(title_frame, text="OPEN ACCESS", fg_color="#7A9E7E", text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            if record.get("oa_url"):
                ctk.CTkLabel(title_frame, text="PDF", fg_color="#DF3117", text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
            
        lang = str(record.get("language", "")).upper()
        if lang:
            ctk.CTkLabel(title_frame, text=lang, fg_color="#E0E0E0", text_color=INK, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))
        
        if record.get("is_duplicate"):
            ctk.CTkLabel(title_frame, text=str(record.get("dup_reason", "Duplicado")).upper(), fg_color=RED, text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"), corner_radius=0).pack(side="left", padx=(0, 6))

        title = str(record.get("title", "Sem título"))
        ctk.CTkLabel(self, text=title, text_color=BLUE if not record.get("is_duplicate") else "#999999", font=ctk.CTkFont(size=14, weight="bold"), anchor="w", justify="left", wraplength=700).grid(row=1, column=2, padx=(4, 12), pady=0, sticky="w")
        
        # Meta: Authors - Journal
        authors = str(record.get("authors", ""))
        journal = str(record.get("source", ""))
        meta_text = ""
        if authors: meta_text += authors
        if journal: meta_text += f" — {journal}"
        if meta_text:  # sem autor/fonte: não reserva linha vazia
            ctk.CTkLabel(self, text=meta_text, text_color=INK, font=ctk.CTkFont(size=12, slant="italic"), anchor="w", justify="left").grid(row=2, column=2, padx=(4, 12), pady=(2, 4), sticky="w")
        
        # Abstract
        abs_text = str(record.get("abstract", ""))
        if len(abs_text) > 200: abs_text = abs_text[:197] + "..."
        if abs_text:
            ctk.CTkLabel(self, text=abs_text, text_color="#555555", font=ctk.CTkFont(size=12), anchor="w", justify="left", wraplength=700).grid(row=3, column=2, padx=(4, 12), pady=(0, 4), sticky="w")
            
        # Idem: registro OA (ou sem DOI) não ganha botão, e a faixa vazia reservava 200px.
        # Com height=1 ela custa 1px e continua garantindo o respiro inferior de 12px.
        actions_f = ctk.CTkFrame(self, fg_color="transparent", height=1)
        actions_f.grid(row=4, column=2, padx=(4, 12), pady=(0, 12), sticky="w")
        if not record.get("is_oa") and record.get("doi"):
            import webbrowser
            ctk.CTkButton(actions_f, text="Abrir DOI", width=80, height=24, fg_color="#EEEEEE", text_color=INK, command=lambda d=record.get("doi"): webbrowser.open(f"https://doi.org/{d}")).pack(side="left")


        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)
            
    def _on_enter(self, e):
        self.configure(border_width=4)
        self.left_bar.configure(fg_color=RED)
        
    def _on_leave(self, e):
        self.configure(border_width=2)
        self.left_bar.configure(fg_color=WHITE)

    def _on_check(self):
        self._selected = bool(self.cb.get())
        self.on_toggle(self._selected, self.index)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.cb.select()
        else:
            self.cb.deselect()

class SearchFeedView(ctk.CTkFrame):
    """
    A comprehensive UI view for displaying search results from APIs.
    Features filtering sidebars, pagination, selection logic,
    and a bottom bar for confirming import to the corpus.
    """
    def __init__(self, master, on_import_confirm: Callable, on_cancel: Callable,
                 on_ai_assistant: Callable = None, on_refilter: Callable = None):
        super().__init__(master, fg_color="transparent")
        self.on_import_confirm = on_import_confirm
        self.on_cancel = on_cancel
        self.on_ai_assistant = on_ai_assistant
        self.on_refilter = on_refilter  # re-consulta server-side com os filtros da sidebar
        self.records = []
        self.filtered_indices = []
        self.selected_indices = set()
        # Modo navegação: a seleção viaja por CHAVE, não por índice, para sobreviver à troca
        # de página. `selected_indices` continua sendo a visão da página corrente.
        self.selected_keys: set[str] = set()
        self.browse_session = None
        self.browse_total = 0
        self.browse_page = 1
        self.browse_pages = 1
        #: Há resultados além do que a paginação alcança? Muda o rótulo do pager.
        self.browse_clipped = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)   # a área de conteúdo é quem estica
        
        # Header
        hdr = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK, height=60)
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(16, 8))
        hdr.pack_propagate(False)
        self.title_lbl = ctk.CTkLabel(hdr, text="Resultados da Busca", font=ctk.CTkFont(size=18, weight="bold"), text_color=INK)
        self.title_lbl.pack(side="left", padx=16)
        
        self.trail_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12), text_color="#555555")
        self.trail_lbl.pack(side="left", padx=16)

        ctk.CTkButton(hdr, text="Cancelar", fg_color=WHITE, text_color=INK, hover_color="#EEEEEE", border_width=2, border_color=INK, corner_radius=0, command=self.on_cancel).pack(side="right", padx=16)

        # Barra de progresso neoplasticista: bloco sólido chapado, canto zero, sem gradiente.
        self.progress = ctk.CTkProgressBar(hdr, progress_color=RED, fg_color="#E0E0E0",
                                           corner_radius=0, height=12, width=180, mode="determinate")
        self.progress.set(0)
        # criada oculta; exibida em begin_stream()

        # Chips de filtros ativos, logo abaixo do cabeçalho (só aparecem quando há filtro).
        self.chips_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.chips_bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 4))
        self.chips_bar.grid_remove()

        # Barra de paginação: "◀ Página 1 de 12.772 ▶" + ir para N.
        self.pager = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0,
                                  border_width=2, border_color=INK, height=44)
        self.pager.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(4, 0))
        self.pager.grid_remove()
        self._build_pager()

        # Estado de streaming
        self._skeletons = []
        self._stream_rendered = 0
        self._stream_limit = 1
        
        # Sidebar
        self.sidebar = ctk.CTkScrollableFrame(self, width=250, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self.sidebar.grid(row=2, column=0, sticky="ns", padx=(16, 8), pady=8)
        
        # Main feed
        self.feed = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.feed.grid(row=2, column=1, sticky="nsew", padx=(8, 16), pady=8)
        self.feed.grid_columnconfigure(0, weight=1)
        
        # Bottom Bar
        self.bottom_bar = ctk.CTkFrame(self, fg_color=INK, corner_radius=0, height=60)
        self.bottom_bar.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.bottom_bar.pack_propagate(False)
        
        self.sel_lbl = ctk.CTkLabel(self.bottom_bar, text="0 selecionados de 0", text_color=WHITE, font=ctk.CTkFont(size=14, weight="bold"))
        self.sel_lbl.pack(side="left", padx=24)
        
        ctk.CTkButton(self.bottom_bar, text="Importar para o corpus", fg_color=RED, text_color=WHITE, hover_color="#b82611", corner_radius=0, border_width=0, font=ctk.CTkFont(weight="bold"), command=self._show_summary_and_import).pack(side="right", padx=(0, 24))
        
        if self.on_ai_assistant:
            ctk.CTkButton(self.bottom_bar, text="✨ Blink", fg_color="#F5BE00", text_color=INK, hover_color="#D4A000", corner_radius=0, border_width=0, font=ctk.CTkFont(weight="bold"), command=self._trigger_ai).pack(side="right", padx=16)
        
        self.cards = []
        self.page = 0
        self.page_size = 25
        self.load_more_btn = ctk.CTkButton(self.feed, text="Carregar mais", fg_color=WHITE, text_color=INK, hover_color="#EEEEEE", border_width=2, border_color=INK, corner_radius=0, command=self._render_page)

    def _trigger_ai(self):
        if self.on_ai_assistant:
            self.on_ai_assistant(self.records, self.selected_indices)

    def load_results(self, records: List[dict], count_trail: str):
        self.records = records
        self.filtered_indices = list(range(len(records)))
        self.selected_indices = {i for i, r in enumerate(records) if not r.get("is_duplicate")}
        
        langs = Counter([r.get('language') for r in records if r.get('language')]).most_common(3)
        lang_str = " · ".join(f"{l.upper()}: {c}" for l, c in langs) if langs else "Sem idioma detectado"
        self.trail_lbl.configure(text=f"{count_trail} | Idiomas: {lang_str}")
        
        self._build_sidebar()
        self._clear_feed()
        self.page = 0
        self._render_page()
        self._update_bottom_bar()

    # ---------------- Streaming (carregamento vivo) ----------------
    def begin_stream(self, limit: int):
        """Estado inicial: skeletons + barra de progresso + contador vivo."""
        self._stream_limit = max(1, int(limit))
        self._stream_rendered = 0
        self.records = []
        self.selected_indices = set()
        self.title_lbl.configure(text="Buscando…")
        self.trail_lbl.configure(text="Encontrados … · carregando 0…")
        self.progress.set(0)
        self.progress.pack(side="right", padx=16)  # exibe
        self._clear_feed()
        self._skeletons = []
        for _ in range(4):
            sk = SkeletonCard(self.feed)
            sk.pack(fill="x", pady=4)
            self._skeletons.append(sk)

    def _drop_skeletons(self):
        for sk in self._skeletons:
            try:
                sk.stop(); sk.destroy()
            except Exception:
                pass
        self._skeletons = []

    def stream_update(self, records: List[dict], loaded: int, total: int):
        """Novo lote chegou (ordem estável da API). Renderiza a 1ª página de cards
        conforme chegam e atualiza contador vivo + barra. Não reordena."""
        if self._skeletons:
            self._drop_skeletons()
        self.records = records
        # Renderiza até page_size cards (uma vez); o resto fica no 'Carregar mais'.
        while self._stream_rendered < len(records) and self._stream_rendered < self.page_size:
            i = self._stream_rendered
            card = ArticleCard(self.feed, records[i], self._on_card_toggle, i)
            card.pack(fill="x", pady=4)
            card.set_selected(True)
            self.selected_indices.add(i)
            self.cards.append(card)
            self._stream_rendered += 1
        tot = total or loaded
        self.trail_lbl.configure(text=f"Encontrados {tot} · carregando {loaded}…")
        # Denominador: o que for menor entre limite e total real (no Ilimitado o
        # limite é uma sentinela gigante — usa o total da base).
        denom = min(self._stream_limit, tot) if tot else self._stream_limit
        self.progress.set(min(1.0, loaded / max(1, denom)))
        self._update_bottom_bar()

    def finish_stream(self, records: List[dict], count_trail: str):
        """Fim do carregamento: esconde a barra e faz o render final (sidebar,
        deduplicação, paginação). Sort/filtros só passam a valer agora."""
        self._drop_skeletons()
        self.progress.pack_forget()
        self.title_lbl.configure(text="Resultados da Busca")
        # load_results -> _clear_feed() destrói os cards de streaming (self.cards) e
        # re-renderiza a página 1 já com deduplicação/enriquecimento.
        self.load_results(records, count_trail)

    # ---------------- Barra de paginação, chips e facetas ----------------
    def _build_pager(self):
        """Rodapé de paginação, no modelo do WoS: setas, "Página N de M" e pular para N."""
        self.on_goto_page: Callable[[int], None] | None = None

        self._prev_btn = ctk.CTkButton(
            self.pager, text="◀", width=44, fg_color=WHITE, text_color=INK,
            border_width=2, border_color=INK, corner_radius=0, hover_color="#EEEEEE",
            command=lambda: self._goto(self.browse_page - 1))
        self._prev_btn.pack(side="left", padx=(12, 6), pady=6)

        self._page_lbl = ctk.CTkLabel(self.pager, text="", font=ctk.CTkFont(size=13, weight="bold"),
                                      text_color=INK)
        self._page_lbl.pack(side="left", padx=8)

        self._next_btn = ctk.CTkButton(
            self.pager, text="▶", width=44, fg_color=WHITE, text_color=INK,
            border_width=2, border_color=INK, corner_radius=0, hover_color="#EEEEEE",
            command=lambda: self._goto(self.browse_page + 1))
        self._next_btn.pack(side="left", padx=6)

        self._goto_entry = ctk.CTkEntry(self.pager, width=70, corner_radius=0,
                                        border_width=2, border_color=INK)
        self._goto_entry.pack(side="right", padx=(6, 12), pady=6)
        ctk.CTkLabel(self.pager, text=t("browse.goto"), font=ctk.CTkFont(size=12),
                     text_color=INK).pack(side="right")
        self._goto_entry.bind("<Return>", lambda _e: self._goto_from_entry())

    def _goto(self, pagina: int):
        """Vai para a página, presa à faixa válida — clicar ◀ na página 1 não faz nada."""
        alvo = max(1, min(int(pagina), max(1, self.browse_pages)))
        if alvo == self.browse_page:
            return
        if self.on_goto_page:
            self.on_goto_page(alvo)

    def _goto_from_entry(self):
        try:
            self._goto(int(self._goto_entry.get().strip()))
        except (TypeError, ValueError):
            pass

    def update_pager(self):
        """Atualiza rótulo e habilitação das setas a partir do estado corrente.

        O pager anuncia as páginas **navegáveis**, não as que os resultados dariam: com
        366.949 resultados a conta dá 14.678 páginas, mas o OpenAlex só entrega 400. Prometer
        as outras 14.278 é promessa quebrada — o total de resultados continua em destaque no
        cabeçalho (`set_result_header`), que é o lugar dessa informação.
        """
        from core.browse import format_count

        if self.browse_total <= 0:
            self.pager.grid_remove()
            return
        self.pager.grid()
        # "de 400 navegáveis" quando há resultados fora do alcance; "de 400" quando não há.
        chave = "browse.page_of_navigable" if self.browse_clipped else "browse.page_of"
        self._page_lbl.configure(text=t(chave,
                                        p=format_count(self.browse_page),
                                        t=format_count(self.browse_pages)))
        self._prev_btn.configure(state="normal" if self.browse_page > 1 else "disabled")
        self._next_btn.configure(
            state="normal" if self.browse_page < self.browse_pages else "disabled")

    def render_chips(self, chips: list[dict], on_remove: Callable[[str, str], None] | None = None):
        """Chips dos filtros ativos, cada um removível pelo ✕."""
        for w in self.chips_bar.winfo_children():
            w.destroy()
        if not chips:
            self.chips_bar.grid_remove()
            return
        self.chips_bar.grid()
        for c in chips:
            chip = ctk.CTkFrame(self.chips_bar, fg_color=WHITE, corner_radius=0,
                                border_width=2, border_color=INK)
            chip.pack(side="left", padx=(0, 6), pady=4)
            ctk.CTkLabel(chip, text=str(c.get("label") or c.get("key"))[:28],
                         font=ctk.CTkFont(size=12), text_color=INK).pack(side="left", padx=(8, 4))
            ctk.CTkButton(chip, text="✕", width=22, height=22, fg_color=WHITE, text_color=RED,
                          hover_color="#EEEEEE", corner_radius=0, border_width=0,
                          command=lambda f=c["field"], k=c["key"]: (on_remove or (lambda *a: None))(f, k)
                          ).pack(side="left", padx=(0, 4))

    def render_facets(self, facets: dict, on_toggle: Callable[[str, str], None] | None = None,
                      ativos: dict | None = None):
        """Sidebar "Refinar resultados" com as contagens reais do universo.

        Faceta com erro aparece com a nota de erro em vez de sumir sem explicação; provider
        que não suporta a faceta simplesmente não a envia, e ela não é desenhada.
        """
        from core.browse import FACET_LABELS, format_count

        for w in self.sidebar.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.sidebar, text=t("facet.title"),
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=INK).pack(
            anchor="w", pady=(4, 8))

        if not facets:
            ctk.CTkLabel(self.sidebar, text=t("facet.unsupported"), font=ctk.CTkFont(size=11),
                         text_color="#555555", wraplength=210, justify="left").pack(anchor="w")
            return

        marcados = ativos or {}
        for campo, faceta in facets.items():
            ctk.CTkLabel(self.sidebar, text=t(FACET_LABELS.get(campo, campo)),
                         font=ctk.CTkFont(size=12, weight="bold"), text_color=INK).pack(
                anchor="w", pady=(10, 2))
            if getattr(faceta, "error", ""):
                ctk.CTkLabel(self.sidebar, text=t("facet.error"), font=ctk.CTkFont(size=11),
                             text_color=RED, wraplength=210, justify="left").pack(anchor="w")
                continue
            for v in getattr(faceta, "values", []):
                marcado = str(v.key) in marcados.get(campo, [])
                var = ctk.BooleanVar(value=marcado)
                rotulo = f"{truncate_source_name(str(v.label))} ({format_count(v.count)})"
                ctk.CTkCheckBox(
                    self.sidebar, text=rotulo, variable=var, corner_radius=0,
                    font=ctk.CTkFont(size=12), fg_color=RED, hover_color=RED, text_color=INK,
                    command=lambda f=campo, k=str(v.key): (on_toggle or (lambda *a: None))(f, k)
                ).pack(anchor="w", pady=1)

    def show_facets_loading(self):
        """Sidebar com o título e um aviso de carregando, enquanto as facetas não chegam.

        Sem isto ela fica um retângulo branco vazio ao lado de uma lista já pronta — o que
        parece defeito, não espera.
        """
        for w in self.sidebar.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.sidebar, text=t("facet.title"),
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=INK).pack(
            anchor="w", pady=(4, 8))
        ctk.CTkLabel(self.sidebar, text=t("facet.loading"), font=ctk.CTkFont(size=12),
                     text_color="#555555").pack(anchor="w")

    def set_result_header(self, total: int, query: str = ""):
        """Cabeçalho compacto: "Resultados: 319.300" em destaque + a query embaixo."""
        from core.browse import format_count

        self.title_lbl.configure(text=t("browse.results", n=format_count(total)))
        if query:
            self.trail_lbl.configure(text=query[:90])

    # ---------------- Modo navegação (estilo Web of Science) ----------------
    def load_browse_page(self, page_obj, session=None, count_trail: str = ""):
        """Renderiza UMA página do modo navegação.

        Diferente de `load_results`, que recebia o corpus inteiro: aqui só chegam os 25
        registros da página corrente. A seleção é restaurada a partir de `selected_keys`,
        então marcar um registro na página 1 e voltar depois de passear pela 7 continua
        mostrando ele marcado.
        """
        self.browse_session = session
        self.browse_total = int(getattr(page_obj, "total", 0) or 0)
        self.browse_page = int(getattr(page_obj, "page", 1) or 1)
        # `navigable_pages`, não `pages`: o pager só pode oferecer página que abre.
        self.browse_pages = int(getattr(page_obj, "navigable_pages", None)
                                or getattr(page_obj, "pages", 1) or 1)
        self.browse_clipped = bool(getattr(page_obj, "clipped", False))

        erro = getattr(page_obj, "error", "")
        if erro:
            # Erro com mensagem própria (limite de uso da API) mostra a explicação e o que
            # fazer; o resto mostra o texto cru, que ao menos diz o que houve.
            chave = getattr(page_obj, "error_key", "")
            args = getattr(page_obj, "error_args", None) or {}
            self.show_error_state(t(chave, **args) if chave else erro,
                                  on_retry=getattr(self, "on_retry", None))
            # A busca falhou: as facetas não vêm. Deixar "Carregando filtros…" na sidebar
            # daria a impressão de que ainda há algo a caminho.
            self.render_facets({})
            return
        registros = list(getattr(page_obj, "records", []) or [])
        if not registros and self.browse_total == 0:
            self.show_empty_state()
            return

        self.records = registros
        self.filtered_indices = list(range(len(registros)))
        # Restaura a seleção da página a partir das chaves já marcadas.
        self.selected_indices = {i for i, r in enumerate(registros)
                                 if record_key(r) in self.selected_keys}

        if count_trail:
            self.trail_lbl.configure(text=count_trail)
        self._clear_feed()
        self.page = 0
        self._render_page()
        self._update_bottom_bar()
        self.update_pager()

    def select_all_on_page(self, marcar: bool = True):
        """Marca/desmarca os registros DA PÁGINA, mantendo a seleção das outras."""
        for r in self.records:
            chave = record_key(r)
            if marcar:
                self.selected_keys.add(chave)
            else:
                self.selected_keys.discard(chave)
        self.selected_indices = {i for i, r in enumerate(self.records)
                                 if record_key(r) in self.selected_keys}
        for i, card in enumerate(self.cards):
            if hasattr(card, "set_selected"):
                card.set_selected(i in self.selected_indices)
        self._update_bottom_bar()

    def selected_count(self) -> int:
        """Total selecionado em TODAS as páginas visitadas, não só na corrente."""
        return len(self.selected_keys)

    def show_empty_state(self, sugestoes: bool = True):
        """"Nenhum resultado" com o que fazer a respeito — não uma tela em branco."""
        self.records = []
        self.selected_indices = set()
        self._clear_feed()
        # grid, não pack: o conteúdo de `self.feed` é gerenciado por grid (os cards), e
        # misturar os dois gerenciadores no mesmo pai levanta TclError.
        self._empty_frame = ctk.CTkFrame(self.feed, fg_color="transparent")
        self._empty_frame.grid(row=0, column=0, sticky="ew", pady=40)
        ctk.CTkLabel(self._empty_frame, text=t("browse.empty_title"),
                     font=ctk.CTkFont(size=18, weight="bold"), text_color=INK).pack(pady=(0, 8))
        if sugestoes:
            ctk.CTkLabel(self._empty_frame, text=t("browse.empty_hint"),
                         font=ctk.CTkFont(size=13), text_color="#555555",
                         justify="left").pack()
        self._update_bottom_bar()

    def show_error_state(self, mensagem: str, on_retry: Callable | None = None):
        """Erro de rede com botão de tentar de novo — nunca falha silenciosa."""
        self.records = []
        self.selected_indices = set()
        self._clear_feed()
        self._error_frame = ctk.CTkFrame(self.feed, fg_color="transparent")
        self._error_frame.grid(row=0, column=0, sticky="ew", pady=40)
        ctk.CTkLabel(self._error_frame, text=t("browse.error_title"),
                     font=ctk.CTkFont(size=18, weight="bold"), text_color=RED).pack(pady=(0, 8))
        ctk.CTkLabel(self._error_frame, text=str(mensagem)[:200],
                     font=ctk.CTkFont(size=12), text_color="#555555",
                     wraplength=520, justify="left").pack(pady=(0, 12))
        self._retry_btn = ctk.CTkButton(
            self._error_frame, text=t("browse.retry"), fg_color=RED, text_color=WHITE,
            corner_radius=0, border_width=0, command=on_retry or (lambda: None))
        self._retry_btn.pack()
        self._update_bottom_bar()

    def has_empty_state(self) -> bool:
        f = getattr(self, "_empty_frame", None)
        return f is not None and f.winfo_exists()

    def has_error_state(self) -> bool:
        f = getattr(self, "_error_frame", None)
        return f is not None and f.winfo_exists()

    # ---------------- Drawer do Blink (BUG-B: não destrói o feed) ----------------
    def open_blink_drawer(self):
        """Abre o Blink AO LADO do feed (coluna 3), preservando cards/seleções/filtros/scroll.
        Retorna o textbox de saída para streaming. Idempotente (reusa o drawer)."""
        if getattr(self, "_blink_drawer", None) is not None and self._blink_drawer.winfo_exists():
            self._blink_drawer.grid()
            self._blink_output.configure(state="normal")
            self._blink_output.delete("1.0", "end")
            self._blink_output.configure(state="disabled")
            return self._blink_output
        self._blink_drawer = ctk.CTkFrame(self, width=340, fg_color=WHITE, corner_radius=0, border_width=2, border_color=INK)
        self._blink_drawer.grid(row=2, column=2, sticky="ns", padx=(0, 16), pady=8)
        self._blink_drawer.grid_propagate(False)
        self._blink_drawer.grid_rowconfigure(1, weight=1)
        self._blink_drawer.grid_columnconfigure(0, weight=1)
        hdr = ctk.CTkFrame(self._blink_drawer, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkLabel(hdr, text="✨ Blink", font=ctk.CTkFont(size=14, weight="bold"), text_color=INK).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=28, fg_color=WHITE, text_color=INK, border_width=1, border_color=INK, corner_radius=0, hover_color="#EEEEEE", command=self.close_blink_drawer).pack(side="right")
        self._blink_output = ctk.CTkTextbox(self._blink_drawer, wrap="word", font=ctk.CTkFont(size=12), fg_color=PAPER, text_color=INK, border_width=1, border_color=INK, corner_radius=0)
        self._blink_output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._blink_output.configure(state="disabled")
        return self._blink_output

    def close_blink_drawer(self):
        if getattr(self, "_blink_drawer", None) is not None and self._blink_drawer.winfo_exists():
            self._blink_drawer.grid_remove()

    def blink_drawer_open(self) -> bool:
        d = getattr(self, "_blink_drawer", None)
        # winfo_manager() == 'grid' quando gridado; '' após grid_remove (independe de
        # o toplevel estar mapeado — funciona headless).
        return d is not None and d.winfo_exists() and d.winfo_manager() == "grid"

    def _server_filters(self) -> dict:
        """Filtros da sidebar que mapeiam para a API (ano/OA/tipo/idioma)."""
        sf = {}
        if hasattr(self, "year_slider"):
            sf["year_start"] = int(self.year_slider.get())
        if hasattr(self, "oa_var") and self.oa_var.get():
            sf["is_oa"] = True
        if hasattr(self, "type_var") and self.type_var.get() != "Todos":
            sf["type"] = self.type_var.get()
        if hasattr(self, "lang_var") and self.lang_var.get() != "Todos":
            sf["language"] = self.lang_var.get()
        return sf

    def _build_sidebar(self):
        for widget in self.sidebar.winfo_children():
            widget.destroy()

        if not self.records:
            return

        # Re-consulta server-side com os filtros abaixo (encolhe a query de verdade,
        # não só esconde o que já foi baixado). Ano/OA/tipo/idioma vão para a API.
        if self.on_refilter is not None:
            ctk.CTkButton(self.sidebar, text="🔁 Rebuscar na fonte", corner_radius=0,
                          fg_color=INK, text_color=WHITE, hover_color="#333333",
                          command=lambda: self.on_refilter(self._server_filters())
                          ).pack(fill="x", pady=(0, 8))

        # Filters logic
        self.filter_vars = {}
        
        # Year
        # Rebuild limpo: descarta um slider de uma busca anterior (evita referência
        # a widget destruído em _apply_filters).
        if hasattr(self, "year_slider"):
            del self.year_slider
        years = [r.get("year") for r in self.records if r.get("year")]
        if years:
            min_y, max_y = min(years), max(years)
            ctk.CTkLabel(self.sidebar, text="Ano de Publicação", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(8, 0))
            # ESTE `if` é a proteção contra o ZeroDivisionError do CTkSlider: com ano único
            # (max_y == min_y) o slider não é criado. Havia aqui um `max(1, max_y - min_y)`
            # comentado como sendo a proteção — mas dentro deste ramo a diferença já é >= 1,
            # então era inalcançável, e o comentário apontava para o guarda errado.
            if max_y > min_y:
                self.year_slider = ctk.CTkSlider(self.sidebar, from_=min_y, to=max_y, number_of_steps=max_y - min_y, command=self._apply_filters)
                self.year_slider.set(min_y)
                self.year_slider.pack(fill="x", pady=4)
                self.year_lbl = ctk.CTkLabel(self.sidebar, text=f"A partir de {min_y}")
                self.year_lbl.pack(anchor="w")
            else:
                # Ano único: slider não faz sentido; rótulo estático.
                ctk.CTkLabel(self.sidebar, text=f"Ano único: {min_y}").pack(anchor="w")
            
        # Open Access
        ctk.CTkLabel(self.sidebar, text="Acesso", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        self.oa_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.sidebar, text="Apenas Open Access", variable=self.oa_var, command=self._apply_filters, corner_radius=0).pack(anchor="w", pady=4)
        
        # Journals (Top 10)
        ctk.CTkLabel(self.sidebar, text="Principais Fontes", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        journals = [r.get("source") for r in self.records if r.get("source")]
        top_journals = Counter(journals).most_common(10)
        self.journal_vars = {}
        for j, c in top_journals:
            var = ctk.BooleanVar(value=True)
            self.journal_vars[j] = var
            name = truncate_source_name(j)
            cb = ctk.CTkCheckBox(self.sidebar, text=f"{name} ({c})", variable=var, command=self._apply_filters, corner_radius=0)
            cb.pack(anchor="w", pady=2)
            
        # Type
        ctk.CTkLabel(self.sidebar, text="Tipo", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        types = [r.get("type", "unknown") for r in self.records if r.get("type")]
        self.type_var = ctk.StringVar(value="Todos")
        type_options = ["Todos"] + [t for t, _ in Counter(types).most_common()]
        ctk.CTkOptionMenu(self.sidebar, variable=self.type_var, values=type_options, command=self._apply_filters, corner_radius=0).pack(fill="x", pady=4)

        # Language
        ctk.CTkLabel(self.sidebar, text="Idioma", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(16, 0))
        languages = [r.get("language") for r in self.records if r.get("language")]
        self.lang_var = ctk.StringVar(value="Todos")
        lang_options = ["Todos"] + [lang for lang, _ in Counter(languages).most_common()]
        ctk.CTkOptionMenu(self.sidebar, variable=self.lang_var, values=lang_options, command=self._apply_filters, corner_radius=0).pack(fill="x", pady=4)
        
        # DECISÃO DE PRODUTO: importar NUNCA deduplica — a dedup é ação explícita
        # no Corpus (botão Deduplicar). Por isso não há mais opção aqui.

    def _apply_filters(self, *args):
        if hasattr(self, "year_slider"):
            y = int(self.year_slider.get())
            self.year_lbl.configure(text=f"A partir de {y}")
        else:
            y = 0
            
        oa_only = self.oa_var.get() if hasattr(self, "oa_var") else False
        allowed_journals = {j for j, v in self.journal_vars.items() if v.get()} if hasattr(self, "journal_vars") else set()
        sel_lang = self.lang_var.get() if hasattr(self, "lang_var") else "Todos"
        sel_type = self.type_var.get() if hasattr(self, "type_var") else "Todos"
        
        new_filtered = []
        for i, r in enumerate(self.records):
            if hasattr(self, "year_slider") and r.get("year", 0) < y:
                continue
            if oa_only and not r.get("is_oa"):
                continue
            if hasattr(self, "journal_vars") and r.get("source") in self.journal_vars and r.get("source") not in allowed_journals:
                continue
            if sel_lang != "Todos" and r.get("language") != sel_lang:
                continue
            if sel_type != "Todos" and r.get("type", "unknown") != sel_type:
                continue
            new_filtered.append(i)
            
        # Update selection: uncheck non-matching
        for i in self.filtered_indices:
            if i not in new_filtered and i in self.selected_indices:
                self.selected_indices.remove(i)
                
        self.filtered_indices = new_filtered
        self._clear_feed()
        self.page = 0
        self._render_page()
        self._update_bottom_bar()

    def _clear_feed(self):
        for c in self.cards:
            c.destroy()
        self.cards.clear()
        self.load_more_btn.pack_forget()
        # Os frames de estado (vazio/erro) usam grid dentro do mesmo `self.feed` em que o
        # "Carregar mais" usa pack. Deixar um deles vivo faz o Tk recusar o outro gerenciador
        # ("cannot use geometry manager pack ... grid is already managing"). Some com eles
        # aqui, que é o ponto por onde toda troca de conteúdo passa.
        for nome in ("_empty_frame", "_error_frame"):
            f = getattr(self, nome, None)
            if f is not None and f.winfo_exists():
                f.destroy()
            setattr(self, nome, None)
        
    def _render_page(self):
        start = self.page * self.page_size
        end = start + self.page_size
        indices = self.filtered_indices[start:end]
        
        self.load_more_btn.pack_forget()
        
        for i in indices:
            r = self.records[i]
            card = ArticleCard(self.feed, r, self._on_card_toggle, i)
            card.pack(fill="x", pady=4)
            card.set_selected(i in self.selected_indices)
            self.cards.append(card)
            
        self.page += 1
        if end < len(self.filtered_indices):
            self.load_more_btn.pack(pady=12)
            
    def _on_card_toggle(self, selected: bool, index: int):
        if selected:
            self.selected_indices.add(index)
        else:
            self.selected_indices.discard(index)
        # Espelha na seleção por CHAVE, que é a que atravessa a troca de página.
        if 0 <= index < len(self.records):
            chave = record_key(self.records[index])
            if selected:
                self.selected_keys.add(chave)
            else:
                self.selected_keys.discard(chave)
        self._update_bottom_bar()
        
    def _update_bottom_bar(self):
        self.sel_lbl.configure(text=f"{len(self.selected_indices)} selecionados de {len(self.records)}")
        
    def _show_summary_and_import(self):
        selected_records = [self.records[i] for i in sorted(list(self.selected_indices))]
        if not selected_records:
            # Nada marcado no modo navegação = "quero o conjunto inteiro desta busca".
            # É o download em massa, que passa pelo aviso de volume — e é a única forma de
            # trazer mais do que os 25 da página, já que navegar não baixa nada.
            if getattr(self, "browse_session", None) is not None and self.browse_total > 0:
                if getattr(self, "on_import_all", None):
                    self.on_import_all(self.browse_session, self.browse_total)
            return
            
        years = [r.get("year") for r in selected_records if r.get("year")]
        yr_range = f"{min(years)} - {max(years)}" if years else "N/A"
        
        # Summary Dialog
        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirmar Importação")
        dlg.geometry("400x300")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        
        ctk.CTkLabel(dlg, text="Resumo da Importação", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=16)
        
        frame = ctk.CTkFrame(dlg, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24)
        
        ctk.CTkLabel(frame, text=f"Total a importar: {len(selected_records)}", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=4)
        ctk.CTkLabel(frame, text=f"Período: {yr_range}").pack(anchor="w", pady=4)
        
        def on_confirm():
            dlg.destroy()
            self.on_import_confirm(selected_records, False)
            
        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", pady=16, padx=24)
        ctk.CTkButton(btns, text="Voltar", fg_color=WHITE, text_color=INK, border_width=2, border_color=INK, command=dlg.destroy).pack(side="left", expand=True, padx=4)
        ctk.CTkButton(btns, text="Confirmar", fg_color=RED, text_color=WHITE, command=on_confirm).pack(side="right", expand=True, padx=4)
