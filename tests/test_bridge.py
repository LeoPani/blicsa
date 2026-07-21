import json
import socket
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

import requests

from core.bridge import BridgeServer
from core.project import create_project, append_backlog, load_backlog


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


FIXTURE_RECORD = {
    "title": "Bibliometric networks in Python",
    "doi": "https://doi.org/10.1234/test",
    "authors": "Pani, L.; Smith, J.",
    "year": 2024,
    "keywords": "bibliometrics; python",
}


class TestBridgeServer(unittest.TestCase):
    def setUp(self):
        self.token = "test-secret-token"
        self.port = _free_port()
        self.server = BridgeServer(token=self.token, port=self.port)
        self.mock_on_add = MagicMock(return_value=42)
        self.server.set_callbacks(self.mock_on_add)
        self.server.start()
        time.sleep(0.1)

    def tearDown(self):
        self.server.stop()

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    # ── /api/status: token Bearer ─────────────────────────────────────────
    def test_status_unauthorized(self):
        resp = requests.get(self._url("/api/status"))
        self.assertEqual(resp.status_code, 401)

    def test_status_authorized(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(self._url("/api/status"), headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok", "version": "1.0"})

    def test_status_wrong_token(self):
        headers = {"Authorization": "Bearer nope"}
        resp = requests.get(self._url("/api/status"), headers=headers)
        self.assertEqual(resp.status_code, 401)

    # ── /api/add: lookup EXATO por DOI (get_by_doi), não busca textual ─────
    @patch("core.bridge.OpenAlexProvider")
    def test_add_uses_get_by_doi(self, MockProvider):
        inst = MockProvider.return_value
        inst.get_by_doi.return_value = dict(FIXTURE_RECORD)

        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"doi": "10.1234/test", "source_url": "https://doi.org/10.1234/test"}
        resp = requests.post(self._url("/api/add"), json=payload, headers=headers)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["added"], 1)
        self.assertEqual(data["count"], 42)
        # Usou o lookup por DOI, NÃO a busca textual.
        inst.get_by_doi.assert_called_once_with("10.1234/test")
        inst.search.assert_not_called()
        # A URL de origem chega ao registro entregue ao callback.
        record = self.mock_on_add.call_args[0][0]
        self.assertEqual(record["title"], FIXTURE_RECORD["title"])
        self.assertEqual(record["origin_url"], "https://doi.org/10.1234/test")

    @patch("core.bridge.OpenAlexProvider")
    def test_add_fallback_to_title_when_doi_fails(self, MockProvider):
        inst = MockProvider.return_value
        inst.get_by_doi.return_value = None  # DOI não resolve
        inst.search.return_value = iter([dict(FIXTURE_RECORD)])

        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"doi": "10.9999/broken", "title": "Bibliometric networks",
                   "authors": "Pani, L.; Smith, J."}
        resp = requests.post(self._url("/api/add"), json=payload, headers=headers)

        self.assertEqual(resp.status_code, 200)
        inst.get_by_doi.assert_called_once()
        inst.search.assert_called_once()  # caiu para o fallback título+autor

    @patch("core.bridge.OpenAlexProvider")
    def test_add_no_auto_dedup(self, MockProvider):
        """O bridge adiciona sempre: duas chamadas do MESMO DOI => callback 2x
        (dedup é ação explícita no app, nunca automática)."""
        inst = MockProvider.return_value
        inst.get_by_doi.return_value = dict(FIXTURE_RECORD)

        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"doi": "10.1234/test"}
        requests.post(self._url("/api/add"), json=payload, headers=headers)
        requests.post(self._url("/api/add"), json=payload, headers=headers)
        self.assertEqual(self.mock_on_add.call_count, 2)

    def test_add_unauthorized(self):
        resp = requests.post(self._url("/api/add"), json={"doi": "10.1/x"})
        self.assertEqual(resp.status_code, 401)


class TestBridgePortFallback(unittest.TestCase):
    def test_port_fallback_when_busy(self):
        """Porta ocupada → o boot tenta a próxima (espelha o loop de _start_bridge)."""
        p = _free_port()
        busy = BridgeServer("t", p)
        busy.start()
        try:
            chosen = None
            for cand in (p, p + 1, p + 2, p + 3):
                srv = BridgeServer("t", cand)
                try:
                    srv.start()
                except OSError:
                    continue
                chosen = cand
                srv.stop()
                break
            self.assertNotEqual(chosen, p)  # p estava ocupada
            self.assertEqual(chosen, p + 1)
        finally:
            busy.stop()


class TestExtensionBacklog(unittest.TestCase):
    def test_backlog_extension_add(self):
        tmp = tempfile.mkdtemp()
        slug = create_project("Projeto Extensao", projects_dir=tmp)
        detail = {"doi": "10.1234/test", "titulo": "Bibliometric networks",
                  "origem_url": "https://doi.org/10.1234/test"}
        append_backlog(slug, "extension_add", detail, projects_dir=tmp)

        entries = load_backlog(slug, projects_dir=tmp)
        ext = [e for e in entries if e["action"] == "extension_add"]
        self.assertEqual(len(ext), 1)
        self.assertEqual(ext[0]["detail"]["doi"], "10.1234/test")
        self.assertIn("origem_url", ext[0]["detail"])


if __name__ == "__main__":
    unittest.main()
