"""
Verificação do i18n do Blink (piloto): a diretiva de idioma do system prompt e a
diferenciação da saudação entre catálogos. Não instancia a UI (CTk) — replica a
lógica de `BlicsaApp._blink_system_prompt` (main.py) de forma pura, referenciando-a
explicitamente para permanecer fiel.
"""
import json
import os

import pytest

from core import i18n

LOCALES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")

# Espelha main.py::_blink_system_prompt (mapa de nomes de idioma).
LANG_NAMES = {"pt_BR": "Brazilian Portuguese", "en": "English", "fr": "French"}


def blink_system_prompt() -> str:
    base = i18n.t("blink.system_prompt")
    target = LANG_NAMES.get(i18n.get_lang(), "English")
    directive = (f"IMPORTANT: Always respond to the user in {target}, "
                 f"regardless of the language of this prompt.")
    return f"{base}\n\n{directive}"


@pytest.mark.parametrize("lang,expected", [
    ("pt_BR", "Brazilian Portuguese"),
    ("en", "English"),
    ("fr", "French"),
])
def test_blink_directive_language(lang, expected):
    i18n.set_lang(lang)
    prompt = blink_system_prompt()
    assert f"respond to the user in {expected}" in prompt
    # não deve conter a diretiva de outro idioma
    for other in set(LANG_NAMES.values()) - {expected}:
        assert f"respond to the user in {other}" not in prompt


def test_get_lang_reflects_set_lang():
    for lang in ("pt_BR", "en", "fr"):
        i18n.set_lang(lang)
        assert i18n.get_lang() == lang


def test_blink_saudacao_differs_across_catalogs():
    saud = {}
    for lang in ("pt_BR", "en", "fr"):
        with open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf-8") as f:
            saud[lang] = json.load(f)["blink.saudacao"]
    # As três saudações devem ser distintas (traduzidas de fato, não copiadas).
    assert len({saud["pt_BR"], saud["en"], saud["fr"]}) == 3, saud


def test_all_pilot_keys_present_in_all_catalogs():
    keys = [
        "settings.ok", "blink.titulo_1", "blink.titulo_destaque", "blink.titulo_2",
        "blink.voltar", "blink.system_prompt", "blink.saudacao", "blink.placeholder",
        "blink.rag_contexto", "blink.erro", "blink.enviar",
        "blink.sugestao_1", "blink.sugestao_2", "blink.sugestao_3",
    ]
    for lang in ("pt_BR", "en", "fr"):
        with open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf-8") as f:
            cat = json.load(f)
        missing = [k for k in keys if k not in cat]
        assert not missing, f"{lang} faltando: {missing}"
