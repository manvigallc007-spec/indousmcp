"""Tests for opening-hours parsing / 'open now' and tag extraction (no DB)."""

import datetime as dt

from indo_usa_mcp import hours, tags


def test_parse_simple_and_ranges():
    s = hours.parse("Mo-Fr 09:00-17:00")
    assert s["0"] == [[540, 1020]] and s["4"] == [[540, 1020]]
    assert "5" not in s and "6" not in s


def test_parse_multiple_rules_and_segments():
    s = hours.parse("Mo-Th 11:00-14:30,17:00-22:00; Fr 11:00-23:00")
    assert s["0"] == [[660, 870], [1020, 1320]]
    assert s["4"] == [[660, 1380]]


def test_parse_overnight_and_247():
    s = hours.parse("Su-Th 17:00-02:00")
    assert s["6"] == [[1020, 1560]]  # Sunday 17:00 -> 02:00 next day
    assert hours.parse("24/7")["0"] == [[0, 1440]]


def test_is_open():
    s = hours.parse("Mo-Su 09:00-17:00")
    mon_noon = dt.datetime(2026, 6, 8, 12, 0)   # Monday
    mon_8pm = dt.datetime(2026, 6, 8, 20, 0)
    assert hours.is_open(s, mon_noon) is True
    assert hours.is_open(s, mon_8pm) is False
    assert hours.is_open(None) is None


def test_open_now_overnight_into_next_morning():
    s = hours.parse("Fr 18:00-02:00")           # Friday into Saturday
    sat_1am = dt.datetime(2026, 6, 13, 1, 0)     # Saturday 01:00
    assert hours.is_open(s, sat_1am) is True


def test_tag_extraction_restaurant():
    t = tags.extract("restaurants", {
        "name": "Bombay Biryani & Tandoori", "description": "vegetarian buffet",
        "cuisine_type": "North Indian", "dietary_tags": ["vegetarian"]})
    assert "biryani" in t and "tandoori" in t and "buffet" in t and "vegetarian" in t


def test_tag_extraction_temple_uses_facets():
    t = tags.extract("temples", {"religion": "sikh", "deity": "Guru", "denomination": None})
    assert "sikh" in t and "guru" in t
