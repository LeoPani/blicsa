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


def get_api_key() -> str:
    """Precedência: env (dev) → keyring → settings.json (fallback sem keyring)."""
    env = os.environ.get("AI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if env:
        return env
    migrate_api_key_from_json()  # idempotente e barato quando não há nada a migrar
    kr = _keyring()
    if kr is not None:
        try:
            v = kr.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if v:
                return v
        except Exception as e:
            logger.warning(f"[Settings] keyring indisponível na leitura: {e}")
    return str(get_settings().get("api_key") or "")


def set_api_key(value: str):
    """Grava no keyring; sem keyring, cai para o settings.json. Nunca loga a chave."""
    value = (value or "").strip()
    kr = _keyring()
    if kr is not None:
        try:
            if value:
                kr.set_password(KEYRING_SERVICE, KEYRING_USERNAME, value)
            else:
                try:
                    kr.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
                except Exception:
                    pass
            # garante que não sobra cópia em texto plano no JSON
            s = get_settings()
            if "api_key" in s:
                s.pop("api_key")
                save_settings(s)
            return
        except Exception as e:
            logger.warning(f"[Settings] keyring indisponível na escrita: {e}")
    s = get_settings()
    if value:
        s["api_key"] = value
    else:
        s.pop("api_key", None)
    save_settings(s)


def migrate_api_key_from_json() -> bool:
    """Chave no JSON (texto plano) → keyring, APAGANDO do JSON. True se migrou."""
    kr = _keyring()
    if kr is None:
        return False
    s = get_settings()
    key = s.get("api_key")
    if not key:
        return False
    try:
        kr.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
        s.pop("api_key")
        save_settings(s)
        logger.info("[Settings] API key migrada do settings.json para o keyring")
        return True
    except Exception as e:
        logger.warning(f"[Settings] migração da chave para o keyring falhou: {e}")
        return False
