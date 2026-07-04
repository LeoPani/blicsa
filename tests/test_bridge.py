import unittest
import threading
import requests
import json
import time
from unittest.mock import patch, MagicMock

from core.bridge import BridgeServer

class TestBridgeServer(unittest.TestCase):
    def setUp(self):
        self.token = "test-secret-token"
        self.port = 8766  # Use a different port for testing
        self.server = BridgeServer(token=self.token, port=self.port)
        
        self.mock_on_add = MagicMock(return_value=42)
        self.mock_on_expand = MagicMock(return_value={"status": "expanded"})
        
        self.server.set_callbacks(self.mock_on_add, self.mock_on_expand)
        self.server.start()
        
        # Give it a moment to start
        time.sleep(0.1)

    def tearDown(self):
        self.server.stop()
        
    def test_status_unauthorized(self):
        resp = requests.get(f"http://127.0.0.1:{self.port}/api/status")
        self.assertEqual(resp.status_code, 401)
        
    def test_status_authorized(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(f"http://127.0.0.1:{self.port}/api/status", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok", "version": "1.0"})
        
    @patch('core.bridge.OpenAlexProvider')
    def test_add_record_success(self, MockProvider):
        # Setup mock provider
        mock_instance = MockProvider.return_value
        mock_instance.search.return_value = iter([{
            "title": "Test Paper",
            "doi": "10.1234/test",
            "year": 2023
        }])
        
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"doi": "10.1234/test"}
        
        resp = requests.post(f"http://127.0.0.1:{self.port}/api/add", json=payload, headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["added"], 1)
        self.assertEqual(data["count"], 42)
        self.assertEqual(data["title"], "Test Paper")
        
        # Verify callback was called
        self.mock_on_add.assert_called_once()
        called_record = self.mock_on_add.call_args[0][0]
        self.assertEqual(called_record["title"], "Test Paper")

if __name__ == '__main__':
    unittest.main()
