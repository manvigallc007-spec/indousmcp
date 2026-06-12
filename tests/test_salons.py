"""Tests for the salons vertical (no DB)."""

from indo_usa_mcp import describe, tags, verticals
from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.salons import pipeline as salons


def test_salon_tag_extraction():
    t = tags.extract("salons", {"name": "Ziba Threading & Brow Bar", "salon_type": "beauty"})
    assert "threading" in t and "brows" in t and "beauty" in t


def test_clean_salon_record_and_description():
    rec = salons.clean_salon({
        "name": "Henna Brows Threading", "lat": 40.5, "lng": -74.4, "salon_type": "beauty",
        "city": "Edison", "state": "NJ", "address_full": "1 Oak Tree Rd, Edison, NJ",
        "source_name": "osm_overpass"})
    assert "threading" in rec["tags"] and "henna" in rec["tags"]
    assert "beauty salon" in rec["description"].lower() and "Edison, NJ" in rec["description"]
    assert "Services:" in rec["description"]


def test_salon_registered_everywhere():
    assert "salons" in verticals.VERTICALS
    assert "salons" in describe._BUILDERS
    assert "salon_scraper" in AGENTS and "salon_cleaner" in AGENTS


def test_salon_mcp_tools_registered():
    import asyncio
    import indo_usa_mcp.server as s
    names = [t.name for t in asyncio.run(s.mcp.list_tools())]
    assert "get_indian_salons" in names and "search_salons_by_text" in names
