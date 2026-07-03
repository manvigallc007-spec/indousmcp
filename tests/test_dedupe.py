"""Duplicate auto-merge: the physical-identity clustering that decides what is safe to merge.

These cover the risky part (so a chain's two branches are NOT merged) without touching the DB."""

import indo_usa_mcp.embeddings as emb
import indo_usa_mcp.verticals as v
from indo_usa_mcp import db


def _row(**k):
    base = {"id": 1, "name": "Spice Hut", "city": "Plano", "state": "TX", "phone": None,
            "website": None, "address_full": None, "lat": None, "lng": None,
            "is_claimed": False, "confidence_score": 0.5}
    base.update(k)
    return base


def test_same_place_by_phone():
    assert v._same_place(_row(id=1, phone="(972) 555-1234"), _row(id=2, phone="9725551234")) is True


def test_same_place_by_website_host():
    assert v._same_place(_row(id=1, website="https://www.spicehut.com/menu"),
                         _row(id=2, website="http://spicehut.com")) is True


def test_same_place_by_close_coords():
    assert v._same_place(_row(id=1, lat=33.0000, lng=-96.7000),
                         _row(id=2, lat=33.0008, lng=-96.7005)) is True   # ~100m apart


def test_chain_branches_not_merged():
    # Same name+city but two real locations (different address/phone/coords) must NOT merge.
    a = _row(id=1, address_full="100 First St", phone="9725550001", lat=33.0, lng=-96.7)
    b = _row(id=2, address_full="900 Legacy Dr", phone="9725559999", lat=33.2, lng=-96.9)
    assert v._same_place(a, b) is False


def test_both_without_locating_info_are_dupes():
    assert v._same_place(_row(id=1), _row(id=2)) is True


def test_cluster_keeps_only_real_dupes():
    a = _row(id=1, phone="9725550001")
    b = _row(id=2, phone="9725550001")                                   # dup of a
    c = _row(id=3, address_full="900 Legacy Dr", phone="9725559999", lat=33.2, lng=-96.9)
    clusters = v._cluster([a, b, c])
    assert len(clusters) == 1
    assert {r["id"] for r in clusters[0]} == {1, 2}                      # distinct c left alone


def test_pick_survivor_prefers_claimed_then_confidence():
    assert v._pick_survivor([_row(id=1, is_claimed=False, confidence_score=0.9),
                             _row(id=2, is_claimed=True, confidence_score=0.4)])["id"] == 2
    assert v._pick_survivor([_row(id=3, confidence_score=0.95),
                             _row(id=4, confidence_score=0.6)])["id"] == 3


def test_completeness_counts_filled_fields():
    assert v._completeness(_row(phone="x", website="y")) == 2
    assert v._completeness(_row()) == 0


def test_merge_fill_and_admin_merge_fill_are_distinct_constants():
    # Regression: these two USED TO share the name `_MERGE_FILL`, so the later definition
    # (admin's, which includes the JSONB `hours_json`) silently shadowed the earlier one (auto
    # dedupe's, scalar-only) -> dedupe_listings tried to gap-fill hours_json with a raw dict and
    # psycopg rejected it, crashing the `curation` agent. Keep them separate, scalar-only for dedupe.
    assert v._MERGE_FILL is not v._ADMIN_MERGE_FILL
    assert "hours_json" not in v._MERGE_FILL
    assert "hours_json" in v._ADMIN_MERGE_FILL          # admin merge intentionally fills it


def test_dedupe_listings_apply_survives_jsonb_hours_field(monkeypatch):
    # Regression (real DB, apply path): duplicates where the LOSER has hours_json set used to crash
    # the whole agent run with "cannot adapt type 'dict'". Must merge cleanly and leave hours_json
    # alone (it is intentionally NOT in the auto-dedupe fill list).
    monkeypatch.setattr(emb, "enabled", lambda: False)
    names = ("ZZDedupe Hours Test",)
    db.execute("DELETE FROM restaurants WHERE name = ANY(%s)", (list(names),))
    try:
        addr = "100 Main St"
        keep = v.create_record("restaurants", {
            "name": "ZZDedupe Hours Test", "city": "Testville", "state": "TX",
            "address_full": addr, "lat": 30.0, "lng": -97.0}, source="test")
        # Different (rounded) coords so create_record's own natural_key dedup doesn't reject this as
        # a literal duplicate; the SAME address_full is what makes dedupe_listings's _same_place
        # cluster them together regardless of the coordinate gap. "hours" (raw string) is what
        # create_record accepts -- it builds hours_json (a JSONB dict) internally.
        drop = v.create_record("restaurants", {
            "name": "ZZDedupe Hours Test", "city": "Testville", "state": "TX",
            "address_full": addr, "lat": 30.05, "lng": -97.05,
            "hours": "Mo-Su 11:00-22:00"}, source="test")
        assert keep.get("ok") and drop.get("ok")

        out = v.dedupe_listings(dry_run=False)                  # must not raise

        remaining = db.query(
            "SELECT id, deleted_at FROM restaurants WHERE name = %s ORDER BY id", (names[0],))
        active = [r for r in remaining if r["deleted_at"] is None]
        assert len(active) == 1                                 # one survivor, one soft-deleted
        assert out["removed"] >= 1
    finally:
        db.execute("DELETE FROM restaurants WHERE name = ANY(%s)", (list(names),))
