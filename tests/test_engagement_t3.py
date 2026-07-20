"""Tranche 3 — engagement surfaces: Today never-empty fallbacks (popular-near + help-answer), the
/leaderboard + /u/{code} public profiles, and the homepage Today strip. Real dev DB, ZZTEST rows,
try/finally."""

from starlette.testclient import TestClient

from indo_usa_mcp import accounts, db, qa, reviews as rv, today, verticals
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_CITY = "Zztestville"
_E = "zztest_t3@example.com"


def _rated_listing(rating=4.6, n=3):
    rid = verticals.create_record("restaurants", {"name": "ZZTEST Popular Cafe", "city": _CITY,
                                                  "state": "TX", "lat": 33.0, "lng": -96.7,
                                                  "email": "owner@zz.com"}, source="test")["id"]
    db.execute("UPDATE restaurants SET community_rating=%s, community_rating_count=%s WHERE id=%s",
               (rating, n, rid))
    return rid


# --------------------------------------------------------------- popular-near fallback
def test_popular_near_returns_top_rated():
    rid = _rated_listing()
    try:
        pop = today.popular_near(_CITY, "TX", limit=6)
        assert any(p["id"] == rid and p["vertical"] == "restaurants" for p in pop)
        assert today.popular_near(None) == []            # no city -> empty, never raises
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_assemble_uses_popular_when_no_new_places():
    rid = _rated_listing()
    db.execute("UPDATE restaurants SET created_at = now() - interval '60 days' WHERE id=%s", (rid,))
    try:
        feed = today.assemble(city=_CITY, state="TX")     # nothing added recently -> fall back
        assert feed["new_places"] == []
        assert any(p["id"] == rid for p in feed["popular"])
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- help-answer fallback
def test_assemble_surfaces_an_unanswered_question():
    q = qa.create_question("ZZTEST which sabzi mandi is open late in Zztestville?", asker_email=_E)
    try:
        feed = today.assemble(city=_CITY, state="TX")
        assert feed.get("help_answer") is not None       # an unanswered question is offered
    finally:
        db.execute("DELETE FROM questions WHERE id=%s", (q["id"],))


# --------------------------------------------------------------- leaderboard + profile
def test_leaderboard_and_public_profile():
    rid = verticals.create_record("restaurants", {"name": "ZZTEST LB Cafe", "city": _CITY, "state": "TX",
                                                  "lat": 33.0, "lng": -96.7}, source="test")["id"]
    try:
        r = rv.submit("restaurants", rid, 5, body="Fantastic thali, must visit again.",
                      name="Ravi", email=_E)
        db.execute("UPDATE reviews SET status='published' WHERE id=%s", (r["id"],))
        prof = accounts.upsert_profile(_E, display_name="Ravi K", home_city=_CITY, home_state="TX")
        code = accounts.ensure_referral_code(_E)

        lb = accounts.leaderboard(city=_CITY)
        assert any(row["code"] == code and row["points"] > 0 for row in lb)

        # public pages render
        assert _client.get("/leaderboard?city=" + _CITY).status_code == 200
        pr = _client.get(f"/u/{code}")
        assert pr.status_code == 200 and "Ravi K" in pr.text
    finally:
        db.execute("DELETE FROM reviews WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
        db.execute("DELETE FROM user_profiles WHERE email=%s", (_E,))


# --------------------------------------------------------------- homepage strip
def test_homepage_today_strip_links():
    html = _client.get("/").text
    assert "/today" in html          # festival pill (or at least the Today nav) present
