"""Free web retrieval (Wikipedia + DuckDuckGo): parsing, dedup, graceful failure. No network."""

import httpx

import indo_usa_mcp.websearch as ws


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_wikipedia_lookup_parses(monkeypatch):
    def fake_get(url, **kw):
        if "rest_v1/page/summary" in url:
            return _Resp({"title": "Diwali", "extract": "Diwali is the festival of lights.",
                          "content_urls": {"desktop": {"page": "http://en.wiki/Diwali"}}})
        return _Resp({"query": {"search": [{"title": "Diwali"}]}})  # search + DDG (no abstract)
    monkeypatch.setattr(ws.httpx, "get", fake_get)
    out = ws.lookup("diwali")
    assert out and out[0]["source"] == "Wikipedia"
    assert "festival of lights" in out[0]["text"] and out[0]["url"].endswith("Diwali")


def test_lookup_empty_query_skips_network():
    assert ws.lookup("   ") == []


def test_lookup_survives_network_errors(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(ws.httpx, "get", boom)
    assert ws.lookup("anything at all") == []
