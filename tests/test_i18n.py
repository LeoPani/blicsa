import unittest
import json
import os

class TestI18nCompatibility(unittest.TestCase):

    def test_keys_match(self):
        # Locate files
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        locales_dir = os.path.join(base_dir, "locales")
        
        en_path = os.path.join(locales_dir, "en.json")
        pt_path = os.path.join(locales_dir, "pt_BR.json")
        
        self.assertTrue(os.path.exists(en_path), "en.json should exist")
        self.assertTrue(os.path.exists(pt_path), "pt_BR.json should exist")
        
        with open(en_path, "r", encoding="utf-8") as f:
            en_data = json.load(f)
            
        with open(pt_path, "r", encoding="utf-8") as f:
            pt_data = json.load(f)
            
        en_keys = set(en_data.keys())
        pt_keys = set(pt_data.keys())
        
        # Check that both catalogs have exactly the same keys
        missing_in_pt = en_keys - pt_keys
        missing_in_en = pt_keys - en_keys
        
        self.assertEqual(len(missing_in_pt), 0, f"Keys present in en.json but missing in pt_BR.json: {missing_in_pt}")
        self.assertEqual(len(missing_in_en), 0, f"Keys present in pt_BR.json but missing in en.json: {missing_in_en}")

if __name__ == '__main__':
    unittest.main()


# ── Navegação e tela de boas-vindas totalmente traduzidas ──────────────────

def test_nav_and_welcome_keys_exist_in_every_catalog():
    """As chaves da barra lateral e da tela de boas-vindas existem nos 3 catálogos.

    Antes, 5 rótulos da navegação e os 3 textos da tela de boas-vindas eram literais em
    português — a barra lateral aparecia meio traduzida em en/fr, e a PRIMEIRA tela do app
    ficava toda em português.
    """
    import json
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent / "locales"
    obrigatorias = ("nav.collect", "nav.stats", "nav.analyses", "nav.gallery", "nav.export",
                    "welcome.subtitle", "welcome.new", "welcome.load")
    for cat in ("pt_BR", "en", "fr"):
        d = json.loads((base / f"{cat}.json").read_text(encoding="utf-8"))
        for chave in obrigatorias:
            assert chave in d, f"{cat}.json não tem {chave}"
            assert str(d[chave]).strip(), f"{cat}.json tem {chave} vazia"


def test_nav_labels_are_not_hardcoded_portuguese():
    """O fonte da navegação não pode voltar a trazer rótulo literal em português.

    "Blink" e "Corpus" seguem literais de propósito (iguais nos três idiomas).
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    # A lista saiu de dentro do `for` para poder ser contada (as linhas do rodapé da barra
    # lateral derivam do tamanho dela). A âncora do teste acompanha.
    inicio = src.index("itens_de_navegacao = [")
    bloco = src[inicio:src.index("]\n        for i, (key", inicio)]
    for literal in ('"Coletar"', '"Estatísticas"', '"Análises"', '"Galeria"', '"Exportar"',
                    '"Relatório"'):
        assert literal not in bloco, f"rótulo voltou a ser hardcoded na navegação: {literal}"
    assert 't("nav.collect")' in bloco and 't("nav.export")' in bloco
    assert 't("nav.relatorio")' in bloco


def test_welcome_screen_uses_catalog_and_zero_corner_radius():
    """A tela de boas-vindas usa o catálogo e respeita o canto zero do design system."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    inicio = src.index("def _build_welcome_screen")
    corpo = src[inicio:src.index("def _build_layout", inicio)]
    assert 't("welcome.subtitle")' in corpo and 't("welcome.new")' in corpo
    assert "Bem-vindo! Inicie" not in corpo, "texto de boas-vindas voltou a ser hardcoded"
    assert "corner_radius=20" not in corpo, (
        "os cards da tela de boas-vindas voltaram a ter canto arredondado — "
        "o design system exige canto zero")


# ── Seletor de idioma só oferece o que existe ──────────────────────────────

def test_language_selector_only_offers_languages_that_have_a_catalog(tmp_path, monkeypatch):
    """O seletor não pode oferecer idioma sem catálogo.

    Havia uma bandeira alemã fixa no código, mas `de.json` fora removido por quebrar a
    paridade. Clicar não quebrava — caía no fallback inglês — mas gravava `lang="de"`, e o
    app ficava em inglês dizendo que estava em alemão.
    """
    import main
    from core.i18n import available_langs

    disponiveis = available_langs()
    assert "de" not in disponiveis, "de.json não existe; não deveria ser oferecido"
    assert disponiveis[:3] == ["pt_BR", "en", "fr"], f"ordem inesperada: {disponiveis}"

    oferecidos = [l for l, _ in main._flag_options()]
    assert oferecidos == disponiveis, (
        f"o seletor oferece {oferecidos} mas só existem {disponiveis}")
    assert "de" not in oferecidos


def test_flag_selector_follows_the_catalogs_present(monkeypatch, tmp_path):
    """Criar um catálogo reativa a bandeira sozinho; removê-lo tira a opção da tela."""
    import core.i18n as i18n
    import main

    falsa = tmp_path / "locales"
    falsa.mkdir()
    for nome in ("pt_BR", "en", "fr", "de"):
        (falsa / f"{nome}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(i18n, "locales_dir", lambda: str(falsa))
    assert "de" in [l for l, _ in main._flag_options()], "catálogo novo deveria aparecer"

    (falsa / "de.json").unlink()
    assert "de" not in [l for l, _ in main._flag_options()], "catálogo removido deveria sumir"


def test_available_langs_survives_a_missing_locales_dir(monkeypatch):
    """Diretório de locales ausente não pode derrubar o app — cai no inglês."""
    import core.i18n as i18n

    monkeypatch.setattr(i18n, "locales_dir", lambda: "/caminho/que/nao/existe")
    assert i18n.available_langs() == ["en"]
