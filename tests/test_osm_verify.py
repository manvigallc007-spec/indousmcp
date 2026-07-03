"""OSM verification: confirm + enrich non-OSM listings against OpenStreetMap (reward-only).

Pure helpers + mocked orchestration + a real-DB write test for _apply_match. No live network."""

import indo_usa_mcp.embeddings as emb
import indo_usa_mcp.osm as osm
import indo_usa_mcp.osm_verify as osm_verify
from indo_usa_mcp import db as _db
from indo_usa_mcp import verticals
from indo_usa_mcp.osm import OverpassError


# ------------------------------------------------------------------ pure helpers (no DB/net)
def test_nearby_named_builds_around_query(monkeypatch):
    cap = {}
    monkeypatch.setattr(osm, "overpass_post",
                        lambda q, timeout, **k: cap.update(q=q, timeout=timeout)
                        or {"elements": [{"tags": {"name": "X"}}]})
    els = osm.nearby_named(40.5, -74.2, radius_m=300)
    assert els == [{"tags": {"name": "X"}}]
    assert "around:300,40.5,-74.2" in cap["q"] and "[out:json]" in cap["q"]


def test_contact_from_tags_extracts():
    info = osm.contact_from_tags({"contact:phone": "+1 555", "website": "https://y.example",
                                  "opening_hours": "Mo-Fr 09:00-17:00", "diet:vegetarian": "yes"})
    assert info["phone"] == "+1 555" and info["website"] == "https://y.example"
    assert info["hours"] == "Mo-Fr 09:00-17:00" and "vegetarian" in info["tags"]
    empty = osm.contact_from_tags({})
    assert empty["phone"] is None and empty["website"] is None and empty["tags"] == []


def test_name_match():
    assert osm_verify._name_match("Sri Ganesha Temple", "sri ganesha temple")       # equality
    assert osm_verify._name_match("Patel Brothers", "Patel Brothers Grocery")        # containment
    assert osm_verify._name_match("India Bazaar Fremont", "Fremont India Bazaar")     # token overlap
    assert not osm_verify._name_match("Taj Mahal", "Star Kabob House")
    assert not osm_verify._name_match("", "anything")


def test_match_element_skips_homonyms_and_nonmatches():
    els = [{"tags": {"name": "American Indian Cultural Center"}},   # excluded homonym
           {"tags": {"name": "Sri Ganesha Temple"}}]               # the real match
    assert osm_verify._match_element("Sri Ganesha Temple", els)["tags"]["name"] == "Sri Ganesha Temple"
    assert osm_verify._match_element("Sri Ganesha Temple", [{"tags": {"name": "Unrelated Cafe"}}]) is None


# ------------------------------------------------------------------ orchestration (mocked db/osm)
def _mock_scan(monkeypatch, row, elements=None, raise_overpass=False):
    monkeypatch.setattr(osm_verify, "_VERTICALS", ["services"])
    monkeypatch.setattr(osm_verify.verticals, "_table_columns",
                        lambda t: {"osm_checked_at", "osm_verified_at", "phone", "website", "tags",
                                   "updated_at"})
    monkeypatch.setattr(osm_verify.db, "query", lambda *a, **k: [row])
    monkeypatch.setattr(osm_verify.db, "query_one", lambda *a, **k: None)
    monkeypatch.setattr(osm_verify.embeddings, "enabled", lambda: False)
    monkeypatch.setattr(osm_verify.time, "sleep", lambda *a: None)
    execs = []
    monkeypatch.setattr(osm_verify.db, "execute", lambda sql, params=None: execs.append(sql))

    def _near(lat, lng, **k):
        if raise_overpass:
            raise OverpassError("down")
        return elements or []
    monkeypatch.setattr(osm_verify.osm, "nearby_named", _near)
    return execs


def test_verify_verifies_a_match(monkeypatch):
    row = {"id": 1, "name": "Sri Ganesha Temple", "lat": 40.0, "lng": -74.0,
           "phone": None, "website": None, "tags": [], "confidence_score": 0.7}
    execs = _mock_scan(monkeypatch, row, elements=[{"tags": {
        "name": "Sri Ganesha Temple", "contact:phone": "+1 555 0100",
        "website": "https://ganesha.example"}}])
    out = osm_verify.verify_listings(limit_per_vertical=10)
    assert out["services"] == {"checked": 1, "verified": 1, "enriched": 1}
    assert out["_total"]["verified"] == 1
    upd = " ".join(execs)
    assert "phone = %s" in upd and "website = %s" in upd and "osm_verified_at = now()" in upd


def test_verify_miss_sets_cursor_only(monkeypatch):
    row = {"id": 2, "name": "Sri Ganesha Temple", "lat": 40.0, "lng": -74.0,
           "phone": None, "website": None, "tags": [], "confidence_score": 0.7}
    execs = _mock_scan(monkeypatch, row, elements=[{"tags": {"name": "Unrelated Diner"}}])
    out = osm_verify.verify_listings(limit_per_vertical=10)
    assert out["services"] == {"checked": 1, "verified": 0, "enriched": 0}
    assert execs == ["UPDATE services SET osm_checked_at = now() WHERE id = %s"]  # cursor only


def test_verify_stops_on_overpass_down(monkeypatch):
    row = {"id": 3, "name": "X", "lat": 1.0, "lng": 2.0, "phone": None, "website": None,
           "tags": [], "confidence_score": 0.7}
    _mock_scan(monkeypatch, row, raise_overpass=True)
    out = osm_verify.verify_listings(limit_per_vertical=10)
    assert out["services"]["stopped"] == "overpass_unavailable"


def test_verify_skips_when_migration_missing(monkeypatch):
    monkeypatch.setattr(osm_verify, "_VERTICALS", ["services"])
    monkeypatch.setattr(osm_verify.verticals, "_table_columns", lambda t: {"phone"})  # no osm_checked_at
    monkeypatch.setattr(osm_verify.db, "query",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not query")))
    out = osm_verify.verify_listings()
    assert "services" not in out                          # skipped before touching the DB


# ------------------------------------------------------------------ real-DB write logic (_apply_match)
def _seed(monkeypatch, name, **extra):
    monkeypatch.setattr(emb, "enabled", lambda: False)   # no embedding on create
    _db.execute("DELETE FROM services WHERE name = %s", (name,))
    data = {"name": name, "city": "Testville", "state": "TX", "lat": 41.0, "lng": -96.0,
            "service_type": "consulate"}
    data.update(extra)
    return verticals.create_record("services", data, source="consulate", confidence=0.7)


def test_apply_match_fills_bumps_and_stamps(monkeypatch):
    name = "ZZOsm Verify Fill"
    try:
        res = _seed(monkeypatch, name)
        assert res.get("ok"), res
        row = _db.query_one("SELECT id, name, phone, website, tags, confidence_score FROM services "
                            "WHERE id = %s", (res["id"],))
        monkeypatch.setattr(osm_verify.embeddings, "enabled", lambda: False)
        changed = osm_verify._apply_match(
            "services", verticals._table_columns("services"), row,
            {"phone": "+1 555 0100", "website": "https://x.example", "tags": ["vegetarian"]})
        assert changed is True
        a = _db.query_one("SELECT phone, website, tags, confidence_score, osm_verified_at, "
                          "osm_checked_at, last_seen_at FROM services WHERE id = %s", (res["id"],))
        assert a["phone"] == "+1 555 0100" and a["website"] == "https://x.example"
        assert "vegetarian" in (a["tags"] or [])
        assert float(a["confidence_score"]) > 0.7            # independent OSM confirmation -> bump
        assert a["osm_verified_at"] is not None and a["osm_checked_at"] is not None
    finally:
        _db.execute("DELETE FROM services WHERE name = %s", (name,))


def test_apply_match_preserves_existing_values(monkeypatch):
    name = "ZZOsm Verify Keep"
    try:
        res = _seed(monkeypatch, name, phone="+1 999 0000")
        row = _db.query_one("SELECT id, name, phone, website, tags, confidence_score FROM services "
                            "WHERE id = %s", (res["id"],))
        monkeypatch.setattr(osm_verify.embeddings, "enabled", lambda: False)
        osm_verify._apply_match("services", verticals._table_columns("services"), row,
                                {"phone": "+1 555 0100", "website": None, "tags": []})
        a = _db.query_one("SELECT phone, confidence_score FROM services WHERE id = %s", (res["id"],))
        assert a["phone"] == "+19990000"                     # existing (normalized) preserved, not OSM's
        assert a["phone"] != "+15550100"                     # fill-missing only: OSM did NOT overwrite
        assert float(a["confidence_score"]) > 0.7            # still gets the trust bump
    finally:
        _db.execute("DELETE FROM services WHERE name = %s", (name,))
