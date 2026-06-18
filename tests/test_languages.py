"""languages_spoken: parse/normalize, fold into searchable tags + describe text, surface on cards.
Pure functions, no DB (create/edit covered by a live end-to-end check)."""

from indo_usa_mcp import assistant, describe, tags


def test_parse_languages_normalizes_and_dedupes():
    assert tags.parse_languages("telugu, hindi ,english") == ["Telugu", "Hindi", "English"]
    assert tags.parse_languages(["Telugu", "telugu", "TAMIL"]) == ["Telugu", "Tamil"]
    assert tags.parse_languages("oriya / odia") == ["Odia"]        # canonical alias + dedupe
    assert tags.parse_languages("Klingon") == ["Klingon"]          # unknown kept, title-cased
    assert tags.parse_languages("") == [] and tags.parse_languages(None) == []


def test_language_tags():
    assert tags.language_tags(["Telugu", "Hindi"]) == ["telugu-speaking", "hindi-speaking"]
    assert tags.language_tags([]) == [] and tags.language_tags(None) == []


def test_describe_includes_speaks():
    d = describe.describe("professionals",
                          {"name": "Dr X", "city": "Irving", "state": "TX",
                           "languages": ["Telugu", "Hindi"]})
    assert "Speaks Telugu, Hindi." in d


def test_describe_no_speaks_when_empty():
    d = describe.describe("professionals", {"name": "Dr X", "city": "Irving", "state": "TX"})
    assert "Speaks" not in d


def test_cards_carry_languages():
    res = {"results": [{"vertical": "professionals", "name": "Dr X", "id": 1,
                        "languages": ["Telugu"]}]}
    assert assistant._cards(res)[0]["languages"] == ["Telugu"]
