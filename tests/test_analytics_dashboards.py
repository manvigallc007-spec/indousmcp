"""Analytics upgrades: owner-facing trend/CTR/sparkline helpers, the site-wide conversion funnel, the
daily series for sparklines, and the inline-SVG sparkline/trend-badge renderers. Real dev DB, ZZTEST
rows, try/finally."""

from indo_usa_mcp import analytics, db, verticals
from indo_usa_mcp.web.common import sparkline, trend_badge


def _mk():
    return verticals.create_record("restaurants", {"name": "ZZTEST Analytics2", "city": "Plano",
                                                   "state": "TX", "lat": 33.0, "lng": -96.7},
                                   source="test")["id"]


# --------------------------------------------------------------- helpers
def test_listing_trend_and_ctr():
    rid = _mk()
    try:
        for _ in range(10):
            analytics.log_listing_event("restaurants", rid, "view")
        analytics.log_listing_event("restaurants", rid, "call")
        analytics.log_listing_event("restaurants", rid, "website")
        t = analytics.listing_trend("restaurants", rid, 30)
        assert t["views"] == 10 and t["taps"] == 2
        assert t["ctr"] == 20                              # 2 taps / 10 views
        assert t["delta_pct"] == 100                       # no prior-period views -> treated as +100%
    finally:
        db.execute("DELETE FROM listing_events WHERE record_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_daily_series_length_and_last_bucket():
    rid = _mk()
    try:
        analytics.log_listing_event("restaurants", rid, "view")
        series = analytics.listing_daily_views("restaurants", rid, 30)
        assert len(series) == 30 and series[-1] >= 1       # today's bucket is last, has our view
    finally:
        db.execute("DELETE FROM listing_events WHERE record_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_conversion_summary_shape():
    c = analytics.conversion_summary(30)
    assert set(c) >= {"view", "call", "website", "directions", "taps", "ctr"}
    assert all(isinstance(c[k], int) for k in c)


# --------------------------------------------------------------- renderers
def test_sparkline_and_badge():
    svg = sparkline([1, 4, 2, 6, 3])
    assert svg.startswith("<svg") and "polyline" in svg
    assert sparkline([0, 0, 0]) == "" and sparkline([]) == ""    # nothing to draw
    assert "▲" in trend_badge(10) and "▼" in trend_badge(-3)
    assert "—" in trend_badge(0)
