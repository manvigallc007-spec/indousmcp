"""assistant.diagnose(): tells you WHY the live assistant is/isn't working (config + a real ping),
without ever printing the key. Mocked — no real network."""

import httpx

import indo_usa_mcp.assistant as a
from indo_usa_mcp.config import settings


def _http_error(code: int, body: str = "err"):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(code, content=body.encode("utf-8"), request=req)
    return httpx.HTTPStatusError("boom", request=req, response=resp)


def test_diagnose_off_when_provider_search(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    out = a.diagnose()
    assert out["status"] == "off" and out["llm_active"] is False
    assert "LLM_PROVIDER" in out["reason"]


def test_diagnose_ok_on_successful_ping(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "llm_api_key", "gsk_test_key")
    monkeypatch.setattr(a, "_chat", lambda messages, use_tools: {"content": "pong"})
    out = a.diagnose()
    assert out["status"] == "ok" and out["sample"] == "pong"
    assert out["api_key_set"] is True and out["provider"] == "groq" and out["llm_active"] is True


def test_diagnose_reports_401_bad_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.groq.com/openai/v1")  # order-independent
    monkeypatch.setattr(settings, "llm_api_key", "ollama")             # default -> treated as unset
    monkeypatch.setattr(a, "_chat",
                        lambda *a_, **k: (_ for _ in ()).throw(_http_error(401, '{"error":"invalid key"}')))
    out = a.diagnose()
    assert out["status"] == "error" and out["http_status"] == 401
    assert "401" in out["reason"] and out["api_key_set"] is False and out.get("hint")


def test_diagnose_reports_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "llm_api_key", "gsk_test_key")
    monkeypatch.setattr(a, "_chat",
                        lambda *a_, **k: (_ for _ in ()).throw(httpx.ConnectError("dns fail")))
    out = a.diagnose()
    assert out["status"] == "error" and "egress" in out["reason"]


def test_explain_http_known_and_unknown():
    assert "401" in a._explain_http(401)
    assert "429" in a._explain_http(429)
    assert "500" in a._explain_http(500)   # unknown code still explained
