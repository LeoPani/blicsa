"""Coloca a raiz do repositório no `sys.path` para a suíte de testes.

Sem isto, `pytest tests/` falha com `ModuleNotFoundError: No module named 'core'`, enquanto
`python -m pytest tests/` funciona — a diferença é que `python -m` insere o diretório atual no
`sys.path` e o executável `pytest` não. O projeto não é instalado como pacote (roda de dentro
do diretório, via `python3 main.py`), então nada mais coloca a raiz lá.

O custo dessa diferença foi concreto: o CI chamava `pytest tests/` e quebrava na coleção dos
32 módulos de teste, mas isso ficou **escondido atrás de outra falha** — o build já morria
antes, em `Install dependencies`, por causa da matriz com Python 3.10. Corrigida a primeira
camada, a segunda apareceu.

Um `conftest.py` na raiz resolve para as duas formas de invocar, inclusive a de quem clona o
repositório e digita `pytest` por hábito.
"""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


class _KeyringDeMentira:
    """Cofre em memória com a interface que `core.settings` usa do keyring."""

    def __init__(self):
        self._cofre: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._cofre.get((service, username))

    def set_password(self, service, username, value):
        self._cofre[(service, username)] = value

    def delete_password(self, service, username):
        if (service, username) not in self._cofre:
            raise KeyError("nada a apagar")
        del self._cofre[(service, username)]


@pytest.fixture(autouse=True)
def configuracao_isolada(tmp_path, monkeypatch):
    """Nenhum teste toca o settings.json nem o keyring REAIS da máquina.

    Isto não é zelo preventivo, é conserto. `tests/test_ai_onboarding.py` tentava se isolar
    com

        monkeypatch.setattr(cs, "SETTINGS_PATH", tmp_path / "settings.json", raising=False)
        monkeypatch.setattr(cs, "_settings_cache", None, raising=False)

    e `core/settings.py` nunca teve nenhum dos dois nomes — tem `settings_path()` e
    `_OVERRIDE_PATH`. Com `raising=False` o monkeypatch cria atributos novos, ninguém lê, e
    o isolamento é decorativo: os testes gravavam a `CHAVE_FALSA` no
    `~/Library/Application Support/blicsa/settings.json` de verdade. No start seguinte,
    `migrate_api_key_from_json()` a promovia ao keyring do SO e **sobrescrevia a chave real
    do usuário**. Rodar a suíte desconfigurava o app, e o sintoma aparecia longe da causa:
    o Blink dizia estar configurado e devolvia 401.

    Autouse de propósito. Isolar só os módulos que hoje escrevem deixaria a próxima
    escrita — a de um teste que ainda não existe — livre para repetir o estrago.
    """
    import core.settings as cs

    monkeypatch.setattr(cs, "_OVERRIDE_PATH", tmp_path / "settings.json")
    cofre = _KeyringDeMentira()
    monkeypatch.setattr(cs, "_keyring", lambda: cofre)
    # `get_api_key()` lê o ambiente ANTES do keyring. Sem limpar, a chave real da máquina
    # de quem roda a suíte vaza para dentro dos testes — e para as mensagens de falha.
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    return cofre
