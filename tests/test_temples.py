"""Tests for the temples vertical: enrichment, cleaning, agents, tools (no DB)."""

from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.temples import pipeline as temples


def test_region_inferred_from_religion_and_name():
    assert temples._infer_region("anything", "sikh") == "Punjabi"
    assert temples._infer_region("anything", "jain") == "Jain"
    assert temples._infer_region("baps swaminarayan mandir", "hindu") == "Gujarati"
    assert temples._infer_region("sri venkateswara temple", "hindu") == "Telugu"


def test_deity_inferred_from_name():
    assert temples._infer_deity("sri venkateswara temple") == "Venkateswara"
    assert temples._infer_deity("hindu temple of ganesha") == "Ganesha"
    assert temples._infer_deity("community center") is None


def test_clean_temple_builds_canonical_record():
    rec = temples.clean_temple({
        "name": "Sri Venkateswara Temple", "lat": 33.0, "lng": -96.0,
        "religion": "hindu", "address_full": "1 Main St, Plano, TX",
        "city": "Plano", "state": "TX", "website": "https://x", "source_name": "osm_overpass",
    })
    assert rec["religion"] == "hindu"
    assert rec["deity"] == "Venkateswara"
    assert rec["region_tag"] == "Telugu"
    assert rec["natural_key"].startswith("sri venkateswara temple@")
    assert 0.0 < rec["confidence_score"] <= 1.0


def test_temple_agents_registered():
    assert "temple_scraper" in AGENTS
    assert "temple_cleaner" in AGENTS


def test_temple_mcp_tools_registered():
    import asyncio
    import indo_usa_mcp.server as s

    names = [t.name for t in asyncio.run(s.mcp.list_tools())]
    assert "get_indian_temples" in names
    assert "search_temples_by_text" in names
