"""Surface the photos web_enrich already collects: thumbnails on cards, hero + og:image on the
listing page, and LocalBusiness.image schema. DB is monkeypatched out."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import landing
from indo_usa_mcp.web import reviews as rv
from indo_usa_mcp.web.app import app

PHOTO = "https://cdn.example.com/spicehut.jpg"


def _row(**over):
    base = {"id": 1, "name": "Spice Hut", "address_full": "1 Main St", "city": "plano",
            "state": "TX", "lat": 33.0, "lng": -96.7, "phone": None, "website": "https://x.com",
            "description": "Tasty.", "tags": None, "languages": ["Telugu"], "is_claimed": True,
            "is_featured": False, "rating": 4.7, "rating_count": 80, "community_rating": None,
            "community_rating_count": 0, "photo_url": PHOTO}
    base.update(over)
    return base


def test_best_card_shows_thumbnail_and_image_schema(monkeypatch):
    monkeypatch.setattr(landing, "_best_listings", lambda v, s, c, limit=15: [_row() for _ in range(4)])
    r = TestClient(app).get("/best/restaurants/tx/plano")
    assert r.status_code == 200
    assert f"<img src='{PHOTO}'" in r.text          # thumbnail rendered on the card
    assert f'"image": "{PHOTO}"' in r.text          # LocalBusiness.image in the ItemList schema
    assert f'property="og:image" content="{PHOTO}"' in r.text   # top photo as the share image


def test_listing_page_shows_hero_and_og_image(monkeypatch):
    monkeypatch.setattr(rv, "_fetch", lambda v, i: _row())
    monkeypatch.setattr(rv.reviews_mod, "list_for_listing", lambda *a, **k: [])
    r = TestClient(app).get("/listing/restaurants/1")
    assert r.status_code == 200
    assert f"<img src='{PHOTO}'" in r.text          # hero image
    assert f'property="og:image" content="{PHOTO}"' in r.text
    assert f'"image": "{PHOTO}"' in r.text          # schema image


def test_no_photo_renders_no_img(monkeypatch):
    monkeypatch.setattr(rv, "_fetch", lambda v, i: _row(photo_url=None))
    monkeypatch.setattr(rv.reviews_mod, "list_for_listing", lambda *a, **k: [])
    r = TestClient(app).get("/listing/restaurants/1")
    assert r.status_code == 200
    assert "<img src='https://cdn.example.com" not in r.text   # gracefully absent
