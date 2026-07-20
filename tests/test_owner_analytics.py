"""Real owner analytics: per-listing human views + call/website/directions taps via a client beacon,
surfaced on the owner manage page + dashboard. Real dev DB, ZZTEST rows, try/finally; login mocked."""

from starlette.testclient import TestClient

from indo_usa_mcp import analytics, db, verticals
from indo_usa_mcp.web import portal
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_E = "zztest_analytics@example.com"


def _mk_owned():
    return verticals.create_record("restaurants", {"name": "ZZTEST Analytics", "city": "Plano",
                                                   "state": "TX", "lat": 33.0, "lng": -96.7,
                                                   "phone": "+19725550000", "website": "https://x.com",
                                                   "email": _E}, source="test")["id"]


def _cleanup(rid):
    db.execute("DELETE FROM listing_events WHERE record_id=%s", (rid,))
    db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- analytics core
def test_log_listing_event_validates_kind():
    rid = _mk_owned()
    try:
        assert analytics.log_listing_event("restaurants", rid, "view") is True
        assert analytics.log_listing_event("restaurants", rid, "bogus") is False
        analytics.log_listing_event("restaurants", rid, "call")
        analytics.log_listing_event("restaurants", rid, "call")
        m = analytics.listing_metrics("restaurants", rid, 30)
        assert m == {"view": 1, "call": 2, "website": 0, "directions": 0}
    finally:
        _cleanup(rid)


# --------------------------------------------------------------- beacon endpoint
def test_track_records_and_ignores_bad_input():
    rid = _mk_owned()
    try:
        for k in ("view", "website", "website", "directions"):
            assert _client.post(f"/track?v=restaurants&id={rid}&k={k}").status_code == 204
        _client.post(f"/track?v=restaurants&id={rid}&k=hacker")     # bad kind -> ignored
        _client.post(f"/track?v=nope&id={rid}&k=view")              # bad vertical -> ignored
        m = analytics.listing_metrics("restaurants", rid, 30)
        assert m["view"] == 1 and m["website"] == 2 and m["directions"] == 1 and m["call"] == 0
    finally:
        _cleanup(rid)


def test_track_dedupes_repeat_views_and_rejects_missing_listing():
    rid = _mk_owned()
    try:
        for _ in range(4):                                          # same IP reloads the page 4x...
            _client.post(f"/track?v=restaurants&id={rid}&k=view")
        _client.post(f"/track?v=restaurants&id={rid}&k=call")       # taps are NOT deduped
        _client.post(f"/track?v=restaurants&id={rid}&k=call")
        _client.post("/track?v=restaurants&id=999999999&k=view")    # non-existent listing -> dropped
        m = analytics.listing_metrics("restaurants", rid, 30)
        assert m["view"] == 1                                       # ...counts as a single view
        assert m["call"] == 2                                       # genuine intent taps each count
        assert analytics.listing_metrics("restaurants", 999999999, 30)["view"] == 0
    finally:
        _cleanup(rid)


def test_listing_page_emits_view_beacon_and_trackable_links():
    rid = _mk_owned()
    try:
        html = _client.get(f"/listing/restaurants/{rid}").text
        assert "navigator.sendBeacon('/track" in html and "bx('view')" in html
        assert "data-k='call'" in html and "data-k='website'" in html and "data-k='directions'" in html
    finally:
        _cleanup(rid)


# --------------------------------------------------------------- owner surfaces
def test_manage_page_shows_performance_panel(monkeypatch):
    rid = _mk_owned()
    try:
        analytics.log_listing_event("restaurants", rid, "view")
        analytics.log_listing_event("restaurants", rid, "call")
        monkeypatch.setattr(portal, "portal_email", lambda req: _E)
        html = _client.get(f"/portal/listing/restaurants/{rid}").text
        assert "Performance" in html and "page views" in html and "calls" in html and "directions" in html
    finally:
        _cleanup(rid)


def test_dashboard_shows_views(monkeypatch):
    rid = _mk_owned()
    try:
        analytics.log_listing_event("restaurants", rid, "view")
        monkeypatch.setattr(portal, "portal_email", lambda req: _E)
        html = _client.get("/portal").text
        assert "views (30d)" in html and f"/portal/listing/restaurants/{rid}" in html
    finally:
        _cleanup(rid)
