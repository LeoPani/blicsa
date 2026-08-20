"""Settings do Blicsa — API única, no diretório de CONFIGURAÇÃO DO USUÁRIO.

Antes o .blicsa_settings.json era gravado em os.path.dirname(__file__) (o
diretório do CÓDIGO): num app instalado/congelado (PyInstaller, /Applications)
isso é somente-leitura e salvar settings falhava. Agora:

- settings.json em platformdirs.user_config_dir("blicsa")
  (macOS: ~/Library/Application Support/blicsa/)
- migração automática do arquivo legado na primeira leitura
- API key da IA no KEYRING do SO (service "blicsa", username "ai_api_key"),
  com fallback transparente para o settings.json quando não há keyring
  (headless/CI); env AI_API_KEY/GROQ_API_KEY tem precedência (fluxo dev)
- toda escrita com context manager
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("blicsa.settings")

APP_NAME = "blicsa"
KEYRING_SERVICE = "blicsa"
KEYRING_USERNAME = "ai_api_key"

#: Credenciais que o app guarda, por id → (username no keyring, envs que têm precedência).
#:
#: A chave da IA já morava no keyring; a do OpenAlex morava em TEXTO PLANO no settings.json
#: (`openalex_api_key`) e a do PubMed não existia. Um registro único evita que a próxima
#: credencial invente um terceiro lugar — que foi como a dispersão começou.
CREDENCIAIS = {
    "ai":       (KEYRING_USERNAME,     ("AI_API_KEY", "GROQ_API_KEY")),
    "openalex": ("openalex_api_key",   ("OPENALEX_API_KEY",)),
    "pubmed":   ("pubmed_api_key",     ("NCBI_API_KEY", "PUBMED_API_KEY")),
}

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


# ── API key no keyring (com fallback transparente) ─────────────────────────
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
    usuario, envs = CREDENCIAIS[nome]
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
    return str(get_settings().get(_CHAVE_JSON[nome]) or "")


def set_credencial(nome: str, value: str):
    """Grava no keyring; sem keyring, cai para o settings.json. Nunca loga o valor."""
    usuario, _ = CREDENCIAIS[nome]
    chave_json = _CHAVE_JSON[nome]
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


#: Nome da chave no settings.json, por credencial. Difere do username do keyring por
#: acidente histórico: a da IA era gravada como `api_key` e a do OpenAlex como
#: `openalex_api_key`. Migrar o nome quebraria a leitura de quem já tem o arquivo.
_CHAVE_JSON = {"ai": "api_key", "openalex": "openalex_api_key", "pubmed": "pubmed_api_key"}


def get_api_key() -> str:
    """A chave da IA. Atalho preservado: é lido em sete pontos do app."""
    return get_credencial("ai")


def set_api_key(value: str):
    return set_credencial("ai", value)


def migrate_credenciais_do_json() -> bool:
    """Credenciais em texto plano no JSON → keyring, APAGANDO do JSON. True se migrou alguma.

    A do OpenAlex nasceu no settings.json e ficou lá: quem já usa o app tem a chave legível
    em `~/Library/Application Support/blicsa/settings.json`. Esta migração a tira de lá na
    primeira leitura, sem o usuário precisar recolá-la.
    """
    kr = _keyring()
    if kr is None:
        return False
    s = get_settings()
    migrou = False
    for nome, (usuario, _) in CREDENCIAIS.items():
        chave_json = _CHAVE_JSON[nome]
        valor = s.get(chave_json)
        if not valor:
            continue
        try:
            kr.set_password(KEYRING_SERVICE, usuario, valor)
            s.pop(chave_json)
            migrou = True
            logger.info(f"[Settings] credencial '{nome}' migrada do settings.json "
                        f"para o keyring")
        except Exception as e:
            logger.warning(f"[Settings] migração de '{nome}' para o keyring falhou: {e}")
    if migrou:
        save_settings(s)
    return migrou


def migrate_api_key_from_json() -> bool:
    """Nome antigo, preservado: migra todas as credenciais, não só a da IA."""
    return migrate_credenciais_do_json()
