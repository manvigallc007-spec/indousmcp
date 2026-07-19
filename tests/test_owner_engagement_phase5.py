"""Phase 5 — owner engagement: offers/announcements + reply-to-reviews (+ AI draft). Ownership is
enforced by the portal; owner_content scopes every write by (vertical, listing_id). Real dev DB,
ZZTEST rows, try/finally; login/LLM mocked."""

import indo_usa_mcp.assistant as assistant
from indo_usa_mcp import db, owner_content as oc, reviews as rv, verticals
from indo_usa_mcp.web import portal
from indo_usa_mcp.web.app import app
from starlette.testclient import TestClient

_client = TestClient(app)
_E = "zztest_p5@example.com"


def _mk_owned():
    """A listing whose `email` column = _E, so portal `_owned` treats _E as the owner."""
    rid = verticals.create_record("restaurants", {"name": "ZZTEST P5 Cafe", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7,
                                                  "email": _E}, source="test")["id"]
    return rid


def _cleanup(rid):
    db.execute("DELETE FROM owner_posts WHERE listing_id=%s", (rid,))
    db.execute("DELETE FROM reviews WHERE listing_id=%s", (rid,))
    db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def _published_review(rid, body="Good food, slow service.", stars=4):
    r = rv.submit("restaurants", rid, stars, body=body, name="Asha")
    db.execute("UPDATE reviews SET status='published' WHERE id=%s", (r["id"],))
    return r["id"]


# --------------------------------------------------------------- owner_content
def test_create_offer_screens_and_lists():
    rid = _mk_owned()
    try:
        assert oc.create_post("restaurants", rid, _E, title="20% off thalis")["ok"]
        assert oc.create_post("restaurants", rid, _E, title="a")["error"] == "too_short"
        assert oc.create_post("restaurants", rid, _E, title="visit http://spam.com now!!!")["error"] == "flagged"
        assert [p["title"] for p in oc.active_posts("restaurants", rid)] == ["20% off thalis"]
    finally:
        _cleanup(rid)


def test_expired_offer_hidden_from_public():
    rid = _mk_owned()
    try:
        oc.create_post("restaurants", rid, _E, title="Yesterday only", expires_at="2000-01-01")
        assert oc.active_posts("restaurants", rid) == []      # expired -> not public
        assert len(oc.owner_posts("restaurants", rid, _E)) == 1   # owner still sees it in manage
    finally:
        _cleanup(rid)


def test_reply_is_scoped_to_the_right_listing():
    rid = _mk_owned()
    try:
        rev = _published_review(rid)
        assert oc.reply_to_review(rev, "restaurants", rid, "Thanks — we've added staff.")["ok"]
        assert oc.reply_to_review(rev, "restaurants", 999_999, "x hello")["error"] == "not_found"
        got = next(x for x in rv.list_for_listing("restaurants", rid) if x["id"] == rev)
        assert got["owner_reply"].startswith("Thanks")
        oc.clear_reply(rev, "restaurants", rid)
        got2 = next(x for x in rv.list_for_listing("restaurants", rid) if x["id"] == rev)
        assert got2["owner_reply"] is None
    finally:
        _cleanup(rid)


def test_ai_reply_draft(monkeypatch):
    monkeypatch.setattr(assistant, "llm_active", lambda: True)
    monkeypatch.setattr(assistant, "complete_text", lambda s, u: "Thank you so much! Please visit again.")
    draft = oc.ai_reply_draft("ZZTEST Cafe", {"rating": 5, "body": "Loved it"})
    assert draft == "Thank you so much! Please visit again."
    monkeypatch.setattr(assistant, "llm_active", lambda: False)
    assert oc.ai_reply_draft("ZZTEST Cafe", {"rating": 5, "body": "Loved it"}) is None


# --------------------------------------------------------------- public listing surfaces
def test_public_listing_shows_offer_and_owner_reply():
    rid = _mk_owned()
    try:
        oc.create_post("restaurants", rid, _E, title="Free lassi with any thali")
        rev = _published_review(rid, body="Loved it!", stars=5)
        oc.reply_to_review(rev, "restaurants", rid, "Thank you, come again!")
        html = _client.get(f"/listing/restaurants/{rid}").text
        assert "Free lassi with any thali" in html
        assert "Response from the owner" in html and "Thank you, come again!" in html
    finally:
        _cleanup(rid)


# --------------------------------------------------------------- portal manage (ownership-gated)
def test_manage_page_owner_only(monkeypatch):
    rid = _mk_owned()
    try:
        monkeypatch.setattr(portal, "portal_email", lambda req: _E)
        _published_review(rid)
        html = _client.get(f"/portal/listing/restaurants/{rid}").text
        assert "Offers" in html and "Reply" in html and "Draft with AI" in html
        # a different signed-in user can't manage it
        monkeypatch.setattr(portal, "portal_email", lambda req: "intruder@example.com")
        assert _client.get(f"/portal/listing/restaurants/{rid}", follow_redirects=False).status_code == 403
    finally:
        _cleanup(rid)


def test_manage_offer_and_reply_routes(monkeypatch):
    rid = _mk_owned()
    try:
        monkeypatch.setattr(portal, "portal_email", lambda req: _E)
        rev = _published_review(rid)
        r = _client.post(f"/portal/listing/restaurants/{rid}/offer",
                         data={"kind": "offer", "title": "Weekend biryani special"}, follow_redirects=False)
        assert r.status_code == 303
        assert any(p["title"] == "Weekend biryani special" for p in oc.active_posts("restaurants", rid))
        r2 = _client.post(f"/portal/listing/restaurants/{rid}/reply",
                          data={"review_id": str(rev), "text": "Thanks for visiting!"}, follow_redirects=False)
        assert r2.status_code == 303
        got = next(x for x in rv.list_for_listing("restaurants", rid) if x["id"] == rev)
        assert got["owner_reply"] == "Thanks for visiting!"
    finally:
        _cleanup(rid)
