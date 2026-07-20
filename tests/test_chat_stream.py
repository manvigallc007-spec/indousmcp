"""Streaming chat (/chat/stream, SSE). The endpoint only streams the clean case (English + grounded
model + a directory hit) and otherwise returns {"fallback": true} so the browser uses the untouched
blocking /chat/api. LLM is mocked; no network."""

from starlette.testclient import TestClient

import indo_usa_mcp.assistant as assistant
from indo_usa_mcp.config import settings
from indo_usa_mcp.web.app import app

_client = TestClient(app)


# --------------------------------------------------------------- can_stream gate
def test_can_stream_only_english_grounded_active(monkeypatch):
    monkeypatch.setattr(assistant, "llm_active", lambda: True)
    monkeypatch.setattr(settings, "llm_provider", "gemini")     # grounded preset (use_tools False)
    assert assistant.can_stream({"lang": "en"}) is True
    assert assistant.can_stream({"lang": "hi"}) is False        # non-English -> blocking (translation)
    monkeypatch.setattr(settings, "llm_provider", "groq")       # tool-calling preset
    assert assistant.can_stream({"lang": "en"}) is False
    monkeypatch.setattr(assistant, "llm_active", lambda: False)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    assert assistant.can_stream({"lang": "en"}) is False


# --------------------------------------------------------------- endpoint fallback
def test_stream_returns_fallback_when_cannot_stream(monkeypatch):
    monkeypatch.setattr(assistant, "can_stream", lambda f: False)
    r = _client.post("/chat/stream", json={"messages": [{"role": "user", "content": "biryani"}], "lang": "en"})
    assert r.headers["content-type"].startswith("application/json") and r.json()["fallback"] is True


def test_stream_non_english_falls_back():
    # real can_stream: hi -> fallback json (no LLM configured in tests anyway)
    r = _client.post("/chat/stream", json={"messages": [{"role": "user", "content": "x"}], "lang": "hi"})
    assert r.json().get("fallback") is True


# --------------------------------------------------------------- endpoint streaming
def test_stream_emits_deltas_then_final(monkeypatch):
    monkeypatch.setattr(assistant, "can_stream", lambda f: True)

    def fake(msgs, geo, filters):
        for t in ["Here ", "are ", "picks."]:
            yield ("delta", t)
        yield ("final", {"cards": [{"name": "ZZTEST Spice Hut", "vertical": "restaurants"}], "provider": "llm"})
    monkeypatch.setattr(assistant, "stream_reply", fake)

    r = _client.post("/chat/stream", json={"messages": [{"role": "user", "content": "biryani"}], "lang": "en"})
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "Here " in body and "picks." in body
    assert '"final"' in body and "ZZTEST Spice Hut" in body
    assert body.count("data: ") == 4                            # 3 deltas + 1 final


def test_stream_forwards_fallback_signal(monkeypatch):
    monkeypatch.setattr(assistant, "can_stream", lambda f: True)
    monkeypatch.setattr(assistant, "stream_reply", lambda m, g, f: iter([("fallback", None)]))
    r = _client.post("/chat/stream", json={"messages": [{"role": "user", "content": "x"}], "lang": "en"})
    assert '"fallback": true' in r.text                         # client will call /chat/api


# --------------------------------------------------------------- stream_reply generator
def test_stream_reply_falls_back_without_directory_hit(monkeypatch):
    monkeypatch.setattr(assistant, "_search_query", lambda m: "something")
    monkeypatch.setattr(assistant, "_run_search", lambda *a, **k: {"results": [], "count": 0})
    out = list(assistant.stream_reply([{"role": "user", "content": "something obscure"}]))
    assert out == [("fallback", None)]                          # no results -> let reply() handle it


# --------------------------------------------------------------- client wiring intact
def test_homepage_has_streaming_and_blocking_fallback():
    html = _client.get("/").text
    assert "/chat/stream" in html and "sendBlocking" in html    # tries streaming...
    assert "/chat/api" in html                                  # ...and keeps the proven fallback
