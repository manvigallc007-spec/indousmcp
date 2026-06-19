"""Duplicate auto-merge: the physical-identity clustering that decides what is safe to merge.

These cover the risky part (so a chain's two branches are NOT merged) without touching the DB."""

import indo_usa_mcp.verticals as v


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
