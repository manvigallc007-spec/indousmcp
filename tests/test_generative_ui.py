"""Generative UI in chat: an answer renders components, not just prose + cards.

Three pieces, all zero-cost:
  * an inline map of exactly these results, reusing web/mapview (one implementation, so a fix to
    panning or to the OSM tile-politeness rules lands on the chat page too);
  * contextual follow-up chips, derived from the results rather than from the model — so they work
    identically when llm_provider is "search" and cost nothing;
  * a compare table built from the cards already in hand, with no extra request.
"""

import re

from starlette.testclient import TestClient

from indo_usa_mcp import assistant, db, verticals
from indo_usa_mcp.web import mapview
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_CITY = "Zzgenui"


def _mk(name, **over):
    rec = {"name": name, "city": _CITY, "state": "TX", "lat": 33.0, "lng": -96.7}
    rec.update(over)
    return verticals.create_record("restaurants", rec, source="test")["id"]


# ------------------------------------------------------------------ follow-ups (pure logic)
_CARDS = [
    {"vertical": "restaurants", "name": "A", "open_now": True, "community_rating": 4.3,
     "features": ["vegetarian", "delivery"], "lat": 1.0, "lng": 2.0, "id": 1},
    {"vertical": "temples", "name": "B", "open_now": False, "features": ["parking"],
     "lat": 1.1, "lng": 2.1, "id": 2},
]


def test_followups_offer_open_now_only_when_the_data_can_answer_it():
    with_hours = assistant.followups("thali", _CARDS, {}, None)
    assert any(f.get("action") == "open_now" for f in with_hours)
    # no hours on any result -> offering the filter would just produce an empty list
    blind = [{"vertical": "restaurants", "name": "A", "open_now": None, "id": 1}]
    assert not any(f.get("action") == "open_now" for f in assistant.followups("thali", blind, {}, None))


def test_followups_do_not_offer_a_filter_that_is_already_on():
    on = assistant.followups("thali", _CARDS, {"open_now": True}, None)
    assert not any(f.get("action") == "open_now" for f in on)


def test_mixed_results_offer_to_narrow_to_one_category():
    out = assistant.followups("food and a temple", _CARDS, {}, None)
    actions = [f.get("action") for f in out]
    assert "vertical:restaurants" in actions and "vertical:temples" in actions


def test_single_category_results_do_not_offer_a_pointless_narrowing():
    one = [dict(_CARDS[0]), dict(_CARDS[0])]
    out = assistant.followups("thali", one, {}, None)
    assert not any((f.get("action") or "").startswith("vertical:") for f in out)


def test_refinements_only_offer_tags_the_results_actually_have():
    """Offering a filter the results cannot satisfy sends the visitor into an empty list."""
    # single category + known location, so the chip budget isn't spent on narrowing/near-me first
    cards = [{"vertical": "restaurants", "name": "A", "id": 1,
              "features": ["vegetarian", "delivery"]},
             {"vertical": "restaurants", "name": "B", "id": 2, "features": ["vegetarian"]}]
    out = assistant.followups("thali", cards, {}, {"lat": 1, "lng": 2})
    sends = " ".join(f.get("send", "") for f in out)
    assert "vegetarian" in sends, f"a present tag was not offered: {out}"
    assert "halal" not in sends, "offered a tag no result has"
    assert "parking" not in sends, "offered a tag no result has"


def test_a_refinement_already_in_the_question_is_not_offered_again():
    cards = [{"vertical": "restaurants", "name": "A", "id": 1, "features": ["vegetarian"]},
             {"vertical": "restaurants", "name": "B", "id": 2, "features": ["vegetarian"]}]
    out = assistant.followups("vegetarian thali", cards, {}, {"lat": 1, "lng": 2})
    assert not any("vegetarian" in f.get("send", "") for f in out)


def test_near_me_is_offered_only_when_location_is_unknown():
    assert any(f.get("action") == "near_me" for f in assistant.followups("thali", _CARDS, {}, None))
    known = assistant.followups("thali", _CARDS, {}, {"lat": 33.0, "lng": -96.7})
    assert not any(f.get("action") == "near_me" for f in known)


def test_compare_needs_at_least_two_results():
    assert any(f.get("action") == "compare"
               for f in assistant.followups("x", _CARDS, {}, {"lat": 1, "lng": 2}))
    one = assistant.followups("x", _CARDS[:1], {}, {"lat": 1, "lng": 2})
    assert not any(f.get("action") == "compare" for f in one)


def test_a_miss_offers_a_wider_net_instead_of_a_dead_end():
    out = assistant.followups("nothing matches this", [], {"open_now": True, "vertical": "temples"}, None)
    actions = [f.get("action") for f in out]
    assert "clear_open_now" in actions           # drop the restriction that may have caused the miss
    assert "vertical:" in actions                # search all categories
    assert any(f.get("href") == "/browse" for f in out)


def test_followups_are_capped():
    many = [dict(c, features=["vegetarian", "vegan", "jain", "halal", "delivery", "catering"])
            for c in _CARDS]
    assert len(assistant.followups("food", many, {}, None)) <= assistant._MAX_FOLLOWUPS


def test_followups_never_raise_on_odd_input():
    assert assistant.followups("", [], None, None) is not None
    assert assistant.followups("x", [{}], {}, None) is not None


# ------------------------------------------------------------------ cards carry coordinates
def test_cards_carry_coordinates_so_a_map_can_be_built():
    rid = _mk("ZZTEST Genui Cafe")
    try:
        d = _client.post("/chat/api", json={
            "messages": [{"role": "user", "content": f"ZZTEST Genui in {_CITY}"}],
            "filters": {}}).json()
        card = next((c for c in d["cards"] if c["name"].startswith("ZZTEST Genui")), None)
        assert card and card["lat"] is not None and card["lng"] is not None
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# ------------------------------------------------------------------ the API payload
def test_chat_api_returns_a_map_and_followups():
    rid = _mk("ZZTEST Mappable Cafe")
    try:
        d = _client.post("/chat/api", json={
            "messages": [{"role": "user", "content": f"ZZTEST Mappable in {_CITY}"}],
            "filters": {}}).json()
        m = d.get("map")
        assert m, "no map in the reply"
        assert m["count"] >= 1 and m["cfg"]["pins"]
        assert "imap-box" in m["box"] and "imap-ctl" in m["box"]
        assert "openstreetmap.org/copyright" in m["attr"]
        assert isinstance(d.get("followups"), list)
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_a_reply_with_no_geocoded_results_has_no_map():
    d = _client.post("/chat/api", json={
        "messages": [{"role": "user", "content": "what is diwali"}], "filters": {}}).json()
    assert not d.get("map")


def test_the_map_payload_reuses_mapview():
    """Not a second implementation: the box markup and config come from web/mapview."""
    rows = [{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0, "vertical": "restaurants"}]
    cfg = mapview.config(rows, "restaurants")
    assert cfg and cfg["tile"] == mapview.TILE_URL and cfg["maxZ"] == mapview._MAX_Z
    assert "imap-box" in mapview.box_html("x")


# ------------------------------------------------------------------ the client layer
def test_chat_page_loads_the_map_client_and_styles():
    t = _client.get("/").text
    assert '<link rel="stylesheet" href="/map.css">' in t
    assert '<script src="/map.js">' in t
    # the client must load before anything that calls into it
    assert t.index('src="/map.js"') < t.index("function answerMap(")
    assert ".imap-box{" in _client.get("/map.css").text
    assert "window.naMap=window.naMap||" in _client.get("/map.js").text


def test_chat_page_ships_every_renderer():
    t = _client.get("/").text
    for fn in ("function answerMap(", "function followupRow(", "function showCompare(",
               "function applyRefinement("):
        assert fn in t, f"missing {fn}"
    assert ".fups{" in t and ".cmp table{" in t                # chat-only styles stay inline


def test_both_transports_pass_the_payload_to_one_renderer():
    """The streaming and blocking paths must render identically; two renderers would drift."""
    t = _client.get("/").text
    assert "fillBot(content,reply,cards,suggest,contribute,mapData,fups)" in t
    assert "data.map,data.followups" in t                       # blocking
    assert "fin.map,fin.followups" in t                         # streaming


def test_compare_table_escapes_listing_text():
    """Names and tags are scraper/user data and reach innerHTML, so they go through cesc()."""
    t = _client.get("/").text
    assert "function cesc(" in t and "d.textContent=" in t
    assert "cesc(c.name" in t and "cesc(c.phone)" in t


def test_inline_map_defers_tiles_until_opened():
    """The chat map is a <details> like the others, so an answer costs no tile requests until the
    visitor asks for the map. This is the OSM politeness guarantee, inherited not re-implemented."""
    assert "det.className='imap'" in _client.get("/").text      # the chat wrapper is a <details>
    assert "det.addEventListener('toggle'" in _client.get("/map.js").text   # shared client defers


def test_no_unresolved_placeholders_on_the_chat_page():
    assert not re.findall(r"__[A-Z][A-Z0-9_]{2,}__", _client.get("/").text)
