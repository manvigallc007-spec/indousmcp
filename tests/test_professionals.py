"""Tests for the professionals vertical (no DB)."""

from indo_usa_mcp import describe, verticals
from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.professionals import pipeline as professionals


def test_speciality_inferred():
    assert professionals._infer_speciality("smile dental care", "dentist") == "dentist"
    assert professionals._infer_speciality("pediatric clinic", "clinic") == "pediatrics"
    assert professionals._infer_speciality("patel cardiology", "doctors") == "cardiology"


def test_clean_professional_builds_record():
    rec = professionals.clean_professional({
        "name": "Patel Dental Care", "lat": 40.5, "lng": -74.4, "profession_type": "dentist",
        "address_full": "1 Oak Tree Rd, Edison, NJ", "city": "Edison", "state": "NJ",
        "source_name": "osm_overpass"})
    assert rec["profession_type"] == "dentist"
    assert rec["speciality"] == "dentist"
    assert "dentist" in rec["description"].lower() and "Edison, NJ" in rec["description"]
    assert "dentist" in rec["tags"]
    assert 0.0 < rec["confidence_score"] <= 1.0


def test_professionals_in_registry_and_describe():
    assert "professionals" in verticals.VERTICALS
    assert "professionals" in describe._BUILDERS


def test_professional_agents_registered():
    assert "professional_scraper" in AGENTS
    assert "professional_cleaner" in AGENTS


def test_professional_mcp_tools_registered():
    import asyncio
    import indo_usa_mcp.server as s
    names = [t.name for t in asyncio.run(s.mcp.list_tools())]
    assert "get_indian_professionals" in names
    assert "search_professionals_by_text" in names
