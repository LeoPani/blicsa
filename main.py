import sys
import logging
# Console em INFO desde o IMPORT: a migracao de settings roda ao importar core.i18n.
logging.basicConfig(level=logging.INFO, format="%(message)s")
import os
import re

#: FONTE ÚNICA da versão do app. Rodapé, janela "Sobre", `--version` e o `CITATION.cff`
#: derivam daqui. Antes havia cinco declarações independentes — `1.1.0-beta` aqui, `v3.0`
#: no rodapé e na janela Sobre, `0.9.0` no CHANGELOG e `2.0-upgrade` no CITATION.cff — e o
#: `v3.0` não correspondia a nenhuma versão que tivesse existido. Ele aparecia nas capturas
#: de tela da documentação.
__version__ = "2.1.0-beta.4"

try:
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    # `setdefault`, não atribuição: o ambiente REAL vence o arquivo.
                    #
                    # Era o contrário, e o efeito foi este: uma chave velha no `.env` do
                    # diretório de trabalho sobrescrevia silenciosamente a chave válida que
                    # o usuário tinha acabado de exportar no shell. A IA respondia 401, o
                    # app mostrava "falha na requisição", e não havia nada na tela ligando
                    # o erro a um arquivo que o usuário nem lembrava que existia.
                    #
                    # É também a semântica que todo mundo espera de `.env` (dotenv, docker
                    # compose, 12-factor): o arquivo preenche o que falta, não manda.
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
except Exception:
    pass
import contextlib
import json
import threading
import gc
from core.tk_seguro import instalar as _instalar_tk_seguro
_instalar_tk_seguro()   # finalizadores do Tk nunca chamam o Tk fora da thread da tela
import webbrowser
import tempfile
from pathlib import Path
from collections import Counter
import networkx as nx
import pandas as pd

import customtkinter as ctk
from core.i18n import t
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD as _TkDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from core.parsers import BibliometricParser, find_duplicates
from core.matrix_builders import NetworkGenerator, CLUSTER_PALETTE
from core.visualizer import compute_fa2_layout, build_plotly_map, export_plotly_html, export_figure_image, build_thematic_map, build_historiograph
from core.nlp import load_thesaurus
from ai.client import GroqBibliometricAnalyst, AIClientError

from ui.design_tokens import SIDEBAR_BG, CONTENT_BG, CARD_BG, CARD2_BG, ACCENT, ACCENT_HOV, TEXT_MUTED, MUTED, BLUE, YELLOW, RED, INK, PAPER, RED_HOV, RED_HOVER, WHITE_CARD, INK_HOV, BLUE_HOV, YELLOW_HOV
from ui.styles import get_color, TextboxLogHandler
from ui.components import DedupPreviewDialog, classify_dedup_reason, TrendChartWindow, VerificationDialog, MapCanvas, BurstDetectionWindow, HoverTooltip

# Force light mode globally since we use a custom light theme (Paper & Ink)
ctk.set_appearance_mode("Light")

log = logging.getLogger("blicsa")

def caminho_do_recurso(relativo: str) -> str:
    """Caminho absoluto de um arquivo empacotado (`assets/`, `locales/`), venha de onde vier.

    Os onze pontos que carregam imagem usavam caminho relativo ao DIRETÓRIO DE TRABALHO.
    Iniciado de dentro do repositório funcionava; iniciado de qualquer outro lugar — atalho,
    Spotlight, duplo clique — todo `Image.open("assets/...")` levantava `FileNotFoundError`,
    e o `except:` nu ao lado engolia. O efeito visível era a marca virar a palavra "Blicsa"
    na barra lateral, as abas perderem os ícones, as bandeiras e o splash sumirem — sem uma
    linha de log dizendo por quê.

    No binário do PyInstaller o problema é estrutural, não de hábito: os dados são extraídos
    para `sys._MEIPASS`, que nunca é o diretório de trabalho. O `Blicsa.spec` empacota
    `assets/` corretamente desde sempre (linha 16); faltava alguém procurar no lugar certo.
    """
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relativo)



OUTPUT_DIR  = Path(__file__).parent   # leitura de assets empacotados

# Onde o app GRAVA (B10, auditoria 2026-09). Rodando do código-fonte, nada muda: pasta do
# app e `reports/`. No executável (PyInstaller) a pasta do app é temporária (onefile, apagada
# ao fechar) ou protegida (instalado em "Arquivos de Programas"); lá tudo vai para ~/Blicsa,
# onde já ficam os projetos e o diretório servido.
if getattr(sys, "frozen", False):
    WORK_DIR    = Path.home() / "Blicsa" / "saidas"
    REPORTS_DIR = Path.home() / "Blicsa" / "reports"
else:
    WORK_DIR    = OUTPUT_DIR
    REPORTS_DIR = Path("reports")
WORK_DIR.mkdir(parents=True, exist_ok=True)
MAP_PATH    = str(WORK_DIR / "blicsa_mapa.html")
PLOTLY_PATH = str(WORK_DIR / "blicsa_plotly.html")

MAP_TYPES = [
    "Coocorrência de Palavras-chave",
    "Coautoria",
    "Cocitação de Referências",
    "Acoplamento Bibliográfico",
    "Citação Direta (paper→paper)",
    "Co-classificação IPC (patentes)",
    "Agrupamento Semântico (Embeddings)",
]
def _ThreadDaTela(*args, **kwargs):
    """`threading.Thread(...)` que, criada pela interface, coleta o lixo ANTES.

    Janelas fechadas (Revisar termos, Rankings…) deixam variáveis e imagens do Tk em ciclos
    de referência. Se a coleta automática do Python roda dentro de uma thread de trabalho, o
    `__del__` desses objetos chama o Tk fora da thread da tela, e o Tk pode abortar o
    programa inteiro ("Tcl_AsyncDelete: async handler deleted by the wrong thread"). Foi
    visto 1 vez em 4 medições do cálculo de mapa logo após fechar "Revisar termos". Coletar
    na thread da tela antes de cada trabalho em segundo plano tira esses objetos do caminho;
    custa menos de 1 ms. Todos os pontos criam e iniciam a thread na mesma linha.

    É função (e não subclasse) para que `threading.Thread` seja lido na hora da chamada:
    os testes que trocam a thread por uma síncrona continuam valendo.
    """
    if threading.current_thread() is threading.main_thread():
        try:
            gc.collect()
        except Exception:
            pass
    return threading.Thread(*args, **kwargs)


#: Tipos (índices de MAP_TYPES) agrupados pela pergunta que o mapa responde. Os títulos
#: entram na lista do seletor e não são escolhíveis; os nomes dos tipos não mudam porque
#: ficam gravados nos projetos.
GRUPOS_TIPO_DE_MAPA = (("map.grupo.termos", (0,)),
                       ("map.grupo.autores", (1,)),
                       ("map.grupo.referencias", (2, 3, 4)),
                       ("map.grupo.outros", (5, 6)))


def valores_tipo_de_mapa() -> list[str]:
    valores = []
    for chave, indices in GRUPOS_TIPO_DE_MAPA:
        valores.append(t(chave).upper())
        valores.extend(MAP_TYPES[i] for i in indices)
    return valores


VIZ_MODES  = [
    "Clusters", "Grau (Degree)", "Ano Médio",
    "Betweenness", "PageRank",
    "Densidade (matplotlib)", "Densidade (Plotly)",
]
FIELD_OPTS = [
    ("Palavras-chave (Author Keywords)", "keywords"),
    ("Títulos",                          "titles"),
    ("Resumos",                          "abstracts"),
    ("Títulos + Resumos",                "titles_abstracts"),
]

def _flag_options() -> list[tuple[str, str]]:
    """(código, arquivo da bandeira) para os idiomas que TÊM catálogo.

    Derivado de `core.i18n.available_langs()`: o seletor não pode oferecer um idioma que não
    existe. Idioma sem bandeira mapeada fica de fora do seletor gráfico (não vira botão
    quebrado); a lista abaixo é só o mapa código→arquivo.
    """
    from core.i18n import available_langs
    bandeiras = {"pt_BR": "flag-pt-br.png", "en": "flag-en.png",
                 "fr": "flag-fr.png", "de": "flag-de.png", "es": "flag-es.png"}
    return [(l, bandeiras[l]) for l in available_langs() if l in bandeiras]


# ── Main App ───────────────────────────────────────────────────────────────────
class ErroParaUsuario(Exception):
    """Falha cuja mensagem já foi escrita para o usuário (pode ir direto para a caixa)."""


class CampoInvalido(ErroParaUsuario, ValueError):
    """Valor digitado num campo numérico que não é número. A mensagem já é para o usuário."""


def _numero_do_campo(texto, nome_do_campo: str) -> float | None:
    """Lê um número digitado à mão: vazio → None; aceita vírgula decimal, "%" e espaços."""
    bruto = str(texto if texto is not None else "").strip().replace("%", "").replace(" ", "")
    if not bruto:
        return None
    try:
        return float(bruto.replace(",", "."))
    except ValueError:
        raise CampoInvalido(t("campo.nao_numero", campo=nome_do_campo, valor=str(texto).strip()))


_JARGAO_TECNICO = re.compile(
    r"Traceback|invalid literal|KeyError|IndexError|NoneType|AttributeError|TypeError|"
    r"object has no attribute|could not convert|Errno|not subscriptable|unexpected keyword|"
    r"division by zero|out of range|is not defined|codec can't", re.I)


def _mensagem_para_usuario(exc: BaseException, generica: str) -> str:
    """A mensagem da exceção, se ela já foi escrita para gente (ex.: "Coluna de códigos IPC
    não encontrada"); a genérica, se é erro interno de Python."""
    if isinstance(exc, ErroParaUsuario):
        return str(exc)
    texto = str(exc).strip()
    if not texto or isinstance(exc, (KeyError, IndexError, AttributeError, TypeError,
                                     NameError, ZeroDivisionError)) \
            or _JARGAO_TECNICO.search(texto):
        return generica
    return texto


class _ImportacaoVazia(Exception):
    """Nenhum registro foi lido dos arquivos escolhidos (B2)."""


class BlicsaApp(ctk.CTk):
    """
    Main application window and controller for the Blicsa UI.
    
    This class inherits from customtkinter.CTk and acts as the central hub
    managing all tabs (home, import, corpus, analyses, export), UI state,
    and background worker threads for data loading, search, and AI integration.
    """
    def __init__(self):
        super().__init__()
        self.title("Blicsa — Inteligência Bibliométrica")
        self.geometry("1380x880")
        self.minsize(1100, 700)
        self.resizable(True, True)
        self.configure(fg_color=CONTENT_BG)

        self._mapping_lock = threading.Lock()   # um mapa por vez (D4)
        self._file_paths: list[str]              = []
        self._file_formats: list[str]            = []
        self._dataframe                          = None
        self._generator: NetworkGenerator | None = None
        self._positions: dict                    = {}
        
        self._start_local_server()
        self._start_bridge()  # servidor da extensão de navegador (token + porta)

        self._map_canvas: MapCanvas | None       = None
        self._thesaurus: dict[str, str]          = {}
        self._thesaurus_path: str | None         = None
        self._candidate_counts: Counter          = Counter()
        self._candidate_scores: dict             = {}
        self._cluster_labels: dict[int, str]     = {}
        #: Origem de cada rótulo: "ia" ou "usuario". Rótulo editado à mão DEIXA de ser
        #: conteúdo de IA — marcar o texto que a pessoa escreveu seria tão errado quanto
        #: deixar de marcar o que a máquina escreveu.
        self._cluster_label_origins: dict = {}
        self._max_edge_weight: float             = 1.0

        #: Contexto de pesquisa do projeto ativo. String simples, e não `StringVar`, porque
        #: ele sobrevive à destruição da tela do Blink: `_refresh_language` reconstrói todos
        #: os widgets, e uma análise disparada de outra aba precisa do contexto mesmo que o
        #: chat nunca tenha sido montado nesta sessão.
        self._research_context: str = ""
        self._research_context_bar = None

        # Configuration variables
        self._map_type_var = ctk.StringVar(value=MAP_TYPES[0])
        self._field_var = ctk.StringVar(value="keywords")
        self._counting_var = ctk.StringVar(value="full")
        self._assoc_var = ctk.BooleanVar(value=True)
        self._min_occ_var = ctk.IntVar(value=3)
        self._max_nodes_var = ctk.StringVar(value="100")
        self._max_pct_var = ctk.StringVar(value="")
        self._fa2_iter_var = ctk.IntVar(value=500)
        self._linlog_var = ctk.BooleanVar(value=False)
        self._viz_mode_var = ctk.StringVar(value=VIZ_MODES[0])
        self._year_min_var = ctk.StringVar(value="")
        self._year_max_var = ctk.StringVar(value="")
        self._extra_sw_var = ctk.StringVar(value="")
        self._plotly_mode_var = ctk.StringVar(value="cluster")
        from core.settings import config_ia, get_api_key, settings_path
        log.info(f"[Settings] usando {settings_path()}")
        self._api_key_var = ctk.StringVar(value=get_api_key())
        # persiste no keyring com debounce (a cada edição no campo dos Ajustes)
        self._api_key_save_job = None
        #: Ligado enquanto `_sincronizar_chave_da_sessao` escreve na variável. O debounce
        #: existe para persistir o que o USUÁRIO digita; sem esta trava ele também
        #: re-persistia o que o app acabou de LER, e na remoção isso era destrutivo: com
        #: `GROQ_API_KEY` no ambiente, apagar a chave repunha a do ambiente dentro do
        #: keyring 900 ms depois — remover passava a gravar.
        self._sincronizando_chave = False
        def _schedule_key_save(*_):
            if self._sincronizando_chave:
                return
            if self._api_key_save_job:
                self.after_cancel(self._api_key_save_job)
            def _do():
                from core.settings import set_api_key
                set_api_key(self._api_key_var.get())
            self._api_key_save_job = self.after(900, _do)
        self._api_key_var.trace_add("write", _schedule_key_save)
        # Provedor, URL base e modelo VÊM DO DISCO, e voltam para ele a cada edição.
        # Eram inicializados só a partir do ambiente, com o preset do Groq como default, e
        # nunca gravados em lugar nenhum: quem configurava a OpenAI reabria o app apontado
        # para o Groq, e a chave da OpenAI — íntegra no cofre — voltava 401. A tela acusava
        # "chave inválida" sobre uma chave boa, e o efeito para o usuário era o app ter
        # esquecido a chave.
        _prov_ia, _base_ia, _modelo_ia = config_ia()
        self._ai_provider_var = ctk.StringVar(value=_prov_ia)
        self._ai_base_url_var = ctk.StringVar(value=_base_ia)
        self._ai_model_var = ctk.StringVar(value=_modelo_ia)
        self._config_ia_save_job = None
        # Mesma trava do debounce da chave: `_on_ai_provider_change` e a sincronização
        # escrevem nestas variáveis, e sem a trava a leitura seria re-persistida como se
        # fosse digitação do usuário.
        self._config_ia_sincronizando = False
        for _var_ia in (self._ai_base_url_var, self._ai_model_var):
            _var_ia.trace_add("write", lambda *_a: self._agendar_gravacao_config_ia())
        self._show_ai_modal = False
        self._prune_isolated_var = ctk.BooleanVar(value=True)
        self._prune_largest_var = ctk.BooleanVar(value=False)
        self._cluster_alg_var = ctk.StringVar(value="louvain")
        self._cluster_res_var = ctk.DoubleVar(value=1.0)
        # Fase 3 — controles de qualidade do mapa.
        self._binary_count_var = ctk.BooleanVar(value=True)   # padrão do VOSviewer
        self._attraction_var = ctk.DoubleVar(value=1.0)
        self._repulsion_var = ctk.DoubleVar(value=0.0)
        self._excluded_terms: set[str] = set()                # da lista revisável

        self._build_layout()
        self._attach_log_handler()
        self._setup_dnd()
        self._setup_shortcuts()
        # Fechar a janela para o servidor da extensão junto.
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    # ── Projeto ativo (passo 3: tudo vive numa pasta de projeto) ──────────
    def _open_project_slug(self, slug: str):
        """Abre projeto pelo card (corrige o antigo _load_project_file inexistente)."""
        self._set_busy("Carregando projeto...")
        try:
            self._set_active_project(slug)
            self._set_idle("Projeto carregado")
            has_corpus = self._dataframe is not None and not getattr(self._dataframe, "empty", True)
            self._switch_tab("corpus" if has_corpus else "import")
        except Exception as e:
            self._set_idle(t("projeto.erro_titulo"))
            self._erro_de_projeto(e, t("projeto.erro_titulo"))

    def _create_project_flow(self):
        dialog = ctk.CTkInputDialog(text="Digite o nome do novo projeto (Pesquisa):", title="Novo Projeto")
        proj_name = dialog.get_input()
        if not (proj_name and proj_name.strip()):
            return
        from core.project import create_project
        slug = create_project(proj_name.strip())
        log.info(f"[Sistema] Projeto '{proj_name.strip()}' criado ({slug}).")
        self._set_active_project(slug)
        self._switch_tab("import")

    def _set_active_project(self, slug: str):
        """Abre o projeto (pasta): restaura corpus + config + histórico."""
        from core.project import open_project
        data = open_project(slug)
        self._active_project = slug
        self._active_project_name = data.get("config", {}).get("name", slug)
        self._current_project_path = os.path.join(data["path"], "project.blicsa")
        self._restore_project_data(data)
        self._update_project_banner()
        if hasattr(self, "_hist_frame"):
            self._refresh_hist_tab()
        log.info(f"[Sistema] Projeto '{self._active_project_name}' aberto "
                 f"({len(data.get('backlog', []))} eventos no histórico).")

    def _update_project_banner(self):
        if not hasattr(self, "_project_banner_label"):
            return
        name = getattr(self, "_active_project_name", None)
        if name:
            self._project_banner_label.configure(text=t("project.banner", name=name))
            self._project_banner_warn.pack_forget()
            self._banner_new_btn.pack_forget()
            self._banner_open_btn.pack_forget()
        else:
            self._project_banner_label.configure(text=t("project.none"))
            self._project_banner_warn.pack(side="left", padx=8)
            self._banner_new_btn.pack(side="right", padx=(4, 16), pady=4)
            self._banner_open_btn.pack(side="right", padx=4, pady=4)

    def _backlog(self, action: str, detail: dict):
        """Grava no backlog do projeto ativo; sem projeto, não grava (fluxo avulso)."""
        slug = getattr(self, "_active_project", None)
        if not slug:
            return
        try:
            from core.project import append_backlog
            append_backlog(slug, action, detail)
        except Exception as e:
            log.info(f"[Backlog] falha ao gravar ({action}): {e}")

    def _record_export(self, formato: str, src_path, action: str = "export"):
        """Copia a saída para <projeto>/exports/ e registra no backlog."""
        slug = getattr(self, "_active_project", None)
        if not slug:
            return
        try:
            import shutil
            from core.project import project_dir
            src = Path(src_path)
            dest_dir = project_dir(slug) / "exports"
            dest_dir.mkdir(parents=True, exist_ok=True)
            rel = f"exports/{src.name}"
            if src.exists():
                shutil.copy2(src, dest_dir / src.name)
            self._backlog(action, {"formato": formato, "caminho_relativo": rel})
        except Exception as e:
            log.info(f"[Backlog] falha ao registrar export: {e}")

    # ── Extensão de navegador (passo 7) ───────────────────────────────────
    def _start_bridge(self):
        """Sobe o BridgeServer (token Bearer, CORS restrito a extensões) numa
        porta 8765-8768. Token persistente via settings; porta escolhida também
        gravada (a extensão lê nas options)."""
        import secrets
        from core.settings import get_settings, update_settings
        from core.bridge import BridgeServer

        self._bridge_server = None
        self._bridge_port = None

        s = get_settings()
        token = s.get("bridge_token")
        if not token:
            token = secrets.token_urlsafe(32)
            update_settings(bridge_token=token)
        self._bridge_token = token

        for port in (8765, 8766, 8767, 8768):
            srv = BridgeServer(token, port)
            srv.set_callbacks(self._on_extension_add)
            try:
                srv.start()  # bind acontece aqui; porta ocupada → OSError
            except OSError:
                continue
            self._bridge_server = srv
            self._bridge_port = port
            break

        if self._bridge_port:
            update_settings(bridge_port=self._bridge_port)
            log.info(f"[Extensão] Bridge ativo em http://127.0.0.1:{self._bridge_port}")
        else:
            log.info("[Extensão] Nenhuma porta livre em 8765-8768; extensão indisponível.")

    def _on_extension_add(self, record: dict) -> int:
        """Callback do /api/add: adiciona o registro ao corpus ativo SEM dedup
        automática (decisão de produto). Roda na thread do BridgeServer — só a
        atualização da UI é marshaled para a main thread. Retorna a contagem nova."""
        df_new = pd.DataFrame([record])
        if self._dataframe is not None and not getattr(self._dataframe, "empty", True):
            self._dataframe = pd.concat([self._dataframe, df_new], ignore_index=True)
        else:
            self._dataframe = df_new
        new_count = int(len(self._dataframe))

        detail = {
            "doi": record.get("doi", "") or "",
            "titulo": record.get("title", "") or "",
            "origem_url": record.get("origin_url", "") or "",
        }
        has_project = bool(getattr(self, "_active_project", None))
        if has_project:
            self._backlog("extension_add", detail)
        else:
            # Sem projeto: corpus avulso + diário legado (mesmo comportamento do
            # fluxo avulso), com o mesmo aviso persistente do banner.
            self._extension_legacy_diary(detail)

        log.info(f"[Extensão] +1 registro (DOI={detail['doi'] or '—'}); corpus={new_count}")
        # O dado já está commitado acima; a atualização da UI é best-effort e
        # nunca pode derrubar a resposta HTTP da extensão (200 mesmo se o
        # agendamento no loop Tk falhar).
        try:
            self.after(0, self._after_extension_add, new_count, has_project)
        except Exception:
            pass
        return new_count

    def _after_extension_add(self, new_count: int, has_project: bool):
        """Atualização de UI pós-adição (main thread)."""
        try:
            self._refresh_candidate_counts()
        except Exception:
            pass
        try:
            self._update_stats_tab()
        except Exception:
            pass
        try:
            if hasattr(self, "_refresh_corpus_tab"):
                self._refresh_corpus_tab()
        except Exception:
            pass
        if not has_project:
            log.info(f"[Extensão] {t('ext_added_no_project')}")
        self._set_idle(t("ext_added", count=new_count))

    def _extension_legacy_diary(self, detail: dict):
        """Registra a adição via extensão no diário legado (fluxo sem projeto)."""
        import os, json as _json, datetime
        proj_name = "Pesquisa_Atual"
        if getattr(self, "_current_project_path", None):
            proj_name = Path(self._current_project_path).stem
        diary_dir = os.path.expanduser(f"~/Blicsa/pesquisas/{proj_name}")
        os.makedirs(diary_dir, exist_ok=True)
        diary_path = os.path.join(diary_dir, "diary.json")
        diary = {"strings_usadas": [], "blink_usage": 0}
        if os.path.exists(diary_path):
            try:
                with open(diary_path, "r", encoding="utf-8") as df:
                    diary = _json.load(df)
            except Exception:
                pass
        diary.setdefault("extension_adds", []).append({
            **detail, "timestamp": datetime.datetime.now().isoformat()})
        with open(diary_path, "w", encoding="utf-8") as df:
            _json.dump(diary, df, indent=2, ensure_ascii=False)

    def _regenerate_bridge_token(self):
        """Gera um novo token, persiste e reinicia o bridge. A extensão precisa
        ser reconfigurada com o novo token."""
        import secrets
        from core.settings import update_settings
        new_token = secrets.token_urlsafe(32)
        update_settings(bridge_token=new_token)
        self._bridge_token = new_token
        try:
            if getattr(self, "_bridge_server", None):
                self._bridge_server.stop()
        except Exception:
            pass
        self._start_bridge()
        if hasattr(self, "_ext_token_var"):
            self._ext_token_var.set(self._bridge_token)
        if hasattr(self, "_ext_port_lbl"):
            self._ext_port_lbl.configure(text=str(self._bridge_port or "—"))
        self._set_idle(t("ext_regenerated"))

    def _copy_bridge_token(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._bridge_token or "")
            if hasattr(self, "_ext_copy_btn"):
                self._ext_copy_btn.configure(text=t("ext_copied"))
                self.after(1500, lambda: self._ext_copy_btn.configure(text=t("ext_copy")))
        except Exception:
            pass

    def _on_app_close(self):
        """Fechar pela janela é destruir a janela. A limpeza mora em `destroy`."""
        self.destroy()

    def destroy(self):
        """Desmonta a janela E o que ela deixou de pé FORA dela.

        Três coisas sobrevivem a um `destroy` de Tk, porque nenhuma é widget: o servidor da
        extensão, o servidor de estáticos e o handler de log pendurado no logger raiz. No
        app real o processo morre em seguida e ninguém nota. Numa suíte que abre e fecha
        dezenas de janelas no mesmo processo, as sobras se acumulam e o dano aparece longe
        de quem o causou:

        - sockets segurados faziam `tests/test_seguranca.py` levar `TimeoutError`
          intermitente, com a falha mudando de lugar a cada execução;
        - handlers empilhados no logger raiz, cada um escrevendo num Textbox já destruído,
          levaram `tests/test_search_browse.py` de 0,9 s para mais de setenta segundos.

        A limpeza fica aqui, e não em `_on_app_close`, porque `destroy()` é o que todo mundo
        chama — inclusive os testes, que nunca passam pelo protocolo da janela.
        """
        try:
            if getattr(self, "_bridge_server", None):
                self._bridge_server.stop()
                self._bridge_server = None
        except Exception:
            pass
        try:
            if getattr(self, "_http_server", None):
                self._http_server.shutdown()
                self._http_server.server_close()
                self._http_server = None
        except Exception:
            pass
        try:
            handler = getattr(self, "_gui_log_handler", None)
            if handler is not None:
                logging.getLogger().removeHandler(handler)
                self._gui_log_handler = None
        except Exception:
            pass
        super().destroy()

    def _attach_log_handler(self):
        """Item 6: o log box é alimentado por logging.Handler — sys.stdout e
        sys.stderr ficam intactos (tracebacks continuam no terminal)."""
        if not hasattr(self, "_log_box"):
            return
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        # eco no terminal (uma única vez)
        if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, TextboxLogHandler)
                   for h in root.handlers):
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(message)s"))
            root.addHandler(console)
        old = getattr(self, "_gui_log_handler", None)
        if old is not None:
            root.removeHandler(old)
        self._gui_log_handler = TextboxLogHandler(self._log_box)
        root.addHandler(self._gui_log_handler)

    def _start_local_server(self):
        # SEGURANÇA: serve APENAS ~/Blicsa/.serve (estáticos do webview copiados
        # para lá) — nunca a raiz do repo (settings com API key, código, projetos).
        if hasattr(self, '_local_server_port'): return
        from core.local_server import prepare_serve_dir, start_server
        self._serve_dir = prepare_serve_dir(OUTPUT_DIR)
        self._local_server_port, self._http_server = start_server(self._serve_dir)
        log.info(f"[HTTP Server] Started at http://127.0.0.1:{self._local_server_port} serving {self._serve_dir}")

    # ── Skeleton ───────────────────────────────────────────────────────

    def _build_welcome_screen(self):
        from ui.design_tokens import WHITE_CARD, INK, BLUE, PAPER
        from PIL import Image
        import os
        
        self._welcome_frame = ctk.CTkFrame(self, fg_color=PAPER, corner_radius=0)
        # Só na PRIMEIRA montagem. `_refresh_language` destrói tudo e chama `_build_layout`
        # de novo — e como esta tela é um `place()` por cima de tudo (que `_switch_tab` não
        # remove), trocar de idioma no meio do trabalho devolvia o usuário para
        # "novo projeto / abrir projeto" com o corpus dele intacto, porém invisível atrás.
        # Medido na Auditoria 1: aba continuava 'corpus', a tela mostrava as boas-vindas.
        if not getattr(self, "_boas_vindas_dispensadas", False):
            self._welcome_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        center = ctk.CTkFrame(self._welcome_frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        
        try:
            logo_img = ctk.CTkImage(light_image=Image.open(caminho_do_recurso("assets/branding/blicsa-logo-horizontal.png")), size=(300, 80))
            ctk.CTkLabel(center, image=logo_img, text="").pack(pady=(0, 20))
        except Exception as e:
            # Plano B com aviso. O `except:` nu daqui escondeu por meses que o arquivo pedido
            # (`blicsa-logo-vertical.png`) nunca existiu na pasta.
            log.warning(f"[Marca] logo da tela inicial não carregou: {type(e).__name__}: {e}")
            ctk.CTkLabel(center, text="Blicsa", font=ctk.CTkFont(size=56, weight="bold"), text_color=INK).pack(pady=(0, 20))
            
        ctk.CTkLabel(center, text=t("welcome.subtitle"),
                     font=ctk.CTkFont(size=18), text_color="#666666").pack(pady=(0, 40))
                     
        cards_frame = ctk.CTkFrame(center, fg_color="transparent")
        cards_frame.pack()
        
        def new_proj():
            self._dispensa_boas_vindas()
            self._create_project_flow()

        def load_proj():
            self._dispensa_boas_vindas()
            self._switch_tab("projects")
            
        # corner_radius=0: os dois cards estavam com 20, violando o "canto zero" do design
        # system — e é a PRIMEIRA tela que o usuário vê.
        c1 = ctk.CTkButton(cards_frame, text=f'{t("welcome.new")}', font=ctk.CTkFont(size=24, weight="bold"),
                           width=260, height=260, fg_color=BLUE, hover_color="#153a7a", corner_radius=0,
                           command=new_proj)
        c1.grid(row=0, column=0, padx=30)

        c2 = ctk.CTkButton(cards_frame, text=f'{t("welcome.load")}', font=ctk.CTkFont(size=24, weight="bold"),
                           width=260, height=260, fg_color=WHITE_CARD, text_color=INK, hover_color="#E5E5E5",
                           border_width=2, border_color=INK, corner_radius=0,
                           command=load_proj)
        c2.grid(row=0, column=1, padx=30)

    def _dispensa_boas_vindas(self):
        """Tira a tela de boas-vindas e marca que ela não deve voltar sozinha.

        A marca é o que sobrevive ao `_build_layout` da troca de idioma. Sem ela, quem
        escolheu um caminho era devolvido ao começo toda vez que mexesse no seletor.
        """
        self._boas_vindas_dispensadas = True
        if getattr(self, "_welcome_frame", None) is not None:
            self._welcome_frame.place_forget()

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        self._content = ctk.CTkFrame(self, fg_color=CONTENT_BG, corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(1, weight=1)
        
        # Banner "Projeto Atual" — sempre visível; sem projeto mostra o aviso do
        # fluxo avulso + criar/abrir rápido (canto reto, sem sombra).
        from ui.design_tokens import BLUE
        self._project_banner = ctk.CTkFrame(self._content, fg_color=BLUE, corner_radius=0, height=34)
        self._project_banner.grid(row=0, column=0, sticky="ew")
        self._project_banner_label = ctk.CTkLabel(self._project_banner, text="", text_color="white", font=ctk.CTkFont(weight="bold", size=13))
        self._project_banner_label.pack(side="left", padx=(16, 8), pady=4)
        self._project_banner_warn = ctk.CTkLabel(self._project_banner, text=t("project.none_warning"),
                                                 text_color="#CFE0FF", font=ctk.CTkFont(size=12))
        self._banner_open_btn = ctk.CTkButton(self._project_banner, text=t("project.open_quick"), height=22,
                                              width=110, corner_radius=0, fg_color="transparent", text_color="#FFFFFF",
                                              border_width=1, border_color="#FFFFFF", hover_color="#153a7a",
                                              command=lambda: self._switch_tab("projects"))
        self._banner_new_btn = ctk.CTkButton(self._project_banner, text=t("project.create_quick"), height=22,
                                             width=110, corner_radius=0, fg_color=WHITE_CARD, text_color=INK,
                                             hover_color="#E5E5E5", command=self._create_project_flow)
        self._update_project_banner()

        self._tabs_container = ctk.CTkFrame(self._content, fg_color="transparent")
        self._tabs_container.grid(row=1, column=0, sticky="nsew")
        self._tabs_container.grid_columnconfigure(0, weight=1)
        self._tabs_container.grid_rowconfigure(0, weight=1)

        self._tabs: dict[str, ctk.CTkFrame] = {
            "home":    self._build_tab_home(),
            "projects": self._build_tab_projects(),
            "import":  self._build_tab_import(),
            "review":  self._build_tab_review(),
            "corpus":  self._build_tab_corpus(),
            "stats":   self._build_tab_stats(),
            "credenciais": self._build_tab_credenciais(),
            "analises": self._build_tab_analises(),
            "hist":     self._build_tab_hist(),
            "relatorio": self._build_tab_relatorio(),
            "galeria":  self._build_tab_gallery(),
            "export":  self._build_tab_export(),
        }
        self._switch_tab("home")
        
        self._build_welcome_screen()

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=SIDEBAR_BG, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)

        try:
            from PIL import Image
            logo_img = ctk.CTkImage(light_image=Image.open(caminho_do_recurso("assets/branding/blicsa-logo-horizontal.png")), size=(180, 48))
            ctk.CTkLabel(sb, image=logo_img, text="").grid(row=0, column=0, padx=16, pady=(30, 22), sticky="w")
        except Exception as e:
            log.warning(f"[Marca] logo da barra lateral não carregou: {type(e).__name__}: {e}")
            ctk.CTkLabel(sb, text="Blicsa",
                         font=ctk.CTkFont(size=34, weight="bold"),
                         text_color=ACCENT).grid(
                row=0, column=0, padx=22, pady=(30, 22), sticky="w")

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self._nav_icons: dict[str, tuple] = {}
        
        from PIL import Image
        #: A lista sai do `for` para poder ser CONTADA. As linhas do rodapé da barra eram
        #: números fixos (10, 11, 12, 13, 14) escolhidos quando havia dez itens, e o badge
        #: do corpus já dividia a linha 10 com o último botão. Acrescentar a aba de
        #: Relatório poria o décimo primeiro botão em cima da linha que estica. Derivado da
        #: contagem, o rodapé desce sozinho quando uma aba nova entra.
        itens_de_navegacao = [
            # "Blink" e "Corpus" ficam literais de propósito: são iguais nos três idiomas
            # (nome do produto e termo técnico consagrado). O resto passa pelo catálogo —
            # antes 5 destes rótulos eram hardcoded em português e a barra lateral aparecia
            # meio traduzida em en/fr.
            ("home",     "sparkle", "Blink"),
            ("projects", "house",   t("projects.title")),
            ("credenciais", "stack", t("nav.credenciais")),
            ("import",   "magnet",  t("nav.collect")),
            ("corpus",   "stack",   "Corpus"),
            ("stats",    "chart-network", t("nav.stats")),
            ("analises", "chart-network", t("nav.analyses")),
            ("hist",     "stack",   t("history.title")),
            ("relatorio", "stack",  t("nav.relatorio")),
            ("galeria",  "stack",   t("nav.gallery")),
            ("export",   "export-arrow", t("nav.export")),
        ]
        for i, (key, icon_name, label_text) in enumerate(itens_de_navegacao, start=1):
            # Navegação em TEXTO, sem ícone, e isso é escolha.
            #
            # `assets/icons/` tem 14 arquivos e apenas DUAS imagens distintas: os sete
            # `_normal` são byte a byte idênticos entre si, e os sete `_active` também.
            # O conjunto nunca foi desenhado — é espaço reservado. Ligá-lo põe o mesmo
            # círculo ao lado de Blink, Corpus, Estatísticas e Exportar: dez repetições
            # de um símbolo que não distingue nada.
            #
            # Os nomes dos arquivos aqui já estão corretos (`{icon_name}_normal.png`, e
            # `chart-network`/`export-arrow` no lugar de `chart`/`export`), o que antes não
            # era verdade. Quando existir um conjunto de ícones de fato, basta voltar a
            # carregar por `caminho_do_recurso`.
            self._nav_icons[key] = (None, None)
            image_arg = None
                
            btn = ctk.CTkButton(
                sb, text=f" {label_text}", anchor="w", image=image_arg,
                font=ctk.CTkFont(size=14, weight="normal"),
                fg_color="transparent", hover_color="#e0e0e0", text_color=INK,
                corner_radius=0, height=44, border_width=0, border_color=RED,
                command=lambda k=key: self._switch_tab(k)
            )
            btn.grid(row=i, column=0, padx=10, pady=2, sticky="ew")
            
            # Hover micro-interaction (underline)
            def on_enter(e, b=btn):
                b.configure(font=ctk.CTkFont(size=14, weight="bold", underline=True))
            def on_leave(e, b=btn, k=key):
                active = getattr(self, '_current_tab_key', '') == k
                b.configure(font=ctk.CTkFont(size=14, weight="bold" if active else "normal", underline=False))
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            
            self._nav_btns[key] = btn

        # Rodapé da barra, ancorado ao FIM da navegação: a linha que estica vem logo depois
        # do último botão, e o resto desce a partir dela.
        linha = len(itens_de_navegacao) + 1
        sb.grid_rowconfigure(linha, weight=1)

        self._corpus_badge = ctk.CTkLabel(sb, text=t("corpus.badge_none"), text_color=MUTED, font=ctk.CTkFont(size=11))
        self._corpus_badge.grid(row=linha + 1, column=0, padx=16, pady=(10, 5), sticky="sw")
        
        try:
            gear_img = None   # mesmo espaço reservado dos ícones de navegação: ver acima
        except: gear_img = None
        self._settings_btn = ctk.CTkButton(sb, text=t("menu_settings"), image=gear_img, anchor="w", font=ctk.CTkFont(size=11), fg_color="transparent", hover_color="#e0e0e0", text_color=INK, corner_radius=0, height=32, border_width=1, border_color=INK, command=self._show_settings)
        self._settings_btn.grid(row=linha + 2, column=0, padx=16, pady=(0, 10), sticky="ew")

        self._status_square = ctk.CTkFrame(sb, width=10, height=10, fg_color=BLUE, corner_radius=0)
        self._status_square.grid(row=linha + 3, column=0, padx=(16, 0), pady=(0, 2), sticky="sw")
        self._status_lbl = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._status_lbl.grid(row=linha + 3, column=0, padx=(32, 16), pady=(0, 2), sticky="sew")

        # BLUE, não YELLOW: progresso é estado da aplicação, não conteúdo gerado por IA.
        self._progress_bar = ctk.CTkProgressBar(sb, mode="indeterminate", height=5, progress_color=BLUE, fg_color=PAPER, border_width=1, border_color=INK, corner_radius=0)
        self._progress_bar.grid(row=linha + 3, column=0, padx=16, pady=(0, 8), sticky="sew")
        self._progress_bar.grid_remove()

        self._about_btn = ctk.CTkButton(sb, text=f"v{__version__} • Blicsa Engine", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED, fg_color="transparent", hover_color="#e0e0e0", corner_radius=0, command=self._show_about)
        self._about_btn.grid(row=linha + 4, column=0, padx=22, pady=(0, 16), sticky="sw")

    # ── Drag-and-drop ──────────────────────────────────────────────────
    def _setup_dnd(self):
        if not _DND_AVAILABLE:
            return
        try:
            _TkDnD._require(self)
            self._file_list_frame.drop_target_register(DND_FILES)
            self._file_list_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        import re as _re
        raw = event.data or ""
        # tkinterdnd2 wraps paths with braces on macOS/Windows for spaces
        paths = _re.findall(r"\{([^}]+)\}|(\S+)", raw)
        paths = [p[0] or p[1] for p in paths]
        for path in paths:
            path = path.strip()
            if path and path not in self._file_paths:
                fmt = self._auto_detect_format(path)
                self._file_paths.append(path)
                self._file_formats.append(fmt)
                self._add_file_row(path, fmt)

    # ── Keyboard shortcuts ─────────────────────────────────────────────
    def _setup_shortcuts(self):
        self.bind_all("<Control-g>", lambda _: self._run_mapping())
        self.bind_all("<Control-G>", lambda _: self._run_mapping())
        self.bind_all("<Control-e>", lambda _: self._switch_tab("export"))
        self.bind_all("<Control-E>", lambda _: self._switch_tab("export"))
        self.bind_all("<Control-i>", lambda _: self._run_ai())
        self.bind_all("<Control-I>", lambda _: self._run_ai())
        self.bind_all("<Control-r>", lambda _: self._reset_view())
        self.bind_all("<Control-R>", lambda _: self._reset_view())
        self.bind_all("<Control-f>", lambda _: self._switch_tab("home"))
        self.bind_all("<Control-F>", lambda _: self._switch_tab("home"))
        self.bind_all("<Escape>",    lambda _: self._reset_view())

    def _set_busy(self, msg: str = "Processando…"):
        self._status_lbl.configure(text=msg)
        if msg == 'Concluído' or 'Sucesso' in msg: self.blink_status()
        self._progress_bar.grid()
        self._progress_bar.start()

    
    def blink_status(self):
        try:
            from core.settings import get_settings
            if get_settings().get("reduce_animations"): return
        except Exception: pass
        if hasattr(self, '_status_square'):
            orig_h = self._status_square.winfo_height()
            self._status_square.configure(height=2)
            self.after(250, lambda: self._status_square.configure(height=10))

    
    
    def _janela_secundaria(self, dlg):
        """Centraliza uma janela auxiliar e a deixa se comportar como janela do sistema.

        Ajustes e Sobre eram `overrideredirect(True)` + `-topmost`: sem barra de título e
        acima de TODOS os aplicativos. Três consequências, todas relatadas como "não deixa
        voltar para outra janela": não dava para arrastar a janela para o lado, não dava
        para fechá-la pelo botão do sistema (só pelo OK, que nem sempre estava à vista), e
        ela continuava flutuando por cima do navegador ou do editor depois que a pessoa
        trocava de aplicativo. `-topmost` é para alerta que não pode ser perdido; um
        diálogo de preferências não é isso.

        `transient` no lugar: a janela acompanha a principal (minimiza junto, some junto),
        fica acima DELA e de mais nada. `Escape` fecha, porque é o que a mão faz.
        """
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        try:
            dlg.tk.call("tk::PlaceWindow", str(dlg), "center")
        except Exception:
            pass
        return dlg

    def _show_settings(self):
        import tkinter as tk
        from PIL import Image, ImageTk

        dlg = tk.Toplevel(self)
        dlg.title(t("menu_settings"))
        dlg.geometry("400x430")
        dlg.configure(bg="#F6F4EE")
        self._janela_secundaria(dlg)

        f = tk.Frame(dlg, bg="#141414")
        f.pack(fill="both", expand=True)
        content = tk.Frame(f, bg="#F6F4EE")
        content.pack(fill="both", expand=True, padx=3, pady=3)
        
        tk.Label(content, text=t("menu_settings"), font=("Arial", 16, "bold"), bg="#F6F4EE", fg="#141414").pack(pady=(20, 10))
        
        # Animations toggle (settings no user_config_dir via core.settings)
        from core.settings import get_settings, update_settings
        reduce = bool(get_settings().get("reduce_animations", False))

        import customtkinter as ctk
        var = ctk.BooleanVar(value=reduce)
        def toggle():
            update_settings(reduce_animations=var.get())
            
        chk = ctk.CTkCheckBox(content, text=t("reduce_animations"), variable=var, command=toggle, text_color="#141414", fg_color="#DF3117", hover_color="#B82813", corner_radius=0)
        chk.pack(pady=10)
        
        # Flags
        flag_f = tk.Frame(content, bg="#F6F4EE")
        flag_f.pack(pady=10)
        def set_l(l):
            from core.i18n import set_lang
            set_lang(l)
            self._refresh_language()
            dlg.destroy()
            
        try:
            for i, (l, f_name) in enumerate(_flag_options()):
                img = ImageTk.PhotoImage(Image.open(caminho_do_recurso(f"assets/branding/{f_name}")).resize((32, 22)))
                btn = tk.Button(flag_f, image=img, command=lambda x=l: set_l(x), bg="#F6F4EE", relief="flat", bd=2, highlightbackground="#141414")
                btn.image = img
                btn.grid(row=0, column=i, padx=5)
        except:
            pass

        # As credenciais saíram daqui. Ficavam em três lugares — este diálogo, o painel do
        # Blink e a barra de parâmetros do mapa —, cada um com um comportamento: só o do
        # Blink testava a conexão, só este mascarava a chave, e o da barra, que era o que
        # de fato alimentava as chamadas, não fazia nem um nem outro. A aba de Credenciais
        # é a fonte única; um quarto lugar seria repetir o problema.
        tk.Label(content, text=t("settings.ai_section"), font=("Arial", 12, "bold"),
                 bg="#F6F4EE", fg="#141414").pack(pady=(16, 2))
        tk.Button(content, text=t("cred.titulo"),
                  command=lambda: (dlg.destroy(), self._switch_tab("credenciais")),
                  bg="#F6F4EE", fg="#141414", relief="flat",
                  highlightbackground="#141414", bd=2).pack(pady=(2, 4))

        close = tk.Button(content, text=t("settings.ok"),
                          command=dlg.destroy,
                          bg="#DF3117", fg="white", relief="flat",
                          highlightbackground="#141414", bd=2)
        close.pack(side="bottom", pady=20)

    def _on_research_context_change(self, texto: str):
        """Espelha a barra na variável que sobrevive à reconstrução da tela.

        Sem isso, trocar de idioma (que destrói e remonta todos os widgets) apagaria o
        contexto que a pessoa acabou de escrever, sem aviso e sem jeito de recuperar.
        """
        self._research_context = texto

    def _contexto_pesquisa(self) -> str:
        """Contexto de pesquisa do projeto ativo, normalizado. Vazio quando não há.

        Ponto único de leitura: a barra é a fonte da verdade enquanto a tela do Blink existe,
        e a variável guarda o valor quando ela não existe (o app pode disparar análise de IA
        a partir de outra aba, sem nunca ter montado o chat).
        """
        from core.research_context import normalizar

        barra = getattr(self, "_research_context_bar", None)
        if barra is not None:
            try:
                if barra.winfo_exists():
                    return barra.valor()
            except Exception:
                pass
        return normalizar(getattr(self, "_research_context", ""))

    def _blink_system_prompt(self, dados_corpus: str = "") -> str:
        """System prompt na ordem fixa: papel → idioma → contexto do usuário → corpus.

        A ordem e o corte de orçamento moram em `core/research_context.py`, sem Tk, para
        serem testáveis sem abrir janela. Ver o cabeçalho daquele módulo para o porquê de o
        contexto do usuário vir **antes** dos dados e de o corte sacrificar abstracts.
        """
        from core.i18n import get_lang
        from core.research_context import diretiva_idioma, montar_system_prompt

        return montar_system_prompt(
            papel=t("blink.system_prompt"),
            idioma=diretiva_idioma(get_lang()),
            contexto_usuario=self._contexto_pesquisa(),
            dados_corpus=dados_corpus,
            cabecalho_contexto=t("ai.contexto_prompt"),
            cabecalho_corpus=t("blink.rag_contexto"),
        )

    def _refresh_language(self):
        curr_tab = getattr(self, '_current_tab_key', "home")
        for widget in self.winfo_children():
            widget.destroy()
        self._build_layout()
        self._attach_log_handler()
        self._setup_shortcuts()
        self._setup_dnd()
        self._switch_tab(curr_tab)

    def _show_about(self):
        import tkinter as tk
        from PIL import Image
        import webbrowser
        
        dlg = tk.Toplevel(self)
        dlg.title(t("menu_about"))
        dlg.geometry("400x350")
        dlg.configure(bg="#F6F4EE")
        self._janela_secundaria(dlg)

        # 3px ink border
        f = tk.Frame(dlg, bg="#141414")
        f.pack(fill="both", expand=True)
        content = tk.Frame(f, bg="#F6F4EE")
        content.pack(fill="both", expand=True, padx=3, pady=3)
        
        try:
            from PIL import ImageTk
            img = ImageTk.PhotoImage(Image.open(caminho_do_recurso("assets/branding/blicsa-logo-horizontal.png")).resize((200, 54)))
            lbl = tk.Label(content, image=img, bg="#F6F4EE")
            lbl.image = img
            lbl.pack(pady=(20, 0))
        except Exception as e:
            log.warning(f"[Marca] logo dos Ajustes não carregou: {type(e).__name__}: {e}")
            tk.Label(content, text="Blicsa", font=("Arial", 24, "bold"), bg="#F6F4EE", fg="#141414").pack(pady=(20, 0))
            
        tk.Label(content, text="just blink", font=("Arial", 12), bg="#F6F4EE", fg="#8A877F").pack(pady=(0, 10))
        tk.Label(content, text=f"v{__version__}", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        
        tk.Label(content, text="Desenvolvido por ICSA/UFOP", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        tk.Label(content, text="Licença MIT", font=("Arial", 10), bg="#F6F4EE", fg="#141414").pack(pady=5)
        
        btn_f = tk.Frame(content, bg="#F6F4EE")
        btn_f.pack(side="bottom", fill="x", pady=20, padx=20)
        
        gh = tk.Button(btn_f, text="GitHub", command=lambda: webbrowser.open("https://github.com"), bg="#F6F4EE", fg="#141414", relief="flat", highlightbackground="#141414", bd=2)
        gh.pack(side="left", padx=10)
        
        close = tk.Button(btn_f, text="OK", command=dlg.destroy, bg="#DF3117", fg="white", relief="flat", highlightbackground="#141414", bd=2)
        close.pack(side="right", padx=10)

    def _set_idle(self, msg: str = ""):
        self._progress_bar.stop()
        self._progress_bar.grid_remove()
        self._status_lbl.configure(text=msg)
        if msg == 'Concluído' or 'Sucesso' in msg: self.blink_status()

    def _switch_tab(self, tab_key: str):
        prev = getattr(self, '_current_tab_key', None)
        if prev and prev != tab_key:
            self._previous_tab_key = prev
        self._current_tab_key = tab_key
        
        if hasattr(self, '_blink_back_btn'):
            if tab_key == 'home' and getattr(self, '_previous_tab_key', None):
                self._blink_back_btn.pack(side="right", padx=20)
            else:
                self._blink_back_btn.pack_forget()
        for key, frame in self._tabs.items():
            frame.grid_remove()
        if tab_key in self._tabs:
            if tab_key == "corpus":
                self._refresh_corpus_tab()
            elif tab_key == "hist":
                self._refresh_hist_tab()
            elif tab_key == "relatorio":
                self._refresh_relatorio_tab()
            elif tab_key == "stats" and getattr(self, "_stats_pendente", False):
                self._calcular_estatisticas()
            self._tabs[tab_key].grid(row=0, column=0, sticky="nsew")
        
        for k, btn in self._nav_btns.items():
            active = (k == tab_key)
            img_normal, img_active = self._nav_icons.get(k, (None, None))
            btn.configure(
                border_spacing=6 if active else 2, # spacing adjustment for left bar
                border_width=6 if active else 0, 
                font=ctk.CTkFont(size=14, weight="bold" if active else "normal", underline=False),
                image=img_active if active and img_active else img_normal
            )

    def _toggle_theme(self):
        current = ctk.get_appearance_mode().lower()
        new_mode = "light" if current == "dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self._update_treeview_style()
        if self._map_canvas:
            self._map_canvas.update_theme()
            if self._map_canvas._G and self._map_canvas._pos:
                self._map_canvas.render(
                    self._map_canvas._G,
                    self._map_canvas._pos,
                    mode=self._map_canvas._last_mode,
                    node_scale=self._map_canvas._node_scale,
                    edge_opacity=self._map_canvas._edge_opacity,
                    edge_threshold=self._map_canvas._edge_threshold,
                )

    def _update_treeview_style(self):
        _ts = ttk.Style()
        _ts.theme_use("default")
        bg_col = get_color(CARD2_BG)
        fg_col = "black" if ctk.get_appearance_mode().lower() == "light" else "#e0e0e0"
        header_bg = get_color(CARD_BG)
        sel_bg = "#b0c4de" if ctk.get_appearance_mode().lower() == "light" else "#2a2a5a"
        sel_fg = "black" if ctk.get_appearance_mode().lower() == "light" else "white"

        _ts.configure("Blicsa.Treeview",
            background=bg_col,
            fieldbackground=bg_col,
            foreground=fg_col,
            rowheight=28,
            font=("Inter", 11),
            borderwidth=0,
        )
        _ts.configure("Blicsa.Treeview.Heading",
            background=header_bg,
            foreground=ACCENT,
            font=("Inter", 11, "bold"),
            relief="flat",
            padding=(0, 5)
        )
        _ts.map("Blicsa.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        
        _ts.map("Blicsa.Treeview.Heading",
            background=[("active", ACCENT_HOV)],
        )

    # ── UI helpers ─────────────────────────────────────────────────────
    def _tab(self) -> ctk.CTkFrame:
        f = ctk.CTkFrame(getattr(self, "_tabs_container", self._content), fg_color=CONTENT_BG)
        f.grid_columnconfigure(0, weight=1)
        return f

    def _card(self, parent, row: int, pady: int = 8) -> ctk.CTkFrame:
        c = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=0)
        c.grid(row=row, column=0, padx=24, pady=pady, sticky="nsew")
        c.grid_columnconfigure(0, weight=1)
        return c

    def _h1(self, parent, text: str, row: int):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=row, column=0, padx=28, pady=(18, 4), sticky="w")

    def _btn(self, parent, text: str, cmd,
             color=ACCENT, hover=ACCENT_HOV,
             height: int = 44, **kw) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, height=height,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=color, hover_color=hover,
            text_color="#000" if color == ACCENT else "white",
            command=cmd, **kw)

    def _add_blink_message(self, role, text="", gerado_por_ia=True):
        from core.markdown_parser import configure_markdown_tags, insert_markdown
        row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
        row.pack(fill="x", pady=5)
        
        from ui.design_tokens import BLUE, WHITE_CARD, INK
        from ui.ai_marking import LARGURA_FAIXA, YELLOW as _AMARELO_IA, selo_ia

        # Toda fala do assistente é conteúdo gerado por IA — e este método é o funil por onde
        # passam o chat, os insights do corpus, as obras seminais, a análise temática, o
        # Sankey, a historiografia e o assistente de importação. Marcar aqui cobre os sete
        # sem espalhar a convenção por sete lugares que podem divergir.
        # `gerado_por_ia=False` para texto do PRÓPRIO app (saudação, avisos): ele vem do
        # catálogo i18n, escrito por quem desenvolveu, e marcá-lo como IA diria ao usuário
        # que um modelo escreveu o que nós escrevemos. Diluir o sinal nos dois sentidos é
        # igualmente ruim.
        e_ia = role == "assistant" and gerado_por_ia
        bubble = ctk.CTkFrame(row, fg_color=BLUE if role == "user" else WHITE_CARD, corner_radius=0, border_width=0 if role == "user" else 2, border_color=INK)
        bubble.pack(side="right" if role == "user" else "left", padx=10, pady=2)

        if e_ia:
            # Faixa amarela à esquerda + selo textual. A cor NUNCA vem sozinha: em impressão
            # P&B e para daltônicos, o selo é a informação que sobra.
            # `fill="y"` sem `expand`: a faixa acompanha a altura do conteúdo em vez de
            # esticar o bloco. Com `expand=True` o frame reservava a altura padrão do
            # CTkFrame e deixava um vão branco embaixo do texto.
            faixa = ctk.CTkFrame(bubble, width=LARGURA_FAIXA, height=1,
                                 fg_color=_AMARELO_IA, corner_radius=0)
            faixa.pack(side="left", fill="y", expand=False)
            faixa.pack_propagate(False)
            interno = ctk.CTkFrame(bubble, fg_color="transparent")
            interno.pack(side="left", fill="both", expand=True)
            selo_ia(interno).pack(anchor="w", padx=10, pady=(8, 0))
            recipiente = interno
        else:
            recipiente = bubble

        tb = ctk.CTkTextbox(recipiente, wrap="word", font=ctk.CTkFont(size=14), fg_color="transparent", text_color=WHITE_CARD if role == "user" else INK, corner_radius=0, width=550, height=42)
        tb.pack(padx=10, pady=10)
        
        if role == "assistant":
            configure_markdown_tags(tb)
            
        if text:
            if role == "assistant":
                insert_markdown(tb, text)
            else:
                tb.insert("end", text)
        tb.configure(state="disabled")
        
        def update_height(rolar: bool = True):
            """Altura da bolha medida em PIXELS, não em linhas vezes uma constante.

            `rolar=False` é para o streaming: lá quem decide se a conversa acompanha é o
            `FluxoDeResposta`, que mede se o usuário está no fim ANTES de escrever. Rolar
            daqui, depois de já ter inserido texto, arrastaria de volta quem tivesse subido
            para reler — quatorze vezes por segundo, enquanto o modelo escreve.

            O 22 era a altura estimada de uma linha na fonte base. Um `# título` é fonte 20
            e desenha ~28px; uma tabela é fonte 12 e desenha ~17. Resposta com cabeçalho
            saía CORTADA embaixo e resposta sem ele ganhava um vão — e o modelo abre quase
            toda resposta longa com um cabeçalho. `ypixels` é a altura que o Tk de fato
            desenhou, e não depende de fonte nenhuma.
            """
            altura = None
            try:
                tb.update_idletasks()
                px = tb._textbox.count("1.0", "end", "ypixels")
                # `Text.count` devolve tupla de um elemento, ou None quando a conta dá zero.
                altura = px[0] if isinstance(px, tuple) else px
            except Exception:
                altura = None
            if not altura:
                # Fallback pela contagem de linhas, para quando o widget ainda não foi
                # desenhado e o `ypixels` volta zero.
                try:
                    linhas = tb._textbox.count("1.0", "end", "displaylines")
                    n = linhas[0] if isinstance(linhas, tuple) else linhas
                except Exception:
                    n = None
                if not n:
                    n = tb.get("1.0", "end").count('\n') + 1
                altura = n * 22
            tb.configure(height=altura + 16)
            if rolar:
                self._rolar_conversa_para_o_fim()

        tb.after(50, update_height)
        return tb, update_height, row

    @contextlib.contextmanager
    def _uso_de_ia(self, ponto: str, **extras):
        """Entrega o analista e GRAVA o uso quando o bloco termina — inclusive se falhar.

        Gerenciador de contexto, e não um `registrar()` chamado no fim, porque a alternativa
        já foi tentada de fato: eram onze pontos construindo `AIAnalyst` na mão e **nenhum**
        registrava nada. Um passo que depende de cada chamador lembrar é um passo que o
        décimo segundo ponto vai esquecer. Aqui, quem quer o analista passa por aqui.

        O `finally` cobre a chamada que estourou no meio: a tentativa que falhou também é
        uso de IA na cadeia de decisão da pesquisa, e um relatório que só conta sucesso
        conta menos do que houve.
        """
        from core.uso_de_ia import ACAO, evento, provedor_do_endereco

        # `_get_ai_analyst`, e não `AIAnalyst(...)` na mão: a fábrica já existia e é onde
        # moram provedor, URL, modelo e o contexto de pesquisa do projeto. Os quatro pontos
        # de chat construíam o analista por fora dela, e o resultado era duas formas de
        # montar a mesma coisa — a que o relatório precisa ler é uma só.
        #
        # (O `contexto_pesquisa` da fábrica alimenta `_chat`, das cinco análises. O chat
        # não o usa por aqui: ele injeta o contexto pelo `_blink_system_prompt`. Sobra
        # inofensivo, e evita a terceira forma de construir analista.)
        analista = self._get_ai_analyst()
        erro = ""
        try:
            yield analista
        except BaseException as ex:
            erro = f"{type(ex).__name__}: {ex}"
            raise
        finally:
            try:
                self._backlog(ACAO, evento(
                    ponto,
                    modelo=analista.model,
                    provedor=provedor_do_endereco(analista.base_url),
                    uso=analista.ultimo_uso,
                    erro=erro,
                    **extras))
            except Exception as e:
                log.info(f"[IA] falha ao registrar o uso de {ponto}: {e}")

    def _analise_de_ia(self, ponto: str, chamar):
        """Uma análise que NÃO passa pela conversa (Sankey, temático, historiografia,
        obras seminais, rótulos de cluster), com o uso registrado.

        `chamar` recebe o analista e devolve o resultado — `lambda a:
        a.generate_sankey_insights(resumo)`. Um lambda em vez do nome do método em texto
        porque o argumento de cada uma é diferente, e um `getattr` por string esconderia do
        leitor (e de qualquer busca no código) quem chama o quê.
        """
        with self._uso_de_ia(ponto) as analista:
            return chamar(analista)

    def _responder_no_chat(self, ponto: str, messages: list, indicator_row=None,
                           temperature: float = 0.7) -> str:
        """Uma resposta do Blink: chama o modelo, escreve na conversa e registra o uso.

        Os quatro pontos que respondem NA CONVERSA — chat, assistente de busca, insights do
        corpus e insights do mapa — repetiam as mesmas seis linhas de streaming. Reunidas
        aqui, o registro de uso entra de graça nos quatro e o próximo ponto de chat nasce
        registrado.
        """
        with self._uso_de_ia(ponto) as analista:
            fluxo = self._fluxo_de_resposta(indicator_row)
            for pedaco in analista.chat_history_stream(messages, temperature=temperature):
                fluxo.escrever(pedaco)
            fluxo.concluir()
            return fluxo.texto

    def _fluxo_de_resposta(self, indicator_row=None):
        """O canal por onde uma resposta do Blink chega à tela enquanto é escrita.

        Os quatro pontos que fazem streaming — chat, insights do corpus, análise temática e
        assistente de busca — tinham CADA UM a sua cópia do laço: `after(0, ...)` por token,
        `delete("1.0", "end")` e reparse do texto inteiro a cada pedaço. Quatro cópias da
        mesma peça é quatro lugares onde consertar o piscar e a travada. Agora é uma.

        O porquê de cada decisão está no cabeçalho de `ui/streaming.py`.
        """
        from core.markdown_parser import insert_markdown
        from ui.streaming import FluxoDeResposta, perto_do_fim

        def abrir_balao():
            # O indicador pulsante sai no MESMO quadro em que o balão entra: destruí-lo
            # antes deixaria um vão piscando até o primeiro token chegar.
            try:
                if indicator_row is not None and indicator_row.winfo_exists():
                    indicator_row.destroy()
            except Exception:
                pass
            caixa, remedir, _ = self._add_blink_message("assistant", "")
            return caixa, lambda: remedir(rolar=False)

        def _canvas():
            historico = getattr(self, "_research_chat_history_main", None)
            if historico is None or not historico.winfo_exists():
                return None
            return historico._parent_canvas

        def no_fim():
            canvas = _canvas()
            return True if canvas is None else perto_do_fim(canvas)

        def rolar():
            if _canvas() is not None:
                self._rolar_conversa_para_o_fim()

        return FluxoDeResposta(self, abrir_balao, insert_markdown, rolar, no_fim)

    def aplicar_string_de_busca(self, string: str, base: str = None):
        """Joga uma string no campo de busca, na base escolhida, e leva o usuário até lá.

        Ponto único: o cartão de sugestão, os testes e qualquer atalho futuro passam por
        aqui. Trocar a base é DUAS coisas — a variável que a busca lê e o botão segmentado
        que o usuário vê. Mexer só na variável deixaria a tela dizendo "OpenAlex" enquanto a
        busca sai no PubMed, que é pior do que não trocar.
        """
        if base:
            self._search_provider_var.set(base)
            rotulo = next((k for k, v in self._PROVIDER_LABELS.items() if v == base), None)
            if rotulo and getattr(self, "_provider_seg", None) is not None:
                self._provider_seg.set(rotulo)
        self._search_query_entry.delete(0, "end")
        self._search_query_entry.insert(0, string)
        self._switch_tab("import")
        self._search_query_entry.focus_set()

    def _oferecer_string_de_busca(self, resposta: str):
        """Sob a resposta, a string proposta JÁ TRADUZIDA para cada uma das três bases.

        Antes havia um botão só, que jogava a string do Blink literalmente no campo — e a
        mesma string ia para qualquer base que estivesse selecionada. As três não falam a
        mesma língua, e era daí que vinha o "a string sugerida não dá resultado": um
        `bibliometric*` faz o OpenAlex responder HTTP 400 (a busca inteira falha, sem
        resultado nenhum), um `TITLE-ABS-KEY(...)` derruba o PubMed de 1.310 registros para
        1, e o Crossref, que não tem booleano, ordenava a base inteira por relevância com o
        ramo do `NOT` incluído — devolvendo em primeiro lugar exatamente as revisões que o
        usuário tinha pedido para excluir. A tradução mora em `core/strings_por_base.py`,
        com os números medidos contra as APIs.

        Uma linha por base: a string que ela de fato entende, o que mudou em relação ao que
        o Blink escreveu, e um botão que seleciona a base E preenche o campo.

        Sai calado quando a resposta não traz string: o Blink também responde pergunta que
        não é sobre busca, e um cartão inerte sob toda resposta seria ruído.
        """
        from core.string_de_busca import extrair_string_de_busca
        from core.strings_por_base import ROTULOS, traduzir
        from ui.design_tokens import INK, MUTED, PAPER, WHITE_CARD

        string = extrair_string_de_busca(resposta)
        historico = getattr(self, "_research_chat_history_main", None)
        if not string or historico is None or not historico.winfo_exists():
            return

        adaptacoes = [a for a in traduzir(string) if a.string]
        if not adaptacoes:
            return

        cartao = ctk.CTkFrame(historico, fg_color=WHITE_CARD, corner_radius=0,
                              border_width=2, border_color=INK)
        cartao.pack(fill="x", padx=10, pady=(0, 8))
        cartao.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(cartao, text=t("blink.usar_string"), anchor="w", text_color=INK,
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6))

        for i, adaptacao in enumerate(adaptacoes, start=1):
            rotulo = ROTULOS[adaptacao.base]
            ctk.CTkButton(
                cartao, text=t("blink.usar_na_base", base=rotulo), height=30, width=132,
                corner_radius=0, fg_color=WHITE_CARD, text_color=INK, border_width=2,
                border_color=INK, hover_color=PAPER,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda a=adaptacao: self.aplicar_string_de_busca(a.string, a.base),
            ).grid(row=i, column=0, sticky="w", padx=(12, 10), pady=3)

            # A string À VISTA antes de aplicar: sem ela o usuário não tem como saber que a
            # versão do Crossref perdeu os operadores, e descobriria pelo resultado.
            texto = adaptacao.string
            previa = texto if len(texto) <= 96 else texto[:93] + "…"
            notas = [t(f"strings_base.nota.{codigo}") for codigo in adaptacao.notas]
            if notas:
                previa += "\n" + " · ".join(dict.fromkeys(notas))
            ctk.CTkLabel(cartao, text=previa, font=ctk.CTkFont(size=11), text_color=MUTED,
                         anchor="w", justify="left").grid(row=i, column=1, sticky="ew",
                                                          padx=(0, 12), pady=3)

        ctk.CTkFrame(cartao, height=6, fg_color="transparent").grid(row=len(adaptacoes) + 1,
                                                                    column=0, columnspan=2)
        self._rolar_conversa_para_o_fim()

    # ── Tab: Importação ────────────────────────────────────────────────
    def _ia_configurada(self) -> bool:
        from ai.onboarding import tem_chave
        return tem_chave()

    def _build_tab_credenciais(self) -> ctk.CTkFrame:
        """A aba de Credenciais, fonte única das chaves."""
        from ui.credentials_tab import CredentialsTab

        frame = self._tab()
        self._credenciais_view = CredentialsTab(
            frame, on_change=self._ao_mudar_credencial)
        self._credenciais_view.pack(fill="both", expand=True)
        return frame

    def _ao_mudar_credencial(self):
        """Uma credencial foi salva ou removida: a sessão inteira acompanha NA HORA.

        Mesma exigência da Fase 1, agora para as três: `_api_key_var` alimenta os sete
        pontos de IA, e o Blink precisa trocar entre o convite e o chat conforme a chave
        exista ou não. Sem isto, a aba gravaria no cofre e o resto do app continuaria com o
        estado antigo até o próximo reinício — que foi exatamente o defeito do onboarding.
        """
        self._sincronizar_config_ia_da_sessao()
        self._sincronizar_chave_da_sessao()
        try:
            if self._ia_configurada():
                if getattr(self, "_blink_onboarding", None) is not None:
                    self._ocultar_onboarding_ia()
            else:
                self._mostrar_onboarding_ia()
        except Exception:
            pass

    def _sincronizar_config_ia_da_sessao(self):
        """Traz provedor, URL base e modelo do disco para as variáveis da barra de Ajustes.

        A aba de Credenciais também troca o provedor ativo, e os dois combos — o dela e o
        da barra de parâmetros do mapa — são widgets independentes. Sem esta passada, trocar
        para OpenAI na aba deixava a barra do mapa exibindo "groq" e, pior, mandando as
        chamadas para a URL base do Groq com a chave da OpenAI.
        """
        from core.settings import config_ia

        prov, base, modelo = config_ia()
        self._config_ia_sincronizando = True
        try:
            self._ai_provider_var.set(prov)
            self._ai_base_url_var.set(base)
            self._ai_model_var.set(modelo)
        finally:
            self._config_ia_sincronizando = False

    def _sincronizar_chave_da_sessao(self):
        """Traz a chave persistida para a variável que as chamadas de IA leem.

        Os sete pontos de IA do app — Blink, insights do mapa, Sankey, mapa temático,
        historiografia, feed de busca e obras seminais — montam o `AIAnalyst` com
        `self._api_key_var.get()`. Essa variável só era preenchida uma vez, no `__init__`.
        Quem salvava a chave pelo onboarding gravava no keyring e a variável continuava
        vazia até o próximo reinício: o painel dizia "Conectado. Modelo: …", o chat abria
        com a saudação, e a primeira pergunta morria em "API Key não configurada nos
        Ajustes". O usuário fazia tudo certo e o app dizia que ele não tinha feito.

        A fonte da verdade é `get_api_key()`, não o texto que foi colado: ela respeita a
        precedência env → keyring → JSON. Isso muda o resultado na remoção — com
        `GROQ_API_KEY` no ambiente, apagar do keyring não deixa a sessão sem chave, e a
        variável precisa refletir o que de fato vai ser usado em vez de fingir que zerou.
        """
        from core.settings import get_api_key

        self._sincronizando_chave = True
        try:
            self._api_key_var.set(get_api_key())
        finally:
            self._sincronizando_chave = False

    def _rolar_conversa_para_o_fim(self):
        """Recalcula a região de rolagem ANTES de rolar, e só então vai ao fim.

        `yview_moveto(1.0)` era chamado logo depois de redimensionar a bolha, antes de o
        canvas recomputar o `scrollregion` a partir do novo tamanho do conteúdo. O efeito
        era rolar até o fim de uma região OBSOLETA: medido, 770px de região para 308px de
        conversa, e 2.324px para 938px. O usuário via os 60% vazios da região e as mensagens
        ficavam acima da vista — o "espaço vazio no fim da conversa".

        O `update_idletasks` antes do `bbox` é defensivo, não essencial: removê-lo não
        derruba os testes desta correção. Fica porque garante que a passada de geometria
        terminou antes de medir, e medir cedo demais é o erro que criou o defeito.
        """
        historico = getattr(self, "_research_chat_history_main", None)
        if historico is None or not historico.winfo_exists():
            return
        canvas = historico._parent_canvas
        try:
            historico.update_idletasks()
            caixa = canvas.bbox("all")
            if caixa:
                canvas.configure(scrollregion=caixa)
            canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _empacotar_historico(self):
        """Empacota o histórico ocupando o que sobra ACIMA do rodapé.

        Existe como método porque `_ocultar_onboarding_ia` precisa refazer exatamente este
        empacotamento: repetir os argumentos nos dois lugares foi como o layout divergiu
        entre "app recém-aberto" e "app depois de configurar a chave".
        """
        self._research_chat_history_main.pack(side="top", fill="both", expand=True,
                                              pady=(0, 10))

    def _definir_estado_do_chat(self, bloqueado: bool):
        """Liga e desliga a entrada do Blink conforme o onboarding esteja ou não na tela.

        O painel de onboarding substitui o HISTÓRICO, não a tela inteira: a caixa de texto,
        o botão de enviar e os três botões de sugestão continuam montados logo abaixo dele.
        Dava para perguntar com o onboarding aberto e receber o painel vermelho de erro —
        que é precisamente o que o onboarding existe para o usuário não ver.
        """
        estado = "disabled" if bloqueado else "normal"
        for widget in (getattr(self, "_research_chat_input_main", None),
                       getattr(self, "_blink_send_btn", None),
                       *getattr(self, "_blink_sug_btns", ())):
            # `winfo_exists`, e não só `is not None`: `_refresh_language` chama
            # `_build_layout`, que remonta a aba inteira. Durante a remontagem estes
            # atributos ainda apontam para os widgets da montagem ANTERIOR, já destruídos, e
            # `configure` neles levanta TclError — trocar de idioma sem chave derrubava o app.
            if widget is not None and widget.winfo_exists():
                widget.configure(state=estado)

    def _mostrar_onboarding_ia(self):
        """Troca o histórico do chat pelo painel de onboarding."""
        from ui.ai_onboarding_panel import AIOnboardingPanel

        if getattr(self, "_blink_onboarding", None) is not None:
            return
        self._research_chat_history_main.pack_forget()
        self._blink_onboarding = AIOnboardingPanel(
            self._blink_chat_container, on_saved=self._ocultar_onboarding_ia,
            on_ir_para_credenciais=lambda: self._switch_tab("credenciais"))
        self._blink_onboarding.pack(fill="both", expand=True, pady=(0, 20))
        # Durante a montagem da aba isto é um no-op: os widgets do chat ainda não existem
        # (ou são os da montagem anterior, já destruídos). `_build_tab_home` refaz a chamada
        # depois de criá-los.
        self._definir_estado_do_chat(bloqueado=True)

    def _ocultar_onboarding_ia(self):
        """Chave salva: some o onboarding, volta o chat com a saudação."""
        # ANTES de devolver o chat: a saudação convida a perguntar, e a pergunta lê a chave.
        self._sincronizar_chave_da_sessao()
        if getattr(self, "_blink_onboarding", None) is not None:
            self._blink_onboarding.destroy()
            self._blink_onboarding = None
        self._empacotar_historico()
        self._definir_estado_do_chat(bloqueado=False)
        self._add_blink_message("assistant", t("blink.saudacao"), gerado_por_ia=False)

    def _remover_chave_da_ia(self):
        """Apaga a chave e faz a sessão parar de usá-la NA HORA.

        Apagava só do keyring: `self._api_key_var` seguia com a chave em memória e as
        chamadas de IA continuavam funcionando com uma chave que o usuário acabara de
        remover, até ele fechar o app. O espelho exato do defeito do onboarding — lá a
        chave nova não valia, aqui a chave velha não parava de valer.
        """
        from core.settings import set_api_key

        set_api_key("")
        self._sincronizar_chave_da_sessao()
        if hasattr(self, "_mostrar_onboarding_ia"):
            try:
                self._mostrar_onboarding_ia()
            except Exception:
                pass

    def _build_tab_home(self) -> ctk.CTkFrame:
        from ui.design_tokens import WHITE_CARD, MUTED, INK, RED, RED_HOV, PAPER, BLUE, ACCENT, ACCENT_HOV
        from PIL import Image
        frame = self._tab()
        
        # Top Strip for Flags
        top_strip = ctk.CTkFrame(frame, fg_color="transparent")
        top_strip.pack(fill="x", padx=24, pady=(24, 16))
        
        flag_f = ctk.CTkFrame(top_strip, fg_color="transparent")
        flag_f.pack(side="right")
        
        def set_l(l):
            from core.i18n import set_lang
            set_lang(l)
            self._refresh_language()
            
        try:
            for i, (l, f_name) in enumerate(_flag_options()):
                img = ctk.CTkImage(light_image=Image.open(caminho_do_recurso(f"assets/branding/{f_name}")), size=(32, 22))
                btn = ctk.CTkButton(flag_f, image=img, text="", width=32, height=22, fg_color="transparent", corner_radius=0, border_width=2, border_color=INK, hover_color="#e0e0e0", command=lambda x=l: set_l(x))
                btn.grid(row=0, column=i, padx=4)
        except:
            pass

        # Chat Interface
        chat_container = ctk.CTkFrame(frame, fg_color="transparent")
        chat_container.pack(fill="both", expand=True, padx=40, pady=20)
        
        title_f = ctk.CTkFrame(chat_container, fg_color="transparent")
        title_f.pack(pady=(0, 20), fill="x")
        
        lbl_f = ctk.CTkFrame(title_f, fg_color="transparent")
        lbl_f.pack(side="left")
        ctk.CTkLabel(lbl_f, text=t("blink.titulo_1"), font=ctk.CTkFont(size=32, weight="bold"), text_color=INK).pack(side="left")
        ctk.CTkLabel(lbl_f, text=t("blink.titulo_destaque"), font=ctk.CTkFont(size=32, weight="bold"), text_color=RED).pack(side="left")
        ctk.CTkLabel(lbl_f, text=t("blink.titulo_2"), font=ctk.CTkFont(size=32, weight="bold"), text_color=INK).pack(side="left")
        
        def _go_back():
            if hasattr(self, '_previous_tab_key') and self._previous_tab_key:
                self._switch_tab(self._previous_tab_key)
                
        self._blink_back_btn = ctk.CTkButton(title_f, text=t("blink.voltar"), width=100, height=30, fg_color="#E0E0E0", text_color=INK, hover_color="#C0C0C0", command=_go_back)

        # Contexto de pesquisa ACIMA da conversa, não escondido em Ajustes: ele enquadra tudo
        # o que vem depois, e o usuário precisa ver o que a IA está levando em conta sem
        # precisar procurar. O indicador aceso é a prova de que está indo junto.
        from ui.research_context_bar import ResearchContextBar
        self._research_context_bar = ResearchContextBar(
            chat_container, valor=getattr(self, "_research_context", ""),
            on_change=self._on_research_context_change)
        # `padx=6` iguala o recuo interno que o CTkScrollableFrame do histórico aplica
        # sozinho. Medido: sem isto o histórico começa em x=266 e o resto em x=260, e a
        # quebra de alinhamento aparece na borda esquerda de toda a coluna.
        self._research_context_bar.pack(fill="x", padx=6, pady=(0, 16))

        self._research_chat_history_main = ctk.CTkScrollableFrame(chat_container, fg_color="transparent")
        self._empacotar_historico()
        from core.markdown_parser import configure_markdown_tags, insert_markdown
        
        self._research_messages = [{"role": "system", "content": self._blink_system_prompt()}]

        # Sem chave configurada, o onboarding entra NO LUGAR do chat. Deixar o chat aparecer
        # e falhar na primeira pergunta faria o usuário achar que a IA está quebrada, em vez
        # de saber que falta um passo de configuração — e que ele leva dois minutos.
        self._blink_chat_container = chat_container
        self._blink_onboarding = None
        if not self._ia_configurada():
            self._mostrar_onboarding_ia()
        else:
            self._add_blink_message("assistant", t("blink.saudacao"), gerado_por_ia=False)

        input_f = ctk.CTkFrame(chat_container, fg_color="transparent")
        # `side="bottom"`, e não a ordem de empacotamento: `_ocultar_onboarding_ia` re-empacota
        # o histórico, e o `pack` o joga para o FIM da fila — ou seja, para baixo da entrada.
        # O efeito era visível e confuso: montado do zero o campo ficava embaixo, e depois de
        # configurar a chave ele aparecia ACIMA da conversa. Preso ao rodapé, a ordem em que
        # cada um é (re)empacotado deixa de importar.
        input_f.pack(side="bottom", fill="x", padx=6, pady=(10, 0))

        self._research_chat_input_main = ctk.CTkEntry(input_f, placeholder_text=t("blink.placeholder"), placeholder_text_color=MUTED, font=ctk.CTkFont(size=14), fg_color=WHITE_CARD, text_color=INK, height=44, corner_radius=0, border_width=2, border_color=INK)
        self._research_chat_input_main.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def send_main_chat(e=None):
            # Trava de correção, não de aparência. `_definir_estado_do_chat` desabilita os
            # widgets, mas o atalho <Return> e os botões de sugestão chegam aqui por outros
            # caminhos, e um widget desabilitado ainda responde a `invoke()`.
            if getattr(self, "_blink_onboarding", None) is not None:
                return
            msg = self._research_chat_input_main.get().strip()
            if not msg: return
            self._research_chat_input_main.delete(0, "end")

            self._add_blink_message("user", msg)
            
            corpus_txt = ""
            if self._dataframe is not None and not self._dataframe.empty:
                try:
                    from sklearn.feature_extraction.text import TfidfVectorizer
                    from sklearn.metrics.pairwise import cosine_similarity
                    from core.research_context import bloco_corpus
                    df = self._dataframe.dropna(subset=['abstract'])
                    if not df.empty:
                        docs = df['abstract'].astype(str).tolist()
                        vectorizer = TfidfVectorizer(stop_words='english')
                        tfidf_matrix = vectorizer.fit_transform(docs)
                        query_vec = vectorizer.transform([msg])
                        sims = cosine_similarity(query_vec, tfidf_matrix).flatten()
                        top_indices = sims.argsort()[-5:][::-1]

                        abstracts = []
                        for idx in top_indices:
                            if sims[idx] > 0.01:
                                row = df.iloc[idx]
                                title = row.get("title", "")
                                abs_txt = str(row.get("abstract", ""))[:300]
                                abstracts.append(f"Title: {title}\nAbstract: {abs_txt}...")

                        # `bloco_corpus` usa o MESMO separador que o corte de orçamento
                        # procura. Aqui havia `"\\n\\n---\\n"` — barra escapada duas vezes,
                        # que mandava ao modelo a sequência literal de dois caracteres `\n`
                        # em vez de quebra de linha, e não deixava fronteira onde cortar.
                        corpus_txt = bloco_corpus(abstracts)
                except Exception as ex:
                    log.info(f"[Blink RAG] Error: {ex}")

            # O truncamento cego (`[:4000]`) saiu daqui: ele cortava o FIM do prompt, e o fim
            # passou a ser o lugar dos abstracts só por acidente de montagem. Agora o corte é
            # explícito sobre quem cede — ver core/research_context.py.
            system_prompt = self._blink_system_prompt(dados_corpus=corpus_txt)
            self._research_messages[0] = {"role": "system", "content": system_prompt}
            self._research_messages.append({"role": "user", "content": msg})
            
            # Indicator
            indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
            indicator_row.pack(fill="x", pady=5)
            indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
            indicator.pack(side="left", padx=14, pady=14)
            
            def pulse_indicator():
                if indicator.winfo_exists():
                    current = indicator.cget("fg_color")
                    indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                    indicator.after(400, pulse_indicator)
            pulse_indicator()
            self._rolar_conversa_para_o_fim()
            
            import threading
            def worker():
                try:
                    full_response = self._responder_no_chat(
                        "blink_chat", self._research_messages, indicator_row)
                    
                    self._research_messages.append({"role": "assistant", "content": full_response})
                    # Resposta completa: só agora dá para procurar nela a string proposta —
                    # durante o streaming ela chega pela metade.
                    self.after(0, lambda r=full_response: self._oferecer_string_de_busca(r))
                except AIClientError as ex:
                    def err_ui(e=ex):
                        if indicator_row.winfo_exists(): indicator_row.destroy()
                        self._add_ai_error_row(
                            self._research_chat_history_main, detail=str(e),
                            retry_cb=lambda: _ThreadDaTela(target=worker, daemon=True).start())
                    self.after(0, err_ui)
                except Exception as ex:
                    def err_ui(e=ex):
                        if indicator_row.winfo_exists(): indicator_row.destroy()
                        self._add_ai_error_row(self._research_chat_history_main, detail=str(e))
                    self.after(0, err_ui)
            _ThreadDaTela(target=worker, daemon=True).start()
            
        self._research_chat_input_main.bind("<Return>", send_main_chat)
        #: O envio do Blink é um closure (precisa de `chat_container`, `insert_markdown` e
        #: dos widgets locais). Guardado aqui para o teste poder percorrer o caminho do
        #: usuário — apertar Enviar — em vez de reimplementar o worker por fora.
        self._blink_enviar = send_main_chat
        self._blink_send_btn = ctk.CTkButton(input_f, text=t("blink.enviar"), font=ctk.CTkFont(size=14, weight="bold"), fg_color=RED, text_color="white", hover_color=RED_HOV, corner_radius=0, border_width=2, border_color=INK, height=44, width=100, command=send_main_chat)
        self._blink_send_btn.pack(side="right")

        # Suggestions — acima da entrada, no rodapé, e ficam a conversa inteira. Sumiam na
        # primeira mensagem para devolver altura à conversa, mas o clique nelas é a única
        # forma de mandar uma pergunta pronta sem digitá-la: sumindo, a partir da segunda
        # pergunta o atalho deixava de existir. Custam duas linhas de rodapé; valem.
        sug_f = ctk.CTkFrame(chat_container, fg_color="transparent")
        sug_f.pack(side="bottom", fill="x", padx=6)
        self._blink_sug_frame = sug_f
        
        sugs = [
            t("blink.sugestao_1"),
            t("blink.sugestao_2"),
            t("blink.sugestao_3"),
        ]

        # Grid de 2 colunas: as sugestões quebram em 2 linhas quando não cabem (fr),
        # sem truncar o texto. Largura ajustada ao maior rótulo do idioma atual.
        import tkinter.font as _tkfont
        _sf = _tkfont.Font(family=ctk.CTkFont(size=12).cget("family"), size=12)
        _sug_w = max(_sf.measure(s) for s in sugs) + 24
        sug_f.grid_columnconfigure((0, 1), weight=0)
        self._blink_sug_btns = []
        for i, s_txt in enumerate(sugs):
            btn = ctk.CTkButton(sug_f, text=s_txt, width=_sug_w, font=ctk.CTkFont(size=12), fg_color=PAPER, text_color=INK, hover_color="#e0e0e0", corner_radius=0, border_width=1, border_color=INK, command=lambda txt=s_txt: self._research_chat_input_main.insert(0, txt) or send_main_chat())
            btn.grid(row=i // 2, column=i % 2, padx=(0, 10), pady=(0, 8), sticky="w")
            self._blink_sug_btns.append(btn)

        # Só agora os widgets do chat existem. A chamada dentro de `_mostrar_onboarding_ia`
        # aconteceu antes deles, quando ainda não havia o que desabilitar.
        self._definir_estado_do_chat(bloqueado=self._blink_onboarding is not None)

        return frame

    def _build_tab_projects(self) -> ctk.CTkFrame:
        from ui.projects_view import ProjectsView
        frame = ctk.CTkFrame(getattr(self, "_tabs_container", self._content), fg_color="transparent")
        
        def on_open_project(slug):
            self.after(0, lambda: self._open_project_slug(slug))

        self._projects_view = ProjectsView(frame, on_open_project,
                                           on_new_project=self._create_project_flow)
        self._projects_view.pack(fill="both", expand=True)
        return frame
        
    def _build_tab_import(self) -> ctk.CTkFrame:
        frame = self._tab()
        
        # Search Card (Top)
        scard = self._card(frame, 0)
        scard.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(scard, text="Busca Online", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")
            
        # DECISÃO DE PRODUTO: UMA base por busca — seletor único, sem multi-select.
        self._search_provider_var = ctk.StringVar(value="openalex")
        self._PROVIDER_LABELS = {"OpenAlex": "openalex", "Crossref": "crossref", "PubMed": "pubmed"}
        sp_f = ctk.CTkFrame(scard, fg_color="transparent")
        sp_f.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="w")
        ctk.CTkLabel(sp_f, text=t("search.source"), font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        self._provider_seg = ctk.CTkSegmentedButton(
            sp_f, values=list(self._PROVIDER_LABELS), corner_radius=0,
            fg_color=WHITE_CARD, unselected_color=WHITE_CARD, unselected_hover_color=CARD2_BG,
            selected_color=RED, selected_hover_color=RED_HOV, text_color=INK,
            command=lambda lbl: self._search_provider_var.set(self._PROVIDER_LABELS[lbl]))
        self._provider_seg.set("OpenAlex")
        self._provider_seg.pack(side="left")

        self._search_query_entry = ctk.CTkEntry(scard, placeholder_text="Termo / Query (ex: 'deep learning')", placeholder_text_color=MUTED, height=36, fg_color=WHITE_CARD, text_color=INK)
        self._search_query_entry.grid(row=2, column=0, columnspan=2, padx=16, pady=4, sticky="ew")

        # Translator NÃO-destrutivo: o campo do usuário fica intacto; a query
        # interpretada aparece neste label discreto.
        self._interpreted_lbl = ctk.CTkLabel(scard, text="", font=ctk.CTkFont(size=11),
                                             text_color=MUTED, anchor="w")
        self._interpreted_lbl.grid(row=3, column=0, columnspan=2, padx=18, pady=(0, 2), sticky="w")

        act_sf = ctk.CTkFrame(scard, fg_color="transparent")
        act_sf.grid(row=4, column=0, columnspan=2, padx=16, pady=(4, 16), sticky="e")

        # Explorar a partir de um artigo (grafo de artigos parecidos, à la Connected Papers)
        exp_f = ctk.CTkFrame(scard, fg_color="transparent")
        exp_f.grid(row=4, column=0, padx=16, pady=(4, 16), sticky="w")
        ctk.CTkButton(exp_f, text=t("explorar.botao"), command=self._abrir_explorar,
                      height=30, corner_radius=0, fg_color=WHITE_CARD, hover_color=PAPER,
                      text_color=INK, border_width=2, border_color=INK,
                      font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        ctk.CTkLabel(act_sf, text="Qtd:").pack(side="left", padx=4)
        self._search_max_entry = ctk.CTkEntry(act_sf, width=60, placeholder_text="1000", placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK)
        self._search_max_entry.insert(0, "1000")
        self._search_max_entry.pack(side="left", padx=4)

        # Limite default 1000, sem teto (o número digitado vale); Ilimitado disponível.
        self._search_unlimited_var = ctk.BooleanVar(value=False)
        self._search_unlimited_chk = ctk.CTkCheckBox(act_sf, text="Ilimitado", variable=self._search_unlimited_var, width=50,
                                                     command=lambda: self._search_max_entry.configure(state="disabled" if self._search_unlimited_var.get() else "normal"))
        self._search_unlimited_chk.pack(side="left", padx=4)
        
        self._btn(act_sf, "Avançada", self._open_query_builder, height=30).pack(side="left", padx=4)
        self._btn(act_sf, t("preview.button"), self._run_preview, height=30, color=INK, hover=INK_HOV).pack(side="left", padx=4)
        self._btn(act_sf, "Buscar", self._on_gui_search, height=30, color=RED, hover=RED_HOV).pack(side="left", padx=4)
        self._btn(act_sf, "Blink", self._trigger_import_ai_assistant, height=30, color=YELLOW, hover=YELLOW_HOV).pack(side="left", padx=4)
        
        self._search_cancel_btn = self._btn(act_sf, "Cancelar", self._cancel_search, height=30, color="#E63946", hover="#C12B37")
        self._search_cancel_btn.pack_forget() # Hide initially
        
        filter_f = ctk.CTkFrame(scard, fg_color="transparent")
        filter_f.grid(row=5, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        
        ctk.CTkLabel(filter_f, text="Ano Início:", font=ctk.CTkFont(size=12)).pack(side="left", padx=4)
        self._search_year_start = ctk.CTkEntry(filter_f, width=60, placeholder_text="Ex: 2018", placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK)
        self._search_year_start.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Ano Fim:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_year_end = ctk.CTkEntry(filter_f, width=60, placeholder_text="Ex: 2024", placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK)
        self._search_year_end.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Tipo:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_type_var = ctk.StringVar(value="Todos")
        self._search_type = ctk.CTkOptionMenu(filter_f, variable=self._search_type_var, fg_color=WHITE_CARD, text_color=INK, button_color=WHITE_CARD, button_hover_color=CARD2_BG,
                                              values=["Todos", "article", "review", "book-chapter", "dataset"], width=100)
        self._search_type.pack(side="left", padx=4)
        
        ctk.CTkLabel(filter_f, text="Idioma:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_lang_var = ctk.StringVar(value="Todos")
        self._search_lang = ctk.CTkOptionMenu(filter_f, variable=self._search_lang_var, fg_color=WHITE_CARD, text_color=INK, button_color=WHITE_CARD, button_hover_color=CARD2_BG,
                                              values=["Todos", "en", "pt", "es", "fr", "de"], width=70)
        self._search_lang.pack(side="left", padx=4)
        # BUG-02: no Crossref o filtro de idioma é aplicado localmente (a API não é confiável nisso).
        ctk.CTkLabel(filter_f, text="ⓘ Crossref: local", font=ctk.CTkFont(size=10), text_color=MUTED).pack(side="left", padx=(2,4))
        
        self._search_oa_var = ctk.BooleanVar(value=False)
        self._search_oa_chk = ctk.CTkCheckBox(filter_f, text="Apenas Open Access", variable=self._search_oa_var, font=ctk.CTkFont(size=12), width=20)
        self._search_oa_chk.pack(side="left", padx=(10,4))

        ctk.CTkLabel(filter_f, text="Ordenar por:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,4))
        self._search_sort_var = ctk.StringVar(value="Relevância")
        self._search_sort = ctk.CTkOptionMenu(filter_f, variable=self._search_sort_var, fg_color=WHITE_CARD, text_color=INK, button_color=WHITE_CARD, button_hover_color=CARD2_BG,
                                              values=["Relevância", "Mais citados", "Mais recentes"], width=130)
        self._search_sort.pack(side="left", padx=4)

        # ── Busca avançada por campo (cherry-pick do redesign estilo Scopus;
        # só OpenAlex suporta busca por campo via _oa_filter) ──
        self._FIELD_OPTIONS = {t("fields.all"): "all", t("fields.field_title"): "title",
                               t("fields.author"): "author", t("fields.abstract"): "abstract"}
        ff = ctk.CTkFrame(scard, fg_color="transparent")
        ff.grid(row=6, column=0, columnspan=2, padx=16, pady=(2, 12), sticky="ew")
        ff.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ff, text=t("fields.title"), font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INK).grid(row=0, column=0, sticky="w")
        self._field_rows_frame = ctk.CTkFrame(ff, fg_color="transparent")
        self._field_rows_frame.grid(row=1, column=0, sticky="ew")
        self._field_rows_frame.grid_columnconfigure(1, weight=1)
        self._field_rows = []
        self._add_field_row()
        self._add_field_row()
        ctk.CTkButton(ff, text=t("fields.add"), width=90, height=26, corner_radius=0,
                      fg_color=WHITE_CARD, text_color=INK, hover_color=CARD2_BG,
                      border_width=1, border_color=INK,
                      command=self._add_field_row).grid(row=2, column=0, sticky="w", pady=(2, 0))

        # Trilha de contagem da última busca — visível na própria Coletar
        # (além do header do feed).
        self._search_trail_lbl = ctk.CTkLabel(scard, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                              text_color=INK, anchor="w")
        self._search_trail_lbl.grid(row=7, column=0, columnspan=2, padx=18, pady=(0, 10), sticky="w")

        # File Import Hero Zone (Bottom)
        fcard = self._card(frame, 1)
        fcard.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(fcard, text="Arraste arquivos ou clique", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=16, pady=(16, 8), sticky="w")
            
        list_frame = ctk.CTkFrame(fcard, fg_color=CARD2_BG, corner_radius=0)
        list_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=(8, 16), sticky="ew")
        list_frame.grid_columnconfigure(0, weight=1)
        self._file_list_frame = ctk.CTkScrollableFrame(list_frame, fg_color=CARD2_BG, height=100)
        self._file_list_frame.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        self._file_list_frame.grid_columnconfigure(0, weight=1)
        self._file_row_widgets = []
        self._file_list_frame.grid_remove() # Hide initially
        
        fbf = ctk.CTkFrame(fcard, fg_color="transparent")
        fbf.grid(row=1, column=2, padx=12, pady=(8, 16), sticky="n")
        self._btn(fbf, "Adicionar Arquivos", self._pick_file, height=36).pack(pady=(0, 6))
        self._btn(fbf, "Limpar Tudo", self._clear_files, color="#4a1a1a", hover="#6a2a2a", height=36).pack()
        
        act_f = ctk.CTkFrame(fcard, fg_color="transparent")
        act_f.grid(row=2, column=0, columnspan=3, padx=16, pady=(12, 16), sticky="ew")
        act_f.grid_columnconfigure((0, 1, 2), weight=1)
        
        # DECISÃO DE PRODUTO: a deduplicação saiu da Coletar — é ação explícita
        # no Corpus (botão Deduplicar).
        act_f.grid_columnconfigure((0, 1), weight=1)
        self._btn(act_f, "Carregar e Combinar", self._load_data, height=40, color=RED, hover=RED_HOV).grid(
            row=0, column=0, padx=(0, 4), sticky="ew")
        self._btn(act_f, "Abrir Projeto (.blicsa)", self._load_project_gui, height=40,
                  color=BLUE, hover=BLUE_HOV).grid(
            row=0, column=1, padx=(4, 0), sticky="ew")

        # The Log is now in toasts, so no need for log box here
        # But wait, self._log_box was used for sys.stdout redirection and background thread logs.
        # So I will create a hidden log_box to avoid exceptions from LogWriter.
        self._log_box = ctk.CTkTextbox(frame)
        self._log_box.grid_forget()

        return frame

    def _build_tab_review(self) -> ctk.CTkFrame:
        f = self._tab()
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        
        self._h1(f, "Revisar Resultados", 0)
        
        # Header counts
        self._review_counts_lbl = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED)
        self._review_counts_lbl.grid(row=0, column=0, padx=28, pady=4, sticky="e")
        
        # Main container with filter sidebar and cards
        main_c = ctk.CTkFrame(f, fg_color="transparent")
        main_c.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        main_c.grid_columnconfigure(1, weight=1)
        main_c.grid_rowconfigure(0, weight=1)
        
        # Left Filters
        flt_sidebar = ctk.CTkFrame(main_c, width=200, fg_color=CARD_BG, corner_radius=0)
        flt_sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        flt_sidebar.grid_propagate(False)
        ctk.CTkLabel(flt_sidebar, text="Filtros", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        
        # Right Feed
        self._review_feed = ctk.CTkScrollableFrame(main_c, fg_color=CARD2_BG)
        self._review_feed.grid(row=0, column=1, sticky="nsew")
        
        # Bottom Bar
        bb = ctk.CTkFrame(f, height=60, fg_color=CARD_BG, corner_radius=0)
        bb.grid(row=2, column=0, sticky="ew")
        bb.grid_columnconfigure(0, weight=1)
        
        self._review_selected_lbl = ctk.CTkLabel(bb, text="0 selecionados", font=ctk.CTkFont(size=14, weight="bold"))
        self._review_selected_lbl.grid(row=0, column=0, padx=20, sticky="w")
        
        self._btn(bb, "Importar para o Corpus", lambda: self._switch_tab("corpus"), height=40, color=RED).grid(row=0, column=1, padx=20, pady=10, sticky="e")
        
        return f

    # ── Tab: Mapa & IA ─────────────────────────────────────────────────
    def _build_tab_viz(self, parent=None) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent if parent else self._content, fg_color="transparent", corner_radius=0)
        # Col 0 (left config sidebar, fixed), Col 1 (middle canvas, expanding)
        frame.grid_columnconfigure(0, weight=0, minsize=280)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        
        # ── Left Config Sidebar ──
        config_panel = ctk.CTkFrame(frame, width=280, fg_color=CARD_BG, corner_radius=0)
        config_panel.grid(row=0, column=0, padx=(20, 6), pady=16, sticky="nsew")
        config_panel.grid_propagate(False)
        config_panel.grid_columnconfigure(0, weight=1)
        config_panel.grid_rowconfigure(1, weight=1)
        
        # Title of config sidebar
        ctk.CTkLabel(
            config_panel, text="Parâmetros do Mapa",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ACCENT
        ).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")
        
        sc = ctk.CTkScrollableFrame(config_panel, fg_color="transparent")
        sc.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")
        sc.grid_columnconfigure(0, weight=1)
        
        self._build_config_widgets(sc)
        
        # ── Middle Viz Panel ──
        viz_panel = ctk.CTkFrame(frame, fg_color="transparent")
        viz_panel.grid(row=0, column=1, padx=6, pady=16, sticky="nsew")
        viz_panel.grid_columnconfigure(0, weight=1)
        viz_panel.grid_rowconfigure(3, weight=1) # matplotlib canvas gets all vertical height
        
        # Action buttons
        br = ctk.CTkFrame(viz_panel, fg_color=CONTENT_BG)
        br.grid(row=0, column=0, pady=(0, 4), sticky="ew")
        br.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._btn(br, "Gerar Mapa", self._run_mapping,
                  height=44).grid(row=0, column=0, padx=4, sticky="ew")
        self._btn(br, "Abrir Plotly Interativo",
                  self._open_plotly, color="#1a4a7a",
                  hover="#153a60", height=44).grid(
            row=0, column=1, padx=4, sticky="ew")
        
        def save_plot():
            if not getattr(self, '_graph', None):
                messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
                return
            import os, time, re
            os.makedirs(REPORTS_DIR, exist_ok=True)
            
            # Guarda na galeria uma cópia autocontida do mapa Sigma.
            from core.sigma_exporter import export_sigma_json
            import tempfile
            
            # Temporary path for graph.json
            with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp_json:
                sigma_path = tmp_json.name
            
            export_sigma_json(self._graph, self._positions, sigma_path)
            
            html_template_path = str(OUTPUT_DIR / "assets" / "map_template.html")
            js_path = str(OUTPUT_DIR / "assets" / "map.js")
            vendor_path = str(OUTPUT_DIR / "assets" / "vendor" / "blicsa-vendor.min.js")

            with open(html_template_path, "r", encoding="utf-8") as f:
                template = f.read()
            with open(js_path, "r", encoding="utf-8") as f:
                map_js = f.read()
            with open(vendor_path, "r", encoding="utf-8") as f:
                vendor_js = f.read()
            with open(sigma_path, "r", encoding="utf-8") as f:
                graph_json = f.read()

            os.remove(sigma_path)

            # Dados embutidos no lugar do fetch("graph.json"). Função própria e testada:
            # a versão anterior corrompia o JSON com aspas/barras nos termos (B7).
            from core.sigma_exporter import inline_graph_data
            map_js = inline_graph_data(map_js, graph_json)

            # HTML da galeria é 100% autossuficiente e offline: vendors e i18n
            # do idioma ativo embutidos inline (nenhum fetch/URL externa).
            from core.i18n import get_map_i18n
            i18n_json = json.dumps(get_map_i18n(), ensure_ascii=False)
            template = template.replace(
                '<script src="vendor/blicsa-vendor.min.js"></script>',
                f'<script>\n{vendor_js}\n</script>')
            template = template.replace(
                '<script src="map.js"></script>',
                f'<script>\nwindow.BLICSA_I18N = {i18n_json};\n{map_js}\n</script>')

            path = str(REPORTS_DIR / f"blicsa_mapa_{int(time.time())}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(template)
            self._record_export("html", path, action="map")
                
            messagebox.showinfo("Sucesso", f"Mapa salvo na galeria!\nVerifique a aba Galeria.")
            self._refresh_gallery()

        self._btn(br, "Salvar na Galeria",
                  save_plot,
                  color=RED, hover=RED_HOV, height=44).grid(
            row=0, column=2, padx=4, sticky="ew")
            
        # Removing AI insights button since Blink Research sidebar is preferred
            
        self._btn(br, "Nomear Clusters", self._auto_label_clusters,
                  color="#1a5a3a", hover="#144a2e", height=44).grid(
            row=1, column=0, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "Tendências", self._open_trends,
                  color=INK, hover=INK_HOV, height=44).grid(
            row=1, column=1, padx=4, pady=(4, 0), sticky="ew")
        # BLUE: a nuvem de palavras é DADO do corpus, não conteúdo gerado por IA.
        self._btn(br, "Word Cloud", self._show_wordcloud,
                  color=BLUE, hover=BLUE_HOV, height=44).grid(
            row=1, column=2, columnspan=2, padx=4, pady=(4, 0), sticky="ew")

        # Row 2 Actions
        self._btn(br, "Sankey (3 Campos)", self._open_sankey,
                  color="#D4A017", hover="#b88a10", height=44).grid(
            row=2, column=0, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "⏳  Linha do Tempo", self._open_timeline,
                  color="#1a4a7a", hover="#153a60", height=44).grid(
            row=2, column=1, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "Surtos (Bursts)", self._open_bursts,
                  color="#800020", hover="#600018", height=44).grid(
            row=2, column=2, padx=4, pady=(4, 0), sticky="ew")

        # Row 3 Actions
        self._btn(br, "Mapa Temático (Callon)", self._open_thematic_map,
                  color="#2A9D8F", hover="#207a6f", height=44).grid(
            row=3, column=0, padx=4, pady=(4, 0), sticky="ew")
        self._btn(br, "⏳  Historiografia de Citações", self._open_historiograph,
                  color="#E76F51", hover="#c9583c", height=44).grid(
            row=3, column=1, padx=4, pady=(4, 0), sticky="ew")

        # Search + style controls
        ctrl = ctk.CTkFrame(viz_panel, fg_color=CONTENT_BG)
        ctrl.grid(row=1, column=0, pady=(4, 4), sticky="ew")
        
        # Summary Stats
        sc = ctk.CTkFrame(viz_panel, fg_color=CONTENT_BG)
        sc.grid(row=2, column=0, pady=(0, 4), sticky="ew")
        sc.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self._stat_labels = {}
        for col, (key, nice) in enumerate([
            ("total_nodes",     "Nós"),
            ("total_edges",     "Arestas"),
            ("num_clusters",    "Clusters"),
            ("avg_citations",   "Média Cit."),
            ("network_density", "Densidade"),
        ]):
            inner = ctk.CTkFrame(sc, fg_color=CARD2_BG, corner_radius=0)
            inner.grid(row=0, column=col, padx=4, pady=6, sticky="ew")
            v = ctk.CTkLabel(inner, text="—",
                             font=ctk.CTkFont(size=18, weight="bold"),
                             text_color=ACCENT)
            v.pack(pady=(6, 0))
            ctk.CTkLabel(inner, text=nice,
                          font=ctk.CTkFont(size=10),
                          text_color=TEXT_MUTED).pack(pady=(0, 6))
            self._stat_labels[key] = v

        # ── Right IA & Info Panel ──
        info_panel = ctk.CTkFrame(frame, width=340, fg_color=CARD_BG, corner_radius=0)
        info_panel.grid(row=0, column=2, padx=(6, 20), pady=16, sticky="nsew")
        info_panel.grid_propagate(False)
        info_panel.grid_columnconfigure(0, weight=1)
        info_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            info_panel, text="IA & Análise",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ACCENT
        ).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")

        btabs = ctk.CTkTabview(info_panel, fg_color=CARD2_BG,
                               segmented_button_fg_color=CARD_BG,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color=ACCENT_HOV,
                               segmented_button_unselected_color=CARD_BG,
                               text_color=("#000", "white"),
                               text_color_disabled=TEXT_MUTED)
        btabs.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

        ia_tab   = btabs.add("Insights IA")
        seminal_tab = btabs.add("Autores Seminais")
        node_tab = btabs.add("Nó Selecionado")
        ia_tab.grid_rowconfigure(0, weight=1)
        ia_tab.grid_columnconfigure(0, weight=1)
        seminal_tab.grid_rowconfigure(0, weight=1)
        seminal_tab.grid_columnconfigure(0, weight=1)
        node_tab.grid_rowconfigure(0, weight=1)
        node_tab.grid_columnconfigure(0, weight=1)

        self._insights_box = ctk.CTkTextbox(
            ia_tab, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self._insights_box.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self._insights_box.insert("1.0", "Os insights aparecerão aqui após clicar em 'Insights com IA'.")
        self._insights_box.configure(state="disabled")

        self._seminal_box = ctk.CTkTextbox(
            seminal_tab, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self._seminal_box.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        from core.markdown_parser import configure_markdown_tags
        configure_markdown_tags(self._seminal_box)
        # Não promete mais "após gerar o mapa": a análise agora tem botão próprio, e o texto
        # de espera anunciava uma entrega que nada disparava.
        self._seminal_box.insert("1.0", t("seminal.espera"))
        self._seminal_box.configure(state="disabled")

        seminal_tab.grid_rowconfigure(0, weight=1)
        seminal_tab.grid_rowconfigure(1, weight=0)
        seminal_tab.grid_columnconfigure(0, weight=1)

        sem_btn_frame = ctk.CTkFrame(seminal_tab, fg_color="transparent")
        sem_btn_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

        # Amarelo porque o resultado é gerado por IA — a convenção de `docs/inventario-ia.md`
        # vale para o botão que dispara, não só para o texto que volta.
        ctk.CTkButton(
            sem_btn_frame, text=t("seminal.analisar"), height=32,
            fg_color=YELLOW, hover_color=YELLOW_HOV, text_color=INK,
            font=ctk.CTkFont(weight="bold"), command=self._trigger_seminal_insights
        ).pack(fill="x", pady=(0, 6))

        ctk.CTkButton(
            sem_btn_frame, text="Criar Pasta da Biblioteca", height=32,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000000",
            font=ctk.CTkFont(weight="bold"), command=self._create_seminal_library
        ).pack(fill="x")

        self._node_info_box = ctk.CTkTextbox(
            node_tab, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD2_BG, border_color=ACCENT, border_width=1
        )
        self._node_info_box.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self._node_info_box.insert("end", "Clique em um nó no mapa para ver detalhes.")
        self._node_info_box.configure(state="disabled")

        self._bottom_tabs = btabs
        return frame

    def _build_config_widgets(self, sc):
        # 1. Tipo de Mapa
        lbl_tipo = ctk.CTkLabel(sc, text="Tipo de Mapa:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_tipo.pack(anchor="w", padx=10, pady=(8, 2))
        HoverTooltip(lbl_tipo, "O tipo de rede a ser construída.\n- Coocorrência: Itens que aparecem juntos no mesmo artigo.\n- Coautoria: Autores que publicam juntos.\n- Cocitação: Duas referências citadas pelo mesmo artigo.\n- Acoplamento: Artigos que citam as mesmas referências.")
        # Lista agrupada por pergunta. Os títulos dos grupos não são escolhíveis; os nomes dos
        # tipos não mudam porque ficam gravados nos projetos (`map_type`).
        var_tipo = self._map_type_var
        self._tipo_anterior = var_tipo.get() if hasattr(var_tipo, "get") else MAP_TYPES[0]

        def _lembrar_tipo(*_a):
            v = var_tipo.get()
            if v in MAP_TYPES:
                self._tipo_anterior = v
        if hasattr(var_tipo, "trace_add"):
            var_tipo.trace_add("write", _lembrar_tipo)
        self._tipo_combo = ctk.CTkComboBox(sc, values=valores_tipo_de_mapa(), variable=self._map_type_var, height=28, button_color=ACCENT, border_color=ACCENT,
                        state="readonly", command=getattr(self, "_ao_escolher_tipo_de_mapa", None))
        self._tipo_combo.pack(fill="x", padx=10, pady=(0, 2))
        self._desc_tipo_lbl = ctk.CTkLabel(sc, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
                                           wraplength=205, justify="left", anchor="w")
        self._desc_tipo_lbl.pack(anchor="w", fill="x", padx=10, pady=(0, 6))
        # Aviso ANTES de clicar quando o corpus não tem os dados que o tipo exige (M2).
        self._aviso_tipo_lbl = ctk.CTkLabel(sc, text="", font=ctk.CTkFont(size=11), text_color=RED,
                                            wraplength=205, justify="left", anchor="w")
        
        # 2. Campo
        lbl_campo = ctk.CTkLabel(sc, text="Campo:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_campo.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_campo, "A coluna do conjunto de dados a ser extraída.\nPara Coocorrência, Palavras-chave é o padrão.\nPara Coautoria, Autores.\nPara Cocitação, Referências.")
        FIELD_LABELS = [x[0] for x in FIELD_OPTS]
        FIELD_KEYS = [x[1] for x in FIELD_OPTS]
        
        self._field_label_var = ctk.StringVar(value=FIELD_LABELS[0])
        def _on_field_combo(val):
            idx = FIELD_LABELS.index(val)
            self._field_var.set(FIELD_KEYS[idx])
            self._on_field_change()
            
        ctk.CTkComboBox(sc, values=FIELD_LABELS, variable=self._field_label_var, height=28, button_color=ACCENT, border_color=ACCENT, command=_on_field_combo).pack(fill="x", padx=10, pady=(0, 6))
        
        # 3. Método de Contagem
        lbl_contagem = ctk.CTkLabel(sc, text="Contagem:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_contagem.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_contagem, "Full: peso 1 para cada conexão. Fractional: peso diluído pelo número total de conexões no artigo (minimiza o peso de artigos com dezenas de referências).")
        ctk.CTkComboBox(sc, values=["full", "fractional"], variable=self._counting_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 4. Normalização
        chk_assoc = ctk.CTkCheckBox(sc, text="Assoc. Strength", variable=self._assoc_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV)
        chk_assoc.pack(anchor="w", padx=10, pady=8)
        HoverTooltip(chk_assoc, "Aplica Associação Van Eck & Waltman (VOSviewer) dividindo o peso das arestas pelas frequências de ocorrência dos nós, evidenciando as relações mais raras e significativas.")
        
        # 5. Frequência Mínima
        lbl_freq = ctk.CTkLabel(sc, text=t("map.filter_min_frequency_label"),
                                font=ctk.CTkFont(size=11, weight="bold"))
        lbl_freq.pack(anchor="w", padx=10, pady=(4, 2))
        self._lbl_freq = lbl_freq
        HoverTooltip(lbl_freq, t("map.filter_min_frequency_help"))
        occ_f = ctk.CTkFrame(sc, fg_color="transparent")
        occ_f.pack(fill="x", padx=10, pady=(0, 6))
        self._occ_lbl = ctk.CTkLabel(occ_f, text="3", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._occ_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            occ_f, from_=1, to=100, number_of_steps=99,
            variable=self._min_occ_var, height=14,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=self._on_occ_change,
        ).pack(side="left", fill="x", expand=True)
        
        self._thresh_lbl = ctk.CTkLabel(sc, text="", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
        self._thresh_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # 5b. Contagem binária (padrão do VOSviewer) — distinta de full/fractional, que é
        # sobre o PESO da aresta. Aqui é sobre contar o termo uma vez por documento.
        chk_bin = ctk.CTkCheckBox(sc, text="Contagem binária", variable=self._binary_count_var,
                                  font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV,
                                  command=self._update_thresh_label)
        chk_bin.pack(anchor="w", padx=10, pady=(0, 6))
        HoverTooltip(chk_bin, "Conta cada termo UMA vez por documento, mesmo que ele se repita.\n"
                              "É o padrão recomendado pelo VOSviewer: sem isso, um termo repetido\n"
                              "muitas vezes num único artigo distorce o mapa inteiro.")

        # 5c. Lista de termos revisável ANTES de gerar (passo 13 do guia).
        self._btn(sc, "Revisar termos…", self._open_term_review, height=30,
                  color=INK, hover=INK_HOV).pack(fill="x", padx=10, pady=(0, 6))
        self._excluded_lbl = ctk.CTkLabel(sc, text="", font=ctk.CTkFont(size=10),
                                          text_color=TEXT_MUTED)
        self._excluded_lbl.pack(anchor="w", padx=10, pady=(0, 6))
        
        # 6. Filtro de Nós (Máx. nós ou Top %)
        lbl_max = ctk.CTkLabel(sc, text=t("map.filter_max_nodes_label"),
                               font=ctk.CTkFont(size=11, weight="bold"),
                               wraplength=220, justify="left")
        lbl_max.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_max, t("map.filter_max_nodes_help"))
        ctk.CTkEntry(sc, textvariable=self._max_nodes_var, height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        lbl_top = ctk.CTkLabel(sc, text=t("map.filter_top_percent_label"),
                               font=ctk.CTkFont(size=11, weight="bold"))
        lbl_top.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_top, t("map.filter_top_percent_help"))
        ctk.CTkEntry(sc, textvariable=self._max_pct_var, placeholder_text="ex: 60", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 7. Iterações Layout FA2
        lbl_fa2 = ctk.CTkLabel(sc, text="Iterações FA2:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_fa2.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_fa2, "Quantidade de iterações do algoritmo de espacialização ForceAtlas2. Um valor maior torna o mapa mais estável e agrupado, porém demora mais para calcular.")
        fa2_f = ctk.CTkFrame(sc, fg_color="transparent")
        fa2_f.pack(fill="x", padx=10, pady=(0, 6))
        self._fa2_lbl = ctk.CTkLabel(fa2_f, text="500", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._fa2_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            fa2_f, from_=100, to=2000, number_of_steps=19,
            variable=self._fa2_iter_var, height=14,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=lambda v: self._fa2_lbl.configure(text=str(int(v))),
        ).pack(side="left", fill="x", expand=True)
        
        chk_linlog = ctk.CTkCheckBox(sc, text="LinLog Mode", variable=self._linlog_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV)
        chk_linlog.pack(anchor="w", padx=10, pady=6)
        HoverTooltip(chk_linlog, "Um modo alternativo de força no ForceAtlas2 que afasta mais os clusters uns dos outros para uma visualização com menos sobreposição.")
        
        # Algoritmo de Cluster & Resolução
        lbl_alg = ctk.CTkLabel(sc, text="Algoritmo de Cluster:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_alg.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_alg, "O algoritmo para detectar comunidades na rede. O Leiden é mais rápido e garante melhor otimização matemática para grafos complexos do que o Louvain tradicional.")
        ctk.CTkComboBox(sc, values=["louvain", "leiden"], variable=self._cluster_alg_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        lbl_res = ctk.CTkLabel(sc, text="Resolução Cluster:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_res.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_res, "Controla o particionamento em clusters.\nO efeito NÃO é monotônico com o Louvain: medido no grafo de referência,\n0.5 deu 5 clusters, 1.0 deu 4, 1.5 deu 5 e 2.0 deu 7.\nAjuste e observe o resultado — o padrão 1.0 costuma ser um bom começo.")
        res_f = ctk.CTkFrame(sc, fg_color="transparent")
        res_f.pack(fill="x", padx=10, pady=(0, 6))
        self._res_lbl = ctk.CTkLabel(res_f, text="1.00", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT)
        self._res_lbl.pack(side="left", padx=(0, 8))
        ctk.CTkSlider(
            res_f, from_=0.1, to=5.0, number_of_steps=49,
            variable=self._cluster_res_var, height=14,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT,
            command=lambda v: self._res_lbl.configure(text=f"{v:.2f}"),
        ).pack(side="left", fill="x", expand=True)

        # Reclusterizar SEM refazer o layout: o mapa continua o mesmo mapa, só as cores e os
        # grupos mudam. Refazer o layout a cada ajuste custaria segundos e, pior, embaralharia
        # o desenho — o usuário perderia a referência visual do que estava olhando.
        self._btn(sc, "Aplicar resolução (sem refazer layout)", self._recluster_only,
                  height=30, color=INK, hover=INK_HOV).pack(fill="x", padx=10, pady=(0, 6))

        # Atração e repulsão do ForceAtlas2. O guia recomenda attraction=1 / repulsion=0
        # quando os rótulos se sobrepõem.
        lbl_ar = ctk.CTkLabel(sc, text="Atração / Repulsão:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_ar.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_ar, "Forças do ForceAtlas2.\nO guia do VOSviewer recomenda atração 1 e repulsão 0\nquando os rótulos estão se sobrepondo demais.")
        ar_f = ctk.CTkFrame(sc, fg_color="transparent")
        ar_f.pack(fill="x", padx=10, pady=(0, 6))
        self._attr_lbl = ctk.CTkLabel(ar_f, text="1.0 / 0.0", font=ctk.CTkFont(size=12, weight="bold"),
                                      text_color=ACCENT)
        self._attr_lbl.pack(side="left", padx=(0, 8))

        def _upd_ar(_=None):
            self._attr_lbl.configure(
                text=f"{self._attraction_var.get():.1f} / {self._repulsion_var.get():.1f}")

        ctk.CTkSlider(ar_f, from_=0.1, to=5.0, number_of_steps=49, variable=self._attraction_var,
                      height=14, button_color=ACCENT, button_hover_color=ACCENT_HOV,
                      progress_color=ACCENT, command=_upd_ar).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkSlider(ar_f, from_=0.0, to=5.0, number_of_steps=50, variable=self._repulsion_var,
                      height=14, button_color=INK, button_hover_color=INK_HOV,
                      progress_color=INK, command=_upd_ar).pack(side="left", fill="x", expand=True)

        # 8. Modo de Visualização
        lbl_viz = ctk.CTkLabel(sc, text="Modo de Visualização:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_viz.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_viz, "As cores dos nós serão baseadas nesta métrica:\n- Clusters: Cores por agrupamento.\n- Ano Médio: Heatmap temporal.\n- Grau / Betweenness / Densidade: Métricas de centralidade.")
        ctk.CTkComboBox(sc, values=VIZ_MODES, variable=self._viz_mode_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 9. Filtro de Período (Anos)
        lbl_yr = ctk.CTkLabel(sc, text="Período (Anos):", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_yr.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_yr, "Filtra a base antes da geração do mapa considerando apenas publicações entre os anos indicados.")
        yr_f = ctk.CTkFrame(sc, fg_color="transparent")
        yr_f.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkEntry(yr_f, textvariable=self._year_min_var, placeholder_text="De", width=70, height=28, border_color=ACCENT).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkLabel(yr_f, text="-", text_color=TEXT_MUTED).pack(side="left", padx=4)
        ctk.CTkEntry(yr_f, textvariable=self._year_max_var, placeholder_text="Até", width=70, height=28, border_color=ACCENT).pack(side="left", fill="x", expand=True, padx=(4, 0))
        
        # 10. Stopwords extras
        lbl_sw = ctk.CTkLabel(sc, text="Stopwords Extras:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_sw.pack(anchor="w", padx=10, pady=(4, 2))
        HoverTooltip(lbl_sw, "Palavras para remover explicitamente das palavras-chave separadas por vírgula (Ex: review, human, article).")
        ctk.CTkEntry(sc, textvariable=self._extra_sw_var, placeholder_text="ex: word, study", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 11. Thesaurus CSV
        ctk.CTkLabel(sc, text="Thesaurus CSV:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        th_f = ctk.CTkFrame(sc, fg_color="transparent")
        th_f.pack(fill="x", padx=10, pady=(0, 6))
        self._thesaurus_lbl = ctk.CTkLabel(th_f, text="Nenhum carregado", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
        self._thesaurus_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        self._btn(th_f, "", self._pick_thesaurus, height=26, width=32).pack(side="right")
        
        # 12. Cor Plotly
        ctk.CTkLabel(sc, text="Cor do Plotly:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkComboBox(sc, values=["cluster", "degree", "year"], variable=self._plotly_mode_var, height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # 13. Configuração da IA
        ctk.CTkLabel(sc, text="Provedor de IA:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkComboBox(sc, values=["groq", "openai", "openrouter", "ollama", "custom"], 
                         variable=self._ai_provider_var, command=self._on_ai_provider_change,
                         height=28, button_color=ACCENT, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
                         
        ctk.CTkLabel(sc, text="URL Base da API:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkEntry(sc, textvariable=self._ai_base_url_var, placeholder_text="https://...", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))
        
        # O campo "Chave API" saiu daqui. Era o que de fato alimentava as sete chamadas de
        # IA e o único dos três lugares sem teste de conexão e sem link de criação: colar
        # uma chave errada aqui derrubava tudo com mensagem técnica. A aba de Credenciais é
        # a fonte única; provedor, URL base e modelo continuam sendo ajustes do mapa.
        ctk.CTkButton(sc, text=t("cred.titulo"), height=28, corner_radius=0,
                      fg_color="transparent", text_color=INK, border_width=1,
                      border_color=INK, hover_color="#e0e0e0",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._switch_tab("credenciais")).pack(
            fill="x", padx=10, pady=(4, 6))
        
        ctk.CTkLabel(sc, text="Modelo da IA:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkEntry(sc, textvariable=self._ai_model_var, placeholder_text="Modelo", height=28, border_color=ACCENT).pack(fill="x", padx=10, pady=(0, 6))

        # 13b. Extensão de navegador (passo 7)
        ctk.CTkLabel(sc, text=t("ext_section"), font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INK).pack(anchor="w", padx=10, pady=(10, 2))
        ctk.CTkLabel(sc, text=t("ext_instruction"), font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED, justify="left", wraplength=280).pack(anchor="w", padx=10, pady=(0, 4))

        ctk.CTkLabel(sc, text=t("ext_token"), font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(2, 2))
        self._ext_token_var = ctk.StringVar(value=getattr(self, "_bridge_token", "") or "")
        tok_row = ctk.CTkFrame(sc, fg_color="transparent")
        tok_row.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkEntry(tok_row, textvariable=self._ext_token_var, state="readonly",
                     height=28, border_color=ACCENT).pack(side="left", fill="x", expand=True)
        self._ext_copy_btn = ctk.CTkButton(tok_row, text=t("ext_copy"), width=72, height=28,
                     corner_radius=0, fg_color=ACCENT, hover_color=ACCENT_HOV,
                     command=self._copy_bridge_token)
        self._ext_copy_btn.pack(side="right", padx=(6, 0))

        port_row = ctk.CTkFrame(sc, fg_color="transparent")
        port_row.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(port_row, text=t("ext_port") + ":", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self._ext_port_lbl = ctk.CTkLabel(port_row, text=str(getattr(self, "_bridge_port", None) or "—"),
                     font=ctk.CTkFont(size=11), text_color=INK)
        self._ext_port_lbl.pack(side="left", padx=(6, 0))

        self._btn(sc, t("ext_regenerate"), self._regenerate_bridge_token, height=28,
                  color=INK, hover=INK_HOV).pack(fill="x", padx=10, pady=(2, 8))

        # 14. Network Pruning
        ctk.CTkLabel(sc, text="Pós-processamento:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkCheckBox(sc, text="Remover nós isolados", variable=self._prune_isolated_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV).pack(anchor="w", padx=10, pady=3)
        ctk.CTkCheckBox(sc, text="Manter só maior comp.", variable=self._prune_largest_var, font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOV).pack(anchor="w", padx=10, pady=(3, 8))

        # 15. Config Persistence
        pf = ctk.CTkFrame(sc, fg_color="transparent")
        pf.pack(fill="x", padx=10, pady=8)
        self._btn(pf, "Salvar", self._save_config, height=28, color=INK, hover=INK_HOV).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._btn(pf, "Carregar", self._load_config, height=28, color=INK, hover=INK_HOV).pack(side="right", fill="x", expand=True, padx=(4, 0))
    # ── Tab: Rankings ──────────────────────────────────────────────────
    def _build_tab_ranking(self, parent=None) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent if parent else self._content, fg_color="transparent", corner_radius=0)
        frame.grid_rowconfigure(2, weight=1)
        self._h1(frame, "Rankings", 0)

        ctrl = ctk.CTkFrame(frame, fg_color=CONTENT_BG)
        ctrl.grid(row=1, column=0, padx=24, pady=(0, 6), sticky="ew")
        self._rank_var = ctk.StringVar(value="keywords")
        for lbl, val in [("Top Keywords", "keywords"),
                         ("Top Autores",  "authors"),
                         ("h-index",      "hindex"),
                         ("Top Fontes",   "sources"),
                         ("Clusters",     "clusters")]:
            ctk.CTkRadioButton(ctrl, text=lbl, variable=self._rank_var,
                               value=val, fg_color=ACCENT,
                               hover_color=ACCENT_HOV).pack(
                side="left", padx=12)
        self._btn(ctrl, "Gerar", self._show_ranking,
                  height=36).pack(side="right", padx=8)

        rc = self._card(frame, 2)
        rc.grid_rowconfigure(0, weight=1)
        rc.grid_columnconfigure(0, weight=1)

        # Treeview style
        self._update_treeview_style()

        sb = ctk.CTkScrollbar(rc, orientation="vertical")
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 6))

        self._rank_tree = ttk.Treeview(
            rc,
            style="Blicsa.Treeview",
            yscrollcommand=sb.set,
            selectmode="browse",
            show="headings",
        )
        sb.configure(command=self._rank_tree.yview)
        self._rank_tree.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")
        self._rank_sort_col: str | None = None
        self._rank_sort_rev: bool = False
        return frame

    # ── Tab: Exportar ──────────────────────────────────────────────────
    def _build_tab_export(self) -> ctk.CTkFrame:
        frame = self._tab()
        
        self._h1(frame, "Exportação em Lote", 0)
        
        # Configure variables
        self._exp_adj_var = ctk.BooleanVar(value=True)
        self._exp_gml_var = ctk.BooleanVar(value=True)
        self._exp_ai_var = ctk.BooleanVar(value=True)
        self._exp_xls_var = ctk.BooleanVar(value=True)
        
        options = [
            ("Matriz de Adjacência (CSV)", self._exp_adj_var),
            ("Rede Gephi/VOSviewer (GML)", self._exp_gml_var),
            ("Relatório AI (TXT)", self._exp_ai_var),
            ("Tabela de Corpus Completa (Excel)", self._exp_xls_var),
        ]
        
        list_f = ctk.CTkFrame(frame, fg_color="transparent")
        list_f.grid(row=1, column=0, sticky="ew", padx=30, pady=20)
        
        for i, (text, var) in enumerate(options):
            card = ctk.CTkFrame(list_f, fg_color=CARD_BG, corner_radius=8)
            card.pack(fill="x", pady=5)
            cb = ctk.CTkCheckBox(
                card, text=text, variable=var, 
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color=RED, hover_color=RED_HOVER, text_color=INK
            )
            cb.pack(padx=20, pady=15, anchor="w")
            
        # ── Artefatos visuais do mapa ──
        # `core/map_animation.py` era 543 linhas testadas e sem chamador nenhum. Estes dois
        # botões são o fio que faltava; levantamento em `docs/CODIGO-SEM-CHAMADOR.md`.
        visuais = ctk.CTkFrame(list_f, fg_color="transparent")
        visuais.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(
            visuais, text=t("anim.exportar"), height=36, corner_radius=0,
            fg_color=BLUE, hover_color=BLUE_HOV,
            font=ctk.CTkFont(weight="bold"), command=self._export_map_animation
        ).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(
            visuais, text=t("anim.poster"), height=36, corner_radius=0,
            fg_color=INK, hover_color=INK_HOV,
            font=ctk.CTkFont(weight="bold"), command=self._export_map_poster
        ).pack(fill="x")

        def run_export():
            import os, time
            os.makedirs(REPORTS_DIR, exist_ok=True)
            ts = int(time.time())
            files_saved = []
            
            try:
                if self._exp_adj_var.get() and getattr(self, '_graph', None):
                    import networkx as nx
                    import pandas as pd
                    df_adj = nx.to_pandas_adjacency(self._graph)
                    p = str(REPORTS_DIR / f"adj_{ts}.csv")
                    df_adj.to_csv(p)
                    files_saved.append(p)
                    
                if self._exp_gml_var.get() and getattr(self, '_graph', None):
                    import networkx as nx
                    p = str(REPORTS_DIR / f"rede_{ts}.gml")
                    nx.write_gml(self._graph, p)
                    files_saved.append(p)
                    
                if self._exp_ai_var.get() and getattr(self, '_generator', None):
                    p = str(REPORTS_DIR / f"ai_report_{ts}.txt")
                    # get_cluster_report() devolve lista de dicts; gravá-la direto levantava
                    # TypeError e abortava a exportação inteira (B4). Mesmo texto do export
                    # de clusters individual.
                    with open(p, "w", encoding="utf-8") as f:
                        for c in self._generator.get_cluster_report():
                            f.write(
                                f"Cluster {c['cluster_id']}  |  "
                                f"{c['size']} nós  |  {c['color']}\n"
                                f"  Top nós: {', '.join(map(str, c['top_nodes']))}\n\n"
                            )
                    files_saved.append(p)
                    
                if self._exp_xls_var.get() and getattr(self, '_dataframe', None) is not None:
                    p = str(REPORTS_DIR / f"corpus_{ts}.xlsx")
                    self._dataframe.to_excel(p, index=False)
                    files_saved.append(p)
                    
                for p in files_saved:
                    self._record_export(Path(p).suffix.lstrip("."), p)

                if files_saved:
                    msg = "Arquivos exportados com sucesso!\n" + "\n".join(files_saved)
                    messagebox.showinfo("Exportação Concluída", msg)
                else:
                    messagebox.showwarning("Atenção", "Nenhum dado para exportar (verifique se os dados estão carregados).")
            except Exception as e:
                messagebox.showerror("Erro na exportação", str(e))

        # Bottom right button
        bottom_f = ctk.CTkFrame(frame, fg_color="transparent")
        bottom_f.grid(row=2, column=0, sticky="ew", padx=30, pady=40)
        bottom_f.grid_columnconfigure(0, weight=1)
        
        self._btn(
            bottom_f, "Exportar Selecionados", run_export,
            color=RED, hover=RED_HOV, height=50
        ).pack(side="right")

        return frame

    # ── Actions: data loading ──────────────────────────────────────────
    _FORMAT_LABELS = {
        "scopus":   "Scopus CSV",
        "wos":      "WoS TXT",
        "bibtex":   "BibTeX",
        "pubmed":   "PubMed",
        "openalex": "OpenAlex JSON",
        "crossref": "Crossref JSON",
        "ris":      "RIS",
        "blicsa":   "Blicsa CSV",
    }

    def _auto_detect_format(self, path: str) -> str:
        p = Path(path)
        ext = p.suffix.lower()
        
        # Simple extensions
        if ext == ".ris":
            return "ris"
        if ext in (".bib", ".bibtex"):
            return "bibtex"
        if ext == ".nbib":
            return "pubmed"
        if ext == ".pdf":
            return "pdf"
            
        # Lê o começo do arquivo para inspecionar cabeçalho e etiquetas. UTF-16 com BOM é o
        # "Tab-delimited (Win)" antigo do WoS: lido como UTF-8 vira lixo e caía em "ambíguo".
        try:
            with open(p, "rb") as f:
                bruto = f.read(8192)
            if bruto.startswith((b"\xff\xfe", b"\xfe\xff")):
                head = bruto.decode("utf-16", errors="ignore")
            else:
                head = bruto.decode("utf-8", errors="ignore").lstrip("\ufeff")
        except Exception:
            return "ambiguous" # fallback to dropdown
            
        # 1. JSON analysis
        if ext == ".json" or head.strip().startswith("{") or head.strip().startswith("["):
            if '"results"' in head or '"id":' in head:
                return "openalex"
            if '"message"' in head or '"items"' in head:
                return "crossref"
            return "openalex"
            
        # 2. PubMed Medline / Tagged text
        if "PMID-" in head or "OWN -" in head:
            return "pubmed"

        # RIS e BibTeX salvos como .txt (EndNote, "Other file formats" do WoS): antes caíam
        # em "ambíguo" → leitor do Scopus → registros com todos os campos "nan".
        if re.search(r"^TY  -", head, re.M):
            return "ris"
        if re.search(r"^\s*@\w+\s*\{", head, re.M):
            return "bibtex"

        # 3. Web of Science TXT. Etiqueta no INÍCIO da linha: "PT " em qualquer lugar casava
        # com "CONCEPT " ou "SCRIPT " dentro de um resumo de CSV do Scopus.
        if re.search(r"^(FN|VR|PT)[ \t]", head, re.M):
            return "wos"
            
        # 4. CSV analysis: Scopus vs Web of Science CSV
        if ext == ".csv" or "," in head or ";" in head:
            lines = head.splitlines()
            first_line = lines[0] if lines else ""
            # CSV do próprio Blicsa (export de corpus e docs/sample_dataset.csv): antes caía
            # como "ambíguo" → Scopus → 0 registros (B1).
            if BibliometricParser.is_blicsa_csv_header(first_line):
                return "blicsa"
            if "Authors" in first_line or "Source title" in first_line or "Cited by" in first_line:
                return "scopus"
            # WoS CSV files use AU, TI, SO, PY, etc.
            if "AU" in first_line or "TI" in first_line or "PY" in first_line or "SO" in first_line:
                return "wos"
                
        return "ambiguous"

    def _pick_file(self):
        paths = filedialog.askopenfilenames(
            filetypes=[
                ("Todos os formatos", "*.csv *.txt *.bib *.nbib *.json *.ris"),
                ("CSV", "*.csv"), ("TXT / NBIB / RIS", "*.txt *.nbib *.ris"),
                ("BibTeX", "*.bib"), ("JSON", "*.json"), ("All files", "*.*"),
            ])
        if paths:
            self._file_list_frame.grid() # show the list
            
        for p in paths:
            if p not in self._file_paths:
                fmt = self._auto_detect_format(p)
                if fmt == "ambiguous":
                    fmt = "scopus" # Default if totally unknown but show dropdown?
                self._file_paths.append(p)
                self._file_formats.append(fmt)
                self._add_file_row(p, fmt)

    def _add_file_row(self, path: str, fmt: str):
        row_f = ctk.CTkFrame(self._file_list_frame, fg_color=CARD_BG, corner_radius=0)
        row_f.pack(fill="x", pady=2)
        row_f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(row_f, text=Path(path).name, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=8, pady=4, sticky="ew")
            
        if fmt == "ambiguous" or True: # Just show a dropdown always for safety, but style it like a badge
            fmt_var = ctk.StringVar(value=fmt)
            cb = ctk.CTkComboBox(
                row_f,
                values=list(self._FORMAT_LABELS.keys()),
                variable=fmt_var,
                width=110, height=24,
                fg_color=RED, text_color="white", button_color=RED, border_color=RED, dropdown_hover_color=RED_HOV,
                command=lambda v, p=path: self._set_file_format(p, v),
            )
            cb.grid(row=0, column=1, padx=4, pady=4)
            
        ctk.CTkButton(
            row_f, text="✕", width=28, height=24,
            fg_color="#4a1a1a", hover_color="#6a2a2a",
            font=ctk.CTkFont(size=10),
            command=lambda p=path, f=row_f: self._remove_file(p, f),
        ).grid(row=0, column=2, padx=4, pady=4)
        self._file_row_widgets.append((row_f, path))

    def _set_file_format(self, path: str, fmt: str):
        try:
            idx = self._file_paths.index(path)
            self._file_formats[idx] = fmt
        except ValueError:
            pass

    def _remove_file(self, path: str, frame: ctk.CTkFrame):
        try:
            idx = self._file_paths.index(path)
            self._file_paths.pop(idx)
            self._file_formats.pop(idx)
        except ValueError:
            pass
        self._file_row_widgets = [(f, p) for f, p in self._file_row_widgets if p != path]
        frame.destroy()
        if not self._file_paths:
            self._file_list_frame.grid_remove()

    def _clear_files(self):
        self._file_paths.clear()
        self._file_formats.clear()
        for f, _ in self._file_row_widgets:
            f.destroy()
        self._file_row_widgets.clear()
        self._file_list_frame.grid_remove()

    def _load_data(self):
        if not self._file_paths:
            messagebox.showwarning("Sem arquivo", "Adicione pelo menos um arquivo.")
            return
        _ThreadDaTela(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        self.after(0, self._set_busy, "Carregando arquivos…")
        arquivo_atual = None
        try:
            loaders_map = {
                "scopus":   "load_scopus_csv",
                "wos":      "load_wos_txt",
                "bibtex":   "load_bibtex",
                "pubmed":   "load_pubmed_medline",
                "openalex": "load_openalex_json",
                "crossref": "load_crossref_json",
                "ris":      "load_ris",
                "pdf":      "load_pdf",
                "blicsa":   "load_blicsa_csv",
            }
            dfs = []
            arquivo_atual = None
            for path, fmt in zip(self._file_paths, self._file_formats):
                arquivo_atual = (Path(path).name, self._FORMAT_LABELS.get(fmt, fmt))
                method_name = loaders_map.get(fmt, "load_scopus_csv")
                log.info(f"[Blicsa] Carregando {Path(path).name} ({fmt}) ...")
                parser = BibliometricParser(path)
                df = getattr(parser, method_name)()
                dfs.append(df)
                print(f"  → {len(df)} registros\n")
            if not dfs:
                raise ValueError("Nenhum arquivo carregado.")
            combined = dfs[0] if len(dfs) == 1 else BibliometricParser.merge(*dfs)
            if len(dfs) > 1:
                log.info(f"[OK] Combinados: {len(combined)} registros únicos.\n")
            if combined is None or len(combined) == 0:
                # Antes: "0 registros carregados" e salto para a aba de mapa, como se tivesse
                # dado certo (B2). Agora diz o que houve e o que fazer.
                raise _ImportacaoVazia()
            self._dataframe = combined
            self._generator = None
            self._graph = None
            self._positions = {}
            self._excluded_terms = set()
            log.info(f"[OK] Total: {len(combined)} registros.\n")
            self._refresh_candidate_counts()
            
            # Auto-populate year filter range
            if "year" in combined.columns:
                valid_years = combined["year"].dropna()
                valid_years = valid_years[valid_years > 0]
                if not valid_years.empty:
                    ymin = int(valid_years.min())
                    ymax = int(valid_years.max())
                    self.after(0, lambda y1=ymin, y2=ymax: (
                        self._year_min_var.set(str(y1)),
                        self._year_max_var.set(str(y2))
                    ))
            
            self.after(0, self._update_stats_tab)
            self.after(0, self._set_idle, f"{len(combined)} registros carregados")
            # "analises", não "viz": `viz` não existe em `self._tabs`, e `_switch_tab`
            # esconde TODAS as abas antes de tentar mostrar a pedida. O efeito era a tela
            # ficar em branco logo depois de carregar o arquivo, até o usuário clicar em
            # algum item da navegação. Ver `test_switch_tab_so_usa_abas_que_existem`.
            self.after(0, lambda: self._switch_tab("analises"))
        except Exception as exc:
            # Mensagem de IMPORTAÇÃO, não de projeto (B12): antes um CSV com defeito dizia
            # "Não foi possível abrir o projeto", e o usuário nem tinha aberto projeto.
            log.info(f"[ERRO] importação: {type(exc).__name__}: {exc}\n")
            if isinstance(exc, _ImportacaoVazia):
                msg = t("importacao.erro_vazio")
            elif isinstance(exc, OSError):
                from core.project import diagnosticar_projeto
                msg = t(diagnosticar_projeto(exc))
            else:
                nome, formato = arquivo_atual if arquivo_atual else ("?", "?")
                msg = t("importacao.erro_leitura", arquivo=nome, formato=formato)
            titulo = t("importacao.erro_titulo")
            self.after(0, self._set_idle, titulo)
            self.after(0, lambda m=msg, tt=titulo: messagebox.showerror(tt, m))

    def _cancel_search(self):
        if hasattr(self, '_search_cancel_event') and self._search_cancel_event:
            self._search_cancel_event.set()
            self._set_idle("Cancelando busca... (Aguarde)")
            self._search_cancel_btn.pack_forget()

    def _on_gui_search(self):
        provider = self._search_provider_var.get()
        query = self._effective_query()

        # --- DIÁRIO DE PESQUISA (LEGADO): só no fluxo avulso, sem projeto ativo;
        # com projeto, tudo vai para o backlog.jsonl da pasta do projeto. ---
        import os, json, datetime
        from pathlib import Path
        if getattr(self, "_active_project", None):
            pass  # backlog do projeto registra a busca no _search_worker
        else:
            self._legacy_diary(query, provider)

        fields = self._collect_fields() if provider == "openalex" else []
        if not query and not fields:
            messagebox.showwarning("Campo vazio", "Por favor, digite um termo de busca.")
            return

        max_results = self._current_limit()

        filters = {}
        if fields:
            filters["fields"] = fields
        if self._search_year_start.get().strip(): filters["year_start"] = self._search_year_start.get().strip()
        if self._search_year_end.get().strip(): filters["year_end"] = self._search_year_end.get().strip()
        
        doc_type = self._search_type_var.get()
        if doc_type and doc_type != "Todos":
            filters["type"] = doc_type
            
        lang = getattr(self, "_search_lang_var", ctk.StringVar(value="Todos")).get()
        if lang and lang != "Todos":
            filters["language"] = lang
            
        oa = getattr(self, "_search_oa_var", ctk.BooleanVar(value=False)).get()
        if oa:
            filters["is_oa"] = True

        # Ordenação server-side.
        sort_key = {"Relevância": "relevance", "Mais citados": "citations",
                    "Mais recentes": "date"}.get(
            getattr(self, "_search_sort_var", ctk.StringVar(value="Relevância")).get(), "relevance")
        filters["sort"] = sort_key

        # MODO NAVEGAÇÃO: buscar abre a lista na hora (contagem + 25 primeiros), sem baixar
        # nada em massa. O download só acontece quando o usuário clica em "Importar para o
        # corpus", já com a query e os filtros correntes — e aí sim com aviso de volume.
        # O caminho antigo (colheita completa) continua vivo em `search_to_dataset`, usado
        # pela re-consulta da sidebar, pela prévia e pela recarga offline do backlog.
        self._open_browse(query, provider, filters, max_results)

    def _registrar_busca_da_navegacao(self, baixados: int):
        """Grava a linha `search` da importação feita a partir do modo navegação.

        O botão Buscar não colhe nada: ele abre a navegação com a primeira página. Quem
        confere a página e importa o que está nela nunca passava por `search_to_dataset`, e
        era `search_to_dataset` o único lugar que gravava a busca no backlog. Consequência:
        a **Cadeia de busca** do relatório — a seção do PRISMA-S, a que existe para o leitor
        poder refazer a coleta — saía VAZIA no fluxo mais comum do app, e o fluxo de
        registros ficava com "0 encontrados" para um corpus que tinha registros dentro.

        Só neste caminho: no outro a colheita já gravou a sua, e uma segunda linha somaria
        os `encontrados` duas vezes no fluxograma.

        `baixados` é quantos foram DE FATO importados, não os 25 da página: quem marca
        cinco dos vinte e cinco importou cinco.
        """
        if getattr(self, "_feed_origem", None) != "navegacao":
            return
        sessao = getattr(self, "_browse_session", None)
        if sessao is None:
            return
        try:
            filtros = sessao.current_filters() or {}
            provedor = sessao.provider.__class__.__name__.replace("Provider", "").lower()
            self._backlog("search", {
                "provider": provedor,
                "query": getattr(self, "_last_typed_query", "") or sessao.query,
                "query_interpretada": sessao.query,
                "filters": {k: v for k, v in filtros.items() if k != "fields"},
                "encontrados": int(getattr(sessao, "total", 0) or 0),
                "baixados": int(baixados),
                # A parada é o próprio usuário: ele viu a página e escolheu o que levar.
                # Deixar em branco faria o relatório parecer uma colheita interrompida.
                "stop_reason": "seleção na navegação",
            })
        except Exception as e:
            log.info(f"[Backlog] falha ao registrar a busca da navegação: {e}")

    def _on_feed_import(self, selected_records, fuzzy_dedup=False):
        """Importa a seleção do feed para o corpus.
        DECISÃO DE PRODUTO: importar NÃO deduplica (importar 2x é permitido —
        a dedup é ação explícita no Corpus); registra no backlog do projeto."""
        if not selected_records:
            self._switch_tab("home")
            return
        df_selected = pd.DataFrame(selected_records)
        if self._dataframe is not None and not self._dataframe.empty:
            # concat puro (sem drop_duplicates do merge)
            combined = pd.concat([self._dataframe, df_selected], ignore_index=True)
        else:
            combined = df_selected

        self._dataframe = combined
        self._refresh_candidate_counts()

        if "year" in combined.columns:
            valid_years = combined["year"].dropna()
            valid_years = valid_years[valid_years > 0]
            if not valid_years.empty:
                self._year_min_var.set(str(int(valid_years.min())))
                self._year_max_var.set(str(int(valid_years.max())))

        self._registrar_busca_da_navegacao(len(df_selected))
        self._backlog("import", {"registros": int(len(df_selected)),
                                 "total_corpus": int(len(combined))})
        self._update_stats_tab()
        self._set_idle(f"{len(df_selected)} registros adicionados")
        messagebox.showinfo("Importação", f"{len(df_selected)} registros importados para o corpus com sucesso.")
        self._switch_tab("corpus")

    # ── Estado de erro de IA (item 3 do passo 4) ──────────────────────────
    def _add_ai_error_row(self, container, retry_cb=None, detail=""):
        """Erro REAL de IA: plano chapado no vermelho do design system, canto
        reto, sem parecer resposta do assistente. Retry onde fizer sentido."""
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=5)
        panel = ctk.CTkFrame(row, fg_color=RED, corner_radius=0)
        panel.pack(fill="x", padx=10)
        ctk.CTkLabel(panel, text=t("ai.error_title"), font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#FFFFFF", anchor="w").pack(anchor="w", padx=14, pady=(10, 0))
        body = t("ai.error_body") + (f"\n{detail}" if detail else "")
        ctk.CTkLabel(panel, text=body, font=ctk.CTkFont(size=12), text_color="#FFFFFF",
                     anchor="w", justify="left", wraplength=620).pack(anchor="w", padx=14, pady=(2, 10))
        if retry_cb:
            ctk.CTkButton(panel, text=t("ai.retry"), corner_radius=0, fg_color="#FFFFFF",
                          text_color=INK, hover_color="#E5E5E5", width=130, height=28,
                          command=lambda: (row.destroy(), retry_cb())
                          ).pack(anchor="w", padx=14, pady=(0, 12))
        return row

    def _show_insights(self, text: str):
        """Insights de IA num diálogo (corrige chamada a método INEXISTENTE:
        Sankey/Temático/Historiografia quebravam mesmo com a IA ok).

        Este diálogo é ponto de renderização de IA e estava SEM marcação, embora o
        `docs/inventario-ia.md` já declarasse Sankey, mapa temático e historiografia como
        "faixa + selo". Descoberto ao preparar a captura `ia_marcacao_insights`: não havia
        marcação nenhuma para fotografar. O funil do chat (`_add_blink_message`) cobre os
        outros pontos, mas estes três nunca passam por ele.
        """
        from ui.ai_marking import AIContentFrame

        dlg = ctk.CTkToplevel(self)
        dlg.title("Blicsa — Insights de IA")
        dlg.geometry("720x560")
        dlg.configure(fg_color=CONTENT_BG)

        marcado = AIContentFrame(dlg)
        marcado.pack(fill="both", expand=True, padx=16, pady=16)

        box = ctk.CTkTextbox(marcado.corpo, wrap="word", fg_color=WHITE_CARD, text_color=INK,
                             corner_radius=0, border_width=2, border_color=INK)
        box.pack(fill="both", expand=True)
        from ui.components import insert_markdown
        insert_markdown(box, text)
        box.configure(state="disabled")

    def _show_ai_error_dialog(self, detail: str = "", retry_cb=None):
        """Erro de IA em diálogo: plano chapado vermelho, canto reto, retry."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Blicsa")
        dlg.geometry("560x260")
        dlg.configure(fg_color=RED)
        ctk.CTkLabel(dlg, text=t("ai.error_title"), font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#FFFFFF").pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(dlg, text=t("ai.error_body") + (f"\n\n{detail}" if detail else ""),
                     font=ctk.CTkFont(size=12), text_color="#FFFFFF", justify="left",
                     wraplength=500).pack(anchor="w", padx=20, pady=(0, 12))
        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 20))
        if retry_cb:
            ctk.CTkButton(btns, text=t("ai.retry"), corner_radius=0, fg_color="#FFFFFF",
                          text_color=INK, hover_color="#E5E5E5", width=140, height=32,
                          command=lambda: (dlg.destroy(), retry_cb())).pack(side="left")
        ctk.CTkButton(btns, text=t("dedup.cancel"), corner_radius=0, fg_color="transparent",
                      text_color="#FFFFFF", border_width=2, border_color="#FFFFFF",
                      hover_color="#B82813", width=120, height=32,
                      command=dlg.destroy).pack(side="right")

    # ── Aba Histórico: linha do tempo do backlog do projeto ───────────────
    #: Marcador de tipo na linha do histórico. Texto curto, não emoji: o emoji era a única
    #: informação da coluna e removê-lo sem substituto deixaria a linha sem tipo.
    _HIST_ICONS = {"search": "busca", "import": "import", "dedup": "dedup",
                   "corpus_add": "corpus", "analysis": "análise", "export": "export",
                   "map": "mapa", "extension_add": "extensão", "ia": "IA"}

    def _build_tab_hist(self) -> ctk.CTkFrame:
        frame = self._tab()
        frame.grid_rowconfigure(1, weight=1)
        hdr = ctk.CTkFrame(frame, fg_color=WHITE_CARD, corner_radius=0, border_width=2, border_color=INK, height=60)
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=16)
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=t("history.title"), font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=INK).pack(side="left", padx=16)
        self._hist_sub_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12), text_color=MUTED)
        self._hist_sub_lbl.pack(side="left", padx=8)
        self._hist_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._hist_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        self._hist_frame.grid_columnconfigure(0, weight=1)
        return frame

    # ── Aba: Relatório da pesquisa ─────────────────────────────────────
    def _build_tab_relatorio(self) -> ctk.CTkFrame:
        """A aba que reúne o que o projeto registrou no formato que vai anexo ao artigo.

        Não é a aba de Histórico com outro nome: aquela mostra a linha do tempo crua, uma
        linha por evento. Esta SOMA — declaração de uso de IA, cadeia de busca, fluxo de
        registros, consumo e cobertura —, e é a única que exporta. A montagem está em
        `core/relatorio.py`, sem Tk; aqui só há tela.
        """
        frame = self._tab()
        frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color=WHITE_CARD, corner_radius=0, border_width=2,
                           border_color=INK, height=60)
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=16)
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=t("relatorio.titulo"),
                     font=ctk.CTkFont(size=20, weight="bold"), text_color=INK).pack(
            side="left", padx=16)
        self._relatorio_sub_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12),
                                               text_color=MUTED)
        self._relatorio_sub_lbl.pack(side="left", padx=8)

        for rotulo, comando in (
                (t("relatorio.exportar_pdf"), lambda: self._exportar_relatorio("pdf")),
                (t("relatorio.exportar_json"), lambda: self._exportar_relatorio("json")),
                (t("relatorio.exportar_md"), lambda: self._exportar_relatorio("md")),
                (t("relatorio.copiar_declaracao"), self._copiar_declaracao_de_ia)):
            ctk.CTkButton(hdr, text=rotulo, height=30, width=140, corner_radius=0,
                          fg_color=WHITE_CARD, text_color=INK, border_width=2,
                          border_color=INK, hover_color=PAPER,
                          font=ctk.CTkFont(size=12), command=comando).pack(
                side="right", padx=(4, 16 if rotulo == t("relatorio.exportar_pdf") else 4))

        self._relatorio_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._relatorio_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        self._relatorio_frame.grid_columnconfigure(0, weight=1)
        return frame

    def _relatorio_atual(self) -> dict:
        """O relatório do projeto ativo, montado do backlog + corpus em memória.

        Montado NA HORA, a cada abertura da aba, e nunca guardado: um relatório em cache
        poderia mostrar um número que o projeto já não tem, e num documento de método isso é
        pior do que não ter o documento.
        """
        from core.project import load_backlog
        from core.relatorio import montar

        slug = getattr(self, "_active_project", None)
        backlog = load_backlog(slug) if slug else []
        return montar(backlog,
                      projeto=getattr(self, "_active_project_name", "") or "",
                      versao=__version__,
                      contexto=self._contexto_pesquisa(),
                      df=self._dataframe)

    def _refresh_relatorio_tab(self):
        if not hasattr(self, "_relatorio_frame"):
            return
        for w in self._relatorio_frame.winfo_children():
            w.destroy()

        if not getattr(self, "_active_project", None):
            # Sem projeto não há backlog, e sem backlog o relatório seria um formulário em
            # branco com cara de documento pronto. Dizer que falta o projeto é o conteúdo.
            self._relatorio_sub_lbl.configure(text="")
            ctk.CTkLabel(self._relatorio_frame, text=t("project.none_warning"),
                         font=ctk.CTkFont(size=14), text_color=MUTED).pack(pady=40)
            return

        rel = self._relatorio_atual()
        resumo = rel["ia"]["resumo"]
        self._relatorio_sub_lbl.configure(text=t(
            "relatorio.subtitulo", n=resumo["chamadas"], b=len(rel["buscas"]),
            c=rel["corpus"]["registros"]))

        self._cartao_declaracao(rel)
        self._cartao_pontos_de_ia(rel)
        self._cartao_buscas(rel)
        self._cartao_fluxo(rel)
        self._cartao_cobertura(rel)
        self._cartao_ambiente(rel)

    def _cartao_de_relatorio(self, titulo: str) -> ctk.CTkFrame:
        """Um bloco do relatório, na moldura do design system. Devolve o corpo."""
        cartao = ctk.CTkFrame(self._relatorio_frame, fg_color=WHITE_CARD, corner_radius=0,
                              border_width=2, border_color=INK)
        cartao.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(cartao, text=titulo, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=INK, anchor="w").pack(fill="x", padx=16, pady=(12, 6))
        corpo = ctk.CTkFrame(cartao, fg_color="transparent")
        corpo.pack(fill="x", padx=16, pady=(0, 14))
        corpo.grid_columnconfigure(1, weight=1)
        return corpo

    def _linhas_de_relatorio(self, corpo, linhas, cabecalho=None):
        """Uma tabelinha em grid. Cabeçalho em negrito, uma régua embaixo dele."""
        deslocamento = 0
        if cabecalho:
            for c, texto in enumerate(cabecalho):
                ctk.CTkLabel(corpo, text=texto, font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=INK, anchor="w").grid(row=0, column=c, sticky="w",
                                                              padx=(0, 16), pady=(0, 2))
            ctk.CTkFrame(corpo, height=1, fg_color=INK).grid(
                row=1, column=0, columnspan=max(len(cabecalho), 2), sticky="ew", pady=(0, 4))
            deslocamento = 2
        for r, linha in enumerate(linhas):
            for c, texto in enumerate(linha):
                ctk.CTkLabel(corpo, text=str(texto), font=ctk.CTkFont(size=12),
                             text_color=INK if c == 0 else "#555555", anchor="w",
                             justify="left", wraplength=560 if c else 0).grid(
                    row=r + deslocamento, column=c, sticky="w", padx=(0, 16), pady=1)

    def _cartao_declaracao(self, rel: dict):
        from core.relatorio import declaracao_de_uso

        corpo = self._cartao_de_relatorio(t("relatorio.sec_declaracao"))
        # Numa CAIXA DE TEXTO, e não num rótulo: a declaração existe para ser copiada, e de
        # um `CTkLabel` não se seleciona nada. O botão de copiar continua no cabeçalho,
        # para quem não quer selecionar à mão.
        caixa = ctk.CTkTextbox(corpo, wrap="word", font=ctk.CTkFont(size=12), height=112,
                               fg_color=PAPER, text_color=INK, corner_radius=0,
                               border_width=1, border_color=MUTED)
        caixa.grid(row=0, column=0, columnspan=2, sticky="ew")
        caixa.insert("1.0", declaracao_de_uso(rel))
        caixa.configure(state="disabled")
        self._relatorio_caixa_declaracao = caixa

    def _cartao_pontos_de_ia(self, rel: dict):
        from core.relatorio import _ordem_de_gravidade
        from core.uso_de_ia import DESCREVE, PONTOS

        resumo = rel["ia"]["resumo"]
        corpo = self._cartao_de_relatorio(t("relatorio.sec_pontos"))
        if not resumo["chamadas"]:
            ctk.CTkLabel(corpo, text=t("relatorio.tabela_vazia"), font=ctk.CTkFont(size=12),
                         text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="w")
            return

        linhas = [[t(f"ia.ponto.{p}"), t(f"ia.natureza.{PONTOS.get(p, DESCREVE)}"), str(n)]
                  for p, n in sorted(resumo["por_ponto"].items(), key=_ordem_de_gravidade)]
        self._linhas_de_relatorio(
            corpo, linhas,
            [t("relatorio.col_ponto"), t("relatorio.col_natureza"), t("relatorio.col_chamadas")])

        consumo = self._cartao_de_relatorio(t("relatorio.sec_consumo"))
        self._linhas_de_relatorio(
            consumo,
            [[m, str(v["chamadas"]), str(v["entrada"]), str(v["saida"]), str(v["total"])]
             for m, v in resumo["por_modelo"].items()],
            [t("relatorio.col_modelo"), t("relatorio.col_chamadas"), t("relatorio.col_entrada"),
             t("relatorio.col_saida"), t("relatorio.col_total")])
        avisos = []
        if resumo["sem_medida"]:
            avisos.append(t("relatorio.sem_medida", n=resumo["sem_medida"]))
        if resumo["falhas"]:
            avisos.append(t("relatorio.falhas", n=resumo["falhas"]))
        for i, aviso in enumerate(avisos):
            ctk.CTkLabel(consumo, text=aviso, font=ctk.CTkFont(size=11), text_color=MUTED,
                         anchor="w", justify="left", wraplength=680).grid(
                row=100 + i, column=0, columnspan=5, sticky="w", pady=(6, 0))

    def _cartao_buscas(self, rel: dict):
        corpo = self._cartao_de_relatorio(t("relatorio.sec_buscas"))
        if not rel["buscas"]:
            ctk.CTkLabel(corpo, text=t("relatorio.sem_buscas"), font=ctk.CTkFont(size=12),
                         text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="w")
            return
        for i, b in enumerate(rel["buscas"]):
            bloco = ctk.CTkFrame(corpo, fg_color="transparent")
            bloco.grid(row=i, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            bloco.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(bloco, text=f"{i + 1}. {b['base']} — {b['quando']}",
                         font=ctk.CTkFont(size=12, weight="bold"), text_color=INK,
                         anchor="w").grid(row=0, column=0, sticky="w")
            # A string que FOI para a API, monoespaçada: é o que se copia para refazer a
            # busca, e a diferença para a digitada é o que explica um número que não bate.
            ctk.CTkLabel(bloco, text=b["string_enviada"],
                         font=ctk.CTkFont(family="Courier", size=11), text_color=INK,
                         anchor="w", justify="left", wraplength=680).grid(
                row=1, column=0, sticky="w", pady=(2, 0))
            detalhes = [t("relatorio.encontrados_baixados",
                          e=b["encontrados"] if b["encontrados"] is not None else "—",
                          b=b["baixados"] if b["baixados"] is not None else "—")]
            if b["filtros"]:
                detalhes.append(t("relatorio.filtros",
                                  f=", ".join(f"{k}={v}" for k, v in b["filtros"].items())))
            if b["motivo_de_parada"]:
                detalhes.append(t("relatorio.parada", m=b["motivo_de_parada"]))
            ctk.CTkLabel(bloco, text=" · ".join(detalhes), font=ctk.CTkFont(size=11),
                         text_color=MUTED, anchor="w", justify="left",
                         wraplength=680).grid(row=2, column=0, sticky="w")

    def _cartao_fluxo(self, rel: dict):
        f = rel["fluxo"]
        corpo = self._cartao_de_relatorio(t("relatorio.sec_fluxo"))
        self._linhas_de_relatorio(
            corpo,
            [[t("relatorio.fluxo_encontrados"), f["encontrados"]],
             [t("relatorio.fluxo_baixados"), f["baixados"]],
             [t("relatorio.fluxo_importados"), f["importados"]],
             [t("relatorio.fluxo_duplicatas"), f["duplicatas_removidas"]],
             [t("relatorio.fluxo_final"), f["corpus_final"]]],
            [t("relatorio.col_etapa"), t("relatorio.col_registros")])

    def _cartao_cobertura(self, rel: dict):
        c = rel["corpus"]
        corpo = self._cartao_de_relatorio(t("relatorio.sec_cobertura"))
        if not c["registros"]:
            ctk.CTkLabel(corpo, text=t("relatorio.sem_corpus"), font=ctk.CTkFont(size=12),
                         text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="w")
            return
        periodo = f"{c['ano_min']}–{c['ano_max']}" if c["ano_min"] else "—"
        ctk.CTkLabel(corpo, text=t("relatorio.corpus_resumo", n=c["registros"],
                                   periodo=periodo),
                     font=ctk.CTkFont(size=12), text_color=INK, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        grade = ctk.CTkFrame(corpo, fg_color="transparent")
        grade.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._linhas_de_relatorio(
            grade,
            [[t("relatorio.campo_resumo"), f"{c['com_resumo']}%"],
             [t("relatorio.campo_referencias"), f"{c['com_referencias']}%"],
             [t("relatorio.campo_doi"), f"{c['com_doi']}%"],
             [t("relatorio.campo_palavras"), f"{c['com_palavras_chave']}%"],
             [t("relatorio.campo_oa"), f"{c['acesso_aberto']}%"]],
            [t("relatorio.col_campo"), t("relatorio.col_preenchido")])
        if c["bases"]:
            ctk.CTkLabel(corpo, text=t("relatorio.bases",
                                       b=", ".join(f"{k} ({v})" for k, v in c["bases"].items())),
                         font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w",
                         justify="left", wraplength=680).grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _cartao_ambiente(self, rel: dict):
        a = rel["ambiente"]
        corpo = self._cartao_de_relatorio(t("relatorio.sec_ambiente"))
        self._linhas_de_relatorio(corpo, [
            ["Blicsa", f"{a['blicsa']} ({a['executavel']})"],
            ["Python", f"{a['python']} · {a['sistema']}"],
        ])

    def _copiar_declaracao_de_ia(self):
        from core.relatorio import declaracao_de_uso

        if not getattr(self, "_active_project", None):
            messagebox.showwarning("Blicsa", t("project.none_warning"))
            return
        texto = declaracao_de_uso(self._relatorio_atual())
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._set_idle(t("relatorio.copiado"))

    def _exportar_relatorio(self, formato: str):
        """Salva o relatório e o registra no backlog como qualquer outra exportação."""
        from core.relatorio import para_json, para_markdown

        if not getattr(self, "_active_project", None):
            messagebox.showwarning("Blicsa", t("project.none_warning"))
            return

        if formato == "pdf":
            from core.relatorio_pdf import disponivel
            if not disponivel():
                # Aviso ANTES do seletor de arquivo: pedir onde salvar e só então dizer que
                # não dá seria fazer o usuário escolher pasta e nome à toa.
                messagebox.showwarning("Blicsa", t("relatorio.pdf_ausente"))
                return

        extensoes = {"md": [("Markdown", "*.md")], "json": [("JSON", "*.json")],
                     "pdf": [("PDF", "*.pdf")]}
        caminho = filedialog.asksaveasfilename(
            defaultextension=f".{formato}", filetypes=extensoes[formato],
            initialfile=f"relatorio_{self._active_project}.{formato}")
        if not caminho:
            return

        rel = self._relatorio_atual()
        try:
            if formato == "pdf":
                from core.relatorio_pdf import gerar
                gerar(rel, caminho)
            else:
                texto = para_markdown(rel) if formato == "md" else para_json(rel)
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(texto)
        except Exception as exc:
            log.info(f"[Relatório] falha ao exportar {formato}: {exc}")
            messagebox.showerror("Blicsa", str(exc))
            return

        self._record_export(f"relatorio_{formato}", caminho)
        self._set_idle(t("relatorio.exportado", caminho=caminho))

    def _hist_entry_summary(self, entry) -> str:
        d = entry.get("detail", {}) or {}
        a = entry.get("action", "?")
        if a == "search":
            return (f'{d.get("provider", "?")} · "{d.get("query", "")}" · '
                    f'{d.get("encontrados", "?")} encontrados / {d.get("baixados", "?")} baixados · '
                    f'{d.get("stop_reason", "")}')
        if a == "import":
            return f'{d.get("registros", "?")} registros → corpus com {d.get("total_corpus", "?")}'
        if a == "dedup":
            status = t("dedup.apply") if d.get("aplicado") else t("dedup.cancel")
            return (f'{d.get("pares", "?")} pares · {d.get("por_doi", 0)} DOI · '
                    f'{d.get("por_titulo", 0)} título · {d.get("por_autor_ano", 0)} autor+ano · {status}')
        if a == "analysis":
            return (f'{d.get("tipo", "?")} · {d.get("nos", "?")} nós · '
                    f'{d.get("arestas", "?")} arestas · {d.get("clusters", "?")} clusters')
        if a in ("export", "map"):
            return f'{d.get("formato", "?")} → {d.get("caminho_relativo", "")}'
        if a == "ia":
            # A linha do histórico nomeia o PONTO e a natureza, não só "usou IA": é a
            # diferença entre um rótulo que foi para a figura publicada e uma pergunta no
            # chat, e ela não pode depender de abrir o relatório para aparecer.
            partes = [t(f'ia.ponto.{d.get("ponto", "")}'),
                      t(f'ia.natureza.{d.get("natureza", "descreve")}'),
                      d.get("modelo", "")]
            tokens = d.get("tokens") or {}
            if tokens.get("total"):
                partes.append(f'{tokens["total"]} tokens')
            if d.get("erro"):
                partes.append(d["erro"])
            return " · ".join(p for p in partes if p)
        return json.dumps(d, ensure_ascii=False)[:120]

    def _refresh_hist_tab(self):
        if not hasattr(self, "_hist_frame"):
            return
        for w in self._hist_frame.winfo_children():
            w.destroy()
        slug = getattr(self, "_active_project", None)
        if not slug:
            self._hist_sub_lbl.configure(text="")
            ctk.CTkLabel(self._hist_frame, text=t("project.none_warning"),
                         font=ctk.CTkFont(size=14), text_color=MUTED).pack(pady=40)
            return
        from core.project import load_backlog
        entries = load_backlog(slug)
        self._hist_sub_lbl.configure(text=t("history.subtitle", name=self._active_project_name,
                                            n=len(entries)))
        if not entries:
            ctk.CTkLabel(self._hist_frame, text=t("history.empty"),
                         font=ctk.CTkFont(size=14), text_color=MUTED).pack(pady=40)
            return
        for i, entry in enumerate(reversed(entries)):
            row = ctk.CTkFrame(self._hist_frame, fg_color=WHITE_CARD, corner_radius=0,
                               border_width=2, border_color=INK)
            row.pack(fill="x", pady=4, padx=4)
            row.grid_columnconfigure(2, weight=1)
            icon = self._HIST_ICONS.get(entry.get("action"), "•")
            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=20), width=44).grid(
                row=0, column=0, rowspan=2, padx=(8, 4), pady=8)
            ctk.CTkLabel(row, text=t(f'history.action_{entry.get("action", "search")}'),
                         font=ctk.CTkFont(size=13, weight="bold"), text_color=INK,
                         anchor="w").grid(row=0, column=1, sticky="w", padx=4, pady=(8, 0))
            ctk.CTkLabel(row, text=str(entry.get("ts", ""))[:19].replace("T", " "),
                         font=ctk.CTkFont(size=11), text_color=MUTED).grid(
                row=0, column=3, sticky="e", padx=12, pady=(8, 0))
            ctk.CTkLabel(row, text=self._hist_entry_summary(entry), font=ctk.CTkFont(size=12),
                         text_color="#555555", anchor="w", justify="left", wraplength=760).grid(
                row=1, column=1, columnspan=2, sticky="w", padx=4, pady=(0, 8))
            if entry.get("action") == "search":
                btns = ctk.CTkFrame(row, fg_color="transparent")
                btns.grid(row=1, column=3, sticky="e", padx=8, pady=(0, 8))
                ctk.CTkButton(btns, text=t("history.rerun"), width=110, height=26, corner_radius=0,
                              fg_color=WHITE_CARD, text_color=INK, hover_color=CARD2_BG,
                              border_width=1, border_color=INK,
                              command=lambda e=entry: self._rerun_search_entry(e)).pack(side="left", padx=4)
                if entry.get("detail", {}).get("arquivo"):
                    ctk.CTkButton(btns, text=t("history.reload"), width=150, height=26, corner_radius=0,
                                  fg_color=INK, text_color=WHITE_CARD, hover_color=INK_HOV,
                                  command=lambda e=entry: self._reload_search_entry(e)).pack(side="left", padx=4)

    def _rerun_search_entry(self, entry):
        """Remonta query + filtros da busca antiga na Coletar (não dispara sozinho)."""
        d = entry.get("detail", {}) or {}
        prov = str(d.get("provider", "openalex")).lower()
        seg_label = {"openalex": "OpenAlex", "crossref": "Crossref", "pubmed": "PubMed"}.get(prov, "OpenAlex")
        self._provider_seg.set(seg_label)
        self._search_provider_var.set(prov)
        self._search_query_entry.delete(0, "end")
        self._search_query_entry.insert(0, d.get("query", ""))
        f = d.get("filters", {}) or {}
        for entry_w, key in [(self._search_year_start, "year_start"), (self._search_year_end, "year_end")]:
            entry_w.delete(0, "end")
            if f.get(key):
                entry_w.insert(0, str(f[key]))
        self._search_type_var.set(f.get("type", "Todos"))
        self._search_lang_var.set(f.get("language", "Todos"))
        self._search_oa_var.set(bool(f.get("is_oa", False)))
        self._switch_tab("import")

    def _reload_search_entry(self, entry):
        """LOCAL-FIRST: repopula o feed com o JSON bruto salvo da busca — sem rede."""
        slug = getattr(self, "_active_project", None)
        rel = (entry.get("detail", {}) or {}).get("arquivo")
        if not slug or not rel:
            return
        from core.project import load_search_raw
        try:
            recs = load_search_raw(slug, rel)
        except Exception as e:
            messagebox.showerror("Blicsa", str(e))
            return
        from ui.search_feed import SearchFeedView
        review_tab = self._tabs["review"]
        for w in review_tab.winfo_children():
            w.destroy()
        fv = SearchFeedView(review_tab, self._on_feed_import,
                            lambda: self._switch_tab("hist"))
        fv.pack(fill="both", expand=True)
        fv.load_results(recs, t("history.reloaded", n=len(recs)))
        self.search_feed_view = fv
        self._switch_tab("review")
        log.info(f"[Histórico] recarregado offline: {rel} ({len(recs)} registros)")

    def _legacy_diary(self, query, provider):
        import os, json, datetime
        proj_name = "Pesquisa_Atual"
        if hasattr(self, '_current_project_path') and getattr(self, '_current_project_path', None):
            proj_name = Path(self._current_project_path).stem
            
        diary_dir = os.path.expanduser(f"~/Blicsa/pesquisas/{proj_name}")
        os.makedirs(diary_dir, exist_ok=True)
        diary_path = os.path.join(diary_dir, "diary.json")
        
        diary = {"strings_usadas": [], "blink_usage": 0}
        if os.path.exists(diary_path):
            try:
                with open(diary_path, "r", encoding="utf-8") as df:
                    diary = json.load(df)
            except:
                pass
                
        diary["strings_usadas"].append({
            "query": query,
            "base": provider,
            "timestamp": datetime.datetime.now().isoformat()
        })
        diary["blink_usage"] = diary.get("blink_usage", 0) + 1
        
        with open(diary_path, "w", encoding="utf-8") as df:
            json.dump(diary, df, indent=2, ensure_ascii=False)


    def _effective_query(self) -> str:
        """BLICSA TRANSLATOR não-destrutivo: o campo do usuário fica intacto;
        a query interpretada aparece no label 'Interpretado como:'."""
        typed = self._search_query_entry.get().strip()
        self._last_typed_query = typed
        provider = self._search_provider_var.get()
        query = typed
        if typed and not typed.startswith('"') and "(" not in typed:
            if provider == "openalex":
                query = f'"{typed}"'
            elif provider == "pubmed":
                query = f'{typed}[Title/Abstract]'
        if query != typed:
            self._interpreted_lbl.configure(text=t("search.interpreted", query=query))
        else:
            self._interpreted_lbl.configure(text="")
        return query

    def _current_limit(self) -> int:
        """Limite da colheita: SEM teto e SEM piso — campo vazio é ilimitado.

        Uma regra só: **número positivo digitado vale exatamente; qualquer outra coisa é
        ilimitado.** Vazio, zero, negativo e texto inválido caem todos no mesmo lugar,
        porque nenhum deles expressa um limite — e substituí-los por 1000 seria um teto que
        o usuário não pediu, exatamente o defeito que o campo vazio já tinha.

        A proteção contra colher demais sem querer é o aviso de volume
        (`_search_after_count` → `_show_count_dialog`, a partir de 2000 resultados na base),
        que mostra o total e deixa escolher — não um corte silencioso do valor pedido.
        """
        UNLIMITED = 10_000_000
        if self._search_unlimited_var.get():
            return UNLIMITED
        try:
            n = int(self._search_max_entry.get().strip())
        except (ValueError, TypeError, AttributeError):
            return UNLIMITED
        return n if n >= 1 else UNLIMITED

    # ── Busca por campo + prévia paginada (cherry-pick estilo Scopus) ──
    def _add_field_row(self):
        i = len(self._field_rows)
        fvar = ctk.StringVar(value=list(self._FIELD_OPTIONS)[0] if i == 0 else t("fields.field_title"))
        menu = ctk.CTkOptionMenu(self._field_rows_frame, variable=fvar, width=110, corner_radius=0,
                                 fg_color=WHITE_CARD, text_color=INK, button_color=WHITE_CARD,
                                 button_hover_color=CARD2_BG, values=list(self._FIELD_OPTIONS))
        menu.grid(row=i, column=0, padx=(0, 6), pady=2, sticky="w")
        ent = ctk.CTkEntry(self._field_rows_frame, placeholder_text=t("fields.placeholder"),
                           placeholder_text_color=MUTED, fg_color=WHITE_CARD, text_color=INK, height=30)
        ent.grid(row=i, column=1, pady=2, sticky="ew")
        self._field_rows.append((fvar, ent))

    def _collect_fields(self) -> list:
        out = []
        for fvar, ent in getattr(self, "_field_rows", []):
            v = ent.get().strip()
            if v:
                out.append((self._FIELD_OPTIONS.get(fvar.get(), "all"), v))
        return out

    def _run_preview(self, page: int = 1):
        """Páginas rápidas via OpenAlexProvider.browse(): consulta UMA página
        server-side (nada é baixado em massa)."""
        if self._search_provider_var.get() != "openalex":
            messagebox.showinfo("Blicsa", t("preview.openalex_only"))
            return
        query = self._effective_query()
        fields = self._collect_fields()
        if not query and not fields:
            messagebox.showwarning("Campo vazio", "Por favor, digite um termo de busca.")
            return
        filters = {}
        if fields:
            filters["fields"] = fields
        if self._search_year_start.get().strip(): filters["year_start"] = self._search_year_start.get().strip()
        if self._search_year_end.get().strip(): filters["year_end"] = self._search_year_end.get().strip()
        if self._search_type_var.get() != "Todos": filters["type"] = self._search_type_var.get()
        if self._search_lang_var.get() != "Todos": filters["language"] = self._search_lang_var.get()
        if self._search_oa_var.get(): filters["is_oa"] = True
        filters["sort"] = {"Relevância": "relevance", "Mais citados": "citations",
                           "Mais recentes": "date"}.get(self._search_sort_var.get(), "relevance")

        self._preview_state = {"query": query, "filters": filters, "page": page, "per_page": 25}
        self._ensure_preview_frame()
        self._preview_count_lbl.configure(text=t("preview.loading"))

        import threading
        def worker():
            from core.sources import OpenAlexProvider
            err, recs, total = None, [], 0
            try:
                recs, total = OpenAlexProvider().browse(query, filters, page=page, per_page=25)
            except Exception as e:
                err = str(e)
            self.after(0, lambda: self._render_preview(recs, total, err))
        _ThreadDaTela(target=worker, daemon=True).start()

    def _ensure_preview_frame(self):
        if getattr(self, "_preview_frame", None) is not None and self._preview_frame.winfo_exists():
            self._preview_frame.grid()
            self._preview_frame.tkraise()
            return
        parent = self._tabs["import"]
        parent.grid_rowconfigure(1, weight=1)
        pf = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=0, border_width=2, border_color=INK)
        pf.grid(row=1, column=0, padx=24, pady=8, sticky="nsew")
        pf.grid_columnconfigure(0, weight=1)
        pf.grid_rowconfigure(1, weight=1)
        self._preview_frame = pf

        hdr = ctk.CTkFrame(pf, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        self._preview_count_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=INK)
        self._preview_count_lbl.pack(side="left")
        ctk.CTkButton(hdr, text=t("preview.close"), width=90, height=28, corner_radius=0,
                      fg_color=WHITE_CARD, text_color=INK, hover_color=CARD2_BG,
                      border_width=1, border_color=INK,
                      command=lambda: self._preview_frame.grid_remove()).pack(side="right")

        self._preview_list = ctk.CTkScrollableFrame(pf, fg_color="transparent")
        self._preview_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self._preview_list.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(pf, fg_color=INK, corner_radius=0, height=48)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)
        ctk.CTkButton(bar, text="◀", width=44, corner_radius=0, fg_color=WHITE_CARD, text_color=INK,
                      command=lambda: self._preview_page_step(-1)).pack(side="left", padx=(12, 4), pady=8)
        self._preview_page_lbl = ctk.CTkLabel(bar, text="—", text_color=WHITE_CARD,
                                              font=ctk.CTkFont(size=13, weight="bold"))
        self._preview_page_lbl.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="▶", width=44, corner_radius=0, fg_color=WHITE_CARD, text_color=INK,
                      command=lambda: self._preview_page_step(1)).pack(side="left", padx=4)
        self._preview_harvest_btn = ctk.CTkButton(
            bar, text=t("preview.harvest"), corner_radius=0, fg_color=RED, hover_color=RED_HOV,
            text_color=WHITE_CARD, font=ctk.CTkFont(weight="bold"),
            command=self._harvest_from_preview)
        self._preview_harvest_btn.pack(side="right", padx=12)

    def _render_preview(self, recs, total, err):
        st = getattr(self, "_preview_state", None)
        if st is None or not self._preview_frame.winfo_exists():
            return
        for w in self._preview_list.winfo_children():
            w.destroy()
        if err:
            self._preview_count_lbl.configure(text=f"Erro: {err}")
            return
        st["total"] = total
        page, per_page = st["page"], st["per_page"]
        if total:
            frm = (page - 1) * per_page + 1
            to = min(page * per_page, total)
            self._preview_count_lbl.configure(text=t("preview.count", total=total, frm=frm, to=to))
        else:
            self._preview_count_lbl.configure(text=t("preview.empty"))
        from ui.search_feed import ArticleCard
        for i, r in enumerate(recs):
            ArticleCard(self._preview_list, r, lambda *a, **k: None, i).pack(fill="x", pady=4)
        max_page = max(1, (min(total, 10_000) + per_page - 1) // per_page)
        self._preview_page_lbl.configure(text=t("preview.page", page=page, max=max_page))

    def _preview_page_step(self, delta: int):
        st = getattr(self, "_preview_state", None)
        if not st:
            return
        new_page = st["page"] + delta
        max_page = max(1, (min(st.get("total", 0), 10_000) + st["per_page"] - 1) // st["per_page"])
        if 1 <= new_page <= max_page:
            self._run_preview(page=new_page)

    def _harvest_from_preview(self):
        """Colhe o conjunto da prévia respeitando o LIMITE atual da UI
        (diferente do redesign revertido, que baixava o total inteiro)."""
        st = getattr(self, "_preview_state", None)
        if not st or not st.get("total"):
            return
        self._preview_frame.grid_remove()
        self.search_to_dataset(st["query"], "openalex", self._current_limit(), st["filters"])

    def _count_for_provider(self, provider, query, filters):
        """Contagem barata da base selecionada (fonte única). None se falhar."""
        from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider
        provs = {"openalex": [OpenAlexProvider], "crossref": [CrossrefProvider],
                 "pubmed": [PubMedProvider]}.get(provider.lower())
        if not provs:  # zotero e outros: sem count → não avisa
            return None
        total = 0
        got = False
        for cls in provs:
            try:
                total += cls().count(query, filters)
                got = True
            except Exception:
                pass
        return total if got else None

    def _search_after_count(self, n, query, provider, max_results, filters):
        self._set_idle("")
        THRESHOLD = 2000
        # Só avisa quando REALMENTE vai colher muito (conjunto grande E sem limite baixo).
        if not n or n <= THRESHOLD or max_results <= THRESHOLD:
            self.search_to_dataset(query, provider, max_results, filters)
            return
        self._show_count_dialog(n, query, provider, max_results, filters)

    def _show_count_dialog(self, n, query, provider, max_results, filters):
        import customtkinter as ctk
        dlg = ctk.CTkToplevel(self)
        dlg.title("Muitos resultados")
        dlg.geometry("460x230")
        dlg.transient(self)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=f"Encontrados {n:,}".replace(",", ".") + " resultados.",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 4), padx=20)
        ctk.CTkLabel(dlg, text="Baixar todos pode demorar (paginação de 100 em 100).\n"
                              "Como você quer baixar?", justify="left").pack(pady=(0, 12), padx=20)
        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=8)

        def top_cited():
            dlg.destroy()
            f = dict(filters); f["sort"] = "citations"
            self.search_to_dataset(query, provider, 2000, f)

        def all_of():
            dlg.destroy()
            self.search_to_dataset(query, provider, max_results, filters)

        ctk.CTkButton(btns, text="Top 2000 mais citados", fg_color=RED, text_color="white",
                      corner_radius=0, command=top_cited).pack(fill="x", pady=3)
        ctk.CTkButton(btns, text=f"Baixar todos ({n:,})".replace(",", "."), fg_color=WHITE_CARD,
                      text_color=INK, border_width=2, border_color=INK, corner_radius=0,
                      command=all_of).pack(fill="x", pady=3)
        ctk.CTkButton(btns, text="Cancelar", fg_color="transparent", text_color=INK,
                      hover_color="#e0e0e0", corner_radius=0, command=dlg.destroy).pack(fill="x", pady=3)

    def _open_query_builder(self):
        from ui.query_builder import show_query_builder
        def on_query_built(query_str):
            self._search_query_entry.delete(0, 'end')
            self._search_query_entry.insert(0, query_str)
        show_query_builder(self, on_query_built)

    # ── Modo navegação (core/browse.py) ──────────────────────────────────
    def _open_browse(self, query: str, provider_name: str, filters: dict,
                     max_results: int = 0):
        """Abre a lista no modo navegação: contagem + 25 primeiros + facetas.

        Nenhum download em massa acontece aqui. O `max_results` só é guardado para quando o
        usuário mandar importar.
        """
        import threading

        from core.browse import BrowseSession, supported_facets
        from core.sources import CrossrefProvider, OpenAlexProvider, PubMedProvider
        from ui.search_feed import SearchFeedView

        classe = {"openalex": OpenAlexProvider, "crossref": CrossrefProvider,
                  "pubmed": PubMedProvider}.get(provider_name.lower(), OpenAlexProvider)
        sessao = BrowseSession(classe(), query, base_filters=dict(filters or {}))
        self._browse_session = sessao
        self._browse_import_limit = max_results

        # Feed novo, em branco, na aba de revisão.
        review_tab = self._tabs["review"]
        for w in review_tab.winfo_children():
            w.destroy()
        fv = SearchFeedView(
            review_tab,
            lambda recs, dd=False: self._on_feed_import(recs, dd),
            lambda: self._switch_tab("import"),
            lambda recs, sel: self._feed_cbs.get("ai", lambda *a: None)(recs, sel),
        )
        fv.pack(fill="both", expand=True)
        self.search_feed_view = fv
        #: De ONDE vieram os registros que estão no feed. O `_on_feed_import` precisa saber:
        #: a colheita (`search_to_dataset`) já grava a linha `search` no backlog, a
        #: navegação não gravava nenhuma — e quem buscava, olhava a página e importava o que
        #: estava nela ficava com a Cadeia de Busca do relatório VAZIA. Sem esta marca, a
        #: correção ou perderia o registro ou o contaria duas vezes.
        self._feed_origem = "navegacao"
        fv.on_goto_page = lambda p: self._browse_goto(p)
        fv.on_retry = lambda: self._browse_goto(sessao.page, force=True)
        fv.on_import_all = lambda s, total: self._browse_import_all(s, total)
        if supported_facets(sessao.provider):
            fv.show_facets_loading()
        self._switch_tab("review")
        self._set_busy(t("browse.searching"))

        def worker():
            pagina = sessao.fetch_page(1)
            self.after(0, lambda: self._browse_render(pagina, primeira=True))
            # Facetas depois da lista: a lista é o que o usuário está esperando ver.
            if supported_facets(sessao.provider) and not pagina.error:
                facetas = sessao.fetch_facets()
                self.after(0, lambda: self._browse_render_facets(facetas))

        _ThreadDaTela(target=worker, daemon=True).start()

    def _browse_goto(self, pagina: int, force: bool = False):
        """Troca de página (ou tentar de novo) sem travar a UI."""
        import threading

        sessao = getattr(self, "_browse_session", None)
        fv = getattr(self, "search_feed_view", None)
        if sessao is None or fv is None:
            return
        self._set_busy(t("browse.searching"))

        def worker():
            p = sessao.fetch_page(pagina, use_cache=not force)
            self.after(0, lambda: self._browse_render(p))

        _ThreadDaTela(target=worker, daemon=True).start()

    def _browse_render(self, pagina, primeira: bool = False):
        """Desenha a página, descartando resposta obsoleta."""
        sessao = getattr(self, "_browse_session", None)
        fv = getattr(self, "search_feed_view", None)
        if sessao is None or fv is None or not fv.winfo_exists():
            return
        # Só a última query vence: resposta de token velho é ignorada em silêncio.
        if not sessao.is_current(getattr(pagina, "token", 0)):
            return

        self._set_idle("")
        fv.set_result_header(pagina.total, sessao.query)
        fv.load_browse_page(pagina, session=sessao)
        fv.render_chips(sessao.chips(), on_remove=self._browse_remove_chip)
        if primeira and pagina.total:
            log.info(f"[Busca] {sessao.query!r} → {pagina.total} resultados "
                     f"({pagina.pages} páginas)")

    def _browse_render_facets(self, facetas):
        fv = getattr(self, "search_feed_view", None)
        sessao = getattr(self, "_browse_session", None)
        if fv is None or sessao is None or not fv.winfo_exists():
            return
        fv.render_facets(facetas, on_toggle=self._browse_toggle_facet,
                         ativos=sessao.active_facets)

    def _browse_toggle_facet(self, campo: str, valor: str):
        """Clicar numa faceta refaz a busca com o filtro — é uma requisição de 25."""
        import threading

        sessao = getattr(self, "_browse_session", None)
        if sessao is None:
            return
        sessao.toggle_facet(campo, valor)
        self._set_busy(t("browse.searching"))

        def worker():
            p = sessao.fetch_page(1)
            facetas = sessao.fetch_facets()
            self.after(0, lambda: (self._browse_render(p), self._browse_render_facets(facetas)))

        _ThreadDaTela(target=worker, daemon=True).start()

    def _browse_remove_chip(self, campo: str, chave: str):
        sessao = getattr(self, "_browse_session", None)
        if sessao is None:
            return
        sessao.clear_facet(campo, chave)
        self._browse_toggle_facet_refresh()

    def _browse_toggle_facet_refresh(self):
        import threading

        sessao = getattr(self, "_browse_session", None)
        if sessao is None:
            return
        self._set_busy(t("browse.searching"))

        def worker():
            p = sessao.fetch_page(1)
            facetas = sessao.fetch_facets()
            self.after(0, lambda: (self._browse_render(p), self._browse_render_facets(facetas)))

        _ThreadDaTela(target=worker, daemon=True).start()

    def _browse_import_all(self, sessao, total: int):
        """Importa o conjunto INTEIRO da busca corrente, com aviso de volume.

        Ponte entre o modo navegação e o caminho de colheita que já existe: reusa
        `search_to_dataset`, passando a query e os filtros que estão em tela — inclusive as
        facetas marcadas.
        """
        from core.import_job import decide_volume, format_eta, parse_limit

        limite = parse_limit(getattr(self, "_browse_import_limit", None))
        decisao = decide_volume(total, limite)
        provider = sessao.provider.__class__.__name__.replace("Provider", "").lower()
        filtros = sessao.current_filters()

        def colher(n: int | None):
            self._switch_tab("import")
            self.search_to_dataset(sessao.query, provider, n or 10_000_000, filtros)

        if not decisao.warn:
            colher(limite)
            return

        # Volume grande: o número real na frente, com três saídas.
        dlg = ctk.CTkToplevel(self)
        dlg.title(t("import.volume_title"))
        dlg.geometry("480x250")
        dlg.transient(self)
        dlg.grab_set()
        eta = format_eta(decisao.eta_seconds)
        ctk.CTkLabel(dlg, text=t("import.volume_title"),
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 4), padx=20)
        ctk.CTkLabel(dlg, text=t("import.volume_body", n=f"{total:,}".replace(",", "."),
                                 eta=eta),
                     wraplength=430, justify="left").pack(pady=(0, 12), padx=20)
        botoes = ctk.CTkFrame(dlg, fg_color="transparent")
        botoes.pack(fill="x", padx=20)

        def _tudo():
            dlg.destroy()
            colher(None)

        def _limitar():
            dlg.destroy()
            colher(decisao.suggested_limit)

        ctk.CTkButton(botoes, text=t("import.download_all",
                                     n=f"{total:,}".replace(",", "."), eta=eta),
                      fg_color=RED, text_color="white", corner_radius=0,
                      command=_tudo).pack(fill="x", pady=3)
        ctk.CTkButton(botoes, text=t("import.limit_to", n=f"{decisao.suggested_limit:,}".replace(",", ".")),
                      fg_color=WHITE_CARD, text_color=INK, border_width=2, border_color=INK,
                      corner_radius=0, command=_limitar).pack(fill="x", pady=3)
        ctk.CTkButton(botoes, text=t("import.cancel"), fg_color="transparent", text_color=INK,
                      hover_color="#e0e0e0", corner_radius=0,
                      command=dlg.destroy).pack(fill="x", pady=3)

    def search_to_dataset(self, query: str, provider_name: str, max_results: int, filters: dict = None):
        import threading
        if filters is None: filters = {}
        
        # Setup cancel event
        self._search_cancel_event = threading.Event()
        self._search_cancel_btn.pack(side="left", padx=4)
        
        _ThreadDaTela(target=self._search_worker, args=(query, provider_name, max_results, filters, self._search_cancel_event), daemon=True).start()

    def _search_worker(self, query: str, provider_name: str, max_results: int, filters: dict, cancel_event):
        self.after(0, self._set_busy, f"Buscando em {provider_name.upper()}...")
        # Guarda a última busca para a re-consulta server-side (botão "Rebuscar na fonte").
        self._last_search = {"query": query, "provider": provider_name,
                             "max_results": max_results, "filters": dict(filters or {})}
        try:
            from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider

            # DECISÃO DE PRODUTO: fonte única por busca (multi-fonte simultânea removida).
            provider_cls = {"openalex": OpenAlexProvider, "crossref": CrossrefProvider,
                            "pubmed": PubMedProvider}.get(provider_name.lower(), OpenAlexProvider)
            providers_to_run = [provider_cls()]
                
            records = []
            max_per_provider = max_results
            total_found_sum = 0
            lang_filtered_total = 0  # BUG-02: records descartados por idioma (Crossref client-side)
            net_error_info = None    # BUG-A: (provider, página, motivo) se parou por erro de rede

            # --- Streaming: cria o feed em modo "carregamento vivo" imediatamente ---
            import time as _time
            _t_start = _time.perf_counter()
            _first_batch = [False]
            self._feed_cbs = {}

            def begin_feed():
                from ui.search_feed import SearchFeedView
                self._search_cancel_btn.pack(side="left", padx=4)
                review_tab = self._tabs["review"]
                for w in review_tab.winfo_children():
                    w.destroy()
                self.search_feed_view = SearchFeedView(
                    review_tab,
                    lambda recs, dd=False: self._feed_cbs.get("import", lambda *a: None)(recs, dd),
                    lambda: self._feed_cbs.get("cancel", lambda: None)(),
                    lambda recs, sel: self._feed_cbs.get("ai", lambda *a: None)(recs, sel),
                    on_refilter=lambda sf: self._feed_cbs.get("refilter", lambda *a: None)(sf),
                )
                self.search_feed_view.pack(fill="both", expand=True)
                self.search_feed_view.begin_stream(max_results)
                self._feed_origem = "colheita"   # esta grava a própria linha `search`
                self._switch_tab("review")
            self.after(0, begin_feed)

            def push_batch():
                snap = records[:]  # snapshot thread-safe
                loaded = len(snap)
                total = total_found_sum
                def _upd():
                    fv = getattr(self, "search_feed_view", None)
                    if fv is not None:
                        fv.stream_update(snap, loaded, total)
                self.after(0, _upd)

            BATCH = 25

            for prov in providers_to_run:
                if cancel_event.is_set(): break

                prov_name = prov.__class__.__name__.replace("Provider", "")
                self.after(0, self._set_busy, f"Consultando {prov_name}...")

                def progress(current, total, _prov=prov):
                    nonlocal total_found_sum
                    # "Encontrados" = total REAL da base (total_available). O 2º argumento do
                    # progress_cb é o ALVO da barra (min(limite, total)) — usá-lo aqui fazia a
                    # trilha dizer "Encontrados 1000" com 319300 na base.
                    real_total = max(int(getattr(_prov, "total_available", 0) or 0), total)
                    if real_total > total_found_sum: total_found_sum = real_total

                    if cancel_event.is_set():
                        self.after(0, self._set_idle, "Busca cancelada.")
                    else:
                        self.after(0, self._set_busy, f"Baixando ({prov_name}): {current}/{total} (Total na base: {real_total})")

                try:
                    for r in prov.search(query=query, filters=filters, max_results=max_per_provider, progress_cb=progress, cancel_event=cancel_event):
                        records.append(r)
                        n = len(records)
                        if n == 1 or n % BATCH == 0:
                            if not _first_batch[0]:
                                log.info(f"[feed] primeiro lote em {_time.perf_counter() - _t_start:.1f}s")
                                _first_batch[0] = True
                            push_batch()
                except InterruptedError:
                    print(f"Busca em {prov_name} abortada pelo usuário.")
                    break
                except TypeError:
                    # Fallback if filters argument is not supported by the provider
                    for r in prov.search(query=query, max_results=max_per_provider, progress_cb=progress):
                        if cancel_event.is_set(): break
                        records.append(r)
                        n = len(records)
                        if n == 1 or n % BATCH == 0:
                            if not _first_batch[0]:
                                log.info(f"[feed] primeiro lote em {_time.perf_counter() - _t_start:.1f}s")
                                _first_batch[0] = True
                            push_batch()

                lang_filtered_total += getattr(prov, "language_filtered_count", 0)
                # Total real da base mesmo quando o progress_cb não chegou a rodar
                # (limite menor que uma página, ou parada logo no início).
                prov_total = int(getattr(prov, "total_available", 0) or 0)
                if prov_total > total_found_sum: total_found_sum = prov_total
                if getattr(prov, "stop_error", False):
                    net_error_info = (prov_name, getattr(prov, "pages_fetched", 0), getattr(prov, "stop_reason", ""))

            push_batch()  # descarrega o lote parcial final no contador vivo

            if not records:
                def _empty_feed():
                    fv = getattr(self, "search_feed_view", None)
                    if fv is not None:
                        fv.finish_stream([], "Encontrados 0 · baixados 0")
                self.after(0, _empty_feed)
                self.after(0, self._set_idle, "Busca vazia ou cancelada")
                if not cancel_event.is_set():
                    self.after(0, lambda: messagebox.showinfo(
                        t("busca.sem_resultado_titulo"), t("busca.sem_resultado")))
                self.after(0, self._search_cancel_btn.pack_forget)
                return
                
            df = pd.DataFrame(records)

            if "language" not in df.columns:
                df["language"] = ""
            if "language_source" not in df.columns:
                df["language_source"] = "api"
                
            try:
                import langdetect
                for idx, row in df.iterrows():
                    lang = row.get("language", "")
                    if pd.isna(lang) or not str(lang).strip():
                        text = f"{row.get('title', '')} {row.get('abstract', '')}".strip()
                        if text:
                            try:
                                detected = langdetect.detect(text)
                                df.at[idx, "language"] = detected
                                df.at[idx, "language_source"] = "detected"
                            except Exception:
                                df.at[idx, "language"] = ""
                                df.at[idx, "language_source"] = "api"
                    else:
                        df.at[idx, "language_source"] = "api"
            except ImportError:
                pass
            
            baixados = len(df)

            # DECISÃO DE PRODUTO: a busca NÃO deduplica — a dedup é ação explícita
            # no Corpus (botão Deduplicar). Trilha: Encontrados · baixados · motivo.
            stop_reason = ""
            if providers_to_run:
                stop_reason = str(getattr(providers_to_run[-1], "stop_reason", "") or "")
            if not stop_reason:
                stop_reason = "concluída"
            # O motivo de rede embute a URL inteira: detalhe completo fica no log e no
            # backlog; na trilha entra a versão curta (o label não vira um parágrafo).
            reason_ui = stop_reason if len(stop_reason) <= 90 else stop_reason[:87].rstrip() + "…"
            # Só mostra "de {limite}" quando há um limite FINITO definido pelo usuário
            # (ilimitado usa uma sentinela grande e não exibe teto).
            if total_found_sum > baixados and max_results < 10_000_000:
                trail = t("search.trail_limited", found=total_found_sum, downloaded=baixados,
                          limit=max_results, reason=reason_ui)
            else:
                trail = t("search.trail", found=max(total_found_sum, baixados),
                          downloaded=baixados, reason=reason_ui)
            if lang_filtered_total:
                trail += f" · filtrados por idioma: {lang_filtered_total}"
            if net_error_info:
                trail += f" · interrompido ({net_error_info[0]}, página {net_error_info[1]}) por erro de rede — resultados parciais"
            log.info(f"[Search] {trail}")
            self.after(0, lambda tr=trail: self._search_trail_lbl.configure(text=tr))

            # Backlog do projeto ativo: linha 'search' + JSON bruto p/ reuso offline.
            if getattr(self, "_active_project", None):
                try:
                    from core.project import save_search_raw
                    rel = save_search_raw(self._active_project, df.to_dict("records"))
                    self._backlog("search", {
                        "provider": provider_name,
                        "query": getattr(self, "_last_typed_query", "") or query,
                        "query_interpretada": query,
                        "filters": {k: v for k, v in (filters or {}).items() if k != "fields"} |
                                   ({"fields": list(map(list, filters["fields"]))} if (filters or {}).get("fields") else {}),
                        "encontrados": int(max(total_found_sum, baixados)),
                        "baixados": int(baixados),
                        "stop_reason": stop_reason,
                        "arquivo": rel})
                except Exception as e:
                    log.info(f"[Backlog] falha ao registrar busca: {e}")
            
            # Show SearchFeedView for import review
            on_import_confirm = self._on_feed_import

            def on_cancel():
                # Cancela a colheita em andamento (cancel_event) E volta para a Coletar.
                self._cancel_search()
                self._switch_tab("import")

            def on_ai_assistant(records_list, selected_idx):
                # BUG-B: abre o Blink num DRAWER ao lado do feed — NÃO troca de aba nem
                # destrói o SearchFeedView (cards/seleções/filtros/scroll ficam intactos).
                if not records_list:
                    return
                fv = getattr(self, "search_feed_view", None)
                if fv is None:
                    return
                out = fv.open_blink_drawer()  # textbox de saída

                df_temp = pd.DataFrame(records_list)
                langs = df_temp['language'].value_counts().head(3).to_dict() if 'language' in df_temp.columns else {}
                years = df_temp['year'].value_counts().head(3).to_dict() if 'year' in df_temp.columns else {}
                top_sources = df_temp['source'].value_counts().head(3).to_dict() if 'source' in df_temp.columns else {}

                # RAG: amostra de abstracts dos resultados EM REVISÃO (não o corpus antigo).
                sample = []
                for r in records_list[:8]:
                    ab = str(r.get("abstract", ""))[:280]
                    if ab:
                        sample.append(f"- {r.get('title', '')}: {ab}")
                rag = "\n".join(sample)

                context = (f"Resultados em revisão: {len(records_list)} "
                           f"(selecionados {len(selected_idx)}). "
                           f"Idiomas {langs} · Anos {years} · Fontes {top_sources}.")
                # O resumo é o PRIMEIRO registro do bloco, de propósito: o corte de orçamento
                # come do fim, então o que sobra sempre inclui a caracterização do conjunto.
                # Perder abstracts de amostra é aceitável; perder "são 412 resultados, 80%
                # em inglês" muda o que a resposta pode afirmar.
                from core.research_context import bloco_corpus
                system_prompt = self._blink_system_prompt(
                    dados_corpus=bloco_corpus([context] + (sample if rag else [])))
                user_msg = ("Analise estes resultados em revisão: o que há de bom no conjunto, "
                            "possíveis vieses e o que ajustar antes de consolidar o corpus?")
                messages = [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg}]

                def _set_out(text):
                    if out.winfo_exists():
                        out.configure(state="normal")
                        out.delete("1.0", "end")
                        try:
                            from core.markdown_parser import insert_markdown
                            insert_markdown(out, text)
                        except Exception:
                            out.insert("1.0", text)
                        out.configure(state="disabled")
                self.after(0, lambda: _set_out("Analisando os resultados em revisão…"))

                import threading
                def _stream_worker_ai():
                    try:
                        with self._uso_de_ia("revisao_de_resultados") as analista:
                            full_response = ""
                            for chunk in analista.chat_history_stream(messages,
                                                                     temperature=0.7):
                                full_response += chunk
                                self.after(0, lambda r=full_response: _set_out(r))
                    except Exception as ex:
                        def _set_err(e=ex):
                            if out.winfo_exists():
                                out.configure(state="normal", fg_color=RED, text_color="#FFFFFF")
                                out.delete("1.0", "end")
                                out.insert("1.0", f'{t("ai.error_title")}\n\n{t("ai.error_body")}\n{e}')
                                out.configure(state="disabled")
                        self.after(0, _set_err)
                _ThreadDaTela(target=_stream_worker_ai, daemon=True).start()
                
            # Liga os callbacks reais aos lambdas do feed (criado em begin_feed).
            def on_refilter(server_filters):
                # Re-consulta na fonte: mescla os filtros da sidebar sobre a última busca
                # e roda um novo harvest (encolhe a query de verdade, não só client-side).
                ls = getattr(self, "_last_search", None)
                if not ls:
                    return
                merged = dict(ls["filters"])
                merged.update(server_filters or {})
                self.search_to_dataset(ls["query"], ls["provider"], ls["max_results"], merged)

            self._feed_cbs = {"import": on_import_confirm, "cancel": on_cancel,
                              "ai": on_ai_assistant, "refilter": on_refilter}

            def finalize():
                self._search_cancel_btn.pack_forget()
                fv = getattr(self, "search_feed_view", None)
                if fv is not None:
                    fv.finish_stream(df.to_dict('records'), trail)
                else:
                    from ui.search_feed import SearchFeedView
                    review_tab = self._tabs["review"]
                    for w in review_tab.winfo_children():
                        w.destroy()
                    self.search_feed_view = SearchFeedView(review_tab, on_import_confirm, on_cancel, on_ai_assistant)
                    self.search_feed_view.pack(fill="both", expand=True)
                    self.search_feed_view.load_results(df.to_dict('records'), trail)
                self._set_idle("Pronto para revisar")
                self._switch_tab("review")

            self.after(0, finalize)

        except Exception as e:
            log.info(f"[Search Error] {e}")
            self.after(0, self._set_idle, "Erro na busca")
            # Diagnóstico traduzido na tela; `Errno` e nome de exceção vão para o log.
            # Antes o usuário francês lia português por fora e `urlopen error [Errno 8]`
            # por dentro, sem nada dizendo "verifique sua conexão".
            from core.sources.base import diagnosticar_busca
            chave = diagnosticar_busca(e)
            log.info(f"[ERRO] busca: {type(e).__name__}: {e}  → {chave}\n")
            self.after(0, lambda c=chave: messagebox.showerror(t("busca.erro_titulo"), t(c)))

    def _pick_thesaurus(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._thesaurus = load_thesaurus(path)
            self._thesaurus_path = path
            self._thesaurus_lbl.configure(
                text=f"{Path(path).name} ({len(self._thesaurus)} entradas)",
                text_color=("gray10", "white"),
            )
            self._refresh_candidate_counts()
            log.info(f"[Thesaurus] {len(self._thesaurus)} mapeamentos carregados.\n")
        except Exception as exc:
            messagebox.showerror("Erro ao carregar thesaurus", str(exc))

    # ── Threshold preview ──────────────────────────────────────────────
    def _atualizar_ui_do_corpus(self):
        """Selo "N registros" da barra lateral e aviso do tipo de mapa — sempre na thread do Tk.

        O selo nascia "Nenhum corpus" e nunca mudava: com 6 mil registros carregados a barra
        lateral continuava dizendo que não havia corpus.
        """
        try:
            df = self._dataframe
            n = 0 if df is None else len(df)
            if getattr(self, "_corpus_badge", None) is not None:
                self._corpus_badge.configure(
                    text=t("corpus.badge_count", n=n) if n
                    else t("corpus.badge_none"))
            self._atualizar_tipo_de_mapa()      # o corpus mudou: reavaliar o aviso do tipo (M2)
        except Exception:
            pass

    def _refresh_candidate_counts(self):
        # Pode ser chamada de dentro de _load_worker (thread de importação): widget só se
        # mexe na thread da interface.
        try:
            if threading.current_thread() is threading.main_thread():
                self._atualizar_ui_do_corpus()
            else:
                self.after(0, self._atualizar_ui_do_corpus)
        except (RuntimeError, AttributeError):
            pass
        if self._dataframe is None:
            return
        # Começa depois que a tela termina de se desenhar. A contagem é Python puro e, rodando
        # junto com o redesenho, cada chamada do Tk esperava a vez no interpretador: abrir um
        # projeto de 6 mil registros congelava a janela por ~3 s (auditoria 2026-09, T4).
        def iniciar():
            _ThreadDaTela(target=self._candidate_worker, daemon=True).start()
        try:
            self.after(400, lambda: self.after_idle(iniciar))
        except (RuntimeError, AttributeError):
            iniciar()

    def _candidate_worker(self):
        try:
            gen = NetworkGenerator(self._dataframe)
            field = self._field_var.get() if hasattr(self, "_field_var") else "keywords"
            _, counts, _, scores = gen.get_candidate_terms(
                field=field, thesaurus=self._thesaurus)
            self._candidate_counts = counts
            self._candidate_scores = scores
            self.after(0, self._update_thresh_label)
        except Exception:
            pass

    def _update_thresh_label(self):
        if not self._candidate_counts:
            return
        min_occ = self._min_occ_var.get()
        total   = len(self._candidate_counts)
        passing = sum(1 for n in self._candidate_counts.values() if n >= min_occ)
        self._thresh_lbl.configure(
            text=f"→  {passing} de {total} termos passam")

    def _on_occ_change(self, val):
        self._occ_lbl.configure(text=str(int(val)))
        self._update_thresh_label()

    # ── Fase 3: controles de qualidade ────────────────────────────────────
    def _recluster_only(self):
        """Aplica a resolução ao grafo EXISTENTE, sem refazer o layout."""
        G = getattr(self, "_graph", None)
        if G is None or G.number_of_nodes() == 0:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        from core.map_controls import cluster_sizes, recluster
        antes = len(cluster_sizes(G))
        recluster(G, resolution=self._cluster_res_var.get(),
                  algorithm=self._cluster_alg_var.get())
        depois = cluster_sizes(G)
        log.info(f"[Mapa] resolução {self._cluster_res_var.get():.2f}: "
                 f"{antes} → {len(depois)} clusters (posições intactas)")
        # Publica as novas cores com as MESMAS posições; o mapa Sigma é servido
        # pelo navegador, não por um canvas Tk interno.
        self._publish_sigma_map()
        if not getattr(self, "_demo_no_browser", False):
            import time      # faltava: NameError ao reclusterizar, sempre (D6)
            import webbrowser
            webbrowser.open(
                f"http://127.0.0.1:{self._local_server_port}/assets/map_template.html"
                f"?revision={int(time.time() * 1000)}"
            )

    def _publish_sigma_map(self):
        """Escreve a versão atual do grafo para o mapa Sigma local."""
        from core.sigma_exporter import export_sigma_json
        from core.i18n import get_map_i18n

        sigma_path = self._serve_dir / "assets" / "graph.json"
        export_sigma_json(self._generator.G, self._positions, str(sigma_path))
        i18n_path = self._serve_dir / "assets" / "i18n.json"
        with open(i18n_path, "w", encoding="utf-8") as f:
            json.dump(get_map_i18n(), f, ensure_ascii=False)

    def _open_term_review(self):
        """Tabela de termos revisável antes de gerar (passo 13 do guia do VOSviewer)."""
        if self._dataframe is None or self._dataframe.empty:
            messagebox.showwarning("Sem dados", "Importe um corpus primeiro.")
            return

        from core.term_extraction import extract_terms
        campo = {"keywords": "keywords", "titles": "title_abstract",
                 "abstracts": "title_abstract", "titles_abstracts": "title_abstract"}.get(
            self._field_var.get(), "keywords")

        # Extração em segundo plano: em corpus grande levava segundos na thread da tela e a
        # janela congelava ao clicar em "Revisar termos…" (auditoria 2026-09, T2).
        df = self._dataframe
        binaria = self._binary_count_var.get()
        minimo = int(self._min_occ_var.get())
        tesauro = getattr(self, "_thesaurus", None)
        self._set_busy("Extraindo termos…")

        def worker():
            try:
                res = extract_terms(df, fields=campo, binary_count=binaria,
                                    min_occurrences=minimo, thesaurus=tesauro)
            except Exception as exc:
                log.info(f"[ERRO] revisão de termos: {type(exc).__name__}: {exc}")
                self.after(0, self._set_idle, "")
                msg = _mensagem_para_usuario(exc, t("map.erro_generico"))
                self.after(0, lambda m=msg: messagebox.showerror("Erro", m))
                return
            self.after(0, self._set_idle, "")
            self.after(0, self._mostrar_revisao_termos, res)
        _ThreadDaTela(target=worker, name="term_review_worker", daemon=True).start()

    def _mostrar_revisao_termos(self, resultado):
        if not resultado.terms:
            messagebox.showinfo(
                "Nenhum termo",
                t("map.warn_threshold_empty", total=resultado.total_unique_before_threshold))
            return

        win = ctk.CTkToplevel(self)
        win.title("Revisar termos")
        win.geometry("720x600")
        win.transient(self)

        cab = ctk.CTkFrame(win, fg_color="transparent")
        cab.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(cab, text=f"{len(resultado.terms)} termos (limiar {self._min_occ_var.get()})",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        # Avisos honestos da extração (idioma, backend) aparecem aqui, nunca em silêncio.
        for aviso in resultado.warnings:
            ctk.CTkLabel(win, text=t(aviso, lang=resultado.language or "?",
                                     total=resultado.total_unique_before_threshold),
                         font=ctk.CTkFont(size=11), text_color=RED,
                         wraplength=680, justify="left").pack(anchor="w", padx=16, pady=(0, 2))

        ordenar = ctk.StringVar(value="relevância")
        lista = ctk.CTkScrollableFrame(win, fg_color=WHITE_CARD)
        lista.pack(fill="both", expand=True, padx=16, pady=8)

        marcas: dict[str, ctk.BooleanVar] = {}

        geracao = [0]

        def preencher():
            geracao[0] += 1
            minha = geracao[0]
            for w in lista.winfo_children():
                w.destroy()
            termos = list(resultado.terms)
            if ordenar.get() == "ocorrências":
                termos.sort(key=lambda x: (-x.occurrences, x.term))
            elif ordenar.get() == "alfabética":
                termos.sort(key=lambda x: x.term)
            else:
                termos.sort(key=lambda x: (-x.relevance, -x.occurrences, x.term))

            cabecalho = ctk.CTkFrame(lista, fg_color="transparent")
            cabecalho.pack(fill="x", pady=(0, 4))
            for texto, largura in (("incluir", 60), ("termo", 300),
                                   ("ocorr.", 70), ("relev.", 70)):
                ctk.CTkLabel(cabecalho, text=texto, width=largura, anchor="w",
                             font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")

            # Linhas desenhadas em lotes: são até 600 linhas × 4 widgets, e desenhar tudo de
            # uma vez congelava a janela por segundos (T2). A lista aparece na hora e vai se
            # completando; reordenar no meio cancela o desenho anterior.
            visiveis = termos[:600]    # a UI mostra os 600 primeiros; a exclusão vale p/ todos
            for info in termos:
                marcas.setdefault(
                    info.term, ctk.BooleanVar(value=info.term not in self._excluded_terms))

            def lote(inicio=0, tamanho=25):
                if minha != geracao[0] or not win.winfo_exists():
                    return
                for info in visiveis[inicio:inicio + tamanho]:
                    linha = ctk.CTkFrame(lista, fg_color="transparent")
                    linha.pack(fill="x")
                    ctk.CTkCheckBox(linha, text="", variable=marcas[info.term], width=60,
                                    fg_color=ACCENT, hover_color=ACCENT_HOV).pack(side="left")
                    ctk.CTkLabel(linha, text=info.term, width=300, anchor="w").pack(side="left")
                    ctk.CTkLabel(linha, text=str(info.occurrences), width=70,
                                 anchor="w").pack(side="left")
                    ctk.CTkLabel(linha, text=f"{info.relevance:.2f}", width=70,
                                 anchor="w").pack(side="left")
                if inicio + tamanho < len(visiveis):
                    win.after(1, lote, inicio + tamanho, tamanho)
            lote()

        ord_f = ctk.CTkFrame(cab, fg_color="transparent")
        ord_f.pack(side="right")
        ctk.CTkLabel(ord_f, text="ordenar:").pack(side="left", padx=4)
        ctk.CTkComboBox(ord_f, values=["relevância", "ocorrências", "alfabética"],
                        variable=ordenar, width=130,
                        command=lambda _: preencher()).pack(side="left")

        rodape = ctk.CTkFrame(win, fg_color="transparent")
        rodape.pack(fill="x", padx=16, pady=(0, 16))

        def aplicar():
            self._excluded_terms = {termo for termo, var in marcas.items() if not var.get()}
            n = len(self._excluded_terms)
            self._excluded_lbl.configure(text=f"{n} termo(s) excluído(s)" if n else "")
            log.info(f"[Mapa] {n} termos excluídos pela revisão")
            win.destroy()

        self._btn(rodape, "Aplicar e fechar", aplicar, color=RED, hover=RED_HOV,
                  height=36).pack(side="right")
        self._btn(rodape, "Limpar exclusões",
                  lambda: [v.set(True) for v in marcas.values()],
                  color=INK, hover=INK_HOV, height=36).pack(side="right", padx=8)

        preencher()

    def _indice_tipo_de_mapa(self) -> int:
        try:
            return MAP_TYPES.index(self._map_type_var.get())
        except ValueError:
            return 0

    def _ao_escolher_tipo_de_mapa(self, valor: str):
        if valor not in MAP_TYPES:          # clicou num título de grupo: volta ao que era
            self._map_type_var.set(getattr(self, "_tipo_anterior", MAP_TYPES[0]))
        self._atualizar_tipo_de_mapa()

    def _atualizar_tipo_de_mapa(self):
        """Rótulo do limiar conforme o tipo, e aviso quando o corpus não serve para ele (M2).

        O mesmo controle significava "ocorrências do termo", "publicações por autor",
        "cocitações do par"… com um rótulo só. E o usuário só descobria que o tipo não
        funcionava com o corpus depois de clicar em Gerar Mapa.
        """
        indice = self._indice_tipo_de_mapa()
        if getattr(self, "_lbl_freq", None) is not None:
            self._lbl_freq.configure(text=t(f"map.min_label.{indice}"))
        if getattr(self, "_desc_tipo_lbl", None) is not None:
            self._desc_tipo_lbl.configure(text=t(f"map.descricao.{indice}"))
        aviso = getattr(self, "_aviso_tipo_lbl", None)
        if aviso is None:
            return
        from core.map_controls import viabilidade_tipo
        motivo = viabilidade_tipo(indice, self._dataframe)
        if motivo:
            aviso.configure(text=t(motivo))
            if not aviso.winfo_ismapped():
                aviso.pack(anchor="w", fill="x", padx=10, pady=(0, 6), after=self._desc_tipo_lbl)
        else:
            aviso.configure(text="")
            aviso.pack_forget()
        # Projeto antigo sem o código do OpenAlex: oferecer completar (citação direta).
        btn = getattr(self, "_btn_completar_ids", None)
        if motivo == "map.inviavel_citdir_openalex":
            if btn is None:
                btn = ctk.CTkButton(aviso.master, text=t("map.completar_ids"),
                                    command=self._completar_ids_openalex, height=28,
                                    corner_radius=0, fg_color=WHITE_CARD, hover_color=PAPER,
                                    text_color=INK, border_width=2, border_color=INK,
                                    font=ctk.CTkFont(size=11, weight="bold"))
                self._btn_completar_ids = btn
            if not btn.winfo_ismapped():
                btn.pack(anchor="w", fill="x", padx=10, pady=(0, 8), after=aviso)
        elif btn is not None:
            btn.pack_forget()

    def _completar_ids_openalex(self):
        """Preenche `openalex_id` pelo DOI (lotes de 50) para a citação direta funcionar."""
        if self._dataframe is None or self._dataframe.empty or getattr(self, "_completando_ids", False):
            return
        from core import artigos_conectados as AC
        self._completando_ids = True
        df = self._dataframe.copy()
        btn = getattr(self, "_btn_completar_ids", None)
        if btn is not None:
            btn.configure(state="disabled", text=t("map.completando_ids"))

        def fim(n=None, erro=None):
            self._completando_ids = False
            if btn is not None and btn.winfo_exists():
                btn.configure(state="normal", text=t("map.completar_ids"))
            if erro is not None:
                self._set_idle("")
                messagebox.showerror(t("map.completar_ids"), t("explorar.erro_rede", erro=
                                     _mensagem_para_usuario(erro, t("explorar.erro_generico"))))
                return
            if n:
                self._dataframe = df
                self._refresh_candidate_counts()
                self._backlog("completar_ids", {"preenchidos": n})
            self._set_idle(t("map.ids_completados", n=n))
            messagebox.showinfo(t("map.completar_ids"), t("map.ids_completados", n=n))

        def worker():
            try:
                obter, mailto = AC.obter_padrao()
                n = AC.completar_ids(df, obter, mailto=mailto, ao_progresso=lambda f, tot:
                                     self.after(0, self._set_busy, t("map.completando_ids_n", feitos=f, total=tot)))
                self.after(0, lambda: fim(n))
            except Exception as exc:          # noqa: BLE001
                log.exception("[Mapa] completar códigos do OpenAlex")
                self.after(0, lambda e=exc: fim(erro=e))
        self._set_busy(t("map.completando_ids"))
        _ThreadDaTela(target=worker, daemon=True, name="completar_ids_worker").start()

    def _on_field_change(self):
        self._refresh_candidate_counts()

    # ── Map generation ─────────────────────────────────────────────────
    def _run_mapping(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        from core.map_controls import viabilidade_tipo
        motivo = viabilidade_tipo(self._indice_tipo_de_mapa(), self._dataframe)
        if motivo:
            messagebox.showwarning(t("map.inviavel_titulo"), t(motivo))
            return

        map_type = self._map_type_var.get()
        # Only show verification dialog for keyword/term types
        if map_type == MAP_TYPES[0] and self._candidate_counts:
            min_occ = self._min_occ_var.get()
            field   = self._field_var.get()
            # A lista de revisão já sai sem as stopwords extras: antes elas apareciam como
            # "SIM" (manter), embora o mapa as removesse — o usuário via uma coisa e recebia
            # outra (D3, conferido no app real).
            _sw = {w.strip().lower() for w in self._extra_sw_var.get().split(",") if w.strip()}
            terms_data = [
                (term, count, 0, self._candidate_scores.get(term, 0.0))
                for term, count in self._candidate_counts.items()
                if count >= min_occ and str(term).strip().lower() not in _sw
            ]
            # Acrescenta a frequência documental (doc_freq).
            from core.matrix_builders import _extract_term_lists
            try:
                term_lists = _extract_term_lists(
                    self._dataframe, field, self._thesaurus, None)
                from collections import Counter as _C
                doc_freq = _C()
                for lst in term_lists:
                    for termo in set(lst):
                        doc_freq[termo] += 1
                terms_data = [
                    (term, count, doc_freq.get(term, 0), self._candidate_scores.get(term, 0.0))
                    for term, count, _, score in terms_data
                ]
            except Exception:
                pass

            if terms_data:
                VerificationDialog(
                    self, terms_data,
                    on_confirm=lambda selected: _ThreadDaTela(
                        target=self._mapping_worker, args=(selected,), daemon=True
                    ).start(),
                )
                return

        _ThreadDaTela(target=self._mapping_worker, args=(None,), daemon=True).start()

    def _mapping_worker(self, allowed_terms: set[str] | None):
        """Um mapa por vez. Clique duplo em "Gerar Mapa" (ou Ctrl+G repetido) disparava dois
        cálculos ao mesmo tempo, que gravavam grafo e layout um por cima do outro (D4)."""
        if not self._mapping_lock.acquire(blocking=False):
            log.info("[Mapa] Já há um mapa sendo gerado; clique ignorado.\n")
            return
        try:
            self._mapping_worker_impl(allowed_terms)
        finally:
            self._mapping_lock.release()

    def _mapping_worker_impl(self, allowed_terms: set[str] | None):
        # Exclusões da lista revisável (passo 13 do guia): valem SEMPRE, inclusive quando o
        # chamador não passou uma seleção própria. Sem isso o botão "Revisar termos" seria
        # decorativo — o mapa sairia com os termos que o usuário acabou de descartar.
        map_type = self._map_type_var.get()
        if map_type == MAP_TYPES[0] and getattr(self, "_excluded_terms", None):
            from core.map_controls import allowed_terms_from
            if allowed_terms is None:
                from core.term_extraction import extract_terms
                campo = {"keywords": "keywords"}.get(self._field_var.get(), "title_abstract")
                candidatos = extract_terms(
                    self._dataframe, fields=campo,
                    binary_count=self._binary_count_var.get(),
                    min_occurrences=int(self._min_occ_var.get()),
                    thesaurus=getattr(self, "_thesaurus", None)).term_names
                allowed_terms = allowed_terms_from(candidatos, self._excluded_terms)
            else:
                allowed_terms = allowed_terms_from(allowed_terms, self._excluded_terms)
        self.after(0, self._set_busy, "Gerando rede…")
        try:
            log.info("[Blicsa Engine] Calculando rede...")

            # Apply year filter
            df = self._dataframe.copy()
            # Antes um ano digitado errado ("dois mil") era ignorado em silêncio e o mapa
            # saía com o corpus inteiro, sem filtro (D2). Agora o usuário é avisado.
            _a = _numero_do_campo(self._year_min_var.get(), t("campo.ano_inicial"))
            _b = _numero_do_campo(self._year_max_var.get(), t("campo.ano_final"))
            yr_min = int(_a) if _a is not None else None
            yr_max = int(_b) if _b is not None else None
            # `year` pode faltar: a normalização de schema só roda ao ABRIR um projeto, e um
            # DataFrame vindo de importação de arquivo ou de uma busca chega por outro
            # caminho. Sem a guarda, `df["year"]` levanta KeyError e o cálculo de rede morre
            # com "[ERRO] 'year'" — uma mensagem que não diz nem que o problema é a coluna.
            tem_ano = "year" in df.columns
            if not tem_ano and (yr_min is not None or yr_max is not None):
                log.warning("[Filtro] coluna 'year' ausente: filtro de período ignorado")
            if tem_ano and yr_min is not None:
                df = df[df["year"] >= yr_min]
            if tem_ano and yr_max is not None:
                df = df[df["year"] <= yr_max]
            if yr_min or yr_max:
                log.info(f"[Filtro] Período {yr_min or '?'} – {yr_max or '?'}: {len(df)} registros\n")

            # Extra stop words
            extra_sw_raw = self._extra_sw_var.get().strip()
            extra_sw: set[str] | None = None
            if extra_sw_raw:
                extra_sw = {w.strip().lower() for w in extra_sw_raw.split(",") if w.strip()}

            # Compute max_nodes from top%
            # Campos de texto livre: aceitar "10,5", "50%" e espaços, como um usuário
            # brasileiro digita. Antes "abc" ou "10.5" mostravam "invalid literal for int()"
            # e "50%" era ignorado em silêncio (o mapa saía com todos os nós) — D2.
            max_nodes = _numero_do_campo(self._max_nodes_var.get(), t("campo.max_nos"))
            max_nodes = max(0, int(max_nodes or 0))
            pct_str   = self._max_pct_var.get().strip()
            pct = _numero_do_campo(pct_str, t("campo.top_pct")) if pct_str else None
            if pct and pct > 0 and map_type in (MAP_TYPES[0], MAP_TYPES[1]):
                try:
                    preview = NetworkGenerator(df)
                    if map_type == MAP_TYPES[1]:
                        counts = preview.get_author_counts()
                    else:
                        _, counts, _, _ = preview.get_candidate_terms(
                            field=self._field_var.get(), thesaurus=self._thesaurus,
                            extra_stop_words=extra_sw,
                        )
                    passing = sum(1 for n in counts.values() if n >= self._min_occ_var.get())
                    max_nodes = max(1, int(passing * pct / 100))
                    log.info(f"[Top {pct}%] → {max_nodes} nós selecionados\n")
                except ValueError:
                    pass

            min_occ  = self._min_occ_var.get()
            field    = self._field_var.get()
            counting = self._counting_var.get()
            strength = self._assoc_var.get()
            algoritmo = self._cluster_alg_var.get()
            resolucao = self._cluster_res_var.get()
            podar_isolados = self._prune_isolated_var.get()
            maior_componente = self._prune_largest_var.get()

            def construir(limiar):
                gen = NetworkGenerator(df)
                gen.clustering_algorithm = algoritmo
                gen.clustering_resolution = resolucao
                if map_type == MAP_TYPES[0]:
                    gen.build_keyword_cooccurrence(
                        min_occurrence=limiar,
                        counting_method=counting,
                        normalize_strength=strength,
                        field=field,
                        thesaurus=self._thesaurus,
                        max_nodes=max_nodes,
                        allowed_terms=allowed_terms,
                        extra_stop_words=extra_sw,
                    )
                elif map_type == MAP_TYPES[1]:
                    gen.build_coauthorship_network(
                        min_publications=limiar,
                        counting_method=counting,
                        max_nodes=max_nodes,
                    )
                elif map_type == MAP_TYPES[2]:
                    gen.build_cocitation_network(min_cocitations=limiar, max_nodes=max_nodes)
                elif map_type == MAP_TYPES[3]:
                    gen.build_bibliographic_coupling(min_shared_refs=max(limiar, 2), max_nodes=max_nodes)
                elif map_type == MAP_TYPES[4]:
                    gen.build_direct_citation_network(min_citations=max(limiar, 1), max_nodes=max_nodes)
                elif map_type == MAP_TYPES[5]:
                    gen.build_ipc_cooccurrence(min_occurrence=limiar, max_nodes=max_nodes)
                else:
                    # "Agrupamento Semântico (Embeddings)" não tem construtor; antes caía no
                    # `else` e gerava, sem aviso, um mapa de IPC de patentes (B6).
                    raise ErroParaUsuario(
                        f"O tipo de mapa \"{map_type}\" ainda não está disponível nesta versão.\n"
                        "Escolha outro tipo de mapa (por exemplo, Coocorrência de Palavras-chave).")

                # Network pruning
                from core.map_controls import prune_network
                n_isolated, n_component = prune_network(
                    gen.G,
                    remove_isolated=podar_isolados,
                    largest_component=maior_componente,
                )
                if n_isolated:
                    log.info(f"[Pruning] {n_isolated} nó(s) isolado(s) removido(s)\n")
                if n_component:
                    log.info(f"[Pruning] Mantendo maior componente: "
                             f"{gen.G.number_of_nodes()} nós\n")
                return gen

            gen = construir(min_occ)
            # Fluxo permissivo (M3): se o limiar zerou o mapa, tenta limiares menores (metade
            # a cada passo: no máximo ~6 tentativas) e avisa qual usou. Antes o usuário recebia
            # "Nenhum item passou pelos filtros" e tinha de adivinhar o número certo.
            limiar_usado = min_occ
            while gen.G.number_of_nodes() == 0 and limiar_usado > 1:
                limiar_usado = max(1, limiar_usado // 2)
                log.info(f"[Mapa] Mapa vazio; tentando limiar {limiar_usado}\n")
                gen = construir(limiar_usado)

            if gen.G.number_of_nodes() == 0:
                # Mensagem conforme a causa: "reduza a frequência mínima" não ajuda quando o
                # Blicsa já tentou o mínimo 1, nem na citação direta, que depende de artigos do
                # corpus citarem uns aos outros.
                if map_type == MAP_TYPES[4]:
                    key = "map.warn_empty_citdir"
                elif limiar_usado <= 1:
                    key = "map.warn_empty_mesmo_com_1"
                else:
                    key = "map.warn_empty_coauth" if map_type == MAP_TYPES[1] else "map.warn_empty_network"
                detail = t(key, minimum=min_occ)
                log.info(f"[Mapa] {detail}\n")
                self.after(0, self._set_idle, t("map.warn_empty_title"))
                self.after(0, lambda msg=detail: messagebox.showwarning(
                    t("map.warn_empty_title"), msg))
                return

            if limiar_usado != min_occ:
                aviso_limiar = t("map.limiar_ajustado", pedido=min_occ, usado=limiar_usado)
                log.info(f"[Mapa] {aviso_limiar}\n")

                def _mostrar_limiar(v=limiar_usado, msg=aviso_limiar):
                    self._min_occ_var.set(v)
                    if getattr(self, "_occ_lbl", None) is not None:
                        self._occ_lbl.configure(text=str(v))
                    messagebox.showinfo(t("map.warn_empty_title"), msg)
                self.after(0, _mostrar_limiar)

            # Cocitação com corpus do OpenAlex: nós são IDs (W2741…). Troca o rótulo por
            # "Sobrenome (ano)" pelo OpenAlex, com cache e tempo máximo; sem internet fica o curto.
            if map_type == MAP_TYPES[2]:
                try:
                    from core.rotulos_referencias import aplicar_no_grafo
                    n_rot = aplicar_no_grafo(gen.G)
                    if n_rot:
                        log.info(f"[Mapa] {n_rot} referências do OpenAlex com nome e ano\n")
                except Exception as exc_rot:
                    log.warning("[Mapa] rótulos do OpenAlex indisponíveis: %s", exc_rot)

            self._generator = gen
            self._graph = gen.G

            log.info("[FA2] Calculando layout ForceAtlas2...")
            iters   = self._fa2_iter_var.get()
            linlog  = self._linlog_var.get()
            self._positions = compute_fa2_layout(gen.G, iterations=iters, linlog=linlog)

            stats = gen.get_summary_stats()
            mode  = self._viz_mode_var.get()

            # Backlog: análise gerada (coocorrência etc.) no projeto ativo.
            self._backlog("analysis", {
                "tipo": self._map_type_var.get(),
                "params": {"field": self._field_var.get(),
                           "counting": self._counting_var.get(),
                           "min_occ": limiar_usado,
                           "cluster_algorithm": self._cluster_alg_var.get()},
                "nos": stats.get("total_nodes", 0),
                "arestas": stats.get("total_edges", 0),
                "clusters": stats.get("num_clusters", 0)})
            plotly_color = self._plotly_mode_var.get()

            # O Sigma é a saída principal. A exportação PyVis legada é opcional:
            # uma falha nela não pode impedir o mapa interativo de abrir.
            self._publish_sigma_map()
            try:
                gen.export_to_html(MAP_PATH)
            except Exception as legacy_exc:
                log.warning("[Mapa] HTML legado indisponível: %s", legacy_exc)

            import webbrowser
            url = f"http://127.0.0.1:{self._local_server_port}/assets/map_template.html"
            if not getattr(self, "_demo_no_browser", False):
                webbrowser.open(url)
            log.info("[OK] Mapas prontos.\n")

            self.after(0, self._update_stats, stats)
            if getattr(self, '_tv_analises', None):
                self._tv_analises.set("Mapa")
            self.after(0, self._switch_tab, "analises")
            self.after(0, self._set_idle, "Mapa gerado")
            
            if self._api_key_var.get().strip() or os.environ.get("GROQ_API_KEY"):
                self._show_ai_modal = False
                self.after(200, lambda: _ThreadDaTela(target=self._trigger_map_ai_insights, daemon=True).start())
        except Exception as exc:
            log.info(f"[ERRO] {type(exc).__name__}: {exc}\n")
            # Mensagem escrita para gente; erro interno inesperado não vai cru para a tela.
            msg = _mensagem_para_usuario(exc, t("map.erro_generico"))
            self.after(0, self._set_idle, "Erro")
            self.after(0, lambda m=msg: messagebox.showerror("Erro", m))


    def _update_stats(self, stats: dict):
        for key, lbl in self._stat_labels.items():
            lbl.configure(text=str(stats.get(key, "—")))

    # ── Viz controls ───────────────────────────────────────────────────
    def _apply_style(self):
        pass

    # ── Node info panel ────────────────────────────────────────────────
    def _on_node_click(self, node: str | None):
        if node is None:
            return
        self._bottom_tabs.set("Nó Selecionado")
        _ThreadDaTela(target=self._build_node_info, args=(node,), daemon=True).start()

    def _build_node_info(self, node: str):
        lines: list[str] = []
        G   = self._generator.G if self._generator else None
        df  = self._dataframe

        lines.append(f"{'━'*52}")
        lines.append(f"  {node.upper()}")
        lines.append(f"{'━'*52}")

        if G and node in G.nodes:
            d = G.nodes[node]
            lines.append(f"  Cluster        : {d.get('group','—')}")
            lines.append(f"  Ocorrências    : {d.get('occurrence','—')}")
            lines.append(f"  Grau ponderado : {G.degree(node, weight='weight'):.2f}")
            bc = nx.betweenness_centrality(G, weight="weight")
            lines.append(f"  Betweenness    : {bc.get(node,0):.4f}")
            pr = nx.pagerank(G, weight="weight")
            lines.append(f"  PageRank       : {pr.get(node,0):.4f}")
            yr = d.get("year_mean", 0)
            if yr:
                lines.append(f"  Ano médio      : {yr:.0f}")
            nbrs = sorted(G.neighbors(node),
                          key=lambda n: G[node][n].get("weight", 0), reverse=True)
            if nbrs:
                lines.append("")
                lines.append(f"  TOP CO-OCORRENTES:")
                for nb in nbrs[:8]:
                    w = G[node][nb].get("weight", 0)
                    lines.append(f"    · {nb:<32} {w:.3f}")

        if df is not None:
            field_map = {"keywords":"keywords","titles":"title",
                         "abstracts":"abstract","titles_abstracts":"abstract"}
            col = field_map.get(
                self._field_var.get() if hasattr(self, "_field_var") else "keywords",
                "keywords")
            t_low = node.lower()

            def _has(s):
                if not isinstance(s, str): return False
                sep = ";" if ";" in s else ","
                return t_low in [x.strip().lower() for x in s.split(sep)]

            mask  = df[col].apply(_has)
            papers = df[mask].sort_values("citations", ascending=False).head(10)
            if not papers.empty:
                lines.append("")
                lines.append(f"  ARTIGOS RELACIONADOS ({len(papers)} exibidos):")
                lines.append(f"  {'─'*50}")
                for _, row in papers.iterrows():
                    title = str(row.get("title",""))[:55]
                    yr    = int(row.get("year", 0) or 0)
                    cit   = int(row.get("citations", 0) or 0)
                    lines.append(f"  [{yr}] {title}")
                    lines.append(f"        {str(row.get('authors',''))[:45]}  cit:{cit}")

        lines.append("")
        text = "\n".join(lines)
        self.after(0, self._update_node_info_box, text)

    def _update_node_info_box(self, text: str):
        self._node_info_box.configure(state="normal")
        self._node_info_box.delete("1.0", "end")
        self._node_info_box.insert("end", text)
        self._node_info_box.configure(state="disabled")

    def _populate_cluster_filter(self):
        """Rebuild the cluster checkbox strip after a new map is generated."""
        for w in self._cluster_filter_frame.winfo_children():
            w.destroy()
        self._cluster_filter_vars.clear()
        if self._generator is None:
            return
        report = self._generator.get_cluster_report()
        if not report:
            return
        ctk.CTkLabel(
            self._cluster_filter_frame, text="Clusters:",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        for c in report:
            cid   = c["cluster_id"]
            color = CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)]
            label = self._cluster_labels.get(cid) or f"C{cid}"
            var   = ctk.BooleanVar(value=True)
            self._cluster_filter_vars[cid] = var
            ctk.CTkCheckBox(
                self._cluster_filter_frame,
                text=f"{label[:16]} ({c['size']})",
                variable=var,
                fg_color=color, hover_color=color,
                checkmark_color="#000000",
                font=ctk.CTkFont(size=10),
                width=20, checkbox_width=14, checkbox_height=14,
                command=self._apply_cluster_filter,
            ).pack(side="left", padx=4)

    def _apply_cluster_filter(self):
        pass

    def _on_edge_thresh_change(self, val: float):
        pass

    def _search_node(self):
        pass

    def _reset_view(self):
        pass

    def _open_in_webview(self, title: str, path: str):
        import webbrowser
        webbrowser.open(str(path))

    def _open_plotly(self):
        if self._generator is None or not self._positions:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro antes de abrir a visualização.")
            return
            
        try:
            from core.visualizer import build_plotly_map
            fig = build_plotly_map(
                self._generator.G,
                self._positions,
                color_mode=self._plotly_mode_var.get(),
                df=self._dataframe
            )
            
            import time
            map_type = self._viz_mode_var.get().replace(" ", "_")
            out_name = f"blicsa_mapa_{map_type}_{int(time.time())}.html"
            path = str(WORK_DIR / out_name)
            
            fig.write_html(path, include_plotlyjs=True)
            log.info(f"[Plotly] Interativo salvo → {path}\n")
            
            self._open_in_webview("Blicsa - Visualização Interativa", path)
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Plotly", str(exc))

    def _open_map_browser(self):
        target = PLOTLY_PATH if Path(PLOTLY_PATH).exists() else MAP_PATH
        if Path(target).exists():
            webbrowser.open(str(target))
        else:
            messagebox.showinfo("Não gerado", "Gere o mapa primeiro.")

    def _open_sankey(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        try:
            from core.visualizer import build_sankey_diagram
            fig = build_sankey_diagram(self._dataframe, "authors", "keywords", "source", top_n=10)
            
            import time
            sankey_path = str(WORK_DIR / f"blicsa_sankey_{int(time.time())}.html")
            fig.write_html(sankey_path, include_plotlyjs=True)
            log.info(f"[Sankey] Diagrama salvo → {sankey_path}\n")
            self._open_in_webview("Blicsa - Sankey", sankey_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
            
            # Removed automatic AI call, Blink Research sidebar can be used instead
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Sankey", str(exc))

    def _open_timeline(self):
        if self._generator is None or not self._positions:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro antes de visualizar a Linha do Tempo.")
            return
        try:
            from core.visualizer import build_timeline_view
            fig = build_timeline_view(self._generator.G, self._positions)
            
            import time
            timeline_path = str(WORK_DIR / f"blicsa_linha_tempo_{int(time.time())}.html")
            fig.write_html(timeline_path, include_plotlyjs=True)
            log.info(f"[Linha do Tempo] Salva → {timeline_path}\n")
            self._open_in_webview("Blicsa - Linha do Tempo", timeline_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Linha do Tempo", str(exc))

    def _open_bursts(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        try:
            from core.nlp import detect_bursts
            extra_sw_raw = self._extra_sw_var.get().strip()
            extra_sw = None
            if extra_sw_raw:
                extra_sw = {w.strip().lower() for w in extra_sw_raw.split(",") if w.strip()}
                
            bursts = detect_bursts(
                self._dataframe,
                field=self._field_var.get(),
                thesaurus=self._thesaurus,
                extra_stop_words=extra_sw
            )
            
            if not bursts:
                messagebox.showinfo("Nenhum surto", "Nenhum surto estatisticamente significativo detectado no dataset.")
                return
                
            BurstDetectionWindow(self, bursts)
        except Exception as exc:
            messagebox.showerror("Erro na análise de surtos", str(exc))

    def _open_thematic_map(self):
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro antes de visualizar o Mapa Temático.")
            return
        try:
            fig = build_thematic_map(self._generator.G)
            import time
            thematic_path = str(WORK_DIR / f"blicsa_mapa_tematico_{int(time.time())}.html")
            fig.write_html(thematic_path, include_plotlyjs=True)
            log.info(f"[Mapa Temático] Salvo → {thematic_path}\n")
            self._open_in_webview("Blicsa - Mapa Temático", thematic_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
            
            # Removed automatic AI call
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Mapa Temático", str(exc))

    def _open_historiograph(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo na aba Importação.")
            return
        try:
            fig = build_historiograph(self._dataframe)
            import time
            hist_path = str(WORK_DIR / f"blicsa_historiografia_{int(time.time())}.html")
            fig.write_html(hist_path, include_plotlyjs=True)
            log.info(f"[Historiografia] Salva → {hist_path}\n")
            self._open_in_webview("Blicsa - Historiografia", hist_path)
            if hasattr(self, '_refresh_gallery'): self._refresh_gallery()
            
            # Removed automatic AI call
        except Exception as exc:
            messagebox.showerror("Erro ao gerar Historiografia", str(exc))

    # ── AI ─────────────────────────────────────────────────────────────
    def _run_ai(self):
        if getattr(self, '_dataframe', None) is None or self._dataframe.empty:
            messagebox.showwarning("Sem dados", "Importe ou busque dados antes de analisar.")
            return

        report_txt = ""
        try:
            if self._generator is not None:
                report = self._generator.get_cluster_report()
                report_txt += f"Relatório de Clusters (Mapa):\n{report}\n"
                
            # Adiciona informações gerais do dataset
            df = self._dataframe
            total_docs = len(df)
            anos = df['year'].dropna().tolist() if 'year' in df else []
            min_ano, max_ano = min(anos) if anos else '?', max(anos) if anos else '?'
            report_txt += f"\nDataset possui {total_docs} documentos, período de publicação de {min_ano} a {max_ano}.\n"
            
            if hasattr(self, '_inject_ai_context'):
                self._inject_ai_context(report_txt)
            if hasattr(self, '_toggle_ai_drawer'):
                self._toggle_ai_drawer(force_open=True)
        except Exception as e:
            messagebox.showerror("Erro IA", f"Falha ao iniciar assistente: {e}")

    def _ai_sankey_worker(self):
        try:
            self.after(0, self._set_busy, "IA analisando Sankey…")
            df = self._dataframe
            from collections import Counter as _C
            
            # Simple author -> keyword relation summary
            auths_kws = _C()
            for _, row in df.dropna(subset=["authors", "keywords"]).iterrows():
                a_list = [a.strip() for a in str(row["authors"]).split(";") if a.strip()]
                k_list = [k.strip().lower() for k in str(row["keywords"]).split(";") if k.strip()]
                for a in a_list[:5]:
                    for k in k_list[:5]:
                        auths_kws[(a, k)] += 1
            
            summary = "Top fluxos Autor -> Palavra-chave:\n"
            for (a, k), count in auths_kws.most_common(15):
                summary += f"  - Autor {a} estuda {k} ({count} vezes)\n"
                
            result = self._analise_de_ia(
                "insights_sankey", lambda a: a.generate_sankey_insights(summary))
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights Sankey prontos")
        except AIClientError as exc:
            self.after(0, self._set_idle, "Erro IA")
            import threading
            self.after(0, lambda e=exc: self._show_ai_error_dialog(
                str(e), retry_cb=lambda: _ThreadDaTela(target=self._ai_sankey_worker, daemon=True).start()))
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao analisar Sankey:\n{e}"))

    def _ai_thematic_worker(self):
        try:
            self.after(0, self._set_busy, "IA analisando Tema…")
            G = self._generator.G
            partition = nx.get_node_attributes(G, "group")
            clusters = {}
            for node, grp in partition.items():
                clusters.setdefault(grp, []).append(node)
                
            summary = "Clusters e seus termos centrais:\n"
            for c, nodes in list(clusters.items())[:8]:
                top_nodes = sorted(nodes, key=lambda n: G.nodes[n].get("occurrence", 0), reverse=True)[:5]
                cent = sum(G[u][v].get("weight", 1.0) for u in nodes for v in G.neighbors(u) if v not in nodes)
                dens = sum(G[u][v].get("weight", 1.0) for u in nodes for v in G.neighbors(u) if v in nodes) / (2.0 * len(nodes))
                summary += f"  - Cluster {c} ({len(nodes)} nós, Centralidade: {cent:.1f}, Densidade: {dens:.3f}): {', '.join(top_nodes)}\n"
                
            result = self._analise_de_ia(
                "insights_tematico", lambda a: a.generate_thematic_insights(summary))
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights Temáticos prontos")
        except AIClientError as exc:
            self.after(0, self._set_idle, "Erro IA")
            import threading
            self.after(0, lambda e=exc: self._show_ai_error_dialog(
                str(e), retry_cb=lambda: _ThreadDaTela(target=self._ai_thematic_worker, daemon=True).start()))
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao analisar Mapa Temático:\n{e}"))

    def _ai_historiograph_worker(self):
        try:
            self.after(0, self._set_busy, "IA analisando História…")
            df = self._dataframe
            top_papers = df.sort_values(by="citations", ascending=False).head(15)
            summary = "Artigos principais na linha evolutiva:\n"
            for _, row in top_papers.iterrows():
                authors = str(row.get("authors", ""))
                first = authors.split(";")[0].strip() if authors else "Anon"
                year = int(row.get("year", 0))
                cit = int(row.get("citations", 0))
                title = str(row.get("title", ""))[:60]
                summary += f"  - {first} ({year}) com {cit} citações: \"{title}...\"\n"
                
            result = self._analise_de_ia(
                "insights_historiografico",
                lambda a: a.generate_historiograph_insights(summary))
            self.after(0, self._show_insights, result)
            self.after(0, self._set_idle, "Insights Historiografia prontos")
        except AIClientError as exc:
            self.after(0, self._set_idle, "Erro IA")
            import threading
            self.after(0, lambda e=exc: self._show_ai_error_dialog(
                str(e), retry_cb=lambda: _ThreadDaTela(target=self._ai_historiograph_worker, daemon=True).start()))
        except Exception as exc:
            self.after(0, self._set_idle, "Erro IA")
            self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao analisar Historiografia:\n{e}"))

    def _trigger_map_ai_insights(self):
        if self._dataframe is None:
            return
        try:
            log.info("[IA] Coletando sumário do mapa e de autores seminais...")
            df = self._dataframe
            
            # 1. Seminal authors summary
            ref_col = None
            for col in ("CR", "References", "Cited References", "references"):
                if col in df.columns:
                    ref_col = col
                    break
                    
            seminal_summary = ""
            if ref_col:
                from collections import Counter
                import re
                counter = Counter()
                for val in df[ref_col].dropna():
                    refs = [r.strip() for r in re.split(r"[;\n]", str(val)) if r.strip()]
                    for r in refs:
                        counter[r] += 1
                top_refs = counter.most_common(20)
                if top_refs:
                    seminal_summary = "Principais Trabalhos/Autores Seminais:\n"
                    for ref, count in top_refs:
                        seminal_summary += f"  - {ref} (citado {count} vezes)\n"
            
            # 2. Map thematic summary
            thematic_summary = ""
            if getattr(self, '_generator', None) and getattr(self._generator, 'G', None):
                import networkx as nx
                G = self._generator.G
                partition = nx.get_node_attributes(G, "group")
                clusters = {}
                for node, grp in partition.items():
                    clusters.setdefault(grp, []).append(node)
                
                thematic_summary = "Clusters Temáticos do Mapa:\n"
                for c, nodes in list(clusters.items())[:8]:
                    top_nodes = sorted(nodes, key=lambda n: G.nodes[n].get("occurrence", 0), reverse=True)[:5]
                    thematic_summary += f"  - Cluster {c} (Termos principais: {', '.join(top_nodes)})\n"
                    
            # 3. Request streaming response in Blink Research chat
            if not seminal_summary and not thematic_summary:
                return
                
            full_context = f"{thematic_summary}\n\n{seminal_summary}"
            prompt_msg = "O mapa bibliométrico acabou de ser gerado! Por favor, me dê:\n1. Alguns insights sobre os clusters temáticos do mapa.\n2. Quais são os principais autores seminais (trabalhos mais citados) com um pequeno resuminho sobre eles."
            
            # Use after(0) to update UI
            def _start_streaming():
                # Leva o usuário para a aba do Blink automaticamente.
                self._switch_tab("home")
                self._add_blink_message("user", prompt_msg)
                
                # Remonta em vez de reaproveitar `_research_messages[0]`: aquele valor foi
                # congelado quando a tela foi construída, e o contexto de pesquisa pode ter
                # sido escrito depois. Reaproveitar mandava o prompt SEM o contexto que o
                # usuário está vendo marcado como ativo na tela.
                system_prompt = self._blink_system_prompt(dados_corpus=full_context)

                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                # Indicator
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._rolar_conversa_para_o_fim()
                
                import threading
                def _stream_worker():
                    try:
                        full_response = self._responder_no_chat(
                            "insights_do_mapa", messages, indicator_row)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                    except Exception as ex:
                        def _err_row(e=ex):
                            if indicator_row.winfo_exists(): indicator_row.destroy()
                            self._add_ai_error_row(
                                self._research_chat_history_main, detail=str(e),
                                retry_cb=lambda: _ThreadDaTela(target=_stream_worker, daemon=True).start())
                        self.after(0, _err_row)
                _ThreadDaTela(target=_stream_worker, daemon=True).start()
                
            self.after(0, _start_streaming)
            
        except Exception as exc:
            log.info(f"[ERRO IA] {exc}\n")

    def _trigger_corpus_ai_insights(self):
        if self._dataframe is None or self._dataframe.empty:
            return
            
        try:
            log.info("[IA] Analisando o corpus selecionado...")
            df = self._dataframe
            
            # Prepare context
            total_docs = len(df)
            years = df.get('year', df.iloc[:,0]).dropna()
            try:
                years = years.astype(int)
                years = years[years > 0]
                year_min, year_max = int(years.min()), int(years.max()) if not years.empty else ("?", "?")
            except:
                year_min, year_max = "?", "?"
            
            # Top authors
            from collections import Counter
            all_authors = []
            if 'authors' in df.columns:
                for a in df['authors'].dropna().astype(str):
                    all_authors.extend([x.strip() for x in a.split(';') if x.strip()])
            top_authors = [a for a, c in Counter(all_authors).most_common(5)]
            
            # Top sources
            all_sources = []
            if 'source' in df.columns:
                for s in df['source'].dropna().astype(str):
                    all_sources.extend([x.strip() for x in s.split(';') if x.strip()])
            top_sources = [s for s, c in Counter(all_sources).most_common(5)]
            
            # User filters (search queries or local filters)
            query = self._search_query.get().strip() if getattr(self, '_search_query', None) else "Não especificada / Filtro Local"
            
            context = f"**Estatísticas do Corpus:**\n"
            context += f"- Documentos: {total_docs}\n"
            context += f"- Período: {year_min} a {year_max}\n"
            context += f"- Top Autores: {', '.join(top_authors)}\n"
            context += f"- Top Fontes: {', '.join(top_sources)}\n"
            context += f"- Termo de Busca Original: {query}\n"
            
            prompt_msg = "Gere uma análise justificando a escolha e a utilidade acadêmica deste corpus. Para que ele serve? Quais critérios parecem unir esses documentos e por que outros documentos (de outras épocas, áreas ou autores) podem ter sido deixados de fora dessa filtragem?"
            
            def _start_streaming():
                self._switch_tab("home")
                self._add_blink_message("user", prompt_msg)
                
                system_prompt = self._blink_system_prompt(
                    dados_corpus=f"Corpus selecionado:\n{context}")

                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._rolar_conversa_para_o_fim()
                
                import threading
                def _stream_worker():
                    try:
                        full_response = self._responder_no_chat(
                            "insights_do_corpus", messages, indicator_row)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                    except Exception as ex:
                        def _err_row(e=ex):
                            if indicator_row.winfo_exists(): indicator_row.destroy()
                            self._add_ai_error_row(
                                self._research_chat_history_main, detail=str(e),
                                retry_cb=lambda: _ThreadDaTela(target=_stream_worker, daemon=True).start())
                        self.after(0, _err_row)
                _ThreadDaTela(target=_stream_worker, daemon=True).start()
                
            self.after(0, _start_streaming)
            
        except Exception as exc:
            log.info(f"[ERRO IA Corpus] {exc}\n")

    def _pedido_de_analise_de_busca(self):
        """`(pedido ao modelo, bolha na conversa, contexto)` a partir da busca em tela.

        **O que o modelo lê e o que o usuário lê são coisas diferentes.** A bolha mostrava o
        pedido INTEIRO — regras de sintaxe, lista de proibições, formato de saída —, um
        paredão de instrução apresentado como se fosse a frase que a pessoa acabou de
        escrever. Ela não escreveu aquilo: ela clicou num botão. O modelo continua recebendo
        o pedido completo; a conversa mostra a pergunta.

        Fora do `_trigger_import_ai_assistant` porque é a única parte com decisão dentro, e
        aqui ela se testa sem thread, sem rede e sem chave de IA.
        """
        #: Regras que valem para os dois pedidos. Num lugar só porque divergir foi como o
        #: pedido "sem string" acabou sem a proibição de tipo de documento.
        regras = t("busca_ia.regras")

        query = self._search_query_entry.get().strip()
        if not query:
            return (t("busca_ia.prompt_sem_string", regras=regras),
                    t("busca_ia.bolha_sem_string"),
                    t("busca_ia.contexto_vazio"))

        provider = self._search_provider_var.get()
        start_yr = self._search_year_start.get().strip() or "Qualquer"
        end_yr = self._search_year_end.get().strip() or "Qualquer"
        doc_type = self._search_type_var.get()
        lang = self._search_lang_var.get()
        oa = "Sim" if self._search_oa_var.get() else "Não exigido"

        context = (f"**Parâmetros de Busca Configurados:**\n"
                   f"- Base: {provider.upper()}\n"
                   f"- String: `{query}`\n"
                   f"- Período: {start_yr} a {end_yr}\n"
                   f"- Tipo de Documento: {doc_type}\n"
                   f"- Idioma: {lang}\n"
                   f"- Open Access: {oa}\n")

        return (t("busca_ia.prompt_com_string", regras=regras),
                t("busca_ia.bolha_com_string", query=query),
                context)

    def _trigger_import_ai_assistant(self):
        """O Blink analisando a busca em configuração e propondo uma string.

        O pedido ao modelo é de UMA string conceitual, não de três. A adaptação para cada
        base é determinística e mora em `core/strings_por_base.py` — pedir três ao modelo
        seria três vezes a chance de ele inventar sintaxe, e as regras de cada API são
        fixas, não são questão de julgamento.

        As proibições do pedido não são estilo: cada uma corresponde a uma falha MEDIDA
        contra as APIs (curinga = HTTP 400 no OpenAlex, vírgula = HTTP 400, sintaxe de
        Scopus = 1 resultado no PubMed). O tradutor conserta tudo isso de qualquer forma; a
        proibição existe para o usuário LER uma string que já é a boa, em vez de ver o
        aviso de conserto embaixo de toda sugestão.
        """
        try:
            log.info("[IA] Analisando os parâmetros de busca...")

            prompt_msg, bolha, context = self._pedido_de_analise_de_busca()

            def _start_streaming():
                self._switch_tab("home")
                self._add_blink_message("user", bolha)

                system_prompt = self._blink_system_prompt(
                    dados_corpus=f"Busca em configuração:\n{context}")

                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_msg}]
                self._research_messages.append({"role": "user", "content": prompt_msg})
                
                import customtkinter as ctk
                from ui.design_tokens import INK, WHITE_CARD
                indicator_row = ctk.CTkFrame(self._research_chat_history_main, fg_color="transparent")
                indicator_row.pack(fill="x", pady=5)
                indicator = ctk.CTkFrame(indicator_row, fg_color=INK, width=16, height=16, corner_radius=0)
                indicator.pack(side="left", padx=14, pady=14)
                
                def pulse_indicator():
                    if indicator.winfo_exists():
                        current = indicator.cget("fg_color")
                        indicator.configure(fg_color=WHITE_CARD if current == INK else INK, border_width=2 if current == INK else 0, border_color=INK)
                        indicator.after(400, pulse_indicator)
                pulse_indicator()
                self._rolar_conversa_para_o_fim()
                
                import threading
                def _stream_worker():
                    try:
                        full_response = self._responder_no_chat(
                            "assistente_de_busca", messages, indicator_row)
                        
                        self._research_messages.append({"role": "assistant", "content": full_response})
                        # Resposta completa: só agora dá para procurar nela a string proposta —
                        # durante o streaming ela chega pela metade.
                        self.after(0, lambda r=full_response: self._oferecer_string_de_busca(r))
                    except Exception as ex:
                        def _err_row(e=ex):
                            if indicator_row.winfo_exists(): indicator_row.destroy()
                            self._add_ai_error_row(
                                self._research_chat_history_main, detail=str(e),
                                retry_cb=lambda: _ThreadDaTela(target=_stream_worker, daemon=True).start())
                        self.after(0, _err_row)
                _ThreadDaTela(target=_stream_worker, daemon=True).start()
                
            self.after(0, _start_streaming)
            
        except Exception as exc:
            log.info(f"[ERRO IA Assistente Busca] {exc}\n")


    def _show_seminal_insights(self, text: str):
        """Análise de obras seminais na aba própria.

        A marcação aqui é TEXTUAL (`[IA]` + selo no rótulo da aba), e não faixa + selo: o
        destino é um `CTkTextbox` que já existe no grid da aba, e envolvê-lo num
        `AIContentFrame` reconstruiria o layout do painel inteiro. O texto sobrevive a
        impressão P&B e a copiar-e-colar, que é o que a convenção exige de fato — ver a mesma
        decisão na Treeview de clusters.

        Usa o mesmo parser completo da conversa do Blink: tabelas, listas e links são
        legíveis também na aba seminal.
        """
        from ui.ai_marking import marcar_texto_export
        from core.markdown_parser import insert_markdown

        self._seminal_box.configure(state="normal")
        self._seminal_box.delete("1.0", "end")
        # O selo precisa ocupar sua própria linha: na mesma linha que "# Título"
        # ele impede o parser de reconhecer o cabeçalho Markdown.
        insert_markdown(self._seminal_box, f"{marcar_texto_export('')}\n\n{text}".strip())
        self._seminal_box.configure(state="disabled")

    #: Colunas onde as referências citadas podem estar, por origem do export.
    COLUNAS_REFERENCIAS = ("CR", "References", "Cited References", "references")

    def _coluna_de_referencias(self) -> str | None:
        from core.seminal import reference_column
        return reference_column(self._dataframe)

    def _top_referencias(self, n: int = 20) -> list[tuple[str, int]]:
        """As `n` referências mais citadas do corpus, com a contagem.

        Ponto único: a biblioteca de PDFs e a análise seminal partem da MESMA lista. Contar de
        dois jeitos faria o relatório falar de obras que a pasta não baixou.
        """
        from core.seminal import top_references
        return top_references(self._dataframe, limit=n)

    def _trigger_seminal_insights(self):
        """Análise de autores e obras seminais — o botão que faltava.

        A aba, o destino (`_seminal_box`) e o renderizador com marcação de IA
        (`_show_seminal_insights`) já existiam; `generate_seminal_insights` também, testada
        nos três idiomas. Faltava só o fio entre eles — e o texto de espera da aba dizia
        *"aparecerá aqui após gerar o mapa"*, ou seja, o app prometia e não entregava.
        Levantamento em `docs/CODIGO-SEM-CHAMADOR.md`.
        """
        if self._dataframe is None or self._dataframe.empty:
            messagebox.showwarning(t("seminal.sem_dados_titulo"), t("seminal.sem_dados"))
            return
        if not self._coluna_de_referencias():
            messagebox.showerror(t("seminal.sem_refs_titulo"), t("seminal.sem_refs"))
            return
        top = self._top_referencias()
        if not top:
            messagebox.showinfo(t("seminal.sem_refs_titulo"), t("seminal.sem_refs"))
            return

        self._set_busy(t("seminal.analisando"))
        _ThreadDaTela(target=self._seminal_insights_worker, args=(top,),
                         daemon=True).start()

    @staticmethod
    def _preparar_referencias_seminais(top_refs: list[tuple[str, int]]) -> tuple[str, int]:
        """Metadados exatos para IDs OpenAlex; nunca manda um W... opaco como obra à IA."""
        from core.seminal import OPENALEX_WORK_ID, reference_metadata_consistent
        from core.sources.openalex import OpenAlexProvider
        from core.sources.crossref import CrossrefProvider
        from core.sources.datacite import get_by_doi as get_datacite_by_doi

        provider = None
        crossref = None
        linhas = []
        nao_resolvidas = 0
        for ref, count in top_refs:
            if OPENALEX_WORK_ID.fullmatch(ref.strip()):
                if provider is None:
                    provider = OpenAlexProvider()
                record = provider.get_by_id(ref)
                if not record or not record.get("title"):
                    nao_resolvidas += 1
                    continue
                if record.get("doi"):
                    if crossref is None:
                        crossref = CrossrefProvider()
                    try:
                        registered = crossref.get_by_doi(record["doi"])
                    except Exception as exc:
                        log.warning("[Seminais] conferência do DOI indisponível: %s", exc)
                        registered = None
                    if registered is None:
                        try:
                            registered = get_datacite_by_doi(record["doi"])
                        except Exception as exc:
                            log.warning("[Seminais] DataCite indisponível: %s", exc)
                    if not registered or not reference_metadata_consistent(record, registered):
                        log.warning("[Seminais] DOI sem metadados conferíveis ou contraditórios em %s", ref)
                        nao_resolvidas += 1
                        continue
                authors = record.get("authors") or t("seminal.autor_nao_identificado")
                year = record.get("year") or t("seminal.ano_nao_identificado")
                title = record["title"]
                abstract = str(record.get("abstract") or "").strip()[:800]
                linhas.append(f"{len(linhas) + 1}. {title} ({year}); {authors}; "
                              f"{count} {t('seminal.citacoes_corpus')}; "
                              f"OpenAlex: {ref}; "
                              f"{t('seminal.resumo_metadados')}: {abstract or t('seminal.resumo_ausente')}")
            else:
                linhas.append(f"{len(linhas) + 1}. {ref}; {count} {t('seminal.citacoes_corpus')} "
                              f"({t('seminal.referencia_original')})")
        return "\n".join(linhas), nao_resolvidas

    def _seminal_insights_worker(self, top_refs: list[tuple[str, int]]):
        try:
            resumo, nao_resolvidas = self._preparar_referencias_seminais(top_refs)
            if not resumo:
                raise AIClientError(t("seminal.nao_resolvidas"))
            texto = self._analise_de_ia(
                "obras_seminais", lambda a: a.generate_seminal_insights(resumo))
            if nao_resolvidas:
                texto = (t("seminal.refs_ignoradas", count=nao_resolvidas) + "\n\n" + texto)
        except AIClientError as e:
            # Falta de chave é o estado do usuário novo: recusa clara, nunca traceback.
            #
            # `erro=e` como argumento padrão, não captura livre: o Python apaga o nome do
            # `except` ao sair do bloco, e esta lambda só roda depois, na fila do `after`.
            # Fechar sobre `e` levantava `NameError` **dentro do tratador de erro** — o
            # usuário sem chave não recebia aviso nenhum.
            self.after(0, self._set_idle, t("seminal.erro"))
            self.after(0, lambda erro=e: messagebox.showerror(t("ai.error_title"), str(erro)))
            return
        except Exception as e:
            self.after(0, self._set_idle, t("seminal.erro"))
            self.after(0, lambda erro=e: messagebox.showerror(t("ai.error_title"), str(erro)))
            return
        self.after(0, self._show_seminal_insights, texto)
        self.after(0, self._set_idle, t("seminal.pronto"))

    def _create_seminal_library(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return

        ref_col = self._coluna_de_referencias()
        if not ref_col:
            messagebox.showerror("Erro", "Nenhuma coluna de referências encontrada no dataset.")
            return

        folder_path = filedialog.askdirectory(title="Selecione onde criar a pasta da biblioteca")
        if not folder_path:
            return
            
        from tkinter import simpledialog
        folder_name = simpledialog.askstring("Nome da Pasta", "Qual o nome da pasta da biblioteca?", initialvalue="Biblioteca_Artigos_Seminais")
        if not folder_name:
            return
            
        full_path = Path(folder_path) / folder_name.strip()
        try:
            full_path.mkdir(parents=True, exist_ok=True)

            # Mesma contagem da análise seminal, de propósito: a pasta baixada e o relatório
            # têm de falar das MESMAS obras.
            top_refs = self._top_referencias()
            if not top_refs:
                messagebox.showinfo("Sem referências", "Nenhuma referência encontrada para gerar arquivos.")
                return
                
            self._set_busy("Buscando metadados dos artigos seminais (OpenAlex)...")
            _ThreadDaTela(
                target=self._create_seminal_library_worker,
                args=(full_path, top_refs),
                daemon=True
            ).start()
            
        except Exception as exc:
            messagebox.showerror("Erro ao criar biblioteca", str(exc))

    #: Fração dos termos da consulta que precisa aparecer no título encontrado para o
    #: resultado ser aceito. Calibrado contra a API real: com um piso de 2 termos absolutos,
    #: a referência do VOSviewer casava com "Bibliometric mapping of computer and
    #: information ethics" e a do Ostrom com "Social learning promotes institutions for
    #: governing the commons" — os dois iriam para o arquivo como se fossem o artigo citado.
    #: A 0,7, os pares errados ficam em torno de 40% e os certos em 100%.
    _CONFERE_MINIMO = 0.7

    def _enriquecer_referencia(self, provider, ref: str) -> tuple[dict, str]:
        """Metadados de UMA referência no OpenAlex. Devolve `(dados, motivo_da_falha)`.

        Vai pelo `OpenAlexProvider` em vez de montar URL com `urllib` cru, e isso não é
        arrumação: as duas chamadas soltas que existiam aqui não passavam pelo `fetch_url`
        do provider, então **nunca receberiam a chave da API**, ficavam de fora do retry com
        backoff e mandavam o contato num `User-Agent` com o endereço escrito à mão em vez do
        `MAILTO` de `core/sources/base.py`.

        A busca textual ainda montava `?q=…&limit=1`. `limit` não existe no OpenAlex — a API
        responde `400 Bad Request` ("The 'limit' parameter is not valid. Did you mean
        'per-page'?"). Como tudo estava dentro de um `except Exception: pass`, o
        enriquecimento por texto nunca funcionou e nunca reclamou.

        O motivo da falha volta como texto em vez de virar log: quem pediu a biblioteca
        precisa saber que ela veio incompleta, e por quê.
        """
        import re

        from core.sources.base import AuthError, PaginationLimitError, RateLimitError

        dados = {"title": None, "abstract": None, "url": None}

        # ── Caminho confiável: DOI ────────────────────────────────────────────────
        doi_match = re.search(r'(10\.\d{4,9}/[^\s,;]+)', ref)
        if doi_match:
            doi = doi_match.group(1).strip(".,;()")
            dados["url"] = f"https://doi.org/{doi}"
            registro = provider.get_by_doi(doi)      # AuthError/RateLimitError SOBEM
            if registro and registro.get("title"):
                # Resolveu pelo identificador exato: é O artigo, não um palpite. A busca
                # textual não entra aqui nem para completar — ela traz outro trabalho, e
                # colar o resumo de outro trabalho sob este título seria pior que não ter
                # resumo. Também pouparia 10 créditos para não melhorar nada.
                dados["title"] = registro["title"]
                dados["abstract"] = registro.get("abstract") or None
                if registro.get("is_oa") and registro.get("oa_url"):
                    dados["url"] = registro["oa_url"]
                return dados, "" if dados["abstract"] else "resumo não disponível no OpenAlex"

        # ── Caminho de palpite: busca textual ─────────────────────────────────────
        # A referência precisa ser LIMPA antes de virar consulta. `browse` monta
        # `filter=default.search:<query>`, e no OpenAlex a vírgula é separador de AND: uma
        # referência crua ("Van Eck NJ, Waltman L, 2010, Software survey: ...") vira meia
        # dúzia de filtros inválidos e a API responde 400. Medido contra a API real.
        consulta = re.sub(r'\[.*?\]', ' ', ref)                 # marcadores tipo "[12]"
        # Corta no ano e fica com o que vem DEPOIS. O formato "Autores, ANO, Título" é o
        # mesmo que a montagem do nome do arquivo, logo acima, já assume. Não é cosmético:
        # medido contra a API real, os nomes dos autores dentro da consulta afundam a
        # relevância — a referência do VOSviewer, que contém o título literal, devolvia
        # "Bibliometric mapping of computer and information ethics" com os autores juntos e
        # o artigo certo sem eles.
        m_ano = re.search(r'\b(19|20)\d{2}\b', consulta)
        if m_ano:
            consulta = consulta[m_ano.end():]
        consulta = re.sub(r'[,:;|&()"]', ' ', consulta)          # sintaxe do filter=
        consulta = re.sub(r'\s+', ' ', consulta).strip()
        if not consulta:
            return dados, "referência sem texto pesquisável"

        try:
            registros, _ = provider.browse(consulta, per_page=1)
        except (AuthError, RateLimitError):
            raise
        except PaginationLimitError:
            # `page=1 × per_page=1` não excede teto nenhum: se veio isto, foi um 400 de
            # sintaxe que o `browse` classifica como paginação. Chamar de "limite de
            # paginação" aqui mentiria para o usuário.
            return dados, "a referência não pôde ser convertida em consulta válida"
        except Exception as e:
            return dados, f"busca textual falhou ({type(e).__name__}: {e})"

        if not registros:
            return dados, "nenhum resultado no OpenAlex"

        w = registros[0]
        titulo = w.get("title") or ""
        if not titulo:
            return dados, "resultado sem título"

        # Conferência. Buscar pela citação inteira devolve QUALQUER coisa — a API sempre tem
        # um primeiro resultado. Quando o achado é mesmo o trabalho citado, o título dele
        # está escrito dentro da referência; quando não é, quase nenhum termo bate. Sem essa
        # trava, o arquivo do artigo seminal receberia título e resumo de OUTRO artigo, e o
        # usuário levaria o dado errado adiante sem ter como desconfiar.
        # A comparação é CONSULTA -> título, não título -> referência. A direção importa:
        # referências são truncadas o tempo todo ("...network of interactions" no lugar de
        # "...network of interactions between basic and technological research"), e medindo
        # ao contrário o Callon de 1991 batia 46% contra o artigo CERTO e seria descartado.
        termos_q = [p.lower() for p in re.findall(r'[A-Za-zÀ-ÿ]{4,}', consulta)]
        termos_tit = {p.lower() for p in re.findall(r'[A-Za-zÀ-ÿ]{4,}', titulo)}
        # Piso de 2, não de 3: "Pedagogia do oprimido" tem dois termos significativos e é
        # um título inteiro e legítimo. A 0,7, com dois termos os dois precisam bater.
        if len(termos_q) < 2:
            return dados, "referência curta demais para conferir o resultado"
        casados = sum(1 for p in termos_q if p in termos_tit)
        if casados / len(termos_q) < self._CONFERE_MINIMO:
            return dados, "resultado não confere com a referência"

        dados["title"] = titulo
        dados["abstract"] = w.get("abstract") or None
        if w.get("is_oa") and w.get("oa_url"):
            dados["url"] = w["oa_url"]
        else:
            dados["url"] = w.get("doi") or None
        return dados, "" if dados["abstract"] else "resumo não disponível no OpenAlex"

    def _create_seminal_library_worker(self, full_path, top_refs):
        import re

        from core.sources.base import AuthError, RateLimitError
        from core.sources.openalex import OpenAlexProvider

        provider = OpenAlexProvider()
        created_count = 0
        #: Referências que a API não resolveu. Antes sumiam: o `except Exception: pass`
        #: engolia tudo e o diálogo final dizia "Sucesso" com o mesmo texto de sempre.
        falhas: list[str] = []
        interrompido = ""
        for ref, count in top_refs:
            # 1. Determinar o nome base do arquivo
            match = re.search(r'\b(19\d\d|20\d\d)\b', ref)
            if match:
                year = match.group(1)
                parts = ref.split(year)
                author = parts[0].strip(", \n\t")
                author = re.sub(r'[\\/*?:"<>|]', "", author)
                filename = f"{author} ({year})"
            else:
                filename = re.sub(r'[\\/*?:"<>|]', "", ref)
                
            filename = filename.strip()
            if len(filename) > 110:
                filename = filename[:107] + "..."
            
            # 2. Metadados e resumo via OpenAlex, pelo provider (chave + retry + mailto).
            if interrompido:
                break
            try:
                dados, motivo = self._enriquecer_referencia(provider, ref)
            except (AuthError, RateLimitError) as e:
                # Não é falha DESTA referência: é a credencial ou o teto da API. Insistir
                # nas outras só repetiria o mesmo erro centenas de vezes.
                interrompido = t(getattr(e, "i18n_key", ""), **getattr(e, "i18n_args", {})) \
                    if getattr(e, "i18n_key", "") else str(e)
                break
            title, abstract, url = dados["title"], dados["abstract"], dados["url"]
            if motivo:
                falhas.append(f"{ref[:70]} — {motivo}")

            # 3. Escrever arquivo de descrição em formato .txt
            txt_filename = filename + "_DESCRICAO.txt"
            content_lines = [
                f"==================================================",
                f" ARTIGO SEMINAL - BLICSA / PYBIBLIOMICS",
                f"==================================================\n",
                f"Referência Original: {ref}",
                f"Citações no Dataset: {count} vezes\n",
                f"Título do Artigo:   {title or 'Não identificado pela API OpenAlex'}",
                f"Link / DOI / OA:    {url or 'Link não encontrado'}\n",
                f"Resumo / Descrição:",
                f"--------------------------------------------------",
                f"{abstract or 'Resumo/Abstract não disponível nas fontes de dados abertos.'}",
                f"--------------------------------------------------"
            ]
            
            try:
                with open(full_path / txt_filename, "w", encoding="utf-8") as f:
                    f.write("\n".join(content_lines))
                created_count += 1
            except Exception as e:
                log.info(f"[ERRO ao gravar arquivo {txt_filename}] {e}")
                
        # 4. Finalização na main thread do Tkinter
        def _done():
            self._set_idle()
            corpo = (f"Pasta: {full_path}\n"
                     f"Arquivos de descrição gerados: {created_count}")

            # O enriquecimento é metade do que esta função entrega: sem ele os arquivos saem
            # com "Não identificado pela API OpenAlex" no lugar do título e do resumo.
            # Anunciar "Sucesso" nesse estado é o que escondeu por tanto tempo que a busca
            # textual respondia 400 a cada chamada.
            if interrompido:
                messagebox.showwarning(
                    "Biblioteca criada sem os metadados",
                    f"{corpo}\n\nA consulta ao OpenAlex parou na primeira referência:\n"
                    f"{interrompido}\n\n"
                    "Os arquivos foram gravados, mas sem título e resumo.")
            elif falhas:
                amostra = "\n".join(f"  · {f}" for f in falhas[:5])
                resto = f"\n  … e mais {len(falhas) - 5}" if len(falhas) > 5 else ""
                messagebox.showwarning(
                    "Biblioteca criada com pendências",
                    f"{corpo}\n\n{len(falhas)} de {len(top_refs)} referências não foram "
                    f"encontradas no OpenAlex:\n{amostra}{resto}")
            else:
                messagebox.showinfo(
                    "Sucesso",
                    f"Biblioteca de seminais criada com sucesso!\n\n{corpo}")
            webbrowser.open(f"file://{full_path}")

        self.after(0, _done)

    # ── Rankings ────────────────────────────────────────────────────────
    def _show_ranking(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo.")
            return
        gen  = self._generator or NetworkGenerator(self._dataframe)
        kind = self._rank_var.get()

        # Clear existing rows and columns
        self._rank_tree.delete(*self._rank_tree.get_children())
        self._rank_sort_col = None
        self._rank_sort_rev = False

        def _setup_cols(cols: list[tuple[str, int, str]]):
            self._rank_tree.configure(columns=[c[0] for c in cols])
            for name, width, anchor in cols:
                self._rank_tree.heading(
                    name, text=name,
                    command=lambda c=name: self._sort_rank_tree(c))
                self._rank_tree.column(name, width=width, anchor=anchor, stretch=(width > 150))

        if kind == "keywords":
            _setup_cols([
                ("#",          48,  "center"),
                ("Termo",     300,  "w"),
                ("Ocorrências", 110, "e"),
                ("Grau",       90,  "e"),
                ("Ano Médio",  100, "e"),
            ])
            if self._generator and self._generator.G.number_of_nodes() > 0:
                G = self._generator.G
                nodes = sorted(
                    G.nodes(data=True),
                    key=lambda x: x[1].get("occurrence", 0),
                    reverse=True,
                )[:100]
                for i, (n, d) in enumerate(nodes, 1):
                    yr = d.get("year_mean", 0)
                    self._rank_tree.insert("", "end", values=(
                        i, n,
                        d.get("occurrence", "—"),
                        f"{G.degree(n, weight='weight'):.1f}",
                        f"{yr:.0f}" if yr else "—",
                    ))
            else:
                for i, (kw, n) in enumerate(gen.get_top_keywords(100), 1):
                    self._rank_tree.insert("", "end", values=(i, kw, n, "—", "—"), tags=("striped",) if i % 2 == 0 else ())

        elif kind == "authors":
            _setup_cols([
                ("#",         48,  "center"),
                ("Autor",    400,  "w"),
                ("Publicações", 110, "e"),
            ])
            for i, (a, n) in enumerate(gen.get_top_authors(100), 1):
                self._rank_tree.insert("", "end", values=(i, a, n), tags=("striped",) if i % 2 == 0 else ())

        elif kind == "hindex":
            _setup_cols([
                ("#",          48,  "center"),
                ("Autor",     280,  "w"),
                ("h-index",    80,  "e"),
                ("g-index",    80,  "e"),
                ("Artigos",    80,  "e"),
                ("Cit. Média", 100, "e"),
            ])
            for i, (author, h, g, papers, avg) in enumerate(gen.get_author_hindex(100), 1):
                self._rank_tree.insert("", "end", values=(
                    i, author, h, g, papers, f"{avg:.1f}"))

        elif kind == "sources":
            _setup_cols([
                ("#",              48,  "center"),
                ("Fonte / Periódico", 440, "w"),
                ("Publicações",    110, "e"),
            ])
            for i, (s, n) in enumerate(gen.get_top_sources(100), 1):
                self._rank_tree.insert("", "end", values=(i, s, n), tags=("striped",) if i % 2 == 0 else ())

        else:  # clusters
            _setup_cols([
                ("Cluster",   70,  "center"),
                ("Rótulo IA", 220, "w"),
                ("Nós",       70,  "e"),
                ("Top Termos / Autores", 450, "w"),
            ])
            from ui.ai_marking import rotulo_cluster_e_de_ia
            for c in gen.get_cluster_report():
                label = self._cluster_labels.get(c["cluster_id"], "—")
                # O selo vai no TEXTO da célula: a Treeview do Tk não aceita faixa colorida
                # por linha, e a marcação não pode depender de cor de qualquer forma.
                if label != "—" and rotulo_cluster_e_de_ia(c["cluster_id"],
                                                           self._cluster_label_origins):
                    label = f"[{t('ai.badge')}] {label}"
                self._rank_tree.insert("", "end", values=(
                    f"C{c['cluster_id']}",
                    label,
                    c["size"],
                    ", ".join(c["top_nodes"][:8]),
                ))

    def _sort_rank_tree(self, col: str):
        reverse = (self._rank_sort_col == col) and (not self._rank_sort_rev)
        self._rank_sort_col = col
        self._rank_sort_rev = reverse
        data = [
            (self._rank_tree.set(child, col), child)
            for child in self._rank_tree.get_children("")
        ]
        try:
            data.sort(key=lambda x: float(x[0].replace("—", "-1")), reverse=reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for idx, (_, child) in enumerate(data):
            self._rank_tree.move(child, "", idx)

    # ── Exports ─────────────────────────────────────────────────────────
    def _require_gen(self) -> NetworkGenerator | None:
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
        return self._generator

    def _export_nodes_csv(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")]):
            gen.export_rankings_csv(path)
            log.info(f"[Export] Nós → {path}")

    def _export_edges_csv(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")]):
            gen.export_edges_csv(path)
            log.info(f"[Export] Arestas → {path}")

    def _export_df_csv(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")]):
            # O corpus é dado de terceiro: um título ou keyword começando com `=` vira
            # fórmula quando o pesquisador abre o CSV no Excel. Ver `neutralizar_formula`.
            from core.nlp import neutralizar_formulas_no_df
            neutralizar_formulas_no_df(self._dataframe).to_csv(
                path, index=False, encoding="utf-8-sig")
            self._record_export("csv", path)
            log.info(f"[Export] DataFrame → {path}")

    def _export_clusters_txt(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".txt", filetypes=[("Text", "*.txt")]):
            with open(path, "w", encoding="utf-8") as f:
                for c in gen.get_cluster_report():
                    f.write(
                        f"Cluster {c['cluster_id']}  |  "
                        f"{c['size']} nós  |  {c['color']}\n"
                        f"  Top nós: {', '.join(c['top_nodes'])}\n\n"
                    )
            log.info(f"[Export] Clusters → {path}")

    def _export_plotly_html(self):
        # Antes copiava PLOTLY_PATH, que nenhum código grava: o botão sempre dizia "Gere o
        # mapa primeiro" (B8). Agora monta a mesma figura do "Abrir Plotly".
        if self._generator is None or not self._positions:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".html", filetypes=[("HTML", "*.html")]):
            from core.visualizer import build_plotly_map
            fig = build_plotly_map(self._generator.G, self._positions,
                                   color_mode=self._plotly_mode_var.get(),
                                   df=self._dataframe)
            fig.write_html(path, include_plotlyjs=True)
            self._record_export("html", path)
            log.info(f"[Export] Plotly HTML → {path}")

    def _export_pyvis_html(self):
        if not Path(MAP_PATH).exists():
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".html", filetypes=[("HTML", "*.html")]):
            import shutil
            shutil.copy(MAP_PATH, path)
            log.info(f"[Export] PyVis HTML → {path}")

    def _static_map_canvas(self):
        """Figura estática (matplotlib) do mapa atual para PNG/SVG/PDF.

        Esses exports liam `self._map_canvas`, o canvas matplotlib que saiu da aba de mapa
        quando o Sigma.js assumiu a visualização; ficou sempre `None` e os três botões
        respondiam "Gere o mapa primeiro" com mapa gerado (B8). Aqui o mesmo `MapCanvas` é
        montado numa janela oculta e desenhado com o grafo e o layout atuais.
        """
        if self._map_canvas is not None:
            return self._map_canvas
        gen = self._generator
        if gen is None or gen.G.number_of_nodes() == 0 or not self._positions:
            return None
        host = getattr(self, "_static_canvas_host", None)
        if host is None or not host.winfo_exists():
            host = ctk.CTkToplevel(self)
            host.withdraw()
            host.grid_columnconfigure(0, weight=1)
            host.grid_rowconfigure(0, weight=1)
            self._static_canvas_host = host
            self._static_canvas = MapCanvas(host)
        canvas = self._static_canvas
        canvas.set_cluster_labels(self._cluster_labels or {})
        canvas.render(gen.G, self._positions)
        return canvas

    def _export_png(self):
        if (canvas := self._static_map_canvas()) is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".png", filetypes=[("PNG", "*.png")]):
            export_figure_image(canvas.figure, path, dpi=300)
            self._record_export("png", path)

    def _export_svg(self):
        if (canvas := self._static_map_canvas()) is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".svg", filetypes=[("SVG", "*.svg")]):
            export_figure_image(canvas.figure, path, dpi=150)
            self._record_export("svg", path)

    def _export_pdf(self):
        if (canvas := self._static_map_canvas()) is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".pdf", filetypes=[("PDF", "*.pdf")]):
            export_figure_image(canvas.figure, path, dpi=300)
            self._record_export("pdf", path)

    def _mapa_pronto(self) -> bool:
        """Grafo e posições disponíveis. Sem os dois não há o que animar nem cartografar."""
        if getattr(self, "_graph", None) is None or not getattr(self, "_positions", None):
            messagebox.showwarning(t("anim.sem_mapa_titulo"), t("anim.sem_mapa"))
            return False
        return True

    def _export_map_animation(self):
        """Exporta a evolução temporal do mapa como GIF, sequência de PNG ou MP4.

        O formato sai da **extensão escolhida no diálogo**, e não de um seletor separado:
        quem digita `.mp4` já disse o que quer. Sem `ffmpeg` o MP4 degrada com aviso, em vez
        de falhar — `export_mp4` devolve `(False, motivo)` por projeto.
        """
        if not self._mapa_pronto():
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("GIF", "*.gif"), ("MP4", "*.mp4"), ("PNG (sequência)", "*.png")])
        if not caminho:
            return
        self._set_busy(t("anim.gerando"))
        _ThreadDaTela(target=self._map_animation_worker, args=(caminho,),
                         daemon=True).start()

    def _map_animation_worker(self, caminho: str):
        from core.map_animation import (export_gif, export_mp4, export_png_sequence,
                                        render_frame, timeline_frames)

        try:
            quadros = timeline_frames(self._graph, self._dataframe)
            if not quadros:
                self.after(0, self._set_idle, t("anim.sem_anos"))
                self.after(0, lambda: messagebox.showinfo(t("anim.sem_anos_titulo"),
                                                          t("anim.sem_anos")))
                return
            imagens = [render_frame(q, self._positions) for q in quadros]

            destino = Path(caminho)
            if destino.suffix.lower() == ".mp4":
                ok, motivo = export_mp4(imagens, str(destino))
                if not ok:
                    # Sem ffmpeg o GIF continua saindo: melhor entregar algo com aviso do
                    # que recusar o pedido inteiro por causa de um binário ausente.
                    alternativa = destino.with_suffix(".gif")
                    export_gif(imagens, str(alternativa))
                    self.after(0, lambda m=motivo, a=alternativa: messagebox.showwarning(
                        t("anim.sem_ffmpeg_titulo"), f"{m}\n\n{t('anim.gif_no_lugar')}: {a}"))
                    destino = alternativa
            elif destino.suffix.lower() == ".png":
                export_png_sequence(imagens, str(destino.parent), destino.stem)
            else:
                export_gif(imagens, str(destino))

            log.info(f"[Export] animação ({len(imagens)} quadros) → {destino}\n")
            self.after(0, self._set_idle, t("anim.pronto"))
        except Exception as e:
            self.after(0, self._set_idle, t("anim.erro"))
            self.after(0, lambda erro=e: messagebox.showerror(t("anim.erro"), str(erro)))

    def _export_map_poster(self):
        """Pôster neoplasticista: treemap com a ÁREA de cada plano proporcional ao peso do
        cluster. Não é enfeite — é leitura imediata de tamanho relativo."""
        if not self._mapa_pronto():
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not caminho:
            return
        try:
            from collections import Counter

            from core.map_animation import render_poster

            pesos: Counter = Counter()
            termos: dict[int, list[str]] = {}
            for no, dados in self._graph.nodes(data=True):
                grupo = int(dados.get("group", 0) or 0)
                pesos[grupo] += float(dados.get("occurrence", 1) or 1)
                termos.setdefault(grupo, []).append(str(dados.get("label", no)))
            for grupo in termos:
                termos[grupo] = termos[grupo][:6]

            imagem = render_poster(dict(pesos), cluster_terms=termos,
                                   cluster_labels=getattr(self, "_cluster_labels", None) or {})
            imagem.save(caminho)
            log.info(f"[Export] pôster ({len(pesos)} clusters) → {caminho}\n")
            self._set_idle(t("anim.pronto"))
        except Exception as e:
            messagebox.showerror(t("anim.erro"), str(e))

    def _export_excel(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")]):
            gen.export_excel(path, df_raw=self._dataframe)
            log.info(f"[Export] Excel → {path}\n")

    def _export_gml(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".gml", filetypes=[("GML", "*.gml")]):
            gen.export_gml(path)
            log.info(f"[Export] GML → {path}")

    def _export_gexf(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".gexf", filetypes=[("GEXF", "*.gexf")]):
            gen.export_gexf(path)
            log.info(f"[Export] GEXF → {path}\n")

    def _export_pajek(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".net", filetypes=[("Pajek", "*.net")]):
            gen.export_pajek(path)
            log.info(f"[Export] Pajek → {path}")

    def _export_json(self):
        if not (gen := self._require_gen()):
            return
        if path := filedialog.asksaveasfilename(
                defaultextension=".json", filetypes=[("JSON", "*.json")]):
            gen.export_json_topology(path, positions=self._positions)
            log.info(f"[Export] JSON topologia → {path}")

    def _export_vosviewer(self):
        if not (gen := self._require_gen()):
            return
        map_path = filedialog.asksaveasfilename(
            title="Salvar VOSviewer Map File",
            defaultextension=".txt",
            filetypes=[("VOSviewer Map (*.txt)", "*.txt")]
        )
        if not map_path:
            return
        net_path = map_path.replace(".txt", "_network.txt")
        if net_path == map_path:
            net_path = map_path + "_network.txt"
        gen.export_vosviewer(map_path, net_path, positions=self._positions)
        log.info(f"[Export] VOSviewer Map → {map_path}")
        log.info(f"[Export] VOSviewer Network → {net_path}")
        messagebox.showinfo("Exportação Concluída", f"Arquivos do VOSviewer exportados com sucesso!\n\nMapa: {map_path}\nRede: {net_path}")

    def _save_project_gui(self):
        import os
        # Projeto ativo: snapshot vai direto para <projeto>/project.blicsa
        # (atualiza o manifest) e ganha registro no backlog.
        if getattr(self, "_active_project", None):
            path = self._current_project_path
        else:
            proj_dir = getattr(self, "_projects_dir_var", ctk.StringVar(value=os.path.expanduser("~/Blicsa/projects"))).get()
            os.makedirs(proj_dir, exist_ok=True)
            path = filedialog.asksaveasfilename(
                initialdir=proj_dir,
                defaultextension=".blicsa",
                filetypes=[("Projeto Blicsa", "*.blicsa")],
                title="Salvar Projeto Blicsa",
            )
        if not path:
            return
        self._set_busy("Salvando projeto...")
        try:
            from core.project import save_blicsa_project
            config = {
                "name":         getattr(self, "_active_project_name", None) or Path(path).stem,
                "map_type":     self._map_type_var.get(),
                "field":        self._field_var.get(),
                "counting":     self._counting_var.get(),
                "assoc_strength": self._assoc_var.get(),
                "min_occ":      self._min_occ_var.get(),
                "max_nodes":    self._max_nodes_var.get(),
                "max_pct":      self._max_pct_var.get(),
                "fa2_iter":     self._fa2_iter_var.get(),
                "linlog":       self._linlog_var.get(),
                "viz_mode":     self._viz_mode_var.get(),
                "plotly_mode":  self._plotly_mode_var.get(),
                "year_min":     self._year_min_var.get(),
                "year_max":     self._year_max_var.get(),
                "extra_sw":     self._extra_sw_var.get(),
                "cluster_algorithm": self._cluster_alg_var.get(),
                "cluster_resolution": self._cluster_res_var.get(),
                # Contexto de pesquisa: chave nova no config. Projeto salvo por versão
                # anterior não a tem, e `research_context_do_config` devolve "" nesse caso —
                # a ausência é indistinguível de "sem contexto", que é o comportamento certo.
                "research_context": self._contexto_pesquisa(),
            }

            # Fase 3: bloco único com os parâmetros do mapa, para o projeto reabrir com o
            # MESMO mapa (inclusive os termos que o usuário excluiu na revisão).
            from core.map_controls import MapParams
            config["map_params"] = MapParams(
                fields={"keywords": "keywords"}.get(self._field_var.get(), "title_abstract"),
                binary_count=self._binary_count_var.get(),
                min_occurrences=int(self._min_occ_var.get()),
                resolution=float(self._cluster_res_var.get()),
                algorithm=self._cluster_alg_var.get(),
                attraction=float(self._attraction_var.get()),
                repulsion=float(self._repulsion_var.get()),
                excluded_terms=sorted(getattr(self, "_excluded_terms", set())),
            ).to_dict()


            thumbnail_path = None
            if hasattr(self, '_map_canvas') and getattr(self._map_canvas, 'figure', None) is not None:
                import tempfile
                tmp_png = tempfile.mktemp(suffix=".png")
                self._map_canvas.figure.savefig(tmp_png, dpi=72, bbox_inches='tight')
                thumbnail_path = tmp_png

            save_blicsa_project(
                path,
                df=self._dataframe,
                config=config,
                positions=self._positions,
                G=self._generator.G if self._generator else None,
                cluster_labels=self._cluster_labels,
                cluster_label_origins=self._cluster_label_origins,
                searches=getattr(self, "_searches", []),
                thumbnail_path=thumbnail_path
            )
            
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                
            self._backlog("export", {"formato": "blicsa", "caminho_relativo": "project.blicsa"})
            self._set_idle(f"Projeto salvo: {Path(path).name}")
            messagebox.showinfo("Sucesso", "Projeto salvo com sucesso!")
            
            if hasattr(self, "_projects_view"):
                self._projects_view.refresh()
                
        except Exception as e:
            self._set_idle(t("projeto.erro_titulo_salvar"))
            self._erro_de_projeto(e, t("projeto.erro_titulo_salvar"))

    def _load_project_gui(self):
        path = filedialog.askopenfilename(
            filetypes=[("Projeto Blicsa", "*.blicsa")],
            title="Carregar Projeto Blicsa",
        )
        if not path:
            return
        self._set_busy("Carregando projeto...")
        try:
            from core.project import load_blicsa_project
            project_data = load_blicsa_project(path)
            self._restore_project_data(project_data)
            self._set_idle("Projeto carregado com sucesso")
            if self._dataframe is not None and not self._dataframe.empty:
                # Idem: "viz" não é chave de aba. Carregar um projeto deixava a tela branca.
                self.after(0, lambda: self._switch_tab("analises"))
            messagebox.showinfo("Sucesso", "Projeto carregado com sucesso!")
        except Exception as e:
            self._set_idle(t("projeto.erro_titulo"))
            self._erro_de_projeto(e, t("projeto.erro_titulo"))

    def _erro_de_projeto(self, erro: BaseException, titulo: str):
        """Traduz a falha e mostra ao usuário; o detalhe técnico vai para o log.

        O que aparecia antes era `str(e)` cru: *"File is not a zip file"* em inglês fixo, ou
        *"There is no item named \'manifest.json\' in the archive"* — nomeando um arquivo
        interno do formato. O usuário sabia que falhou e não sabia o que fazer.

        O detalhe **não some**: vai para o log, que é onde um mantenedor procura. O que sai da
        tela é o jargão de biblioteca, não a informação.
        """
        from core.project import diagnosticar_projeto

        chave = diagnosticar_projeto(erro)
        log.info(f"[ERRO] {type(erro).__name__}: {erro}  → {chave}\n")
        messagebox.showerror(titulo, t(chave))

    def _restore_project_data(self, project_data: dict):
        """Restaura config + corpus + layout/grafo a partir de um projeto carregado."""
        from core.matrix_builders import NetworkGenerator
        # 1. Restore configuration
        config = project_data.get("config", {})
        setters: list[tuple] = [
            ("map_type",      self._map_type_var,  "set"),
            ("field",         self._field_var,      "set"),
            ("counting",      self._counting_var,   "set"),
            ("assoc_strength",self._assoc_var,      "set"),
            ("min_occ",       self._min_occ_var,    "set"),
            ("fa2_iter",      self._fa2_iter_var,   "set"),
            ("linlog",        self._linlog_var,      "set"),
            ("viz_mode",      self._viz_mode_var,   "set"),
            ("plotly_mode",   self._plotly_mode_var,"set"),
            ("cluster_algorithm", self._cluster_alg_var, "set"),
            ("cluster_resolution", self._cluster_res_var, "set"),
        ]
        for key, var, _ in setters:
            if (v := config.get(key)) is not None:
                var.set(v)

        # Contexto de pesquisa. Fora do laço acima porque não é `StringVar`: ele precisa
        # sobreviver à reconstrução dos widgets. `research_context_do_config` tolera chave
        # ausente (projeto antigo), `None` e tipo errado — um campo de texto opcional nunca
        # pode impedir um `.blicsa` de abrir.
        from core.project import research_context_do_config
        self._research_context = research_context_do_config(config)
        barra = getattr(self, "_research_context_bar", None)
        if barra is not None:
            try:
                if barra.winfo_exists():
                    barra.definir(self._research_context)
            except Exception:
                pass

        # Fase 3: parâmetros do mapa. `from_dict` tolera projeto de versão anterior (sem o
        # bloco) e valores corrompidos — um `.blicsa` antigo nunca pode deixar de abrir.
        from core.map_controls import MapParams
        mp = MapParams.from_dict(config.get("map_params"))
        self._binary_count_var.set(mp.binary_count)
        self._cluster_res_var.set(mp.resolution)
        self._attraction_var.set(mp.attraction)
        self._repulsion_var.set(mp.repulsion)
        self._excluded_terms = set(mp.excluded_terms)
        if hasattr(self, "_excluded_lbl"):
            n = len(self._excluded_terms)
            self._excluded_lbl.configure(text=f"{n} termo(s) excluído(s)" if n else "")

        for key, var in [
            ("max_nodes", self._max_nodes_var),
            ("max_pct",   self._max_pct_var),
            ("year_min",  self._year_min_var),
            ("year_max",  self._year_max_var),
            ("extra_sw",  self._extra_sw_var),
        ]:
            if (v := config.get(key)) is not None:
                var.set(str(v))
                
        # 2. Restore dataset
        self._dataframe = project_data.get("df")
        
        # 3. Restore layout and generator
        self._positions = project_data.get("positions", {})
        self._cluster_labels = project_data.get("cluster_labels", {})
        self._cluster_label_origins = project_data.get("cluster_label_origins", {})
        
        G = project_data.get("G")
        if G is not None:
            self._generator = NetworkGenerator(self._dataframe)
            self._generator.G = G
            self._graph = G
            self._generator.clustering_algorithm = self._cluster_alg_var.get()
            self._generator.clustering_resolution = self._cluster_res_var.get()
        else:
            # Projeto sem mapa salvo: não herdar o mapa do projeto aberto antes (B9).
            self._generator = None
            self._graph = None
            
        self._refresh_candidate_counts()
        self._update_stats_tab()

    def _get_ai_analyst(self):
        from ai.client import GroqBibliometricAnalyst
        return GroqBibliometricAnalyst(
            api_key=self._api_key_var.get().strip() or None,
            base_url=self._ai_base_url_var.get().strip() or None,
            model=self._ai_model_var.get().strip() or None,
            # Lido AGORA, não guardado: o analista é criado por análise, e o contexto pode
            # ter mudado desde a última.
            contexto_pesquisa=self._contexto_pesquisa(),
        )

    def _agendar_gravacao_config_ia(self):
        """Persiste provedor, URL base e modelo com o mesmo debounce da chave.

        Debounce porque a trace dispara a CADA TECLA nos campos de texto dos Ajustes:
        gravar o settings.json por caractere é uma escrita de disco por tecla.
        """
        if self._config_ia_sincronizando:
            return
        if self._config_ia_save_job:
            self.after_cancel(self._config_ia_save_job)

        def _gravar():
            from core.settings import set_config_ia
            set_config_ia(self._ai_provider_var.get(),
                          self._ai_base_url_var.get(),
                          self._ai_model_var.get())

        self._config_ia_save_job = self.after(900, _gravar)

    def _on_ai_provider_change(self, provider):
        """Troca de provedor: preset da tabela única, gravação em disco e a chave DELE.

        Os presets estavam copiados em três lugares — aqui, em `core.credenciais.
        PROVEDORES_IA` e nos defaults do `ai/client.py`. Três cópias da mesma tabela é como
        o provedor passa a dizer "openai" com a URL base ainda apontando para o Groq.

        A resincronização da chave fecha o ciclo dos slots por provedor: cada um tem o seu
        no cofre, e `_api_key_var` — que alimenta as sete chamadas de IA — precisa passar a
        apontar para o do provedor recém-escolhido.
        """
        from core.credenciais import PROVEDORES_IA
        from core.settings import set_config_ia

        entrada = PROVEDORES_IA.get(provider)
        if entrada is not None:
            self._ai_base_url_var.set(entrada[1])
            self._ai_model_var.set(entrada[2])
        # "custom" não tem preset: preserva o que estiver nos campos e grava só o provedor.
        set_config_ia(provider, self._ai_base_url_var.get(), self._ai_model_var.get())
        self._sincronizar_chave_da_sessao()
        vista = getattr(self, "_credenciais_view", None)
        if vista is not None:
            try:
                vista.atualizar()
            except Exception:
                pass

    # ── Tab: Estatísticas ──────────────────────────────────────────────
    # ── Deduplication ──────────────────────────────────────────────────
    def _run_dedup(self):
        """Ação explícita do Corpus: encontra pares e mostra o resumo REVISÁVEL
        (por motivo + amostra) antes de aplicar qualquer remoção."""
        if self._dataframe is None or self._dataframe.empty:
            messagebox.showwarning("Sem dados", "Carregue um corpus primeiro.")
            return
        log.info("[Dedup] Procurando duplicatas…")
        # Em corpus grande leva 1–2 s: avisar ANTES, senão parece travado (T3).
        self._set_busy("Procurando duplicatas…")
        try:
            self.update_idletasks()
        except Exception:
            pass
        df    = self._dataframe
        try:
            dupes = find_duplicates(df, title_threshold=0.93)
        finally:
            self._set_idle("")
        if not dupes:
            messagebox.showinfo("Blicsa", t("dedup.none"))
            log.info("[Dedup] Nenhuma duplicata.\n")
            return
        log.info(f"[Dedup] {len(dupes)} par(es) encontrado(s).\n")

        def on_cancel(pares=len(dupes)):
            from collections import Counter
            by = Counter(classify_dedup_reason(r) for _, _, r in dupes)
            self._backlog("dedup", {"pares": pares, "por_doi": by.get("doi", 0),
                                    "por_titulo": by.get("title", 0),
                                    "por_autor_ano": by.get("author_year", 0),
                                    "aplicado": False})
        DedupPreviewDialog(self, df, dupes, self._apply_dedup, on_cancel=on_cancel)

    def _apply_dedup(self, dupes: list, desmarcados: int = 0):
        """Aplica a remoção só dos pares MARCADOS e informa o resultado por motivo.
        `desmarcados` = pares que o usuário deixou desmarcados (não removidos)."""
        if not dupes:
            if desmarcados:
                # Tudo desmarcado: registra a revisão sem remoção.
                self._backlog("dedup", {"pares": 0, "desmarcados": int(desmarcados),
                                        "aplicado": True})
                log.info(f"[Dedup] Nada removido ({desmarcados} par(es) desmarcado(s)).\n")
            return
        to_remove = {ri for _, ri, _ in dupes}
        from collections import Counter
        by = Counter(classify_dedup_reason(r) for _, _, r in dupes)
        before = len(self._dataframe)
        self._dataframe = (
            self._dataframe
            .drop(index=list(to_remove))
            .reset_index(drop=True)
        )
        removed = before - len(self._dataframe)
        self._refresh_candidate_counts()        # contagens e selo do corpus ficavam desatualizados
        msg = t("dedup.removed", k=removed, x=by.get("doi", 0),
                y=by.get("title", 0), z=by.get("author_year", 0))
        self._last_dedup_msg = msg
        self._backlog("dedup", {"pares": len(dupes), "por_doi": by.get("doi", 0),
                                "por_titulo": by.get("title", 0),
                                "por_autor_ano": by.get("author_year", 0),
                                "desmarcados": int(desmarcados),
                                "aplicado": True})
        log.info(f"[Dedup] {msg} Base: {len(self._dataframe)} registros.\n")
        self._generator = None
        self._graph = None
        self._positions = {}
        self.after(0, self._update_stats_tab)
        self.after(0, self._refresh_corpus_tab)
        messagebox.showinfo("Blicsa", msg)

    # ── Word Cloud ─────────────────────────────────────────────────────
    def _show_wordcloud(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return
        try:
            from wordcloud import WordCloud
        except ImportError:
            messagebox.showerror("Dependência", "Instale: pip install wordcloud")
            return

        self._set_busy("Gerando Nuvem de Palavras…")
        _ThreadDaTela(target=self._wordcloud_worker, daemon=True).start()

    def _wordcloud_worker(self):
        try:
            import re
            from wordcloud import WordCloud
            
            field = self._field_var.get() if hasattr(self, "_field_var") else "keywords"
            col   = {"keywords": "keywords", "titles": "title",
                     "abstracts": "abstract", "titles_abstracts": "abstract"}.get(field, "keywords")

            if self._candidate_counts:
                freq = dict(self._candidate_counts)
            else:
                from collections import Counter as _C
                sep_re = re.compile(r"[;,]")
                words: list[str] = []
                for s in self._dataframe[col].dropna():
                    words.extend(w.strip().lower() for w in sep_re.split(str(s)) if len(w.strip()) > 2)
                freq = dict(_C(words).most_common(200))

            if not freq:
                self.after(0, self._set_idle, "Pronto")
                self.after(0, lambda: messagebox.showinfo("Word Cloud", "Nenhum termo encontrado."))
                return

            wc = WordCloud(
                width=1000, height=600,
                background_color="#0d0d1f",
                colormap="plasma",
                max_words=150,
                prefer_horizontal=0.85,
                min_font_size=8,
                max_font_size=90,
                collocations=False,
            ).generate_from_frequencies(freq)

            self.after(0, self._display_wordcloud, wc)
        except Exception as exc:
            self.after(0, self._set_idle, "Erro Nuvem")
            self.after(0, lambda e=exc: messagebox.showerror("Erro", f"Erro ao gerar nuvem de palavras:\n{e}"))

    def _display_wordcloud(self, wc):
        self._set_idle("Nuvem gerada")
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            win = ctk.CTkToplevel(self)
            win.title("Blicsa — Nuvem de Palavras")
            win.geometry("1020x640")
            win.configure(fg_color="#0d0d1f")
            win.grid_rowconfigure(0, weight=1)
            win.grid_columnconfigure(0, weight=1)

            fig, ax = plt.subplots(figsize=(10, 6), dpi=110, facecolor="#0d0d1f")
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            fig.tight_layout(pad=0)

            cv = FigureCanvasTkAgg(fig, master=win)
            cv.get_tk_widget().grid(row=0, column=0, sticky="nsew")

            def _save():
                path = filedialog.asksaveasfilename(
                    defaultextension=".png", filetypes=[("PNG", "*.png"), ("SVG", "*.svg")])
                if path:
                    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="#0d0d1f")
                    log.info(f"[Word Cloud] Salva → {path}\n")

            ctk.CTkButton(
                win, text="Salvar", height=34,
                fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#000",
                command=_save,
            ).grid(row=1, column=0, pady=8)
            cv.draw()
            win.lift()
            win.focus()
        except Exception as exc:
            messagebox.showerror("Erro de Exibição", str(exc))

    # ── Trend chart ────────────────────────────────────────────────────
    def _open_trends(self):
        if self._dataframe is None:
            messagebox.showwarning("Sem dados", "Carregue um arquivo primeiro.")
            return
        counts = Counter(self._candidate_counts)
        if not counts and self._generator:
            counts = Counter({
                n: d.get("occurrence", 1)
                for n, d in self._generator.G.nodes(data=True)
            })
        if not counts:
            messagebox.showwarning(
                "Sem termos",
                "Carregue dados e gere o mapa (ou os candidatos) antes de abrir as Tendências.",
            )
            return
        field_map = {
            "keywords":         "keywords",
            "titles":           "title",
            "abstracts":        "abstract",
            "titles_abstracts": "abstract",
        }
        field = field_map.get(self._field_var.get(), "keywords")
        win = TrendChartWindow(
            self, self._dataframe, counts,
            field=field, thesaurus=self._thesaurus,
        )
        win.lift()
        win.focus()

    # ── Cluster auto-labeling ───────────────────────────────────────────
    def _auto_label_clusters(self):
        if self._generator is None:
            messagebox.showwarning("Sem mapa", "Gere o mapa primeiro.")
            return
        _ThreadDaTela(target=self._label_clusters_worker, daemon=True).start()

    def _label_clusters_worker(self):
        try:
            self.after(0, self._set_busy, "IA nomeando clusters…")
            log.info("[IA] Nomeando clusters com IA...")
            report = self._generator.get_cluster_report()
            # `interpreta`: o rótulo que sai daqui vira o nome do cluster NA FIGURA que o
            # artigo publica. `n_clusters` no evento porque é quantos nomes do mapa foram
            # escritos por um modelo — o número que a declaração de uso precisa dizer.
            labels = self._analise_de_ia(
                "rotulos_de_cluster",
                lambda a: a.label_clusters(report, context=self._field_var.get()))
            self._cluster_labels = labels
            self._cluster_label_origins = {cid: "ia" for cid in labels}

            self.after(0, self._set_idle, f"{len(labels)} clusters nomeados")
            log.info(f"[IA] {len(labels)} clusters nomeados.\n")
        except Exception as exc:
            self.after(0, self._set_idle, "Erro ao nomear clusters")
            log.info(f"[ERRO labeling] {exc}\n")
            if isinstance(exc, AIClientError):
                import threading
                self.after(0, lambda e=exc: self._show_ai_error_dialog(
                    str(e), retry_cb=lambda: _ThreadDaTela(target=self._label_clusters_worker, daemon=True).start()))
            else:
                self.after(0, lambda e=exc: messagebox.showerror("Erro IA", f"Erro ao nomear clusters com IA:\n{e}"))

    # ── Config save / load ─────────────────────────────────────────────
    def _save_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Salvar configuração",
        )
        if not path:
            return
        import json
        config = {
            "map_type":     self._map_type_var.get(),
            "field":        self._field_var.get(),
            "counting":     self._counting_var.get(),
            "assoc_strength": self._assoc_var.get(),
            "min_occ":      self._min_occ_var.get(),
            "max_nodes":    self._max_nodes_var.get(),
            "max_pct":      self._max_pct_var.get(),
            "fa2_iter":     self._fa2_iter_var.get(),
            "linlog":       self._linlog_var.get(),
            "viz_mode":     self._viz_mode_var.get(),
            "plotly_mode":  self._plotly_mode_var.get(),
            "year_min":     self._year_min_var.get(),
            "year_max":     self._year_max_var.get(),
            "extra_sw":     self._extra_sw_var.get(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        log.info(f"[Config] Salvo → {path}\n")

    def _load_config(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Carregar configuração",
        )
        if not path:
            return
        import json
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        setters: list[tuple] = [
            ("map_type",      self._map_type_var,  "set"),
            ("field",         self._field_var,      "set"),
            ("counting",      self._counting_var,   "set"),
            ("assoc_strength",self._assoc_var,      "set"),
            ("min_occ",       self._min_occ_var,    "set"),
            ("fa2_iter",      self._fa2_iter_var,   "set"),
            ("linlog",        self._linlog_var,      "set"),
            ("viz_mode",      self._viz_mode_var,   "set"),
            ("plotly_mode",   self._plotly_mode_var,"set"),
        ]
        for key, var, _ in setters:
            if (v := config.get(key)) is not None:
                var.set(v)
        for key, var in [
            ("max_nodes", self._max_nodes_var),
            ("max_pct",   self._max_pct_var),
            ("year_min",  self._year_min_var),
            ("year_max",  self._year_max_var),
            ("extra_sw",  self._extra_sw_var),
        ]:
            if (v := config.get(key)) is not None:
                var.set(str(v))
        self._update_thresh_label()
        log.info(f"[Config] Carregado ← {path}\n")

    def _build_tab_stats(self) -> ctk.CTkFrame:
        frame = self._tab()
        frame.grid_rowconfigure(1, weight=1)
        self._h1(frame, "Estatísticas da Base", 0)

        card = self._card(frame, 1)
        card.grid_rowconfigure(0, weight=1)
        self._stats_box = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Courier", size=12),
            fg_color=CARD2_BG,
        )
        self._stats_box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self._stats_box.insert(
            "end",
            "Carregue um arquivo para ver as estatísticas da base.\n",
        )
        self._stats_box.configure(state="disabled")
        return frame

    def _update_stats_tab(self):
        """Atualiza a aba Estatísticas sem congelar a janela.

        O texto inclui a evolução temporal (uma rede por período), diâmetro e caminho médio:
        num corpus de qualificação isso levava ~5 s, e rodava na thread da tela a cada projeto
        aberto e a cada importação — a janela ficava sem responder (auditoria 2026-09, T1).
        Agora o cálculo roda em segundo plano e só a escrita do texto volta para a tela. O
        conteúdo é o mesmo de antes.
        """
        if self._dataframe is None:
            return
        if not hasattr(self, "after"):          # uso direto (testes): síncrono, como antes
            BlicsaApp._escrever_estatisticas(self, BlicsaApp._compor_estatisticas(self))
            return
        # Só calcula quando a aba Estatísticas está (ou for) aberta. Ao abrir um projeto de
        # qualificação o cálculo recriava 7 redes (uma com 63 mil arestas) e, mesmo em segundo
        # plano, disputava o processador com a tela por ~5 s (T1).
        self._stats_pendente = True
        if getattr(self, "_current_tab_key", None) == "stats":
            self._calcular_estatisticas()

    def _calcular_estatisticas(self):
        if self._dataframe is None:
            return
        self._stats_pendente = False
        self._stats_geracao = getattr(self, "_stats_geracao", 0) + 1
        geracao = self._stats_geracao
        campo = self._field_var.get() if hasattr(self, "_field_var") else "keywords"

        def worker():
            try:
                linhas = self._compor_estatisticas(campo)
            except Exception as exc:
                log.info(f"[Estatísticas] falhou: {type(exc).__name__}: {exc}")
                return
            if geracao == getattr(self, "_stats_geracao", geracao):   # descarta resultado velho
                try:
                    self.after(0, self._escrever_estatisticas, linhas)
                except RuntimeError:
                    pass
        _ThreadDaTela(target=worker, name="stats_worker", daemon=True).start()

    def _escrever_estatisticas(self, lines):
        if lines is None:
            return
        self._stats_box.configure(state="normal")
        self._stats_box.delete("1.0", "end")
        self._stats_box.insert("end", "\n".join(lines))
        self._stats_box.configure(state="disabled")

    def _compor_estatisticas(self, campo: str | None = None) -> list[str] | None:
        if self._dataframe is None:
            return None
        df = self._dataframe
        lines: list[str] = []

        lines.append("═" * 60)
        lines.append("  ESTATÍSTICAS DESCRITIVAS DA BASE")
        lines.append("═" * 60)
        lines.append(f"  Total de registros : {len(df)}")

        from core.document_types import document_type_counts
        type_counts = document_type_counts(df)
        if type_counts:
            lines.extend(("", "─" * 60, f"  {t('stats.types_header')}", "─" * 60))
            journal_total = type_counts.get("article", 0) + type_counts.get("review", 0)
            if journal_total:
                lines.append(f"  {t('stats.journal_total', n=journal_total)}")
            for kind, count in type_counts.items():
                label = t(f"stats.type.{kind}")
                lines.append(f"  {label:<38} {count:>6}  ({count / len(df):.1%})")
            lines.append("")

        if "year" in df.columns:
            yr = df["year"].replace(0, None).dropna()
            if not yr.empty:
                lines.append(f"  Período             : {int(yr.min())} – {int(yr.max())}")
                lines.append(f"  Mediana (ano)       : {int(yr.median())}")

        if "citations" in df.columns:
            cit = df["citations"].dropna()
            if not cit.empty:
                lines.append(f"  Citações totais     : {int(cit.sum())}")
                lines.append(f"  Média de citações   : {cit.mean():.1f}")
                lines.append(f"  Máx. citações       : {int(cit.max())}")

        if "source" in df.columns:
            lines.append("")
            lines.append("─" * 60)
            lines.append("  TOP 15 FONTES / PERIÓDICOS")
            lines.append("─" * 60)
            top_sources = Counter(df["source"].dropna()).most_common(15)
            for i, (src, n) in enumerate(top_sources, 1):
                source_label = str(src).strip() or t("stats.source_unknown")
                lines.append(f"  {i:>2}. {source_label[:48]:<48} {n:>5}")

        if "year" in df.columns:
            lines.append("")
            lines.append("─" * 60)
            lines.append("  DISTRIBUIÇÃO POR ANO")
            lines.append("─" * 60)
            yr = df["year"].replace(0, None).dropna().astype(int)
            year_counts = Counter(yr)
            
            # Calculate Compound Annual Growth Rate (CAGR)
            years = sorted(year_counts.keys())
            if len(years) > 1:
                y_start, y_end = years[0], years[-1]
                n_start, n_end = year_counts[y_start], year_counts[y_end]
                span = y_end - y_start
                if span > 0 and n_start > 0 and n_end > 0:
                    cagr = (n_end / n_start) ** (1 / span) - 1
                    lines.append(f"  Produção Inicial ({y_start}): {n_start} artigos")
                    lines.append(f"  Produção Final ({y_end}): {n_end} artigos")
                    lines.append(f"  Taxa de Crescimento Anual (CAGR): {cagr:.1%}")
                    lines.append("─" * 60)

            max_count = max(year_counts.values(), default=1)
            for year in sorted(year_counts):
                count = year_counts[year]
                bar = "█" * int(count / max_count * 30)
                lines.append(f"  {year}  {bar:<30} {count}")

        if "keywords" in df.columns:
            lines.append("")
            lines.append("─" * 60)
            lines.append("  TOP 20 PALAVRAS-CHAVE")
            lines.append("─" * 60)
            all_kws: list[str] = []
            for kw_str in df["keywords"].dropna():
                if isinstance(kw_str, str):
                    sep = ";" if ";" in kw_str else ","
                    all_kws.extend(k.strip().lower() for k in kw_str.split(sep) if k.strip())
            for i, (kw, n) in enumerate(Counter(all_kws).most_common(20), 1):
                lines.append(f"  {i:>2}. {kw:<46} {n:>5}")

        # ── Lei de Bradford ────────────────────────────────────────────────
        if "source" in df.columns:
            src_counts = Counter(df["source"].dropna()).most_common()
            total_arts = sum(n for _, n in src_counts)
            if total_arts > 0:
                lines.append("")
                lines.append("─" * 60)
                lines.append("  LEI DE BRADFORD — Dispersão por Zonas")
                lines.append("─" * 60)
                third = total_arts / 3
                cumsum = zone = zone_src = 0
                zone_data: list[tuple[int,int,int]] = []
                for _, count in src_counts:
                    cumsum += count
                    zone_src += 1
                    if cumsum >= third * (zone + 1) or zone_src == len(src_counts):
                        zone += 1
                        zone_data.append((zone, zone_src, int(cumsum)))
                        zone_src = 0
                        if zone >= 3:
                            break
                for z, nsrc, nart in zone_data:
                    lines.append(f"  Zona {z}  {nsrc:>5} fontes   {nart:>6} artigos")
                if len(zone_data) >= 2:
                    k = zone_data[1][1] / max(zone_data[0][1], 1)
                    lines.append(f"  Multiplicador k ≈ {k:.1f}")

        # ── Lei de Lotka ───────────────────────────────────────────────
        if "authors" in df.columns:
            auth_pub: Counter = Counter()
            for raw in df["authors"].dropna():
                sep = ";" if ";" in str(raw) else ","
                for a in str(raw).split(sep):
                    if a.strip():
                        auth_pub[a.strip()] += 1
            if auth_pub:
                pub_dist = Counter(auth_pub.values())
                n1 = pub_dist.get(1, 0)
                lines.append("")
                lines.append("─" * 60)
                lines.append("  LEI DE LOTKA — Produtividade de Autores")
                lines.append("─" * 60)
                lines.append(f"  Total de autores únicos : {len(auth_pub)}")
                lines.append(f"  Autores com 1 artigo    : {n1} "
                             f"({100*n1/len(auth_pub):.1f}%)")
                lines.append(f"  {'Artigos':>8}  {'Autores (real)':>14}  {'Lotka C/n²':>12}")
                lines.append("  " + "─" * 38)
                c = n1
                for np_ in sorted(pub_dist)[:8]:
                    real = pub_dist[np_]
                    lotka = round(c / (np_ ** 2))
                    lines.append(f"  {np_:>8}  {real:>14}  {lotka:>12}")

        # ── Métricas de rede ───────────────────────────────────────────
        # ── Citation burst ─────────────────────────────────────────────
        if "keywords" in df.columns and "year" in df.columns:
            yr_series = df["year"].replace(0, None).dropna().astype(int)
            if not yr_series.empty:
                yr_max = int(yr_series.max())
                recent_cut = yr_max - 2   # last 3 years
                early_cut  = yr_max - 7   # 3-year window before that
                bursts: list[tuple[str, float]] = []
                kw_counter_recent: Counter = Counter()
                kw_counter_early:  Counter = Counter()
                for _, row in df.iterrows():
                    yr  = int(row.get("year", 0) or 0)
                    kws = str(row.get("keywords", "") or "")
                    if not kws or not yr:
                        continue
                    sep = ";" if ";" in kws else ","
                    terms = [k.strip().lower() for k in kws.split(sep) if k.strip()]
                    if yr >= recent_cut:
                        kw_counter_recent.update(terms)
                    elif yr >= early_cut:
                        kw_counter_early.update(terms)
                for term, recent_n in kw_counter_recent.items():
                    if recent_n < 2:
                        continue
                    early_n = kw_counter_early.get(term, 0)
                    ratio = recent_n / (early_n + 0.5)
                    bursts.append((term, ratio))
                bursts.sort(key=lambda x: x[1], reverse=True)
                if bursts:
                    lines.append("")
                    lines.append("─" * 60)
                    lines.append(f"  TERMOS EM ASCENSÃO (burst {recent_cut}–{yr_max} vs {early_cut}–{recent_cut-1})")
                    lines.append("─" * 60)
                    for term, ratio in bursts[:15]:
                        bar = "▲" * min(int(ratio), 12)
                        lines.append(f"  {term:<36} {bar} ×{ratio:.1f}")

        if self._generator is not None and self._generator.G.number_of_nodes() > 0:
            try:
                G = self._generator.G
                lines.append("")
                lines.append("─" * 60)
                lines.append("  MÉTRICAS DA REDE")
                lines.append("─" * 60)
                lines.append(f"  Nós               : {G.number_of_nodes()}")
                lines.append(f"  Arestas           : {G.number_of_edges()}")
                lines.append(f"  Densidade         : {nx.density(G):.4f}")
                lines.append(f"  Coef. clustering  : {nx.average_clustering(G, weight='weight'):.4f}")
                comps = list(nx.connected_components(G))
                lines.append(f"  Componentes       : {len(comps)}")
                sg = G.subgraph(max(comps, key=len))
                if sg.number_of_nodes() > 1:
                    lines.append(f"  Diâmetro (maior comp.) : {nx.diameter(sg)}")
                    lines.append(f"  Caminho médio          : {nx.average_shortest_path_length(sg):.3f}")
                # Degree stats
                degs = [d for _, d in G.degree(weight="weight")]
                lines.append(f"  Grau médio        : {sum(degs)/len(degs):.2f}")
                lines.append(f"  Grau máximo       : {max(degs):.2f}  "
                             f"({max(G.degree(weight='weight'), key=lambda x: x[1])[0]})")
            except Exception:
                pass

        if self._generator is not None:
            try:
                field = campo or (self._field_var.get() if hasattr(self, "_field_var")
                                  else "keywords")
                evolution = self._generator.get_temporal_evolution(
                    period_size=5, field=field,
                    min_occurrence=2, thesaurus=getattr(self, "_thesaurus", None),
                )
                if evolution:
                    lines.append("")
                    lines.append("─" * 60)
                    lines.append("  EVOLUÇÃO TEMPORAL DA REDE (períodos de 5 anos)")
                    lines.append("─" * 60)
                    lines.append(f"  {'Período':<14}{'Artigos':>7}{'Nós':>6}{'Arestas':>8}{'Clusters':>10}")
                    lines.append("  " + "─" * 46)
                    for ev in evolution:
                        lines.append(
                            f"  {ev['period']:<14}{ev['papers']:>7}{ev['nodes']:>6}"
                            f"{ev['edges']:>8}{ev['clusters']:>10}"
                        )
                        if ev.get("top_terms"):
                            lines.append(f"    Termos: {', '.join(ev['top_terms'][:5])}")
            except Exception:
                pass

        lines.append("")
        lines.append("═" * 60)

        return lines
    def _build_tab_analises(self) -> ctk.CTkFrame:
        f = self._tab()
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(0, weight=1)
        
        main_content = ctk.CTkFrame(f, fg_color="transparent")
        main_content.grid(row=0, column=0, sticky="nsew")
        main_content.grid_rowconfigure(1, weight=1)
        
        self._tv_analises = ctk.CTkTabview(main_content, fg_color=CONTENT_BG, text_color=INK, segmented_button_selected_color=RED, segmented_button_selected_hover_color=RED_HOVER, segmented_button_unselected_color=PAPER, segmented_button_unselected_hover_color="#e0e0e0")
        self._tv_analises.pack(fill="both", expand=True, padx=20, pady=20)
        
        tab_mapa = self._tv_analises.add("Mapa")
        tab_rankings = self._tv_analises.add("Rankings")
        
        viz_f = self._build_tab_viz(parent=tab_mapa)
        viz_f.pack(in_=tab_mapa, fill="both", expand=True)
        
        rank_f = self._build_tab_ranking(parent=tab_rankings)
        rank_f.pack(in_=tab_rankings, fill="both", expand=True)
        
        return f

    def _build_tab_gallery(self) -> ctk.CTkFrame:
        f = self._tab()
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(0, weight=1)
        
        main_content = ctk.CTkFrame(f, fg_color="transparent")
        main_content.grid(row=0, column=0, sticky="nsew")
        main_content.grid_rowconfigure(1, weight=1)
        main_content.grid_columnconfigure(0, weight=1)
        
        # Header
        hdr = ctk.CTkFrame(main_content, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(hdr, text="Galeria de Mapas", font=ctk.CTkFont(size=24, weight="bold"), text_color=INK).pack(side="left")
        ctk.CTkButton(hdr, text="Atualizar", width=100, height=32, fg_color=CARD_BG, hover_color=CARD2_BG, text_color=INK, border_width=1, border_color=INK, command=self._refresh_gallery).pack(side="right")
        
        # Grid/List of maps
        self._gallery_scroll = ctk.CTkScrollableFrame(main_content, fg_color=CONTENT_BG)
        self._gallery_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
        # IA Drawer for Gallery
        self._gallery_drawer = ctk.CTkFrame(f, fg_color=WHITE_CARD, width=300, corner_radius=0, border_width=1, border_color=INK)
        self._gallery_drawer.grid_propagate(False)
        self._gallery_drawer.grid_rowconfigure(1, weight=1)
        self._gallery_drawer.grid_columnconfigure(0, weight=1)
        
        header = ctk.CTkFrame(self._gallery_drawer, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(header, text="Blink", font=ctk.CTkFont(size=16, weight="bold"), text_color=INK).pack(side="left")
        
        self._gallery_chat_history = ctk.CTkTextbox(self._gallery_drawer, wrap="word", font=ctk.CTkFont(size=13), fg_color=PAPER, text_color=INK, border_width=1, border_color=INK, corner_radius=0)
        self._gallery_chat_history.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        from core.markdown_parser import configure_markdown_tags, insert_markdown
        configure_markdown_tags(self._gallery_chat_history)
        insert_markdown(self._gallery_chat_history, "**Blink:** Selecione um mapa na galeria e pergunte-me sobre ele!\n\n")
        self._gallery_chat_history.configure(state="disabled")
        
        input_f = ctk.CTkFrame(self._gallery_drawer, fg_color="transparent")
        input_f.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        input_f.grid_columnconfigure(0, weight=1)
        
        self._gallery_chat_input = ctk.CTkEntry(input_f, placeholder_text="Sua pergunta...", placeholder_text_color=MUTED, font=ctk.CTkFont(size=13), fg_color=WHITE_CARD, text_color=INK, height=36, corner_radius=0, border_width=1, border_color=INK)
        self._gallery_chat_input.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        def send_chat(e=None):
            msg = self._gallery_chat_input.get().strip()
            if not msg: return
            self._gallery_chat_input.delete(0, "end")
            self._gallery_chat_history.configure(state="normal")
            insert_markdown(self._gallery_chat_history, f"**Você:** {msg}\n")
            self._gallery_chat_history.see("end")
            self._gallery_chat_history.configure(state="disabled")
            
            # Remontado a cada turno, e não só na primeira mensagem: o chat da galeria é
            # persistente entre visitas à aba, e um contexto escrito depois da primeira
            # pergunta nunca chegaria ao modelo se o system fosse congelado ali.
            from core.i18n import get_lang
            from core.research_context import diretiva_idioma, montar_system_prompt
            system = montar_system_prompt(
                papel=("Você é o 'Blink', um assistente focado em analisar mapas "
                       "bibliométricos na galeria. Use markdown."),
                idioma=diretiva_idioma(get_lang()),
                contexto_usuario=self._contexto_pesquisa(),
                cabecalho_contexto=t("ai.contexto_prompt"))
            if not hasattr(self, '_gallery_messages') or not self._gallery_messages:
                self._gallery_messages = [{"role": "system", "content": system}]
            else:
                self._gallery_messages[0] = {"role": "system", "content": system}

            self._gallery_messages.append({"role": "user", "content": msg})
            
            import threading
            def worker():
                try:
                    resp = self._analise_de_ia(
                        "chat_da_galeria",
                        lambda a: a.chat_history(self._gallery_messages, temperature=0.7))
                    self._gallery_messages.append({"role": "assistant", "content": resp})
                except Exception as ex:
                    resp = f"Erro: {ex}"
                def update_ui():
                    self._gallery_chat_history.configure(state="normal")
                    insert_markdown(self._gallery_chat_history, f"**Blink:**\n{resp}\n")
                    self._gallery_chat_history.see("end")
                    self._gallery_chat_history.configure(state="disabled")
                self.after(0, update_ui)
            _ThreadDaTela(target=worker, daemon=True).start()
            
        self._gallery_chat_input.bind("<Return>", send_chat)
        ctk.CTkButton(input_f, text="➤", width=36, height=36, fg_color=RED, hover_color=RED_HOVER, corner_radius=0, command=send_chat).grid(row=0, column=1)
        
        # Default show drawer
        self._gallery_drawer.grid(row=0, column=1, sticky="ns")
        
        self.after(500, self._refresh_gallery)
        
        return f

    def _refresh_gallery(self):
        if not hasattr(self, '_gallery_scroll'): return
        
        # Clear existing
        for w in self._gallery_scroll.winfo_children():
            w.destroy()
            
        from pathlib import Path
        import os, time
        
        reports_dir = REPORTS_DIR
        if not reports_dir.exists(): return
        
        files = list(reports_dir.glob("*.html"))
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        if not files:
            ctk.CTkLabel(self._gallery_scroll, text="Nenhum mapa salvo ainda.", font=ctk.CTkFont(size=14, slant="italic"), text_color=MUTED).pack(pady=40)
            return
            
        for idx, fpath in enumerate(files):
            mtime = os.path.getmtime(fpath)
            date_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(mtime))
            name = fpath.stem.replace("blicsa_", "").replace("_", " ").title()
            
            card = ctk.CTkFrame(self._gallery_scroll, fg_color=CARD_BG, border_width=1, border_color=INK, corner_radius=4)
            card.pack(fill="x", padx=10, pady=5)
            
            info_f = ctk.CTkFrame(card, fg_color="transparent")
            info_f.pack(side="left", padx=15, pady=15, fill="x", expand=True)
            
            ctk.CTkLabel(info_f, text=f"{name}", font=ctk.CTkFont(size=14, weight="bold"), text_color=INK, anchor="w").pack(fill="x")
            ctk.CTkLabel(info_f, text=f"Salvo em: {date_str}", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, anchor="w").pack(fill="x")
            
            btn_f = ctk.CTkFrame(card, fg_color="transparent")
            btn_f.pack(side="right", padx=15, pady=15)
            
            def open_map(p=fpath, n=name):
                # Copia o mapa da galeria para o diretório SERVIDO antes de abrir.
                import urllib.parse, shutil
                shutil.copy2(p, self._serve_dir / "gallery" / p.name)
                url = f"http://127.0.0.1:{self._local_server_port}/gallery/{urllib.parse.quote(p.name)}"
                import webbrowser
                webbrowser.open(url)
                
            def delete_map(p=fpath):
                import os
                if messagebox.askyesno("Excluir", "Deseja excluir este mapa salvo?"):
                    try:
                        os.remove(p)
                        self._refresh_gallery()
                    except Exception as e:
                        messagebox.showerror("Erro", str(e))
                        
            ctk.CTkButton(btn_f, text="Abrir", width=80, height=28, fg_color=BLUE, hover_color="#103050", command=open_map).pack(side="left", padx=5)
            ctk.CTkButton(btn_f, text="Excluir", width=80, height=28, fg_color=RED, hover_color=RED_HOV, command=delete_map).pack(side="left", padx=5)


    
    def _download_oa_pdfs(self):
        """Janela "Baixar PDFs de acesso aberto" (lógica em core/pdf_download.py).

        O botão antigo só olhava registros marcados como acesso aberto (corpus do Scopus e
        do WoS nunca têm essa marca), gravava a página do editor como `.pdf` contando como
        sucesso, não deixava escolher a pasta nem cancelar.
        """
        if self._dataframe is None or self._dataframe.empty:
            messagebox.showinfo(t("pdfs.titulo"), t("pdfs.sem_corpus"))
            return
        if getattr(self, "_pdf_janela", None) is not None and self._pdf_janela.winfo_exists():
            self._pdf_janela.focus()
            return
        from core import pdf_download as PD

        registros = self._dataframe.to_dict("records")
        import time as _tempo
        slug = getattr(self, "_active_project", None) or _tempo.strftime("corpus-%Y-%m-%d")
        pasta = {"v": os.path.join(os.path.expanduser("~"), "Blicsa", "pdfs", str(slug))}

        dlg = ctk.CTkToplevel(self)
        self._pdf_janela = dlg
        dlg.title(t("pdfs.titulo"))
        dlg.geometry("560x420")
        dlg.configure(fg_color=PAPER)
        self._janela_secundaria(dlg)

        ctk.CTkLabel(dlg, text=t("pdfs.titulo"), font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=INK).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(dlg, text=t("pdfs.explicacao", n=len(registros)), wraplength=510,
                     justify="left", text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(anchor="w", padx=24, pady=(0, 12))

        linha = ctk.CTkFrame(dlg, fg_color="transparent")
        linha.pack(fill="x", padx=24, pady=(0, 10))
        lbl_pasta = ctk.CTkLabel(linha, text=pasta["v"], anchor="w", justify="left",
                                 wraplength=380, text_color=INK, font=ctk.CTkFont(size=12))
        lbl_pasta.pack(side="left", fill="x", expand=True)

        def escolher():
            from tkinter import filedialog
            os.makedirs(os.path.dirname(pasta["v"]), exist_ok=True)
            novo = filedialog.askdirectory(parent=dlg, initialdir=os.path.dirname(pasta["v"]),
                                           title=t("pdfs.escolher_pasta"))
            if novo:
                pasta["v"] = novo
                lbl_pasta.configure(text=novo)
        btn_pasta = ctk.CTkButton(linha, text=t("pdfs.escolher_pasta"), command=escolher,
                                  height=30, corner_radius=0, fg_color=WHITE_CARD,
                                  hover_color=PAPER, text_color=INK, border_width=2,
                                  border_color=INK, font=ctk.CTkFont(size=12, weight="bold"))
        btn_pasta.pack(side="right")

        barra = ctk.CTkProgressBar(dlg, corner_radius=0, progress_color=BLUE, height=10)
        barra.set(0)
        barra.pack(fill="x", padx=24, pady=(6, 8))
        lbl_status = ctk.CTkLabel(dlg, text="", justify="left", anchor="w", wraplength=510,
                                  text_color=INK, font=ctk.CTkFont(size=12))
        lbl_status.pack(fill="x", padx=24)

        botoes = ctk.CTkFrame(dlg, fg_color="transparent")
        botoes.pack(side="bottom", fill="x", padx=24, pady=18)
        cancelar = threading.Event()
        estado = {"rodando": False, "resumo": None}

        def texto_contagem(c, feitos, total):
            return t("pdfs.progresso", feitos=feitos, total=total, baixados=c[PD.BAIXADO],
                     ja=c[PD.JA_EXISTIA], fechados=c[PD.SEM_ACESSO_ABERTO],
                     pagina=c[PD.SO_PAGINA], falhas=c[PD.FALHOU] + c[PD.SEM_IDENTIFICADOR])

        def ao_progresso(feitos, total, resumo):
            c = resumo.contagem()
            def ui():
                if dlg.winfo_exists():
                    barra.set(feitos / max(1, total))
                    lbl_status.configure(text=texto_contagem(c, feitos, total))
            self.after(0, ui)

        def abrir(caminho):
            import subprocess
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", caminho])
                elif os.name == "nt":
                    os.startfile(caminho)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", caminho])
            except Exception as exc:
                messagebox.showerror(t("pdfs.titulo"), str(exc), parent=dlg)

        def terminou(resumo, erro=None):
            estado["rodando"] = False
            if not dlg.winfo_exists():
                return
            btn_iniciar.pack_forget()
            btn_cancelar.pack_forget()
            if erro:
                lbl_status.configure(text=t("pdfs.erro", erro=_mensagem_para_usuario(erro, t("pdfs.erro_generico"))),
                                     text_color=RED)
                return
            c = resumo.contagem()
            barra.set(1)
            txt = texto_contagem(c, resumo.total, resumo.total)
            if c[PD.CANCELADO]:
                txt += "\n" + t("pdfs.cancelado", n=c[PD.CANCELADO])
            txt += "\n\n" + t("pdfs.relatorio_explica")
            lbl_status.configure(text=txt)
            self._btn(botoes, t("pdfs.abrir_pasta"), lambda: abrir(resumo.pasta), height=36,
                      color=BLUE, hover=BLUE_HOV, corner_radius=0).pack(side="left")
            self._btn(botoes, t("pdfs.abrir_relatorio"), lambda: abrir(resumo.relatorio),
                      height=36, color=INK, hover=INK_HOV, corner_radius=0
                      ).pack(side="left", padx=8)
            try:
                self._backlog("pdfs", {"pasta": resumo.pasta, **c})
            except Exception:
                pass
            log.info(f"[PDFs] {txt}\n")

        def iniciar():
            if estado["rodando"]:
                return
            try:
                os.makedirs(pasta["v"], exist_ok=True)
                teste = os.path.join(pasta["v"], ".blicsa_teste_escrita")
                open(teste, "w").close()
                os.remove(teste)
            except OSError as exc:
                messagebox.showerror(t("pdfs.titulo"), t("pdfs.pasta_sem_permissao",
                                     pasta=pasta["v"], erro=exc), parent=dlg)
                return
            estado["rodando"] = True
            btn_iniciar.configure(state="disabled")
            btn_pasta.configure(state="disabled")
            btn_cancelar.pack(side="right")
            lbl_status.configure(text=t("pdfs.procurando"))

            def worker():
                try:
                    resumo = PD.baixar_corpus(registros, pasta["v"], cancelar=cancelar,
                                              ao_progresso=ao_progresso)
                    self.after(0, lambda: terminou(resumo))
                except Exception as exc:
                    log.exception("[PDFs] falha geral")
                    self.after(0, lambda e=exc: terminou(None, e))
            _ThreadDaTela(target=worker, daemon=True, name="pdf_worker").start()

        def cancelar_click():
            cancelar.set()
            btn_cancelar.configure(state="disabled", text=t("pdfs.cancelando"))

        def fechar():
            cancelar.set()
            self._pdf_janela = None
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", fechar)

        btn_iniciar = self._btn(botoes, t("pdfs.iniciar"), iniciar, height=36,
                                corner_radius=0)
        btn_iniciar.pack(side="left")
        btn_cancelar = self._btn(botoes, t("pdfs.cancelar"), cancelar_click, height=36,
                                 color=INK, hover=INK_HOV, corner_radius=0)
        self._pdf_iniciar = iniciar          # usado pelos testes

    # ── Explorar a partir de um artigo ───────────────────────────────────────────────
    def _html_mapa_autocontido(self, G, positions, destino: str) -> str:
        """HTML do mapa Sigma com dados, bibliotecas e textos embutidos (abre sem servidor)."""
        import tempfile
        from core.sigma_exporter import export_sigma_json, inline_graph_data
        from core.i18n import get_map_i18n
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json",
                                         encoding="utf-8") as tmp:
            caminho_json = tmp.name
        try:
            export_sigma_json(G, positions, caminho_json)
            graph_json = open(caminho_json, encoding="utf-8").read()
        finally:
            os.remove(caminho_json)
        assets = OUTPUT_DIR / "assets"
        template = (assets / "map_template.html").read_text(encoding="utf-8")
        map_js = inline_graph_data((assets / "map.js").read_text(encoding="utf-8"), graph_json)
        vendor = (assets / "vendor" / "blicsa-vendor.min.js").read_text(encoding="utf-8")
        i18n_json = json.dumps(get_map_i18n(), ensure_ascii=False)
        template = template.replace('<script src="vendor/blicsa-vendor.min.js"></script>',
                                    f"<script>\n{vendor}\n</script>")
        template = template.replace('<script src="map.js"></script>',
                                    f"<script>\nwindow.BLICSA_I18N = {i18n_json};\n{map_js}\n</script>")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(template)
        return destino

    def _abrir_explorar(self):
        """Janela "Explorar a partir de um artigo" (lógica em core/artigos_conectados.py)."""
        if getattr(self, "_explorar_janela", None) is not None and self._explorar_janela.winfo_exists():
            self._explorar_janela.focus()
            return
        from core import artigos_conectados as AC

        dlg = ctk.CTkToplevel(self)
        self._explorar_janela = dlg
        dlg.title(t("explorar.titulo"))
        dlg.geometry("780x680")
        dlg.configure(fg_color=PAPER)
        self._janela_secundaria(dlg)

        ctk.CTkLabel(dlg, text=t("explorar.titulo"), font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=INK).pack(anchor="w", padx=24, pady=(18, 4))
        ctk.CTkLabel(dlg, text=t("explorar.explicacao"), wraplength=730, justify="left",
                     text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
        entrada = ctk.CTkTextbox(dlg, height=64, corner_radius=0, fg_color=WHITE_CARD,
                                 text_color=INK, border_width=2, border_color=INK)
        entrada.pack(fill="x", padx=24, pady=(10, 6))

        linha = ctk.CTkFrame(dlg, fg_color="transparent")
        linha.pack(fill="x", padx=24)
        ctk.CTkLabel(linha, text=t("explorar.quantos"), text_color=INK,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        qtd = ctk.CTkEntry(linha, width=56, corner_radius=0, fg_color=WHITE_CARD, text_color=INK)
        qtd.insert(0, str(AC.N_PADRAO))
        qtd.pack(side="left", padx=(6, 16))
        status = ctk.CTkLabel(dlg, text="", text_color=INK, anchor="w", justify="left",
                              wraplength=730, font=ctk.CTkFont(size=12))
        cancelar = threading.Event()
        estado = {"ex": None, "rodando": False, "marcas": {}}

        resultado = ctk.CTkTabview(dlg, corner_radius=0, fg_color=WHITE_CARD,
                                   segmented_button_selected_color=RED,
                                   segmented_button_selected_hover_color=RED_HOV,
                                   segmented_button_unselected_color=CARD2_BG,
                                   text_color=INK)
        acoes = ctk.CTkFrame(dlg, fg_color="transparent")

        def preencher(ex):
            estado["ex"] = ex
            estado["marcas"] = {}
            for nome in list(resultado._tab_dict.keys()) if hasattr(resultado, "_tab_dict") else []:
                resultado.delete(nome)
            grupos = [
                (t("explorar.aba_grafo", n=len(ex.grafo)),
                 sorted(ex.grafo.nodes, key=lambda i: -ex.semelhanca.get(i, 99 if ex.grafo.nodes[i].get("semente") else 0)),
                 lambda i: t("explorar.semente") if ex.grafo.nodes[i].get("semente") else ""),
                (t("explorar.aba_anteriores", n=len(ex.anteriores)), [i for i, _ in ex.anteriores],
                 lambda i, d=dict(ex.anteriores): t("explorar.citado_por_n", n=d[i])),
                (t("explorar.aba_derivadas", n=len(ex.derivadas)), [i for i, _ in ex.derivadas],
                 lambda i, d=dict(ex.derivadas): t("explorar.cita_n", n=d[i])),
            ]
            for nome, ids, extra in grupos:
                aba = resultado.add(nome)
                lista = ctk.CTkScrollableFrame(aba, corner_radius=0, fg_color=WHITE_CARD)
                lista.pack(fill="both", expand=True)
                for i in ids:
                    w = ex.obras.get(i)
                    if not w:
                        continue
                    var = ctk.BooleanVar(value=False)
                    estado["marcas"][i] = var
                    titulo = str(w.get("title") or w.get("display_name") or "")
                    txt = (f"{AC.rotulo(w)} · {titulo[:90]}"
                           f" · {int(w.get('cited_by_count') or 0)} {t('explorar.citacoes')}")
                    if extra(i):
                        txt += f" · {extra(i)}"
                    ctk.CTkCheckBox(lista, text=txt, variable=var, corner_radius=0,
                                    border_width=2, fg_color=BLUE, hover_color=BLUE_HOV,
                                    text_color=INK, font=ctk.CTkFont(size=12)
                                    ).pack(anchor="w", pady=2, padx=4)
            resultado.pack(fill="both", expand=True, padx=24, pady=(8, 4))
            acoes.pack(fill="x", padx=24, pady=(4, 16))

        def abrir_mapa():
            ex = estado["ex"]
            if not ex:
                return
            from core.visualizer import compute_fa2_layout
            pos = compute_fa2_layout(ex.grafo, iterations=300)
            import time as _time
            destino = str(Path(REPORTS_DIR) / f"blicsa_explorar_{int(_time.time())}.html")
            self._html_mapa_autocontido(ex.grafo, pos, destino)
            try:
                self._record_export("html", destino, action="explorar")
            except Exception:
                pass
            if not getattr(self, "_demo_no_browser", False):
                import webbrowser
                webbrowser.open(Path(destino).as_uri())
            status.configure(text=t("explorar.mapa_salvo", caminho=destino))

        def marcar_todos():
            for v in estado["marcas"].values():
                v.set(True)

        def adicionar():
            ex = estado["ex"]
            ids = [i for i, v in estado["marcas"].items() if v.get()]
            if not ex or not ids:
                messagebox.showinfo(t("explorar.titulo"), t("explorar.nada_marcado"), parent=dlg)
                return
            from core.project import normalize_dataframe
            novos = AC.para_registros(ex, ids)
            ja = set()
            if self._dataframe is not None and not self._dataframe.empty:
                for col in ("doi", "openalex_id"):
                    if col in self._dataframe.columns:
                        ja |= {str(v).lower().replace("https://doi.org/", "").strip()
                               for v in self._dataframe[col].dropna() if str(v).strip()}
            def chave(r):
                return {str(r.get("doi") or "").lower().replace("https://doi.org/", "").strip(),
                        str(r.get("openalex_id") or "").lower().strip()} - {""}
            entram = [r for r in novos if not (chave(r) & ja)]
            repetidos = len(novos) - len(entram)
            if entram:
                df_novo = normalize_dataframe(pd.DataFrame(entram))
                base = self._dataframe if self._dataframe is not None else None
                self._dataframe = (df_novo if base is None or base.empty else
                                   pd.concat([base, df_novo], ignore_index=True))
                self._refresh_candidate_counts()
                try:
                    self._update_stats_tab()
                except Exception:
                    pass
                self._backlog("explorar", {"sementes": ex.sementes, "adicionados": len(entram),
                                           "ja_estavam": repetidos})
            messagebox.showinfo(t("explorar.titulo"), t("explorar.adicionados",
                                n=len(entram), repetidos=repetidos,
                                total=0 if self._dataframe is None else len(self._dataframe)),
                                parent=dlg)

        def terminou(ex=None, erro=None):
            estado["rodando"] = False
            if not dlg.winfo_exists():
                return
            btn_explorar.configure(state="normal")
            btn_cancelar.pack_forget()
            if erro is not None:
                if isinstance(erro, InterruptedError):
                    status.configure(text=t("explorar.cancelado"), text_color=INK)
                elif isinstance(erro, AC.ErroExplorar):
                    status.configure(text=t(f"explorar.erro_{erro}"), text_color=RED)
                else:
                    status.configure(text=t("explorar.erro_rede", erro=_mensagem_para_usuario(
                        erro, t("explorar.erro_generico"))), text_color=RED)
                return
            msg = t("explorar.pronto", n=len(ex.grafo) - len(ex.sementes),
                    sementes=len(ex.sementes), pedidos=ex.pedidos)
            for a in ex.avisos:
                if a.startswith("nao_achados:"):
                    msg += "\n" + t("explorar.nao_achados", lista=a.split(":", 1)[1])
            status.configure(text=msg, text_color=INK)
            preencher(ex)
            log.info(f"[Explorar] {msg}\n")
            self._backlog("explorar", {"sementes": ex.sementes, "nos": len(ex.grafo),
                                       "anteriores": len(ex.anteriores),
                                       "derivadas": len(ex.derivadas)})

        def explorar():
            if estado["rodando"]:
                return
            texto = entrada.get("1.0", "end").strip()
            try:
                n = max(5, min(100, int(qtd.get().strip() or AC.N_PADRAO)))
            except ValueError:
                n = AC.N_PADRAO
            if not AC.interpretar_entrada(texto):
                status.configure(text=t("explorar.erro_sem_entrada"), text_color=RED)
                return
            estado["rodando"] = True
            cancelar.clear()
            btn_explorar.configure(state="disabled")
            btn_cancelar.pack(side="left", padx=8)
            status.configure(text=t("explorar.etapa.sementes"), text_color=INK)

            def progresso(etapa):
                self.after(0, lambda: dlg.winfo_exists() and status.configure(
                    text=t(f"explorar.etapa.{etapa}")))

            def worker():
                try:
                    obter, mailto = AC.obter_padrao()
                    ex = AC.explorar(texto, obter, mailto=mailto, n=n, cancelar=cancelar,
                                     ao_progresso=progresso)
                    self.after(0, lambda: terminou(ex))
                except BaseException as exc:      # noqa: BLE001 — vira mensagem na janela
                    if not isinstance(exc, (InterruptedError, AC.ErroExplorar)):
                        log.exception("[Explorar] falha")
                    self.after(0, lambda e=exc: terminou(erro=e))
            _ThreadDaTela(target=worker, daemon=True, name="explorar_worker").start()

        btn_explorar = self._btn(linha, t("explorar.iniciar"), explorar, height=32, corner_radius=0)
        btn_explorar.pack(side="left")
        btn_cancelar = self._btn(linha, t("pdfs.cancelar"), cancelar.set, height=32,
                                 color=INK, hover=INK_HOV, corner_radius=0)
        status.pack(fill="x", padx=24, pady=(8, 0))
        self._btn(acoes, t("explorar.abrir_mapa"), abrir_mapa, height=34, color=BLUE,
                  hover=BLUE_HOV, corner_radius=0).pack(side="left")
        self._btn(acoes, t("explorar.marcar_todos"), marcar_todos, height=34, color=INK,
                  hover=INK_HOV, corner_radius=0).pack(side="left", padx=8)
        self._btn(acoes, t("explorar.adicionar"), adicionar, height=34,
                  corner_radius=0).pack(side="right")

        def fechar():
            cancelar.set()
            self._explorar_janela = None
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", fechar)
        # ganchos para os testes
        self._explorar_api = {"entrada": entrada, "explorar": explorar, "adicionar": adicionar,
                              "abrir_mapa": abrir_mapa, "estado": estado, "status": status,
                              "marcar_todos": marcar_todos}

    def _build_tab_corpus(self) -> ctk.CTkFrame:
        self._corpus_tab_frame = self._tab()
        self._corpus_tab_frame.grid_columnconfigure(0, weight=1)
        self._corpus_tab_frame.grid_rowconfigure(1, weight=1)
        self._refresh_corpus_tab()
        return self._corpus_tab_frame
        
    def _refresh_corpus_tab(self):
        if not hasattr(self, '_corpus_tab_frame'):
            return
            
        # Clear existing
        for w in self._corpus_tab_frame.winfo_children():
            w.destroy()
            
        if self._dataframe is None or self._dataframe.empty:
            empty_container = ctk.CTkFrame(self._corpus_tab_frame, fg_color="transparent")
            empty_container.pack(expand=True)
            
            # O estado vazio era ilustrado por um `📂` de 64pt. Removido junto com os outros
            # emoji; o label ficaria de 64 pixels de altura sem nada dentro, então sai
            # inteiro em vez de virar um vão. A frase abaixo já diz o que houve.
            ctk.CTkLabel(empty_container, text="Nenhum corpus carregado.", font=ctk.CTkFont(size=20, weight="bold"), text_color=MUTED).pack(pady=10)
            self._btn(empty_container, "Coletar Dados", lambda: self._switch_tab("import"), height=40).pack(pady=20)
            return

        # Header
        hdr = ctk.CTkFrame(self._corpus_tab_frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=30, pady=(30, 20))
        hdr.grid_columnconfigure(1, weight=1)
        
        df = self._dataframe
        total_docs = len(df)
        total_cites = int(df['citations'].sum()) if 'citations' in df.columns else 0
        
        ctk.CTkLabel(hdr, text="Seu Corpus", font=ctk.CTkFont(size=28, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text=f"{total_docs} documentos • {total_cites} citações totais", font=ctk.CTkFont(size=14), text_color=MUTED).grid(row=1, column=0, sticky="w")
        # Resultado da última deduplicação (só aparece quando a ação foi rodada).
        if getattr(self, "_last_dedup_msg", ""):
            ctk.CTkLabel(hdr, text=self._last_dedup_msg, font=ctk.CTkFont(size=12),
                         text_color=INK).grid(row=2, column=0, sticky="w")

        btns_f = ctk.CTkFrame(hdr, fg_color="transparent")
        btns_f.grid(row=0, column=2, rowspan=2, sticky="e")
        self._btn(btns_f, t("dedup.button"), self._run_dedup, height=40, color=INK, hover=INK_HOV).pack(side="left", padx=(0, 10))
        self._btn(btns_f, "Análise IA do Corpus", self._trigger_corpus_ai_insights, height=40, color=YELLOW, hover=YELLOW_HOV).pack(side="left", padx=(0, 10))
        self._btn(btns_f, t("pdfs.botao"), self._download_oa_pdfs, height=40, color="#1E4DA0").pack(side="left", padx=(0, 10))
        self._btn(btns_f, "Ir para Análises", lambda: self._switch_tab("analises"), height=40, color=RED).pack(side="left")
        
        # Main content
        main = ctk.CTkFrame(self._corpus_tab_frame, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=30, pady=10)
        main.grid_columnconfigure(0, weight=7)
        main.grid_columnconfigure(1, weight=3)
        main.grid_rowconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        
        # Left: Histogram
        hist_card = self._card(main, 0, pady=0)
        hist_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        hist_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(hist_card, text="Publicações por Ano", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        hist_f = ctk.CTkFrame(hist_card, fg_color="transparent")
        hist_f.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            fig = Figure(figsize=(6, 3), dpi=100)
            fig.patch.set_facecolor(CARD_BG)
            ax = fig.add_subplot(111)
            ax.set_facecolor(CARD_BG)
            if 'year' in df.columns:
                years = df['year'].dropna()
                years = years[years > 0]
                if not years.empty:
                    counts = years.value_counts().sort_index()
                    ax.bar(counts.index, counts.values, color=RED)
                    ax.tick_params(colors=INK)
                    for spine in ax.spines.values():
                        spine.set_color(MUTED)
            fig.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, master=hist_f)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
        except Exception as e:
            ctk.CTkLabel(hist_f, text=f"Erro no gráfico: {e}").pack()

        # Right: Quick Summary
        sum_card = self._card(main, 0, pady=0)
        sum_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        ctk.CTkLabel(sum_card, text="Visão Geral", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
        sum_f = ctk.CTkFrame(sum_card, fg_color="transparent")
        sum_f.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        
        def get_top3(col):
            if col not in df.columns: return []
            items = df[col].dropna().astype(str)
            all_items = []
            for it in items:
                all_items.extend([x.strip() for x in it.split(";") if x.strip()])
            from collections import Counter
            return [x[0] for x in Counter(all_items).most_common(3)]
            
        top_auth = get_top3('authors')
        top_src = get_top3('source')
        
        ctk.CTkLabel(sum_f, text="Top Autores:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5,0))
        for a in top_auth: ctk.CTkLabel(sum_f, text=f"• {a}", text_color=MUTED).pack(anchor="w", padx=10)
        
        ctk.CTkLabel(sum_f, text="Top Fontes:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(15,0))
        for s in top_src: ctk.CTkLabel(sum_f, text=f"• {s[:30]}", text_color=MUTED).pack(anchor="w", padx=10)
        
        # Bottom: Preview Table
        tab_card = self._card(main, 1, pady=0)
        tab_card.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(20, 0))
        tab_card.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(tab_card, text="Prévia dos Dados (10 registros)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        try:
            import tkinter.ttk as ttk
            style = ttk.Style()
            style.theme_use("default")
            style.configure("Treeview", background=WHITE_CARD, foreground=INK, rowheight=25, fieldbackground=WHITE_CARD, borderwidth=0)
            style.configure("Treeview.Heading", background=PAPER, foreground=INK, font=('Archivo', 10, 'bold'))
            
            tree_f = ctk.CTkFrame(tab_card, fg_color="transparent")
            tree_f.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
            
            cols = [c for c in ['title', 'authors', 'year', 'source', 'citations'] if c in df.columns]
            if not cols: cols = list(df.columns[:5])
            
            tree = ttk.Treeview(tree_f, columns=cols, show="headings", selectmode="none")
            vsb = ttk.Scrollbar(tree_f, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(tree_f, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            tree_f.grid_columnconfigure(0, weight=1)
            tree_f.grid_rowconfigure(0, weight=1)
            
            for c in cols:
                tree.heading(c, text=c.capitalize())
                tree.column(c, width=150)
                
            for _, r in df.head(10).iterrows():
                tree.insert("", "end", values=[str(r[c])[:50] for c in cols])
        except Exception as e:
            ctk.CTkLabel(tab_card, text=f"Erro na tabela: {e}").grid(row=1, column=0)



# ── Exportações nunca falham caladas (auditoria 2026-09, D5) ──────────────────────────
# Uma exceção num botão do Tk só vai para o terminal: o usuário clica e nada acontece. O
# caso mais comum no Windows é o arquivo de destino estar aberto no Excel (gravação negada).
def _exportacao_protegida(metodo):
    import functools

    @functools.wraps(metodo)
    def envolvido(self, *a, **k):
        try:
            return metodo(self, *a, **k)
        except Exception as exc:
            log.info(f"[ERRO] {metodo.__name__}: {type(exc).__name__}: {exc}\n")
            if isinstance(exc, PermissionError):
                chave = "export.erro_permissao"
            elif isinstance(exc, (FileNotFoundError, NotADirectoryError)) or (
                    isinstance(exc, OSError) and "directory" in str(exc).lower()):
                chave = "export.erro_pasta"
            elif isinstance(exc, OSError):
                chave = "export.erro_disco"
            else:
                chave = "export.erro_generico"
            try:
                self._set_idle(t("export.erro_titulo"))
            except Exception:
                pass
            messagebox.showerror(t("export.erro_titulo"), t(chave))
    return envolvido


for _nome in [n for n in vars(BlicsaApp) if n.startswith("_export_")]:
    setattr(BlicsaApp, _nome, _exportacao_protegida(getattr(BlicsaApp, _nome)))
del _nome

if __name__ == "__main__":
    import sys
    if "--selfcheck" in sys.argv:
        try:
            from core.parsers import BibliometricParser
            from core.matrix_builders import NetworkGenerator
            from core.visualizer import build_plotly_map
            # Check translation parity
            import json, os
            locales_dir = os.path.join(os.path.dirname(__file__), "locales")
            with open(os.path.join(locales_dir, "en.json"), encoding="utf-8") as f: en = json.load(f)
            with open(os.path.join(locales_dir, "fr.json"), encoding="utf-8") as f: fr = json.load(f)
            with open(os.path.join(locales_dir, "pt_BR.json"), encoding="utf-8") as f: pt = json.load(f)
            en_keys = set(k for k in en.keys() if k != "_note")
            fr_keys = set(k for k in fr.keys() if k != "_note")
            pt_keys = set(k for k in pt.keys() if k != "_note")
            if not (en_keys == fr_keys == pt_keys):
                print(f"Self-check FAILED: Translation keys do not match. Missing in fr: {en_keys - fr_keys}, Missing in pt: {en_keys - pt_keys}", file=sys.stderr)
                sys.exit(1)
            print(f"Blicsa v{__version__}")
            print("Self-check passed: Core modules imported successfully and catalogs match.")
            sys.exit(0)
        except Exception as e:
            print(f"Self-check FAILED: {e}", file=sys.stderr)
            sys.exit(1)

    if "--smoke-test" in sys.argv:
        # Teste de fumaça pós-build (sem interação): sobe a UI REAL do app,
        # carrega locales + settings, deixa a janela viver ~5s e fecha sozinho
        # com exit 0. Roda no BINÁRIO empacotado para provar que o bundle abre.
        try:
            from core import i18n
            from core.settings import get_settings, settings_path
            i18n.load_locales()
            get_settings()
            print(f"[smoke] locales carregados: idioma={i18n.get_lang()}")
            print(f"[smoke] settings: {settings_path()}")
            app = BlicsaApp()  # constrói toda a UI e sobe o server local
            app.withdraw()     # não exige foco/janela visível
            print("[smoke] UI inicializada")
            app.after(5000, app.destroy)  # fecha sozinho em ~5s
            app.mainloop()
            print("Smoke test passed: app subiu, locales/settings OK, UI fechada limpa.")
            sys.exit(0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Smoke test FAILED: {e}", file=sys.stderr)
            sys.exit(1)

    if "--demo-search" in sys.argv:
        # QA (Evidência do release): dispara no BINÁRIO uma busca online REAL de
        # 25 registros (mesmo provider do botão Buscar) e gera o mapa, deixando a
        # janela aberta para o screenshot. Não abre o navegador (mapa Sigma) para
        # não roubar foco. Fecha sozinho após ~40s como rede de segurança.
        try:
            import pandas as pd
            from core.sources import OpenAlexProvider
            from core.project import create_project
            app = BlicsaApp()
            app._demo_no_browser = True

            def _run_demo():
                slug = create_project("Demo Release v0.9.0")
                app._set_active_project(slug)
                app._switch_tab("import")
                app.update()
                log.info("[Demo] Buscando 25 registros no OpenAlex…")
                records = list(OpenAlexProvider().search(query="bibliometrics", max_results=25))
                log.info(f"[Demo] {len(records)} registros baixados.")
                app._dataframe = pd.DataFrame(records)
                app._refresh_corpus_tab()
                app._switch_tab("corpus")
                app.update()
                app._min_occ_var.set(1)
                app._run_mapping()  # gera o mapa (threaded) + atualiza stats

            app.after(1200, _run_demo)
            app.after(40000, app.destroy)  # rede de segurança
            app.mainloop()
            sys.exit(0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Demo FAILED: {e}", file=sys.stderr)
            sys.exit(1)

    import tkinter as tk
    from PIL import Image, ImageTk
    
    app = BlicsaApp()
    app.withdraw()
    
    splash = tk.Toplevel(app)
    splash.overrideredirect(True)
    splash.geometry("600x400")
    
    # 3px ink border
    splash.configure(bg="#141414")
    content = tk.Frame(splash, bg="#F6F4EE")
    content.pack(fill="both", expand=True, padx=3, pady=3)
    
    lbl = tk.Label(content, bg="#F6F4EE")
    lbl.place(relx=0.5, rely=0.5, anchor="center")
    
    # Version string
    ver = tk.Label(content, text=f"v{__version__}", bg="#F6F4EE", fg="#8A877F", font=("Arial", 11))
    ver.place(relx=0.98, rely=0.98, anchor="se")
    
    frames = []
    try:
        gif = Image.open(caminho_do_recurso("assets/branding/blicsa-splash.gif"))
        for i in range(gif.n_frames):
            gif.seek(i)
            frames.append(ImageTk.PhotoImage(gif.copy()))
    except:
        pass
        
    def play_gif(idx):
        if not frames: return
        
        # Check settings
        from core.settings import get_settings
        reduce = bool(get_settings().get("reduce_animations", False))
            
        if reduce:
            lbl.config(image=frames[-1])
            return
            
        lbl.config(image=frames[idx])
        splash.after(42, play_gif, (idx + 1) % len(frames))
        
    if frames:
        play_gif(0)
        
    # Apply app icon
    try:
        if sys.platform == "win32":
            app.iconbitmap(caminho_do_recurso("assets/branding/blicsa-icon.ico"))
        else:
            ico = tk.PhotoImage(file=caminho_do_recurso("assets/branding/blicsa-icon-256.png"))
            app.iconphoto(True, ico)
    except:
        pass
        
    def center_splash():
        splash.update_idletasks()
        w = splash.winfo_width()
        h = splash.winfo_height()
        ws = splash.winfo_screenwidth()
        hs = splash.winfo_screenheight()
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)
        splash.geometry('%dx%d+%d+%d' % (w, h, x, y))
        
    center_splash()
    
    def close_splash():
        splash.destroy()
        app.deiconify()
        
    # Close after 3 seconds (max) or let one pass finish
    app.after(3000, close_splash)
    app.mainloop()
