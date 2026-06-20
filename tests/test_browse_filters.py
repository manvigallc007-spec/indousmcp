"""Classified browse: region/language/dietary filter chips + sort, parsed and applied. DB mocked."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import landing
from indo_usa_mcp.web.app import app


def _rows(n=3):
    return [{"id": i, "name": f"Place {i}", "city": "plano", "state": "TX", "address_full": "1 St",
             "lat": 33.0, "lng": -96.7, "phone": None, "website": None, "description": "x",
             "tags": None, "languages": ["Telugu"], "is_claimed": False, "is_featured": False,
             "rating": 4.5, "rating_count": 10, "community_rating": None, "community_rating_count": 0,
             "photo_url": None} for i in range(1, n + 1)]


def test_filter_qs_builds_and_clears():
    assert landing._filter_qs({"region": "A", "sort": "best"}, region=None) == "?sort=best"
    assert "region=South%20Indian" in landing._filter_qs({}, region="South Indian")


def test_filter_bar_marks_active():
    facets = {"region": ["South Indian", "Punjabi"], "lang": ["Telugu"], "diet": ["vegetarian"]}
    bar = landing._filter_bar("/browse/restaurants/tx/plano", facets,
                              {"region": "South Indian", "sort": "best"})
    assert "Cuisine/Region" in bar and "Dietary" in bar and "Language" in bar
    assert "South Indian" in bar and "Punjabi" in bar
    assert "background:#c1440e" in bar             # the active chip is highlighted
    assert "✕ Clear" in bar                        # clear link shown when a filter is active


def test_browse_applies_filters(monkeypatch):
    captured = {}

    def fake_listings(v, state, city, **kw):
        captured.update(kw)
        return _rows()

    monkeypatch.setattr(landing, "_listings", fake_listings)
    monkeypatch.setattr(landing, "_facets",
                        lambda *a: {"region": ["South Indian"], "lang": ["Telugu"], "diet": []})
    r = TestClient(app).get("/browse/restaurants/tx/plano?region=South Indian&sort=rating")
    assert r.status_code == 200
    assert captured["region"] == "South Indian"     # parsed + passed to the query
    assert captured["sort"] == "rating"
    assert "Cuisine/Region" in r.text               # filter bar rendered


def test_browse_filtered_empty_keeps_bar(monkeypatch):
    monkeypatch.setattr(landing, "_listings", lambda *a, **k: [])
    monkeypatch.setattr(landing, "_facets",
                        lambda *a: {"region": ["South Indian"], "lang": [], "diet": []})
    r = TestClient(app).get("/browse/restaurants/tx/plano?region=South Indian")
    assert r.status_code == 200
    assert "No matches for these filters" in r.text   # not the generic 'no listings yet'
    assert "Clear filters" in r.text
