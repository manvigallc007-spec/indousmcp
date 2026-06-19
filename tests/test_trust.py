"""Trust/freshness: completeness badge, Suggest-an-edit, and the festival-timing KB article."""

import datetime

from starlette.testclient import TestClient

from indo_usa_mcp import festivals, knowledge_seed
from indo_usa_mcp.web import reviews as rv
from indo_usa_mcp.web.app import app


def _row(**over):
    base = {"id": 1, "name": "Spice Hut", "city": "Plano", "state": "TX", "address_full": "1 Main St",
            "lat": 33.0, "lng": -96.7, "phone": "9725550000", "email": None, "website": "https://x.com",
            "description": "Tasty.", "tags": None, "languages": ["Telugu"], "is_claimed": True,
            "is_featured": False, "rating": None, "rating_count": None, "community_rating": None,
            "community_rating_count": 0, "photo_url": None,
            "updated_at": datetime.datetime(2026, 6, 1)}
    base.update(over)
    return base


def test_festival_article_is_grounded():
    art = festivals.kb_article()
    assert art["slug"] == f"festival-calendar-{festivals.YEAR}"
    assert str(festivals.YEAR) in art["title"]
    assert "Diwali" in art["text"]
    assert "confirm" in art["text"].lower()          # tells users to verify the exact date


def test_seed_includes_festival_article():
    arts = knowledge_seed._all_articles()
    assert len(arts) == len(knowledge_seed.ARTICLES) + 1
    assert f"festival-calendar-{festivals.YEAR}" in {a["slug"] for a in arts}


def test_listing_shows_trust_line(monkeypatch):
    monkeypatch.setattr(rv, "_fetch", lambda v, i: _row())
    monkeypatch.setattr(rv.reviews_mod, "list_for_listing", lambda *a, **k: [])
    r = TestClient(app).get("/listing/restaurants/1")
    assert r.status_code == 200
    assert "% complete" in r.text
    assert "Updated Jun 2026" in r.text
    assert "Suggest an edit" in r.text


def test_suggest_post_creates_inbox_message(monkeypatch):
    from indo_usa_mcp import inbox
    monkeypatch.setattr(rv, "_fetch", lambda v, i: _row())
    monkeypatch.setattr(rv, "verify_captcha", lambda form: True)
    captured = {}
    monkeypatch.setattr(inbox, "create_message",
                        lambda name, email, subject, body, ip=None:
                        captured.update(subject=subject, body=body) or {"ok": True})
    r = TestClient(app).post("/listing/restaurants/1/suggest",
                             data={"body": "Phone is wrong", "email": "", "captcha": "x"},
                             follow_redirects=False)
    assert r.status_code == 303
    assert "Edit suggestion: Spice Hut" in captured["subject"]
    assert "/listing/restaurants/1" in captured["subject"]
    assert captured["body"] == "Phone is wrong"


def test_suggest_post_requires_body(monkeypatch):
    monkeypatch.setattr(rv, "_fetch", lambda v, i: _row())
    monkeypatch.setattr(rv, "verify_captcha", lambda form: True)
    r = TestClient(app).post("/listing/restaurants/1/suggest",
                             data={"body": "  ", "captcha": "x"}, follow_redirects=False)
    assert r.status_code == 400
