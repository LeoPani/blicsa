import locale
import json
import os
from typing import Dict, Any

_translations: Dict[str, str] = {}
_fallback_translations: Dict[str, str] = {}
_current_lang = "en"

def get_system_language() -> str:
    try:
        lang, _ = locale.getdefaultlocale()
        if lang:
            return lang
    except Exception:
        pass
    return "en"

def _load_dict(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[i18n] Error loading {path}: {e}")
    return {}

def load_locales(lang_code: str = None):
    global _translations, _fallback_translations, _current_lang
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "locales")
    
    # Fallback is always English
    en_path = os.path.join(locales_dir, "en.json")
    _fallback_translations = _load_dict(en_path)
    
    if not lang_code:
        # Load from settings if available
        settings_path = os.path.join(base_dir, ".blicsa_settings.json")
        if os.path.exists(settings_path):
            s = _load_dict(settings_path)
            lang_code = s.get("lang")
            
        if not lang_code:
            sys_lang = get_system_language().lower()
            if sys_lang.startswith("pt"):
                lang_code = "pt_BR"
            elif sys_lang.startswith("fr"):
                lang_code = "fr"
            else:
                lang_code = "en"
                
    _current_lang = lang_code
    
    lang_file = f"{lang_code}.json"
    lang_path = os.path.join(locales_dir, lang_file)
    _translations = _load_dict(lang_path)
    if not _translations:
        _translations = _fallback_translations

def t(key: str, **kwargs) -> str:
    val = _translations.get(key)
    if val is None:
        print(f"[i18n] Warning: Missing key '{key}' in {_current_lang}. Falling back to en.")
        val = _fallback_translations.get(key, key)
    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            pass
    return val

def set_lang(lang_code: str):
    load_locales(lang_code)
    # Save to settings
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings_path = os.path.join(base_dir, ".blicsa_settings.json")
    s = _load_dict(settings_path)
    s["lang"] = lang_code
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)

# Automatically load on import
load_locales()
