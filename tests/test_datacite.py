"""DataCite é o segundo registro DOI consultado quando Crossref não tem a obra."""

import io
import json

from core.sources.datacite import get_by_doi


def test_datacite_resolve_doi_exato(monkeypatch):
    urls = []

    def fake_open(request, timeout):
        urls.append(request.full_url)
        return io.BytesIO(json.dumps({"data": {"attributes": {
            "titles": [{"title": "Transformer-Based Feature Learning"}],
            "publicationYear": 2025, "doi": "10.4230/LIPIcs.CP.2025.31",
        }}}).encode())

    monkeypatch.setattr("core.sources.datacite.urllib.request.urlopen", fake_open)
    record = get_by_doi("https://doi.org/10.4230/LIPIcs.CP.2025.31")

    assert urls == ["https://api.datacite.org/dois/10.4230/LIPIcs.CP.2025.31"]
    assert record["title"] == "Transformer-Based Feature Learning"
    assert record["year"] == 2025
