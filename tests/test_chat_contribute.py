"""In-chat 'add a place you know' contribution now enriches (OSM + site + LLM category-fill) before
submitting, so chat-contributed places arrive rich instead of bare name/city."""

from starlette.testclient import TestClient

import indo_usa_mcp.web.chat as chat
from indo_usa_mcp.web.app import app

_client = TestClient(app)


def test_chat_contribute_enriches_payload_before_submit(monkeypatch):
    monkeypatch.setattr(chat.assistant, "enabled", lambda: True)
    monkeypatch.setattr(chat, "_rate_ok", lambda ip: True)
    # avoid network: stub the enrichment helpers to return a rich candidate
    import indo_usa_mcp.onboard as onboard
    monkeypatch.setattr(onboard, "lookup",
                        lambda name, city, state, v, website=None: {
                            "name": name, "city": city, "state": state, "website": website,
                            "phone": "+1 555 0100", "address_full": "1 Main St"})
    monkeypatch.setattr(onboard, "ai_fill",
                        lambda v, rec: {**rec, "cuisine_type": "South Indian"})
    captured = {}
    import indo_usa_mcp.submissions as submissions
    monkeypatch.setattr(submissions, "submit",
                        lambda vertical, payload, **kw: captured.update(vertical=vertical, payload=payload)
                        or {"ok": True, "id": 1})

    r = _client.post("/chat/contribute", json={"name": "Dosa Place", "city": "Plano, TX",
                                               "vertical": "restaurants", "website": "https://dosa.example"})
    assert r.status_code == 200 and r.json()["ok"] is True
    p = captured["payload"]
    assert p["name"] == "Dosa Place" and p["phone"] == "+1 555 0100"
    assert p["cuisine_type"] == "South Indian"        # LLM category-fill reached the submission
    assert p["website"] == "https://dosa.example"
    assert captured["vertical"] == "restaurants"


def test_chat_contribute_degrades_if_enrichment_raises(monkeypatch):
    monkeypatch.setattr(chat.assistant, "enabled", lambda: True)
    monkeypatch.setattr(chat, "_rate_ok", lambda ip: True)
    import indo_usa_mcp.onboard as onboard
    monkeypatch.setattr(onboard, "lookup",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")))
    captured = {}
    import indo_usa_mcp.submissions as submissions
    monkeypatch.setattr(submissions, "submit",
                        lambda vertical, payload, **kw: captured.update(payload=payload) or {"ok": True, "id": 1})
    r = _client.post("/chat/contribute", json={"name": "Bare Place", "city": "Edison, NJ",
                                               "vertical": "restaurants"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert captured["payload"]["name"] == "Bare Place"   # still submits the bare fallback, no crash
