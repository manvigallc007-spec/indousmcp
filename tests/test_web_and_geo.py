"""Tests for state inference and the claim web app wiring (no DB needed)."""

from indo_usa_mcp.pipeline.scrapers.metros import state_for


def test_state_for_single_state_metros():
    assert state_for("bay_area") == "CA"
    assert state_for("dallas") == "TX"
    assert state_for("houston") == "TX"
    assert state_for("chicago") == "IL"


def test_state_for_nyc_nj_splits_at_hudson():
    # Jersey City (west of the Hudson) -> NJ; Manhattan/Brooklyn (east) -> NY.
    assert state_for("nyc_nj", lat=40.72, lng=-74.05) == "NJ"
    assert state_for("nyc_nj", lat=40.75, lng=-73.98) == "NY"
    assert state_for("nyc_nj", lat=40.7, lng=None) is None


def test_state_for_unknown_metro_is_none():
    assert state_for("atlantis") is None


def test_claim_web_routes_registered():
    from indo_usa_mcp.web import app

    paths = {(r.path, tuple(sorted(r.methods - {"HEAD"}))) for r in app.routes}
    assert ("/", ("GET",)) in paths
    assert ("/claim", ("GET",)) in paths
    assert ("/claim", ("POST",)) in paths
