"""Community/Associations vertical: registry, describe/tags, scraper precision. No DB/network."""

from indo_usa_mcp import describe, tags, verticals
from indo_usa_mcp.community.scraper import CommunityOverpassScraper


def test_registered():
    assert "community" in verticals.VERTICALS
    assert hasattr(verticals.VERTICALS["community"]["queries"], "search_community_by_text")


def test_describe_and_tags():
    rec = {"name": "Telugu Association of New Jersey", "city": "Edison", "state": "NJ",
           "org_type": "association", "region_tag": "Telugu"}
    rec["tags"] = tags.extract("community", rec)
    assert "telugu" in rec["tags"] and "association" in rec["tags"]
    d = describe.describe("community", rec)
    assert "Telugu" in d and "association" in d and "Edison" in d


def test_scraper_excludes_native_american_keeps_indian():
    s = CommunityOverpassScraper()
    # Native American org must be rejected even though it contains "Indian"
    bad = s._to_candidate({"type": "node", "id": 1, "tags": {
        "name": "American Indian Community House", "amenity": "community_centre"}}, "nyc_nj")
    assert bad is None
    # A genuine regional association is kept
    ok = s._to_candidate({"type": "node", "id": 2, "tags": {
        "name": "Telugu Association", "amenity": "community_centre", "addr:state": "NJ"}}, "nyc_nj")
    assert ok and ok["name"] == "Telugu Association"


def test_agents_registered():
    from indo_usa_mcp.agents.registry import AGENTS
    assert "community_scraper" in AGENTS and "community_cleaner" in AGENTS
