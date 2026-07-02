import locale
import json
import os
from typing import Dict, Any

_translations: Dict[str, str] = {}
_fallback_translations: Dict[str, str] = {}

def get_system_language() -> str:
    try:
        lang, _ = locale.getdefaultlocale()
        if lang:
            return lang
    except Exception:
        pass
    return "en"

def load_locales():
    global _translations, _fallback_translations
    # Try finding locales folder relative to this file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "locales")
    
    # Load fallback (English)
    en_path = os.path.join(locales_dir, "en.json")
    if os.path.exists(en_path):
        try:
            with open(en_path, "r", encoding="utf-8") as f:
                _fallback_translations = json.load(f)
        except Exception as e:
            print(f"[i18n] Error loading en.json: {e}")
            
    # Load system language
    sys_lang = get_system_language()
    lang_file = "en.json"
    if sys_lang.startswith("pt"):
        lang_file = "pt_BR.json"
        
    lang_path = os.path.join(locales_dir, lang_file)
    if os.path.exists(lang_path):
        try:
            with open(lang_path, "r", encoding="utf-8") as f:
                _translations = json.load(f)
        except Exception as e:
            print(f"[i18n] Error loading {lang_file}: {e}")
            _translations = _fallback_translations
    else:
        _translations = _fallback_translations

def t(key: str, **kwargs) -> str:
    val = _translations.get(key)
    if val is None:
        val = _fallback_translations.get(key, key)
    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            pass
    return val

# Automatically load on import
load_locales()
