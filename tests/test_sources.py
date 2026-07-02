import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import json
from threading import Event

from core.sources import OpenAlexProvider, CrossrefProvider, PubMedProvider

class TestSearchProviders(unittest.TestCase):

    @patch('urllib.request.urlopen')
    def test_openalex_provider(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": [
                {
                    "title": "Test OpenAlex paper",
                    "publication_year": 2024,
                    "authorships": [{"author": {"display_name": "Author One"}}],
                    "concepts": [{"display_name": "AI"}],
                    "cited_by_count": 10,
                    "doi": "https://doi.org/10.1000/xyz123",
                    "primary_location": {"source": {"display_name": "Test Journal"}}
                }
            ],
            "meta": {"count": 1, "next_cursor": None}
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = OpenAlexProvider()
        results = list(provider.search("AI", max_results=1))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test OpenAlex paper")
        self.assertEqual(results[0]["authors"], "Author One")
        self.assertEqual(results[0]["year"], 2024)
        self.assertEqual(results[0]["origin"], "OpenAlex")

    @patch('urllib.request.urlopen')
    def test_crossref_provider(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "message": {
                "total-results": 1,
                "next-cursor": None,
                "items": [
                    {
                        "title": ["Test Crossref paper"],
                        "author": [{"family": "Doe", "given": "Jane"}],
                        "issued": {"date-parts": [[2023]]},
                        "container-title": ["Test Journal"],
                        "subject": ["Machine Learning"],
                        "is-referenced-by-count": 5,
                        "DOI": "10.1001/crossref1"
                    }
                ]
            }
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = CrossrefProvider()
        results = list(provider.search("Machine Learning", max_results=1))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test Crossref paper")
        self.assertEqual(results[0]["authors"], "Doe Jane")
        self.assertEqual(results[0]["year"], 2023)
        self.assertEqual(results[0]["origin"], "Crossref")

    @patch('urllib.request.urlopen')
    def test_pubmed_provider(self, mock_urlopen):
        mock_esearch_resp = MagicMock()
        mock_esearch_resp.read.return_value = json.dumps({
            "esearchresult": {
                "count": "1",
                "idlist": ["12345"]
            }
        }).encode('utf-8')
        mock_esearch_resp.__enter__.return_value = mock_esearch_resp
        
        mock_efetch_resp = MagicMock()
        mock_efetch_resp.read.return_value = (
            "PMID- 12345\n"
            "TI  - Test PubMed paper\n"
            "AU  - Smith A\n"
            "DP  - 2022\n"
            "JT  - PubMed Journal\n"
            "AID - 10.1002/pmid1 [doi]\n"
            "AB  - Test Abstract\n"
            "\n"
        ).encode('utf-8')
        mock_efetch_resp.__enter__.return_value = mock_efetch_resp

        mock_urlopen.side_effect = [mock_esearch_resp, mock_efetch_resp]

        provider = PubMedProvider()
        results = list(provider.search("Smith", max_results=1))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test PubMed paper")
        self.assertEqual(results[0]["authors"], "Smith A")
        self.assertEqual(results[0]["year"], 2022)
        self.assertEqual(results[0]["doi"], "10.1002/pmid1")
        self.assertEqual(results[0]["origin"], "PubMed")

    @patch('urllib.request.urlopen')
    def test_cancellation(self, mock_urlopen):
        cancel_event = Event()
        cancel_event.set()

        provider = OpenAlexProvider()
        
        with self.assertRaises(InterruptedError):
            list(provider.search("AI", cancel_event=cancel_event))

    @patch('urllib.request.urlopen')
    def test_retry_on_429(self, mock_urlopen):
        mock_error = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        
        mock_success = MagicMock()
        mock_success.read.return_value = json.dumps({
            "results": [],
            "meta": {"count": 0, "next_cursor": None}
        }).encode('utf-8')
        mock_success.__enter__.return_value = mock_success

        mock_urlopen.side_effect = [mock_error, mock_success]

        with patch('time.sleep') as mock_sleep:
            provider = OpenAlexProvider()
            list(provider.search("AI", max_results=1))
            mock_sleep.assert_called_once()

if __name__ == '__main__':
    unittest.main()
