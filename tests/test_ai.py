import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import io
import json

from ai.client import call_openai_chat, AIAnalyst

class TestAIClient(unittest.TestCase):

    @patch('urllib.request.urlopen')
    def test_call_openai_chat_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": "Mocked AI Response"
                    }
                }
            ]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        response = call_openai_chat(
            base_url="https://api.openai.com/v1",
            api_key="sk-testkey1234567890abcdef",
            model="gpt-4o",
            system_prompt="Test System",
            user_prompt="Test User"
        )

        self.assertEqual(response, "Mocked AI Response")
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.headers["Authorization"], "Bearer sk-testkey1234567890abcdef")
        self.assertEqual(req.headers["Content-type"], "application/json")

    @patch('urllib.request.urlopen')
    def test_call_openai_chat_rate_limiting_retry(self, mock_urlopen):
        mock_error = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        
        mock_success = MagicMock()
        mock_success.read.return_value = json.dumps({
            "choices": [
                {"message": {"content": "Success After Retry"}}
            ]
        }).encode('utf-8')
        mock_success.__enter__.return_value = mock_success

        mock_urlopen.side_effect = [mock_error, mock_success]

        with patch('time.sleep') as mock_sleep:
            response = call_openai_chat(
                base_url="https://api.openai.com/v1",
                api_key="sk-key",
                model="gpt-4o",
                system_prompt="Test",
                user_prompt="Test"
            )
            self.assertEqual(response, "Success After Retry")
            mock_sleep.assert_called_once()

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('urllib.request.urlopen')
    def test_key_redaction_in_logs(self, mock_urlopen, mock_stdout):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Ok"}}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        call_openai_chat(
            base_url="https://api.openai.com/v1",
            api_key="gsk_very_long_secret_key_12345",
            model="gpt-4",
            system_prompt="Test",
            user_prompt="Test"
        )

        log_output = mock_stdout.getvalue()
        self.assertNotIn("very_long_secret_key", log_output)
        self.assertIn("gsk_ve...2345", log_output)

    def test_ai_analyst_presets(self):
        analyst = AIAnalyst(api_key="gsk_test", base_url="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile")
        self.assertEqual(analyst.base_url, "https://api.groq.com/openai/v1")
        self.assertEqual(analyst.model, "llama-3.3-70b-versatile")

if __name__ == '__main__':
    unittest.main()
