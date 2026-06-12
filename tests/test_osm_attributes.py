"""Tests for OSM attribute -> tag enrichment (no DB)."""

from indo_usa_mcp import describe, osm


def test_attribute_tags_from_osm():
    t = osm.attribute_tags({
        "takeaway": "yes", "delivery": "yes", "outdoor_seating": "yes",
        "wheelchair": "limited", "internet_access": "wlan", "diet:vegan": "only",
        "diet:halal": "yes", "payment:cards": "yes", "smoking": "no"})
    assert {"takeout", "delivery", "outdoor-seating", "wheelchair-accessible", "wifi",
            "vegan", "halal", "cards-accepted", "smoke-free"} <= set(t)


def test_attribute_tags_empty_when_absent():
    assert osm.attribute_tags({"name": "X", "amenity": "restaurant"}) == []


def test_description_mentions_amenities():
    d = describe.describe("restaurants", {
        "name": "Spice Hub", "city": "Edison", "state": "NJ",
        "tags": ["delivery", "takeout", "wheelchair-accessible", "biryani"]})
    assert "Amenities:" in d and "delivery" in d and "wheelchair accessible" in d
