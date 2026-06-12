"""Tests for descriptions, embedding text source, and geocoding (light)."""

from indo_usa_mcp import describe, embeddings, geocode


def test_restaurant_description_is_natural_prose():
    d = describe.describe("restaurants", {
        "name": "Saffron House", "region_tag": "Gujarati", "city": "Edison", "state": "NJ",
        "dietary_tags": ["vegetarian", "jain"], "price_range": "$$",
        "hours_json": {"raw": "Mo-Su 11:00-22:00"}})
    assert "Saffron House" in d and "Gujarati" in d and "Edison, NJ" in d
    assert "vegetarian" in d and "$$" in d and "11:00-22:00" in d


def test_temple_and_grocery_descriptions():
    t = describe.describe("temples", {"name": "Shiva Temple", "religion": "sikh",
                                      "city": "Fremont", "state": "CA", "deity": "Guru"})
    assert "gurdwara" in t.lower() and "Fremont, CA" in t
    g = describe.describe("groceries", {"name": "Patel Bros", "region_tag": "Gujarati",
                                        "store_type": "supermarket", "city": "Chicago", "state": "IL"})
    assert "grocery" in g.lower() and "supermarket" in g


def test_embeddings_text_prefers_description():
    assert embeddings.text_for({"description": "A cozy spot", "name": "X"}) == "A cozy spot"
    assert "X" in embeddings.text_for({"name": "X", "city": "Y"})  # falls back to fields


def test_geocode_fills_us_city_state():
    city, state = geocode.city_state(37.3688, -122.0363)  # Sunnyvale, CA
    assert city == "Sunnyvale"
    assert state in ("California", "CA")
