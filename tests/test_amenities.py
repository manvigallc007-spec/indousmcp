"""Amenity/dietary/service tags (captured from OSM at ingestion) are surfaced to people + agents.
No DB."""

from indo_usa_mcp import assistant, tags


def test_for_display_keeps_amenities_skips_dishes():
    out = tags.for_display(["biryani", "delivery", "halal", "dosa", "wheelchair-accessible"])
    joined = " ".join(out).lower()
    assert "delivery" in joined and "halal" in joined and "accessible" in joined
    assert "biryani" not in joined and "dosa" not in joined          # dish tags are not "features"


def test_for_display_dedupe_limit_empty():
    assert tags.for_display(None) == []
    assert tags.for_display([]) == []
    many = ["delivery", "takeout", "halal", "vegan", "wifi", "reservations", "catering", "buffet"]
    assert len(tags.for_display(many, limit=3)) == 3


def test_cards_carry_features():
    res = {"results": [{"vertical": "restaurants", "name": "X", "id": 1,
                        "tags": ["delivery", "biryani", "wheelchair-accessible"]}]}
    cards = assistant._cards(res)
    feats = cards[0]["features"]
    assert any("Delivery" in f for f in feats) and any("Accessible" in f for f in feats)
    assert not any("biryani" in f.lower() for f in feats)
