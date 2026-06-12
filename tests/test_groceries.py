"""Tests for the groceries vertical: enrichment, cleaning, agents, tools (no DB)."""

from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.groceries import pipeline as groceries


def test_region_inferred_from_name():
    assert groceries._infer_region("patel brothers") == "Gujarati"
    assert groceries._infer_region("apna punjab bazaar") == "Punjabi"
    assert groceries._infer_region("madras groceries") == "South Indian"
    assert groceries._infer_region("corner store") is None


def test_clean_grocery_builds_canonical_record():
    rec = groceries.clean_grocery({
        "name": "Patel Brothers", "lat": 41.99, "lng": -87.69, "store_type": "supermarket",
        "address_full": "1 Devon Ave, Chicago, IL", "city": "Chicago", "state": "IL",
        "website": "https://x", "source_name": "osm_overpass",
    })
    assert rec["store_type"] == "supermarket"
    assert rec["region_tag"] == "Gujarati"
    assert rec["natural_key"].startswith("patel brothers@")
    assert 0.0 < rec["confidence_score"] <= 1.0


def test_grocery_agents_registered():
    assert "grocery_scraper" in AGENTS
    assert "grocery_cleaner" in AGENTS


def test_grocery_mcp_tools_registered():
    import asyncio
    import indo_usa_mcp.server as s

    names = [t.name for t in asyncio.run(s.mcp.list_tools())]
    assert "get_indian_groceries" in names
    assert "search_groceries_by_text" in names
