"""Settings do Blicsa — API única, no diretório de CONFIGURAÇÃO DO USUÁRIO.

Antes o .blicsa_settings.json era gravado em os.path.dirname(__file__) (o
diretório do CÓDIGO): num app instalado/congelado (PyInstaller, /Applications)
isso é somente-leitura e salvar settings falhava. Agora:

- settings.json em platformdirs.user_config_dir("blicsa")
  (macOS: ~/Library/Application Support/blicsa/)
- migração automática do arquivo legado na primeira leitura
- credenciais no KEYRING do SO (service "blicsa"), com fallback transparente
  para o settings.json quando não há keyring (headless/CI); envs têm
  precedência (fluxo dev)
- toda escrita com context manager

**O cofre é por conta do sistema operacional.** O Blicsa não tem login próprio:
quem responde por "de quem é esta chave" é o keyring do usuário logado no SO.
Dois usuários do mesmo computador têm chaves distintas e invisíveis entre si, e
nada disso sai da máquina.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("blicsa.settings")

APP_NAME = "blicsa"
KEYRING_SERVICE = "blicsa"
KEYRING_USERNAME = "ai_api_key"

#: Credenciais de provedor único, por id → (username no keyring, envs com precedência).
#:
#: A chave da IA já morava no keyring; a do OpenAlex morava em TEXTO PLANO no settings.json
#: (`openalex_api_key`) e a do PubMed não existia. Um registro único evita que a próxima
#: credencial invente um terceiro lugar — que foi como a dispersão começou.
#:
#: A da IA NÃO está aqui: ela tem um slot por provedor, resolvido em `_slot`.
CREDENCIAIS = {
    "ai":       (KEYRING_USERNAME,     ("AI_API_KEY", "GROQ_API_KEY")),
    "openalex": ("openalex_api_key",   ("OPENALEX_API_KEY",)),
    "pubmed":   ("pubmed_api_key",     ("NCBI_API_KEY", "PUBMED_API_KEY")),
}

#: Nome da chave no settings.json, por credencial. Difere do username do keyring por
#: acidente histórico: a da IA era gravada como `api_key` e a do OpenAlex como
#: `openalex_api_key`. Migrar o nome quebraria a leitura de quem já tem o arquivo.
_CHAVE_JSON = {"ai": "api_key", "openalex": "openalex_api_key", "pubmed": "pubmed_api_key"}

PROVEDOR_IA_PADRAO = "groq"

#: Envs com precedência por provedor de IA. `AI_API_KEY` é o override genérico do fluxo
#: dev e vale para qualquer provedor; a segunda é a env consagrada de cada um. Sem esta
#: separação um `GROQ_API_KEY` esquecido no ambiente venceria a chave da OpenAI escolhida
#: na tela — o app usaria uma credencial que o usuário não configurou.
ENVS_IA = {
    "groq":       ("AI_API_KEY", "GROQ_API_KEY"),
    "openai":     ("AI_API_KEY", "OPENAI_API_KEY"),
    "openrouter": ("AI_API_KEY", "OPENROUTER_API_KEY"),
    "ollama":     ("AI_API_KEY", "OLLAMA_API_KEY"),
}
ENVS_IA_PADRAO = ("AI_API_KEY",)

#: Preset de último recurso, quando `core.credenciais` não estiver importável. Precisa
#: bater com o do Groq em `PROVEDORES_IA`.
_PRESET_PADRAO = ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b")

# Caminho do arquivo LEGADO (diretório do código) — só para migração.
LEGACY_PATH = Path(__file__).resolve().parent.parent / ".blicsa_settings.json"

# Injetável em testes (monkeypatch): quando setado, ignora platformdirs.
_OVERRIDE_PATH: Path | None = None


def settings_path() -> Path:
    """Caminho REAL do settings novo (user_config_dir do SO)."""
    if _OVERRIDE_PATH is not None:
        return Path(_OVERRIDE_PATH)
    from platformdirs import user_config_dir
    return Path(user_config_dir(APP_NAME)) / "settings.json"


def _migrate_legacy_file(path: Path):
    """Se existir o arquivo antigo no diretório do código e não existir o novo,
    copia UMA vez e loga."""
    if path.exists() or not LEGACY_PATH.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(LEGACY_PATH, path)
        logger.info(f"[Settings] migrado: {LEGACY_PATH} → {path}")
    except Exception as e:
        logger.warning(f"[Settings] falha na migração do legado: {e}")


def get_settings() -> dict:
    path = settings_path()
    _migrate_legacy_file(path)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[Settings] arquivo ilegível ({e}) — usando defaults")
    return {}


def save_settings(settings: dict):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def update_settings(**kv) -> dict:
    """Atalho ler-alterar-gravar para um punhado de chaves."""
    s = get_settings()
    s.update(kv)
    save_settings(s)
    return s


# ── Provedor de IA ativo e seus parâmetros ─────────────────────────────────
def provedor_ia() -> str:
    """Provedor de IA ativo. Precedência: env (dev) → settings.json → padrão.

    Existe porque provedor, URL base e modelo NÃO eram persistidos: ficavam em variáveis
    de UI inicializadas com `os.environ.get(..., <default do Groq>)`. Quem configurava a
    OpenAI reabria o app apontando para o Groq, e a chave da OpenAI — guardada e íntegra —
    era enviada ao Groq, que respondia 401. A tela dizia "chave inválida" sobre uma chave
    perfeitamente boa, e o efeito para o usuário era o app ter esquecido a chave.
    """
    v = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if v:
        return v
    return str(get_settings().get("ai_provider") or PROVEDOR_IA_PADRAO).strip().lower()


def _preset(provedor: str) -> tuple[str, str]:
    """(base_url, modelo) do provedor, da tabela única de `core.credenciais`."""
    try:
        from core.credenciais import PROVEDORES_IA
    except Exception:                                         # pragma: no cover - defensivo
        return _PRESET_PADRAO
    entrada = PROVEDORES_IA.get(provedor)
    if not entrada:
        return _PRESET_PADRAO
    return entrada[1], entrada[2]


def config_ia() -> tuple[str, str, str]:
    """(provedor, base_url, modelo) efetivos, na precedência env → settings → preset.

    Uma leitura só para os três valores: eram lidos em pontos separados de `main.py`, o que
    permitia o provedor dizer "openai" enquanto a URL base seguia no Groq.
    """
    prov = provedor_ia()
    base_preset, modelo_preset = _preset(prov)
    s = get_settings()
    base = ((os.environ.get("AI_BASE_URL") or "").strip()
            or str(s.get("ai_base_url") or "").strip()
            or base_preset)
    modelo = ((os.environ.get("AI_MODEL") or "").strip()
              or str(s.get("ai_model") or "").strip()
              or modelo_preset)
    return prov, base, modelo


def set_config_ia(provedor: str, base_url: str = "", modelo: str = ""):
    """Grava o provedor e SÓ o que diverge do preset dele.

    Guardar a URL e o modelo mesmo quando iguais ao preset teria dois efeitos ruins: uma
    correção futura do preset no código nunca chegaria a quem já usa o app, e trocar de
    provedor deixaria para trás a URL base do anterior. Ausente no JSON significa "use o
    preset", que é o comportamento certo nos dois casos.
    """
    prov = (provedor or PROVEDOR_IA_PADRAO).strip().lower()
    base_preset, modelo_preset = _preset(prov)
    s = get_settings()
    s["ai_provider"] = prov
    for chave, valor, preset in (("ai_base_url", base_url, base_preset),
                                 ("ai_model", modelo, modelo_preset)):
        valor = (valor or "").strip()
        if valor and valor != preset:
            s[chave] = valor
        else:
            s.pop(chave, None)
    save_settings(s)


# ── Resolução de slot ──────────────────────────────────────────────────────
def _slot(nome: str) -> tuple[str, tuple[str, ...], str]:
    """Id de credencial → (username no keyring, envs, chave no settings.json).

    Aceita `"ai"` (o provedor ATIVO) e `"ai:<provedor>"` (um provedor específico, que a
    aba de Credenciais usa para mostrar e gravar a chave do provedor selecionado no combo
    sem que a seleção precise virar a ativa antes).

    O Groq reaproveita o slot histórico `ai_api_key`: era o único que existia, e quem já
    tem chave guardada continua a encontrando sem recolar. Os demais provedores ganham
    `ai_api_key_<provedor>`, que é o que permite configurar Groq e OpenAI uma vez cada e
    alternar entre eles — antes o slot era um só e trocar de provedor sobrescrevia.
    """
    if nome == "ai":
        nome = f"ai:{provedor_ia()}"
    if nome.startswith("ai:"):
        prov = (nome.split(":", 1)[1] or PROVEDOR_IA_PADRAO).strip().lower()
        envs = ENVS_IA.get(prov, ENVS_IA_PADRAO)
        if prov == PROVEDOR_IA_PADRAO:
            return KEYRING_USERNAME, envs, _CHAVE_JSON["ai"]
        return f"{KEYRING_USERNAME}_{prov}", envs, f"{_CHAVE_JSON['ai']}_{prov}"
    usuario, envs = CREDENCIAIS[nome]
    return usuario, envs, _CHAVE_JSON[nome]


# ── Credenciais no keyring (com fallback transparente) ─────────────────────
def _keyring():
    """Módulo keyring com backend UTILIZÁVEL, ou None (headless/CI/sem SO)."""
    try:
        import keyring
        backend = keyring.get_keyring()
        if backend.__class__.__module__.startswith("keyring.backends.fail"):
            return None
        return keyring
    except Exception:
        return None


def get_credencial(nome: str) -> str:
    """Uma credencial qualquer do registro. Precedência: env (dev) → keyring → JSON.

    O fallback em JSON existe para máquina sem keyring utilizável (headless, CI). Não é o
    lugar preferido: guarda em texto plano, e por isso `set_credencial` apaga a cópia do
    JSON assim que o keyring aceita a gravação.
    """
    usuario, envs, chave_json = _slot(nome)
    for env in envs:
        v = os.environ.get(env)
        if v:
            return v
    migrate_credenciais_do_json()  # idempotente e barato quando não há nada a migrar
    kr = _keyring()
    if kr is not None:
        try:
            v = kr.get_password(KEYRING_SERVICE, usuario)
            if v:
                return v
        except Exception as e:
            logger.warning(f"[Settings] keyring indisponível na leitura de {nome}: {e}")
    return str(get_settings().get(chave_json) or "")


def set_credencial(nome: str, value: str):
    """Grava no keyring; sem keyring, cai para o settings.json. Nunca loga o valor."""
    usuario, _, chave_json = _slot(nome)
    value = (value or "").strip()
    kr = _keyring()
    if kr is not None:
        try:
            if value:
                kr.set_password(KEYRING_SERVICE, usuario, value)
            else:
                try:
                    kr.delete_password(KEYRING_SERVICE, usuario)
                except Exception:
                    pass
            # garante que não sobra cópia em texto plano no JSON
            s = get_settings()
            if chave_json in s:
                s.pop(chave_json)
                save_settings(s)
            return
        except Exception as e:
            logger.warning(f"[Settings] keyring indisponível na escrita de {nome}: {e}")
    s = get_settings()
    if value:
        s[chave_json] = value
    else:
        s.pop(chave_json, None)
    save_settings(s)


def get_api_key() -> str:
    """A chave da IA DO PROVEDOR ATIVO. Atalho preservado: é lido em sete pontos do app."""
    return get_credencial("ai")


def set_api_key(value: str):
    return set_credencial("ai", value)


def _slots_persistidos() -> list[tuple[str, str, str]]:
    """(id, username, chave_json) de tudo que pode ter cópia em texto plano no JSON."""
    ids = ["openalex", "pubmed"] + [f"ai:{p}" for p in ENVS_IA]
    vistos, saida = set(), []
    for cred_id in ids:
        usuario, _, chave_json = _slot(cred_id)
        if usuario in vistos:
            continue
        vistos.add(usuario)
        saida.append((cred_id, usuario, chave_json))
    return saida


def migrate_credenciais_do_json() -> bool:
    """Credenciais em texto plano no JSON → keyring, APAGANDO do JSON. True se migrou alguma.

    A do OpenAlex nasceu no settings.json e ficou lá: quem já usa o app tem a chave legível
    em `~/Library/Application Support/blicsa/settings.json`. Esta migração a tira de lá na
    primeira leitura, sem o usuário precisar recolá-la.

    Cobre também os slots por provedor de IA, que é onde o app congelado grava: sem
    `keyring` no bundle ele cai no JSON, e a próxima abertura com keyring disponível
    recolhe o que ficou lá.
    """
    kr = _keyring()
    if kr is None:
        return False
    s = get_settings()
    migrou = False
    for cred_id, usuario, chave_json in _slots_persistidos():
        valor = s.get(chave_json)
        if not valor:
            continue
        try:
            kr.set_password(KEYRING_SERVICE, usuario, valor)
            s.pop(chave_json)
            migrou = True
            logger.info(f"[Settings] credencial '{cred_id}' migrada do settings.json "
                        f"para o keyring")
        except Exception as e:
            logger.warning(f"[Settings] migração de '{cred_id}' para o keyring falhou: {e}")
    if migrou:
        save_settings(s)
    return migrou


def migrate_api_key_from_json() -> bool:
    """Nome antigo, preservado: migra todas as credenciais, não só a da IA."""
    return migrate_credenciais_do_json()
