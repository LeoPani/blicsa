"""Consulta exata de DOI no registro público DataCite para validação bibliográfica."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def get_by_doi(doi: str) -> dict | None:
    raw = str(doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
            break
    if not raw:
        return None
    url = "https://api.datacite.org/dois/" + urllib.parse.quote(raw, safe="/")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Blicsa/2.0 (mailto:blicsa.app@gmail.com)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            attrs = json.load(response).get("data", {}).get("attributes", {})
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    titles = attrs.get("titles") or []
    title = next((item.get("title") for item in titles if item.get("title")), "")
    return {"title": title, "year": int(attrs.get("publicationYear") or 0),
            "doi": str(attrs.get("doi") or raw)} if title else None
