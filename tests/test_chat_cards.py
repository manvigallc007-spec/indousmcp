"""Photo-forward chat result cards: photo_url is batch-attached to cards, and the card UI renders it."""

from starlette.testclient import TestClient

import indo_usa_mcp.assistant as a
import indo_usa_mcp.db as dbmod
from indo_usa_mcp.web.app import app


def test_attach_photos_batches_by_vertical(monkeypatch):
    cards = [{"vertical": "restaurants", "id": 1, "name": "A"},
             {"vertical": "restaurants", "id": 2, "name": "B"},
             {"vertical": "temples", "id": 5, "name": "T"},
             {"vertical": "restaurants", "id": None, "name": "X"}]   # no id -> skipped

    def fake_query(sql, params=None):
        if "restaurants" in sql:
            return [{"id": 1, "photo_url": "http://img/1.jpg"}, {"id": 2, "photo_url": None}]
        if "temples" in sql:
            return [{"id": 5, "photo_url": "http://img/5.jpg"}]
        return []

    monkeypatch.setattr(dbmod, "query", fake_query)
    out = a._attach_photos(cards)
    assert out[0]["photo_url"] == "http://img/1.jpg"
    assert out[1]["photo_url"] is None
    assert out[2]["photo_url"] == "http://img/5.jpg"
    assert out[3]["photo_url"] is None


def test_attach_photos_survives_db_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no db")
    monkeypatch.setattr(dbmod, "query", boom)
    out = a._attach_photos([{"vertical": "restaurants", "id": 1, "name": "A"}])
    assert out[0]["photo_url"] is None          # swallowed, never breaks the chat reply


def test_chat_homepage_renders_photo_card_code():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "lc-photo" in r.text                 # the card photo CSS class
    assert "c.photo_url" in r.text              # card() draws the image when present


def test_chat_homepage_decluttered():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    # the verbose legal paragraph + redundant disclaimer were moved to the static pages
    assert "legal, tax, immigration, medical, or professional advice" not in r.text
    assert "Not legal, tax, or medical advice; details may be out of date." not in r.text
    # a concise caveat remains, pointing to /terms; the footer nav still links the static pages
    assert "verify before relying" in r.text
    assert "herocard" in r.text                 # warm hero band applied to the homepage
    assert 'href="/terms"' in r.text and 'href="/faq"' in r.text and 'href="/about"' in r.text
