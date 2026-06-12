"""Tests for geo normalization + quality registry (no DB)."""

from indo_usa_mcp import quality
from indo_usa_mcp.pipeline import clean


def test_normalize_state_to_code():
    assert clean.normalize_state("California") == "CA"
    assert clean.normalize_state("new jersey") == "NJ"
    assert clean.normalize_state("ca") == "CA"
    assert clean.normalize_state("TX") == "TX"
    assert clean.normalize_state(None) is None
    assert clean.normalize_state("Ontario") == "Ontario"  # unknown passes through


def test_normalize_city_casing():
    assert clean.normalize_city("  fremont ") == "Fremont"
    assert clean.normalize_city("SAN JOSE") == "San Jose"
    assert clean.normalize_city("New York") == "New York"  # mixed case preserved
    assert clean.normalize_city(None) is None


def test_clean_applies_geo_normalization():
    rec = clean.clean({"name": "X", "city": "sunnyvale", "state": "California",
                       "lat": 1.0, "lng": 2.0, "source_name": "t"})
    assert rec["city"] == "Sunnyvale"
    assert rec["state"] == "CA"


def test_quality_issue_registry():
    assert set(quality.ISSUES) >= {"no_region", "no_contact", "no_geo", "no_city", "low_confidence"}
    for label, cond in quality.ISSUES.values():
        assert isinstance(label, str) and isinstance(cond, str)


def test_quality_routes_registered():
    from indo_usa_mcp.web import app
    paths = {r.path for r in app.routes}
    assert "/admin/geo/{vertical}" in paths
    assert "/admin/quality/{vertical}" in paths
