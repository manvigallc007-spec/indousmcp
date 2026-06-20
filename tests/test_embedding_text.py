"""Richer vectorization (Phase C): text_for folds the structured facets into the embedding text."""

import indo_usa_mcp.embeddings as e


def test_text_for_folds_facets_into_description():
    rec = {"description": "Spice Hut is a South Indian restaurant.",
           "cuisine_type": "South Indian", "region_tag": "Andhra", "city": "Plano", "state": "TX",
           "price_range": "$$", "dietary_tags": ["vegetarian", "vegan"],
           "languages": ["Telugu", "Hindi"], "tags": ["delivery", "catering"]}
    t = e.text_for(rec)
    assert t.startswith("Spice Hut is a South Indian restaurant.")
    for token in ("Andhra", "Plano", "TX", "$$", "vegetarian", "Telugu", "delivery"):
        assert token in t, token


def test_text_for_underscored_type_fields_spaced():
    rec = {"description": "A clinic.", "profession_type": "doctor",
           "speciality": "internal_medicine", "languages": ["Telugu"]}
    t = e.text_for(rec)
    assert "internal medicine" in t and "Telugu" in t


def test_text_for_without_description_uses_attributes():
    rec = {"cuisine_type": "Punjabi", "city": "Edison", "state": "NJ", "languages": ["Punjabi"]}
    t = e.text_for(rec)
    assert "Punjabi" in t and "Edison" in t and "NJ" in t


def test_text_for_empty_record_is_safe():
    assert e.text_for({}) == ""
