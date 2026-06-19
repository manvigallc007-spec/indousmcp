"""Best-of curated list pages (/best/<vertical>/<state>/<city>). DB is monkeypatched out."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import landing
from indo_usa_mcp.web.app import app


def _fake_rows(n: int) -> list[dict]:
    return [{"id": i, "name": f"Place {i}", "city": "plano", "state": "TX",
             "address_full": f"{i} Main St", "lat": 33.0, "lng": -96.7, "phone": None,
             "website": "https://example.com", "description": "Great spot.", "tags": None,
             "languages": ["Telugu"], "is_claimed": True, "is_featured": False,
             "rating": 4.7, "rating_count": 50 + i,
             "community_rating": None, "community_rating_count": 0} for i in range(1, n + 1)]


def test_best_page_renders_with_schema(monkeypatch):
    monkeypatch.setattr(landing, "_best_listings", lambda v, s, c, limit=15: _fake_rows(5))
    r = TestClient(app).get("/best/restaurants/tx/plano")
    assert r.status_code == 200
    assert "Best Indian Restaurants in Plano, TX" in r.text
    assert '"@type": "ItemList"' in r.text
    assert '"@type": "BreadcrumbList"' in r.text          # breadcrumb schema present
    assert 'rel="canonical"' in r.text                    # canonical emitted
    assert "1. <a href='/listing/restaurants/1'" in r.text  # ranked, numbered


def test_best_page_redirects_when_too_thin(monkeypatch):
    monkeypatch.setattr(landing, "_best_listings", lambda *a, **k: _fake_rows(2))
    r = TestClient(app).get("/best/restaurants/tx/plano", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/browse/restaurants/tx/plano"


def test_best_page_unknown_vertical_404(monkeypatch):
    r = TestClient(app).get("/best/not-a-vertical/tx/plano")
    assert r.status_code == 404
