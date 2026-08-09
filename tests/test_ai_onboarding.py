"""Onboarding da chave de IA: o usuário traz a dele, e o app diz exatamente o que houve.

O ponto que estes testes protegem é a **especificidade do diagnóstico**. "Deu erro" não
distingue "sua chave está errada" de "seu wi-fi caiu" de "você bateu no limite do provedor" —
e a ação do usuário é diferente, às vezes oposta, em cada caso. Um teste que só verifica "veio
alguma mensagem" deixaria passar exatamente o defeito que importa.
"""

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

# `testar_chave` entra com apelido: importado com o nome original, o pytest o COLETA como
# se fosse um teste (prefixo `test`) e reporta erro de fixture inexistente.
from ai.onboarding import BASE_URL_PADRAO, PREFIXO_GROQ, URL_CONSOLE_GROQ, mascarar
from ai.onboarding import tem_chave
from ai.onboarding import testar_chave as diagnosticar

RAIZ = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _sem_chave_do_ambiente(monkeypatch):
    """Tira as variáveis de ambiente de TODOS os testes deste módulo.

    `get_api_key()` lê `AI_API_KEY`/`GROQ_API_KEY` antes do keyring. Sem isto, um teste de
    persistência comparava contra a chave REAL da máquina e a imprimia inteira na mensagem
    de falha — que no CI seria um log público. Chave real nunca entra em asserção.
    """
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

CHAVE_FALSA = "gsk_" + "T3st3Fals4" * 5      # comprimento de chave real, valor sintético


def _resposta_ok(modelo="llama-3.3-70b-versatile"):
    corpo = json.dumps({"model": modelo, "choices": [{"message": {"content": "p"}}]})

    class _R:
        def read(self): return corpo.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _R()


def _http_error(code):
    return urllib.error.HTTPError("https://api.groq.com/openai/v1/chat/completions",
                                  code, "erro", {}, io.BytesIO(b"{}"))


# ── Os quatro diagnósticos, distintos entre si ────────────────────────────────────

def test_chave_valida_devolve_ok_com_o_modelo():
    with patch("urllib.request.urlopen", return_value=_resposta_ok("llama-3.1-8b-instant")):
        r = diagnosticar(CHAVE_FALSA)
    assert r.ok and r.status == "ok"
    assert r.chave_i18n == "ai.key_ok"
    assert r.modelo == "llama-3.1-8b-instant", "o modelo que respondeu tem que voltar"


@pytest.mark.parametrize("code", [401, 403])
def test_chave_invalida(code):
    with patch("urllib.request.urlopen", side_effect=_http_error(code)):
        r = diagnosticar(CHAVE_FALSA)
    assert r.status == "invalida" and r.chave_i18n == "ai.key_invalid"
    assert not r.ok


def test_sem_internet():
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("nodename nor servname provided")):
        r = diagnosticar(CHAVE_FALSA)
    assert r.status == "sem_internet" and r.chave_i18n == "ai.key_offline"


def test_limite_atingido():
    with patch("urllib.request.urlopen", side_effect=_http_error(429)):
        r = diagnosticar(CHAVE_FALSA)
    assert r.status == "limite" and r.chave_i18n == "ai.key_rate_limit"


def test_os_quatro_diagnosticos_sao_DISTINTOS_entre_si():
    """O coração da fase: quatro situações, quatro mensagens diferentes.

    Se alguém agrupar os casos num `except Exception` genérico, os quatro passam a devolver a
    mesma chave i18n e este teste fica vermelho — os outros continuariam verdes."""
    cenarios = {
        "ok":           patch("urllib.request.urlopen", return_value=_resposta_ok()),
        "invalida":     patch("urllib.request.urlopen", side_effect=_http_error(401)),
        "limite":       patch("urllib.request.urlopen", side_effect=_http_error(429)),
        "sem_internet": patch("urllib.request.urlopen",
                              side_effect=urllib.error.URLError("offline")),
    }
    chaves = {}
    for nome, ctx in cenarios.items():
        with ctx:
            r = diagnosticar(CHAVE_FALSA)
        assert r.status == nome, f"{nome}: veio {r.status}"
        chaves[nome] = r.chave_i18n

    assert len(set(chaves.values())) == 4, (
        f"mensagens repetidas entre situações diferentes: {chaves}")

    # E as mensagens em si têm que ser textos distintos, não só chaves distintas.
    import json as _json
    cat = _json.loads((RAIZ / "locales/pt_BR.json").read_text(encoding="utf-8"))
    textos = [cat[k] for k in chaves.values()]
    assert len(set(textos)) == 4, f"chaves distintas mas texto igual: {textos}"


def test_erro_http_desconhecido_nao_vira_chave_invalida():
    """Adversarial: um 500 do provedor não é culpa da chave. Dizer "chave recusada" mandaria
    o usuário gerar outra chave sem necessidade."""
    with patch("urllib.request.urlopen", side_effect=_http_error(500)):
        r = diagnosticar(CHAVE_FALSA)
    assert r.status == "erro" and r.chave_i18n == "ai.key_error"


# ── Entrada do usuário ────────────────────────────────────────────────────────────

def test_chave_com_espacos_em_volta_e_aceita():
    """Colar de um navegador costuma trazer espaço ou quebra de linha junto."""
    enviados = {}

    def _captura(req, *a, **kw):
        enviados["auth"] = req.headers.get("Authorization")
        return _resposta_ok()

    with patch("urllib.request.urlopen", side_effect=_captura):
        r = diagnosticar(f"  \n{CHAVE_FALSA}\t ")
    assert r.ok
    assert enviados["auth"] == f"Bearer {CHAVE_FALSA}", "o trim não foi aplicado"


def test_chave_vazia_e_rejeitada_sem_bater_na_rede():
    with patch("urllib.request.urlopen") as mock:
        for entrada in ("", "   ", None):
            r = diagnosticar(entrada)
            assert r.status == "vazia" and r.chave_i18n == "ai.key_empty"
    assert mock.call_count == 0, "gastou requisição para um campo vazio"


def test_chamada_de_teste_e_minima():
    """`max_tokens=1`: configurar o app não pode consumir cota do usuário."""
    enviados = {}

    def _captura(req, *a, **kw):
        enviados["corpo"] = json.loads(req.data.decode())
        enviados["url"] = req.full_url
        return _resposta_ok()

    with patch("urllib.request.urlopen", side_effect=_captura):
        diagnosticar(CHAVE_FALSA)
    assert enviados["corpo"]["max_tokens"] == 1
    assert enviados["url"].startswith(BASE_URL_PADRAO)


# ── Mascaramento e sigilo ─────────────────────────────────────────────────────────

def test_chave_e_exibida_mascarada():
    assert mascarar(CHAVE_FALSA) == f"gsk_…{CHAVE_FALSA[-4:]}"
    assert CHAVE_FALSA not in mascarar(CHAVE_FALSA)
    assert mascarar("") == ""
    assert mascarar("abc") == "…bc", "chave curta também não pode vazar inteira"


def test_diagnostico_nunca_carrega_a_chave():
    """`detalhe` vai para log. A chave não pode entrar nele por nenhum caminho."""
    cenarios = [
        patch("urllib.request.urlopen", side_effect=_http_error(401)),
        patch("urllib.request.urlopen", side_effect=_http_error(429)),
        patch("urllib.request.urlopen", side_effect=_http_error(500)),
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError(CHAVE_FALSA)),
    ]
    for ctx in cenarios:
        with ctx:
            r = diagnosticar(CHAVE_FALSA)
        texto = f"{r.status} {r.chave_i18n} {r.detalhe} {r.modelo}"
        assert CHAVE_FALSA not in texto, f"a chave vazou no diagnóstico: {r.detalhe!r}"


def test_nenhuma_chave_real_esta_versionada():
    """Varredura do repositório: nada com formato de credencial real entra em commit."""
    import subprocess
    r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=RAIZ)
    padrao = __import__("re").compile(r"\bgsk_[A-Za-z0-9]{40,}\b")
    achados = []
    for nome in r.stdout.splitlines():
        if nome.lower().endswith((".png", ".gif", ".jpg", ".csv", ".blicsa")):
            continue
        try:
            texto = (RAIZ / nome).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if padrao.search(texto):
            achados.append(nome)
    assert not achados, f"chave com formato real versionada em: {achados}"


# ── Estado: com e sem chave ───────────────────────────────────────────────────────

def test_sem_chave_o_app_sabe_que_precisa_do_onboarding():
    with patch("core.settings.get_api_key", return_value=""):
        assert tem_chave() is False
    with patch("core.settings.get_api_key", return_value="   "):
        assert tem_chave() is False, "só espaços não é chave"


def test_com_chave_o_app_nao_mostra_onboarding():
    with patch("core.settings.get_api_key", return_value=CHAVE_FALSA):
        assert tem_chave() is True


def test_remover_chave_volta_ao_estado_de_onboarding(tmp_path, monkeypatch):
    """Persistência real de ida e volta, sem keyring (caminho de fallback em JSON)."""
    import core.settings as cs

    monkeypatch.setattr(cs, "_keyring", lambda: None)
    monkeypatch.setattr(cs, "SETTINGS_PATH", tmp_path / "settings.json", raising=False)
    monkeypatch.setattr(cs, "_settings_cache", None, raising=False)

    cs.set_api_key(CHAVE_FALSA)
    assert cs.get_api_key() == CHAVE_FALSA

    cs.set_api_key("")
    # Compara o comprimento, não o valor: se falhar, a mensagem do pytest não imprime chave.
    assert len(cs.get_api_key()) == 0, "remover a chave não a apagou"


def test_persistencia_entre_reinicios(tmp_path, monkeypatch):
    """Simula reabrir o app: releitura das configurações do disco, sem cache em memória."""
    import importlib

    import core.settings as cs
    monkeypatch.setattr(cs, "_keyring", lambda: None)
    monkeypatch.setattr(cs, "SETTINGS_PATH", tmp_path / "settings.json", raising=False)
    monkeypatch.setattr(cs, "_settings_cache", None, raising=False)
    cs.set_api_key(CHAVE_FALSA)

    # "Reinício": zera o cache e lê de novo do arquivo.
    monkeypatch.setattr(cs, "_settings_cache", None, raising=False)
    lida = cs.get_api_key()
    assert mascarar(lida) == mascarar(CHAVE_FALSA), (
        "a chave não sobreviveu ao reinício (comparação mascarada de propósito: "
        "mensagem de falha do pytest vira log de CI)")


# ── A requisição de teste tem que CHEGAR ao provedor ──────────────────────────────

def test_teste_de_conexao_manda_user_agent():
    """Sem User-Agent, o Cloudflare do Groq responde 403 (`error code: 1010`) ANTES de olhar
    a chave — e o diagnóstico classificava isso como "invalida".

    O efeito era o pior possível para esta tela: quem colasse uma chave **correta** lia
    "confira se copiou a chave inteira, sem espaços, e se ela ainda está ativa". A IA
    funcionava normalmente depois, porque `ai/client.py` sempre mandou o cabeçalho — só o
    teste de conexão não mandava. A tela que existe para configurar a chave era a única que
    a reprovava.

    Encontrado ao tentar gerar as capturas com chamada real ao modelo: a chave do ambiente
    era boa e `testar_chave` dizia que não.
    """
    from ai.client import USER_AGENT

    capturado = {}

    def _espia(req, *a, **kw):
        capturado["headers"] = {k.lower(): v for k, v in req.headers.items()}
        return _resposta_ok()

    with patch("urllib.request.urlopen", side_effect=_espia):
        diagnosticar(CHAVE_FALSA)

    assert "user-agent" in capturado["headers"], (
        "requisição sem User-Agent — o Cloudflare do Groq devolve 403 antes de avaliar a chave")
    assert capturado["headers"]["user-agent"] == USER_AGENT


def test_teste_de_conexao_usa_o_mesmo_user_agent_do_cliente():
    """Um só valor. Divergir faria a tela de configuração e o uso real terem destinos
    diferentes no Cloudflare — que é exatamente o bug que acabou de acontecer."""
    from ai.client import USER_AGENT

    fonte = (RAIZ / "ai/client.py").read_text(encoding="utf-8")
    assert fonte.count('"User-Agent": USER_AGENT') == 2, (
        "algum ponto de `ai/client.py` voltou a ter o User-Agent literal")
    assert USER_AGENT.strip()


def test_dotenv_nao_sobrescreve_o_ambiente_real(tmp_path, monkeypatch):
    """`.env` preenche o que falta; não manda no que já existe.

    Era o contrário, e o efeito foi concreto: uma chave revogada no `.env` do diretório de
    trabalho vencia a chave válida exportada no shell. A IA devolvia 401, o app dizia "falha
    na requisição de IA" e nada na tela ligava o erro a um arquivo que o usuário não lembrava
    que existia. Encontrado ao gerar as capturas com chamada real.
    """
    (tmp_path / ".env").write_text('GROQ_API_KEY="do-arquivo"\nAI_MODEL=do-arquivo\n',
                                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "do-shell")
    monkeypatch.delenv("AI_MODEL", raising=False)

    # Replica o bloco de carga do topo de `main.py` (importar main aqui subiria a UI).
    import os as _os
    for linha in (tmp_path / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.strip().startswith("#"):
            k, v = linha.strip().split("=", 1)
            _os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    assert _os.environ["GROQ_API_KEY"] == "do-shell", "o .env sobrescreveu o ambiente real"
    assert _os.environ["AI_MODEL"] == "do-arquivo", "o .env deixou de preencher o que faltava"


def test_main_carrega_dotenv_com_setdefault():
    """Guarda na fonte: o teste acima replica o bloco, então precisa de um par que confira
    que o bloco replicado ainda é o que o `main.py` faz."""
    fonte = (RAIZ / "main.py").read_text(encoding="utf-8")
    trecho = fonte.split("import json", 1)[0]
    assert "os.environ.setdefault(k.strip()" in trecho, (
        "o carregador de .env voltou a sobrescrever o ambiente real")
    assert "os.environ[k.strip()] =" not in trecho


# ── Tutorial e i18n ───────────────────────────────────────────────────────────────

def test_url_do_tutorial_e_a_correta():
    """Assertar a URL, não o efeito de abrir o navegador: link errado manda o usuário para
    lugar nenhum e o onboarding inteiro perde a função."""
    assert URL_CONSOLE_GROQ == "https://console.groq.com/keys"
    assert PREFIXO_GROQ == "gsk_"


def test_i18n_das_chaves_novas_nos_tres_idiomas():
    import json as _json

    NOVAS = ["ai.onboarding_title", "ai.onboarding_intro", "ai.step1", "ai.step1_button",
             "ai.step2", "ai.step3", "ai.step3_button", "ai.key_ok", "ai.key_empty",
             "ai.key_invalid", "ai.key_offline", "ai.key_rate_limit", "ai.key_error",
             "ai.key_saved", "ai.key_remove", "ai.badge"]
    for loc in ("pt_BR", "en", "fr"):
        cat = _json.loads((RAIZ / f"locales/{loc}.json").read_text(encoding="utf-8"))
        faltando = [k for k in NOVAS if k not in cat]
        assert not faltando, f"{loc}: faltam {faltando}"
        vazias = [k for k in NOVAS if not str(cat[k]).strip()]
        assert not vazias, f"{loc}: vazias {vazias}"

    # Os marcadores de formatação têm que sobreviver à tradução.
    for loc in ("pt_BR", "en", "fr"):
        cat = _json.loads((RAIZ / f"locales/{loc}.json").read_text(encoding="utf-8"))
        assert "{modelo}" in cat["ai.key_ok"], f"{loc}: ai.key_ok perdeu {{modelo}}"
        assert "{chave}" in cat["ai.key_saved"], f"{loc}: ai.key_saved perdeu {{chave}}"


def test_custo_zero_esta_declarado_nos_tres_idiomas():
    """O item 6 do prompt: o texto precisa dizer que é gratuito e que o Blicsa não cobra."""
    import json as _json

    TERMOS = {"pt_BR": ("gratuita", "não cobra"), "en": ("free", "charges nothing"),
              "fr": ("gratuit", "ne facture rien")}
    for loc, termos in TERMOS.items():
        cat = _json.loads((RAIZ / f"locales/{loc}.json").read_text(encoding="utf-8"))
        texto = cat["ai.onboarding_intro"].lower()
        for termo in termos:
            assert termo.lower() in texto, f"{loc}: falta {termo!r} em ai.onboarding_intro"
