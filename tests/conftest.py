"""
Infraestrutura compartilhada da suíte de testes de busca (níveis 1 e 2).

Nível 1 (offline): fixtures JSON com respostas REAIS gravadas das 3 APIs
(ver tests/fixtures/README.md). Servidas por um mock de
`core.sources.base.SearchProvider.fetch_url`, que devolve os corpos brutos na
ordem em que o provider os requisita (side_effect). Determinístico, sem rede.

Nível 2 (live): marcados @pytest.mark.live, excluídos por padrão via addopts em
pytest.ini. Rodar com `pytest -m live`.
"""
import json
import os
from unittest.mock import patch

import pytest

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> str:
    """Retorna o corpo bruto (string) exatamente como a API respondeu."""
    with open(os.path.join(FIX_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)["body"]


def load_fixture_url(name: str) -> str:
    """Retorna a URL real usada para gravar a fixture (para auditoria)."""
    with open(os.path.join(FIX_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)["url"]


class FetchRecorder:
    """
    Substitui SearchProvider.fetch_url devolvendo os corpos das fixtures na
    ordem `bodies`. Registra as URLs que o provider tentou buscar, para que os
    testes possam validar a construção de query.
    """

    def __init__(self, bodies):
        self._bodies = list(bodies)
        self.calls = []
        self._i = 0

    def __call__(self, _self, url, headers=None, cancel_event=None, rate_limit_delay=0.0, **kwargs):
        # Respeita cancelamento como o fetch_url real faz.
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Search cancelled by user")
        self.calls.append(url)
        if self._i >= len(self._bodies):
            raise AssertionError(
                f"Provider pediu mais páginas ({self._i + 1}) do que a fixture fornece "
                f"({len(self._bodies)}). URL: {url}"
            )
        body = self._bodies[self._i]
        self._i += 1
        return body


def serve(bodies):
    """
    Context manager: faz fetch_url servir `bodies` (str ou lista de str) na ordem.
    Uso:
        with serve([load_fixture("x.json")]) as rec:
            list(provider.search(...))
            assert "filter=" in rec.calls[0]
    """
    if isinstance(bodies, str):
        bodies = [bodies]
    recorder = FetchRecorder(bodies)
    patcher = patch(
        "core.sources.base.SearchProvider.fetch_url",
        autospec=True,
        side_effect=recorder,
    )

    class _Ctx:
        def __enter__(self):
            patcher.start()
            return recorder

        def __exit__(self, *a):
            patcher.stop()
            return False

    return _Ctx()


# --- Marcador 'live': registrado aqui também, além do pytest.ini, por robustez ---
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: testes que batem nas APIs reais (rodar com pytest -m live)",
    )
