"""Passo 4 — core/settings.py: paths injetáveis, migrações e fallback de idioma."""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.settings as cs


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Settings novo e legado apontando para tmp_path (nada toca o SO real)."""
    new_path = tmp_path / "config" / "settings.json"
    legacy = tmp_path / "repo" / ".blicsa_settings.json"
    legacy.parent.mkdir(parents=True)
    monkeypatch.setattr(cs, "_OVERRIDE_PATH", new_path)
    monkeypatch.setattr(cs, "LEGACY_PATH", legacy)
    return new_path, legacy


def test_save_and_get_roundtrip(isolated):
    new_path, _ = isolated
    cs.save_settings({"lang": "fr", "reduce_animations": True})
    assert new_path.exists()
    s = cs.get_settings()
    assert s == {"lang": "fr", "reduce_animations": True}


def test_settings_path_uses_override(isolated):
    new_path, _ = isolated
    assert cs.settings_path() == new_path


def test_legacy_migration_copies_once_and_logs(isolated, caplog):
    new_path, legacy = isolated
    legacy.write_text(json.dumps({"lang": "pt_BR"}), encoding="utf-8")
    import logging
    with caplog.at_level(logging.INFO, logger="blicsa.settings"):
        s = cs.get_settings()
    assert s["lang"] == "pt_BR"
    assert new_path.exists()
    assert any("migrado" in r.message for r in caplog.records)
    # segunda leitura NÃO migra de novo (novo já existe)
    cs.save_settings({"lang": "en"})
    assert cs.get_settings()["lang"] == "en"


def _fake_keyring(store):
    kr = MagicMock()
    kr.get_password = lambda svc, usr: store.get((svc, usr))
    kr.set_password = lambda svc, usr, val: store.__setitem__((svc, usr), val)
    kr.delete_password = lambda svc, usr: store.pop((svc, usr), None)
    return kr


def test_api_key_migrates_from_json_to_keyring(isolated, monkeypatch):
    new_path, _ = isolated
    cs.save_settings({"api_key": "gsk_plaintext_123", "lang": "en"})
    store = {}
    monkeypatch.setattr(cs, "_keyring", lambda: _fake_keyring(store))
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    assert cs.get_api_key() == "gsk_plaintext_123"
    # migrou para o keyring e APAGOU do JSON
    assert store[("blicsa", "ai_api_key")] == "gsk_plaintext_123"
    assert "api_key" not in cs.get_settings()


def test_set_api_key_prefers_keyring_and_purges_json(isolated, monkeypatch):
    store = {}
    monkeypatch.setattr(cs, "_keyring", lambda: _fake_keyring(store))
    cs.save_settings({"api_key": "velha"})
    cs.set_api_key("nova_chave")
    assert store[("blicsa", "ai_api_key")] == "nova_chave"
    assert "api_key" not in cs.get_settings()


def test_api_key_fallback_to_json_without_keyring(isolated, monkeypatch):
    monkeypatch.setattr(cs, "_keyring", lambda: None)  # headless/CI
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cs.set_api_key("chave_ci")
    assert cs.get_settings()["api_key"] == "chave_ci"
    assert cs.get_api_key() == "chave_ci"


def test_env_has_precedence(isolated, monkeypatch):
    store = {("blicsa", "ai_api_key"): "do_keyring"}
    monkeypatch.setattr(cs, "_keyring", lambda: _fake_keyring(store))
    monkeypatch.setenv("AI_API_KEY", "da_env")
    assert cs.get_api_key() == "da_env"


def test_language_fallback_without_getdefaultlocale(monkeypatch):
    from core import i18n
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.get_system_language() == "fr_FR"
    monkeypatch.delenv("LANG")
    assert i18n.get_system_language() == "en"
