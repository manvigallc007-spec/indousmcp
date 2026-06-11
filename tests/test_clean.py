"""Unit tests for the cleaning/enrichment layer (no database needed)."""

from indo_usa_mcp.pipeline import clean


def test_normalize_name_strips_accents_and_punctuation():
    assert clean.normalize_name("Café  Madrás!!") == "cafe madras"


def test_natural_key_rounds_coordinates():
    k = clean.natural_key("Dosa Place", 37.123456, -122.987654)
    assert k == "dosa place@37.123,-122.988"


def test_natural_key_without_coords_is_name_only():
    assert clean.natural_key("Dosa Place", None, None) == "dosa place"


def test_normalize_phone_keeps_digits_and_plus():
    assert clean.normalize_phone("+1 (408) 555-1234") == "+14085551234"
    assert clean.normalize_phone("") is None


def test_infer_region_and_dietary_from_text():
    rec = clean.clean(
        {
            "name": "Pure Veg Udupi Bhavan",
            "lat": 37.0,
            "lng": -122.0,
            "source_name": "test",
        }
    )
    assert rec["region_tag"] == "South Indian"
    assert "vegetarian" in rec["dietary_tags"]


def test_score_rewards_completeness():
    sparse = clean.clean({"name": "X", "source_name": "t"})
    full = clean.clean(
        {
            "name": "Saravana Bhavan",
            "lat": 37.0,
            "lng": -122.0,
            "address_full": "123 Main St, Sunnyvale, CA",
            "phone": "+14085551234",
            "website": "https://example.com",
            "city": "Sunnyvale",
            "source_name": "t",
        }
    )
    assert full["confidence_score"] > sparse["confidence_score"]
    assert 0.0 <= full["confidence_score"] <= 1.0


def test_claim_link_format():
    from indo_usa_mcp.pipeline import outreach

    link = outreach.claim_link(42, "tok123")
    assert "type=restaurant" in link
    assert "id=42" in link
    assert "token=tok123" in link


def test_pick_channel_prefers_phone_then_website():
    from indo_usa_mcp.pipeline import outreach

    assert outreach._pick_channel({"phone": "+1408", "website": "x"}) == "whatsapp"
    assert outreach._pick_channel({"phone": None, "website": "x"}) == "form"
    assert outreach._pick_channel({"phone": None, "website": None}) is None


def test_draft_message_is_honest_and_has_optout():
    from indo_usa_mcp.pipeline import outreach

    msg = outreach.draft_message(
        {"name": "Dosa Hut", "city": "Sunnyvale"}, "https://x/claim?id=1", "whatsapp"
    )
    assert "Dosa Hut" in msg
    assert "Sunnyvale" in msg
    assert "no cost" in msg.lower()
    assert "remove you" in msg.lower()  # opt-out present


def test_diff_ignores_empty_candidate_values():
    from indo_usa_mcp.pipeline import ingest

    existing = {"name": "A", "phone": "+1408", "website": "http://a", "dietary_tags": ["vegan"]}
    candidate = {"name": "A", "phone": None, "website": "http://b", "dietary_tags": ["vegan"]}
    diff = ingest._diff(existing, candidate)
    assert diff == {"website": "http://b"}
