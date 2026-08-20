"""Registro único das credenciais do Blicsa: onde moram, como se testam, onde se criam.

Antes deste módulo a configuração de credencial estava em três lugares com três formatos:
o painel de onboarding da IA (`ui/ai_onboarding_panel.py`), o diálogo de Ajustes
(`_show_settings`, que mostrava a da IA mascarada e deixava colar a do OpenAlex em texto
plano) e a barra de parâmetros do mapa (`_build_config_widgets`, um campo "Chave API" cru,
sem teste e sem link). Três lugares para a mesma tarefa, com comportamentos diferentes.

Aqui fica o que é comum: o diagnóstico (`ResultadoTeste`), a leitura e escrita no keyring
(via `core.settings`) e a definição de cada slot. O que muda de provedor para provedor —
como se testa a chave, onde se cria — fica numa `Credencial` por slot.

**Sem Tk de propósito**, como o `ai/onboarding.py` que o precedeu: o diagnóstico de uma
credencial é testável sem abrir janela.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

USER_AGENT = "Blicsa/1.0 (Python)"


@dataclass(frozen=True)
class ResultadoTeste:
    """Diagnóstico de uma tentativa de conexão.

    `status` é o que a UI usa para escolher a mensagem. Cada valor tem uma saída diferente
    para o usuário, então **mensagem genérica não serve**: "deu erro" não distingue "sua
    chave está errada" de "seu wi-fi caiu", e a ação do usuário é oposta nos dois casos.
    """

    status: str                 # "ok" | "vazia" | "invalida" | "sem_internet" | "limite" | "erro"
    chave_i18n: str             # chave da mensagem no catálogo
    modelo: str = ""            # detalhe positivo (modelo da IA, franquia do OpenAlex…)
    detalhe: str = ""           # texto técnico para log — NUNCA contém a credencial

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def mascarar(chave: str) -> str:
    """`gsk_abc...xyz9` → `gsk_…xyz9`. Nunca devolve a credencial inteira.

    Existe porque a credencial aparece na UI depois de salva (o usuário precisa reconhecer
    qual está ativa) e porque capturas de tela da documentação são feitas com o app
    configurado.
    """
    chave = (chave or "").strip()
    if not chave:
        return ""
    if len(chave) <= 8:
        return "…" + chave[-2:]
    return f"{chave[:4]}…{chave[-4:]}"


def _redigir(texto: str, chave: str) -> str:
    """Tira a credencial de qualquer texto que vá para log ou tela.

    Parece redundante — a chave viaja num cabeçalho ou num parâmetro que não ecoamos. Mas
    mensagem de erro de biblioteca é território de ninguém: basta uma versão futura do
    `urllib` incluir a URL completa no `repr` da exceção para a chave ir parar no log.
    """
    chave = (chave or "").strip()
    if chave and chave in texto:
        return texto.replace(chave, mascarar(chave))
    return texto


def _classificar_http(codigo: int, prefixo: str) -> ResultadoTeste:
    """Código HTTP → diagnóstico, com a mesma tabela para todos os provedores.

    Só 401/403 viram "inválida". Agrupar tudo num "erro de API" devolveria ao usuário a
    mesma frase para problemas com soluções opostas.
    """
    if codigo in (401, 403):
        return ResultadoTeste("invalida", f"{prefixo}.key_invalid", detalhe=f"HTTP {codigo}")
    if codigo == 429:
        return ResultadoTeste("limite", f"{prefixo}.key_rate_limit", detalhe="HTTP 429")
    return ResultadoTeste("erro", f"{prefixo}.key_error", detalhe=f"HTTP {codigo}")


def _pedir(url: str, chave: str, prefixo: str, cabecalhos: dict | None = None,
           corpo: bytes | None = None, timeout: int = 15):
    """Requisição de teste com o tratamento de erro comum. Devolve `(dados, ResultadoTeste)`.

    Exatamente um dos dois vem preenchido.
    """
    cab = {"User-Agent": USER_AGENT}
    cab.update(cabecalhos or {})
    req = urllib.request.Request(url, data=corpo, headers=cab,
                                 method="POST" if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, _classificar_http(e.code, prefixo)
    except urllib.error.URLError as e:
        # DNS, recusa de conexão, timeout: a credencial pode estar ótima e o problema é a rede.
        return None, ResultadoTeste("sem_internet", f"{prefixo}.key_offline",
                                    detalhe=_redigir(str(e.reason), chave)[:120])
    except Exception as e:                                    # pragma: no cover - inesperado
        return None, ResultadoTeste("erro", f"{prefixo}.key_error", detalhe=f"{type(e).__name__}")


# ── Testes de conexão, um por provedor ──────────────────────────────────────────

BASE_URL_GROQ = "https://api.groq.com/openai/v1"
#: Precisa acompanhar o padrão do `ai/client.py`: testar um modelo e usar outro faz a tela
#: de configuração aprovar a chave e o Blink falhar depois.
MODELO_TESTE_GROQ = "openai/gpt-oss-120b"


def testar_ia(chave: str, base_url: str = BASE_URL_GROQ,
              modelo: str = MODELO_TESTE_GROQ, timeout: int = 15) -> ResultadoTeste:
    """Chamada mínima ao provedor de IA. `max_tokens=1`: configurar não gasta cota."""
    chave = (chave or "").strip()
    if not chave:
        return ResultadoTeste("vazia", "ai.key_empty")

    corpo = json.dumps({"model": modelo,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1}).encode("utf-8")
    # Sem User-Agent o Cloudflare do Groq responde 403 ANTES de olhar a chave, e o
    # diagnóstico classificaria como "invalida" — mandando o usuário conferir uma chave
    # perfeitamente correta.
    dados, erro = _pedir(f"{base_url.rstrip('/')}/chat/completions", chave, "ai",
                         cabecalhos={"Authorization": f"Bearer {chave}",
                                     "Content-Type": "application/json"},
                         corpo=corpo, timeout=timeout)
    if erro is not None:
        return erro
    return ResultadoTeste("ok", "ai.key_ok", modelo=str(dados.get("model") or modelo))


def testar_openalex(chave: str, timeout: int = 15) -> ResultadoTeste:
    """Uma requisição de 1 crédito, e o que ela devolve é a FRANQUIA.

    Diferente dos outros dois: aqui a chave é opcional, e o valor de testá-la é justamente
    ver o patamar em que se está. A resposta traz `X-RateLimit-Limit`, então o usuário
    confirma na hora que saiu de ~1.000 para ~10.000 créditos por dia.
    """
    chave = (chave or "").strip()
    if not chave:
        return ResultadoTeste("vazia", "openalex.key_empty")

    url = ("https://api.openalex.org/works?per_page=1&api_key="
           + urllib.parse.quote(chave))
    cab = {"User-Agent": USER_AGENT}
    req = urllib.request.Request(url, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            limite = r.headers.get("X-RateLimit-Limit") or "?"
            return ResultadoTeste("ok", "openalex.key_ok", modelo=str(limite))
    except urllib.error.HTTPError as e:
        return _classificar_http(e.code, "openalex")
    except urllib.error.URLError as e:
        return ResultadoTeste("sem_internet", "openalex.key_offline",
                              detalhe=_redigir(str(e.reason), chave)[:120])
    except Exception as e:                                    # pragma: no cover
        return ResultadoTeste("erro", "openalex.key_error", detalhe=f"{type(e).__name__}")


def testar_pubmed(chave: str, timeout: int = 15) -> ResultadoTeste:
    """`esearch` com `retmax=0`: confirma a chave sem baixar registro nenhum.

    O NCBI NÃO responde 401 a uma chave inválida do jeito que se espera — devolve **400**
    com `{"error":"API key invalid", ...}` no corpo. Classificar pelo código só daria "erro"
    genérico ("tente de novo em instantes") para uma chave que nunca vai funcionar, então o
    corpo é lido. Confirmado contra a API real.

    Cuidado ao mexer aqui: esse corpo **ecoa a chave de volta** num campo `api-key`. Por
    isso o `detalhe` guarda só "HTTP 400" e nunca o corpo — logar a resposta crua deste
    endpoint vaza a credencial do usuário.
    """
    chave = (chave or "").strip()
    if not chave:
        return ResultadoTeste("vazia", "pubmed.key_empty")

    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
           + urllib.parse.urlencode({"db": "pubmed", "term": "bibliometrics",
                                     "retmode": "json", "retmax": 0, "api_key": chave}))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corpo = r.read().decode("utf-8", "replace")
        dados = json.loads(corpo)
        if "error" in dados or "ERROR" in str(dados.get("esearchresult", {})):
            return ResultadoTeste("invalida", "pubmed.key_invalid", detalhe="corpo com erro")
        return ResultadoTeste("ok", "pubmed.key_ok", modelo="10")
    except urllib.error.HTTPError as e:
        corpo = ""
        try:
            corpo = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if e.code == 400 and "api" in corpo.lower() and "key" in corpo.lower():
            return ResultadoTeste("invalida", "pubmed.key_invalid", detalhe="HTTP 400")
        return _classificar_http(e.code, "pubmed")
    except urllib.error.URLError as e:
        return ResultadoTeste("sem_internet", "pubmed.key_offline",
                              detalhe=_redigir(str(e.reason), chave)[:120])
    except Exception as e:                                    # pragma: no cover
        return ResultadoTeste("erro", "pubmed.key_error", detalhe=f"{type(e).__name__}")


# ── Os slots ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Credencial:
    """Um slot de credencial: identidade, onde criar, como testar."""

    id: str                       # id no registro de `core.settings.CREDENCIAIS`
    titulo_i18n: str
    explicacao_i18n: str
    url_criacao: str
    testar: Callable[[str], ResultadoTeste]
    prefixo_i18n: str
    placeholder: str = ""
    #: Provedores selecionáveis, quando houver: rótulo → (url de criação, base_url, modelo).
    #: Só a IA tem; OpenAlex e PubMed são um provedor só.
    provedores: dict = field(default_factory=dict)

    def valor(self) -> str:
        from core.settings import get_credencial
        return get_credencial(self.id)

    def gravar(self, valor: str):
        from core.settings import set_credencial
        set_credencial(self.id, valor)


#: Provedores de IA. O Groq vem primeiro porque é a opção gratuita — a promessa do app é
#: custo zero, e a lista é lida de cima para baixo.
PROVEDORES_IA = {
    "groq":       ("https://console.groq.com/keys",        BASE_URL_GROQ, MODELO_TESTE_GROQ),
    "openai":     ("https://platform.openai.com/api-keys",
                   "https://api.openai.com/v1", "gpt-4o"),
    "openrouter": ("https://openrouter.ai/keys",
                   "https://openrouter.ai/api/v1", "meta-llama/llama-3-70b-instruct"),
    "ollama":     ("https://ollama.com/download",
                   "http://localhost:11434/v1", "llama3"),
}

CREDENCIAIS = (
    Credencial(
        id="ai", titulo_i18n="cred.ai_titulo", explicacao_i18n="cred.ai_explicacao",
        url_criacao=PROVEDORES_IA["groq"][0], testar=testar_ia,
        prefixo_i18n="ai", placeholder="gsk_…", provedores=PROVEDORES_IA),
    Credencial(
        id="openalex", titulo_i18n="cred.openalex_titulo",
        explicacao_i18n="cred.openalex_explicacao",
        url_criacao="https://openalex.org/settings/api", testar=testar_openalex,
        prefixo_i18n="openalex"),
    Credencial(
        id="pubmed", titulo_i18n="cred.pubmed_titulo",
        explicacao_i18n="cred.pubmed_explicacao",
        url_criacao="https://www.ncbi.nlm.nih.gov/account/settings/",
        testar=testar_pubmed, prefixo_i18n="pubmed"),
)


def por_id(cred_id: str) -> Credencial:
    return next(c for c in CREDENCIAIS if c.id == cred_id)


def tem_chave_ia() -> bool:
    """Há chave de IA configurada? É o que decide entre mostrar o chat ou o convite.

    Passa por `get_api_key` de propósito, e não pelo `valor()` genérico do slot: aquela é a
    leitura documentada da chave de IA, usada nos sete pontos que montam o `AIAnalyst`. Ter
    dois caminhos de leitura para a mesma chave é como se abre espaço para eles divergirem.
    """
    try:
        from core.settings import get_api_key
        return bool((get_api_key() or "").strip())
    except Exception:
        return False
