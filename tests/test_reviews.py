"""Community review system: core moderation + roll-up, web form, agents, admin gating. No live DB."""

from starlette.testclient import TestClient

import indo_usa_mcp.reviews as reviews
from indo_usa_mcp.agents.definitions import ReviewAggregatorAgent, ReviewModerationAgent
from indo_usa_mcp.config import settings
from indo_usa_mcp.web import reviews as rweb
from indo_usa_mcp.web.app import app

c = TestClient(app)


# --------------------------------------------------------------------- core: validation
def test_submit_rejects_bad_rating():
    assert reviews.submit("restaurants", 1, 7).get("error") == "bad_rating"
    assert reviews.submit("restaurants", 1, 0).get("error") == "bad_rating"
    assert reviews.submit("restaurants", 1, "x").get("error") == "bad_rating"


def test_submit_rejects_unknown_or_unreviewable_vertical():
    assert reviews.submit("dragons", 1, 5).get("error") == "bad_vertical"
    assert reviews.submit("events", 1, 5).get("error") == "bad_vertical"   # events aren't reviewable


def test_submit_rejects_missing_listing(monkeypatch):
    monkeypatch.setattr(reviews, "_listing", lambda v, lid: None)
    assert reviews.submit("restaurants", 999, 5, body="ok").get("error") == "listing_not_found"


# --------------------------------------------------------------------- core: screening
def test_screen_holds_links_and_abuse():
    assert reviews._screen("Loved it, visit http://spam.example")[0] is False
    assert reviews._screen("buy viagra cheap")[0] is False
    assert reviews._screen("aaaaaaaaaa")[0] is False


def test_screen_passes_clean_text_without_llm():
    # default config has no LLM -> deterministic-clean text is publishable
    ok, reason = reviews._screen("Wonderful biryani and very friendly service.")
    assert ok is True and reason is None


# --------------------------------------------------------------------- core: submit + aggregate
def _stub_store(monkeypatch):
    monkeypatch.setattr(reviews, "_listing", lambda v, lid: {"id": lid, "name": "Spice Villa"})
    monkeypatch.setattr(reviews, "aggregate", lambda v, lid: None)
    monkeypatch.setattr(reviews.db, "query_one", lambda sql, params=None: {"id": 42})


def test_submit_clean_publishes(monkeypatch):
    _stub_store(monkeypatch)
    res = reviews.submit("restaurants", 5, 5, body="Great thali, fresh and tasty.")
    assert res["ok"] and res["status"] == "published" and res["id"] == 42


def test_submit_flagged_is_held(monkeypatch):
    _stub_store(monkeypatch)
    res = reviews.submit("restaurants", 5, 1, body="scam, go to http://x.example now")
    assert res["ok"] and res["status"] == "pending"


def test_submit_holds_all_when_auto_publish_off(monkeypatch):
    _stub_store(monkeypatch)
    monkeypatch.setattr(settings, "review_auto_publish", False)
    assert reviews.submit("restaurants", 5, 5, body="lovely")["status"] == "pending"


def test_aggregate_computes_average(monkeypatch):
    captured = {}
    monkeypatch.setattr(reviews.db, "query_one", lambda sql, params=None: {"n": 2, "avg": 4.5})
    monkeypatch.setattr(reviews.db, "execute",
                        lambda sql, params=None: captured.update(params=params))
    out = reviews.aggregate("restaurants", 5)
    assert out["community_rating"] == 4.5 and out["community_rating_count"] == 2
    assert captured["params"][:2] == [4.5, 2]              # rating, count written to the listing


# --------------------------------------------------------------------- web: listing page + form
def test_listing_page_404_for_unknown_vertical():
    assert c.get("/listing/dragons/1").status_code == 404


def test_listing_page_404_when_missing(monkeypatch):
    monkeypatch.setattr(rweb, "_fetch", lambda v, lid: None)
    assert c.get("/listing/restaurants/123").status_code == 404


def test_listing_page_renders_with_review_form(monkeypatch):
    monkeypatch.setattr(rweb, "_fetch", lambda v, lid: {
        "id": lid, "name": "Spice Villa", "city": "Plano", "state": "TX",
        "address_full": "1 Main St", "rating": None, "community_rating": None})
    monkeypatch.setattr(rweb.reviews_mod, "list_for_listing", lambda *a, **k: [])
    t = c.get("/listing/restaurants/5").text
    assert "Spice Villa" in t and "Write a review" in t


def test_review_post_rejects_bad_captcha(monkeypatch):
    monkeypatch.setattr(rweb.reviews_mod, "_listing", lambda v, lid: {"id": lid, "name": "X"})
    r = c.post("/listing/restaurants/5/review", data={"rating": "5", "body": "hi"})
    assert r.status_code == 400


def test_review_post_honeypot_silently_redirects(monkeypatch):
    monkeypatch.setattr(rweb.reviews_mod, "_listing", lambda v, lid: {"id": lid, "name": "X"})
    r = c.post("/listing/restaurants/5/review",
               data={"rating": "5", "website": "bot"}, follow_redirects=False)
    assert r.status_code == 303


def test_review_post_success_redirects(monkeypatch):
    monkeypatch.setattr(rweb.reviews_mod, "_listing", lambda v, lid: {"id": lid, "name": "X"})
    monkeypatch.setattr(rweb, "verify_captcha", lambda form: True)
    monkeypatch.setattr(rweb.reviews_mod, "recent_for_ip", lambda *a, **k: 0)
    monkeypatch.setattr(rweb.reviews_mod, "ip_count_today", lambda *a, **k: 0)
    monkeypatch.setattr(rweb.reviews_mod, "submit",
                        lambda *a, **k: {"ok": True, "status": "published", "id": 1})
    r = c.post("/listing/restaurants/5/review",
               data={"rating": "5", "body": "great"}, follow_redirects=False)
    assert r.status_code == 303 and "ok=published" in r.headers["location"]


# --------------------------------------------------------------------- agents
def test_moderation_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "reviews_enabled", False)
    assert ReviewModerationAgent().run().get("skipped") == "disabled"
    assert ReviewAggregatorAgent().run().get("skipped") == "disabled"


def test_moderation_publishes_now_clean_and_holds_flagged(monkeypatch):
    monkeypatch.setattr(reviews, "pending", lambda limit=200: [
        {"id": 1, "body": "Wonderful food and service", "flagged_reason": "llm_flagged"},
        {"id": 2, "body": "spam http://x.example", "flagged_reason": "contains_link"}])
    approved = []
    monkeypatch.setattr(reviews, "approve", lambda rid, by="admin": approved.append(rid))
    monkeypatch.setattr(reviews.db, "execute", lambda *a, **k: None)
    out = reviews.moderate_pending()
    assert approved == [1] and out["auto_published"] == 1 and out["left_for_human"] == 1


def test_aggregator_runs(monkeypatch):
    monkeypatch.setattr(reviews.db, "query", lambda sql, params=None: [])
    out = reviews.aggregate_all()
    assert out["ok"] and out["listings_recomputed"] == 0


# --------------------------------------------------------------------- admin gating
def test_admin_reviews_requires_login():
    assert c.get("/admin/reviews", follow_redirects=False).status_code in (302, 303)
