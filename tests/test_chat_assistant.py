"""Human chat front-end: assistant fallback, cards, page render, API, rate limit. No DB/LLM."""

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp import assistant
from indo_usa_mcp.config import settings
from indo_usa_mcp.web import app, chat as chatmod

_FAKE = {"count": 2, "query": "dosa", "results": [
    {"vertical": "restaurants", "id": 1, "name": "Dosa Hut", "city": "Edison", "state": "NJ",
     "phone": "+1 732 555 0100", "website": "https://dosahut.example", "open_now": True,
     "is_featured": True, "description": "South Indian restaurant in Edison, NJ. Offers dosa."},
    {"vertical": "sweets", "id": 5, "name": "Bikaner Sweets", "city": "Iselin", "state": "NJ",
     "description": "Indian sweets shop (mithai)."},
]}


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(assistant.verticals, "search_all", lambda *a, **k: _FAKE)
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)


def test_search_fallback_reply_and_cards(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    out = assistant.reply([{"role": "user", "content": "dosa near edison"}])
    assert out["provider"] == "search"
    assert "2 matches" in out["reply"]
    assert len(out["cards"]) == 2
    c0 = out["cards"][0]
    assert c0["name"] == "Dosa Hut" and c0["vertical"] == "restaurants" and c0["is_featured"]
    assert c0["phone"] and c0["open_now"] is True


def test_empty_query_prompts_for_input(no_db):
    out = assistant.reply([{"role": "user", "content": "   "}])
    assert out["cards"] == [] and "looking for" in out["reply"].lower()


def test_llm_inactive_by_default():
    assert assistant.llm_active() is False  # default provider is "search"


def test_llm_error_degrades_to_search(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:1");
    monkeypatch.setattr(settings, "llm_model", "x")
    monkeypatch.setattr(assistant, "_llm_reply", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    out = assistant.reply([{"role": "user", "content": "dosa"}])
    assert out["provider"] == "search" and "unavailable" in out["reply"].lower()
    assert out["llm_error"] == "RuntimeError"


def test_chat_page_renders():
    r = TestClient(app).get("/chat")
    assert r.status_code == 200 and "chat/api" in r.text


def test_chat_api_returns_cards(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    r = TestClient(app).post("/chat/api", json={"messages": [{"role": "user", "content": "dosa"}]})
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "search" and len(data["cards"]) == 2


def test_chat_api_rate_limit(no_db, monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_min", 1)
    chatmod._HITS.clear()
    c = TestClient(app)
    body = {"messages": [{"role": "user", "content": "dosa"}]}
    assert c.post("/chat/api", json=body).status_code == 200
    assert c.post("/chat/api", json=body).status_code == 429
