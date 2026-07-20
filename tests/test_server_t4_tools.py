"""Tranche 4 — agent-first MCP tools: save/unsave/list_saved, follow_city/list_follows,
ask_community_question, get_offers; owner_reply in get_reviews; offset pagination on the restaurant
tools. Write tools require an authenticated member email. Real dev DB, ZZTEST rows, try/finally;
output must be JSON-serializable."""

import json

from indo_usa_mcp import db, owner_content as oc, reviews as rv, server, verticals

_E = "zztest_mcp_t4@example.com"


def _tool_names():
    return set(server.mcp._tool_manager._tools.keys())


def _mk_listing(name="ZZTEST T4 Cafe", city="Plano"):
    return verticals.create_record("restaurants", {"name": name, "city": city, "state": "TX",
                                                   "lat": 33.0, "lng": -96.7,
                                                   "email": "owner@zz.com"}, source="test")["id"]


# --------------------------------------------------------------- registration
def test_t4_tools_registered():
    for t in ("save_place", "unsave_place", "list_saved_places", "follow_city", "list_follows",
              "ask_community_question", "get_offers"):
        assert t in _tool_names(), t


# --------------------------------------------------------------- saves require auth email
def test_save_requires_member_email_and_round_trips():
    rid = _mk_listing()
    try:
        assert server.save_place("", "restaurants", rid)["error"] == "member_email_required"
        r = server.save_place(_E, "restaurants", rid)
        assert r["ok"] and r["name"]
        out = server.list_saved_places(_E)
        assert out["count"] >= 1 and any(x["id"] == rid for x in out["results"])
        json.dumps(out)                                  # saved_at datetime must be stringified
        assert server.unsave_place(_E, "restaurants", rid)["ok"]
        assert not any(x["id"] == rid for x in server.list_saved_places(_E)["results"])
    finally:
        db.execute("DELETE FROM saved_places WHERE email=%s", (_E,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_follow_city_and_list():
    try:
        assert server.follow_city("", "Plano, TX")["error"] == "member_email_required"
        assert server.follow_city(_E, "Plano, TX")["ok"]
        fol = server.list_follows(_E)
        assert any(f["kind"] == "city" and f["value"] == "Plano, TX" for f in fol["results"])
    finally:
        db.execute("DELETE FROM follows WHERE email=%s", (_E,))


# --------------------------------------------------------------- ask question (moderated write)
def test_ask_community_question_requires_email():
    assert server.ask_community_question("Where is good chaat?", "")["error"] == "member_email_required"
    r = server.ask_community_question("ZZTEST where is good chaat in Iselin NJ?", _E, city="Iselin")
    try:
        assert r["ok"] and r["slug"]
    finally:
        db.execute("DELETE FROM questions WHERE asker_email=%s", (_E,))


# --------------------------------------------------------------- offers
def test_get_offers_lists_live_owner_posts():
    rid = _mk_listing(name="ZZTEST Offer T4", city="Frisco")
    try:
        oc.create_post("restaurants", rid, "owner@zz.com", kind="offer", title="Free lassi this week")
        out = server.get_offers(city="Frisco")
        assert out["count"] >= 1 and any(o["listing_id"] == rid and o["title"] == "Free lassi this week"
                                         for o in out["results"])
        json.dumps(out)
    finally:
        db.execute("DELETE FROM owner_posts WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- get_reviews owner_reply
def test_get_reviews_includes_owner_reply():
    rid = _mk_listing()
    try:
        r = rv.submit("restaurants", rid, 4, body="Decent.", name="Sam")
        db.execute("UPDATE reviews SET status='published' WHERE id=%s", (r["id"],))
        oc.reply_to_review(r["id"], "restaurants", rid, "Thanks for visiting!")
        got = server.get_reviews("restaurants", rid)
        assert got["reviews"] and got["reviews"][0]["owner_reply"] == "Thanks for visiting!"
        assert got["reviews"][0]["owner_reply_at"] is not None
    finally:
        db.execute("DELETE FROM reviews WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- offset pagination
def test_restaurant_tools_support_offset():
    ids = [_mk_listing(name=f"ZZTEST Page {i}", city="Zzpage") for i in range(5)]
    try:
        p1 = server.get_indian_restaurants(city="Zzpage", limit=2, offset=0)
        p2 = server.get_indian_restaurants(city="Zzpage", limit=2, offset=2)
        assert "has_more" in p1 and p1["offset"] == 0 and p2["offset"] == 2
        ids1 = {r["id"] for r in p1["results"]}
        ids2 = {r["id"] for r in p2["results"]}
        assert ids1 and ids2 and ids1.isdisjoint(ids2)      # different pages, no overlap
        st = server.search_restaurants_by_text("ZZTEST Page", city="Zzpage", limit=2, offset=2)
        assert "has_more" in st and st["offset"] == 2
    finally:
        for rid in ids:
            db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
