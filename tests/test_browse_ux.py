"""Browse UX upgrades: the /find search + near-me results page, the search box + open-now/4★ quick
filters on browse-city, and the dependency-free static map. Real dev DB, ZZTEST rows, try/finally."""

import re

from starlette.testclient import TestClient

from indo_usa_mcp import db, verticals
from indo_usa_mcp.web import staticmap
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_CITY = "Zzbrowseville"


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _mk(name, **over):
    rec = {"name": name, "city": _CITY, "state": "TX", "lat": 33.0, "lng": -96.7,
           "phone": "+19725550000", "website": "https://x.com"}
    rec.update(over)
    return verticals.create_record("restaurants", rec, source="test")["id"]


# --------------------------------------------------------------- /find
def test_find_keyword_search_returns_cards():
    rid = _mk("ZZTEST Biryani Palace", tags=["biryani", "catering"])
    try:
        r = _client.get("/find", params={"q": "ZZTEST Biryani", "city": _CITY})
        assert r.status_code == 200
        assert "shero" in r.text and f"/listing/restaurants/{rid}" in r.text
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_find_near_me_lists_by_distance():
    rid = _mk("ZZTEST Near Cafe")
    try:
        r = _client.get("/find", params={"lat": "33.0", "lng": "-96.7"})
        assert r.status_code == 200 and "Near you" in r.text
        assert f"/listing/restaurants/{rid}" in r.text
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_browse_root_has_search_hero():
    r = _client.get("/browse")
    assert "shero" in r.text and "Near me" in r.text and "/find" in r.text


# --------------------------------------------------------------- browse-city filters
def test_browse_city_keyword_and_quick_filters():
    a = _mk("ZZTEST Dosa Corner", tags=["dosa"])
    b = _mk("ZZTEST Chaat House", tags=["chaat"])
    try:
        base = f"/browse/restaurants/tx/{_slug(_CITY)}"
        r = _client.get(base)
        assert "fsearch" in r.text and "Open now" in r.text and "4+ rated" in r.text
        # keyword narrows to the matching listing only
        rq = _client.get(base, params={"q": "dosa"})
        assert f"/listing/restaurants/{a}" in rq.text and f"/listing/restaurants/{b}" not in rq.text
        assert "matching" in rq.text                       # active-filter summary shown
    finally:
        db.execute("DELETE FROM restaurants WHERE id IN (%s,%s)", (a, b))


# --------------------------------------------------------------- static map
def test_static_map_renders_tiles_and_pins():
    rows = [{"id": 1, "name": "A", "lat": 32.99, "lng": -96.70},
            {"id": 2, "name": "B", "lat": 33.01, "lng": -96.72, "vertical": "groceries"}]
    html = staticmap.render(rows, "restaurants", title="Test")
    assert "tile.openstreetmap.org" in html and "Show map" in html
    assert "/listing/restaurants/1" in html and "/listing/groceries/2" in html   # per-row vertical
    assert staticmap.render([{"id": 3, "name": "C"}], "restaurants") == ""        # no coords -> empty
