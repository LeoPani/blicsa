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


# ── Um slot de chave por provedor de IA ─────────────────────────────────────────

@pytest.fixture
def cofre(isolated, monkeypatch):
    """Keyring falso e ambiente limpo: nenhuma env de provedor vencendo o cofre."""
    store = {}
    monkeypatch.setattr(cs, "_keyring", lambda: _fake_keyring(store))
    for env in ("AI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                "OLLAMA_API_KEY", "AI_PROVIDER", "AI_BASE_URL", "AI_MODEL"):
        monkeypatch.delenv(env, raising=False)
    return store


def test_cada_provedor_guarda_a_propria_chave(cofre):
    """Trocar de provedor não pode apagar a chave do anterior.

    Com slot único, configurar a OpenAI sobrescrevia a do Groq: voltar ao Groq exigia
    recolar a chave, e o usuário lia isso como o app esquecendo credencial.
    """
    cs.set_config_ia("groq")
    cs.set_api_key("chave_do_groq")
    cs.set_config_ia("openai")
    cs.set_api_key("chave_da_openai")

    assert cs.get_api_key() == "chave_da_openai"
    cs.set_config_ia("groq")
    assert cs.get_api_key() == "chave_do_groq", "a chave do Groq foi sobrescrita"


def test_o_groq_reaproveita_o_slot_historico(cofre):
    """Quem já tinha chave em `ai_api_key` a encontra sem recolar."""
    cofre[("blicsa", "ai_api_key")] = "chave_antiga"
    assert cs.provedor_ia() == "groq"
    assert cs.get_api_key() == "chave_antiga"


def test_a_env_de_um_provedor_nao_vale_para_outro(cofre, monkeypatch):
    """`GROQ_API_KEY` esquecida no ambiente não pode virar a chave da OpenAI.

    A precedência de env é do fluxo dev; aplicá-la a todos os provedores faria o app usar
    uma credencial que o usuário não escolheu, contra um endpoint que não é o dela.
    """
    monkeypatch.setenv("GROQ_API_KEY", "do_ambiente")
    cs.set_config_ia("openai")
    cs.set_api_key("chave_da_openai")

    assert cs.get_api_key() == "chave_da_openai"
    cs.set_config_ia("groq")
    assert cs.get_api_key() == "do_ambiente", "a env genérica de dev deixou de valer"


def test_o_provedor_e_seus_parametros_sobrevivem_ao_reinicio(cofre):
    """O defeito central: nada disso era gravado e tudo voltava ao Groq a cada abertura."""
    cs.set_config_ia("openai")

    prov, base, modelo = cs.config_ia()
    assert prov == "openai"
    assert "openai.com" in base
    assert "groq" not in base.lower(), "a URL base seguiu no Groq com o provedor em OpenAI"


def test_so_o_que_diverge_do_preset_e_gravado(cofre):
    """Preset gravado no JSON congelaria correções futuras do código."""
    _, base_preset, _ = _preset_do("openai")
    cs.set_config_ia("openai", base_preset, "gpt-4o-mini")

    s = cs.get_settings()
    assert "ai_base_url" not in s, "a URL igual ao preset foi gravada"
    assert s["ai_model"] == "gpt-4o-mini"
    assert cs.config_ia() == ("openai", base_preset, "gpt-4o-mini")


def _preset_do(provedor):
    from core.credenciais import PROVEDORES_IA
    return PROVEDORES_IA[provedor]


def test_migracao_recolhe_a_chave_de_provedor_do_json(cofre):
    """O app congelado sem keyring grava no JSON; a abertura com cofre precisa recolher.

    Sem isto a chave da OpenAI ficaria legível em texto plano no settings.json para
    sempre — a migração só olhava os três slots antigos.
    """
    cs.save_settings({"ai_provider": "openai", "api_key_openai": "em_texto_plano"})

    assert cs.get_api_key() == "em_texto_plano"
    assert cofre[("blicsa", "ai_api_key_openai")] == "em_texto_plano"
    assert "api_key_openai" not in cs.get_settings()


def test_language_fallback_without_getdefaultlocale(monkeypatch):
    from core import i18n
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.get_system_language() == "fr_FR"
    monkeypatch.delenv("LANG")
    assert i18n.get_system_language() == "en"
