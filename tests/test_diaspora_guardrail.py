"""Guardrail: keep the directory to Indians FROM INDIA, not American Indian / Native American
(or West Indian / 'Indian' brand) homonyms. Pure name matching + scraper/create_record gates."""

from indo_usa_mcp import osm, verticals


def test_excludes_native_american_and_homonyms():
    for bad in ("American Indian Community House", "Native American Cultural Center",
                "Cherokee Nation Indian Tribe", "West Indian Roti Shop",
                "Indian Motorcycle of Dallas", "Indian Health Service Clinic",
                "Bureau of Indian Affairs", "Standing Rock Indian Reservation"):
        assert osm.is_excluded_name(bad), bad


def test_keeps_genuine_india_diaspora_names():
    for ok in ("India Cafe", "Indian Spice Grocery", "Gujarati Samaj of NJ",
               "Sri Venkateswara Temple", "Patel Brothers", "Saravana Bhavan",
               "Telugu Association of America", "Bombay Sweets"):
        assert not osm.is_excluded_name(ok), ok


def test_empty_name_is_not_excluded():
    assert osm.is_excluded_name(None) is False
    assert osm.is_excluded_name("") is False


def test_create_record_rejects_excluded_name(monkeypatch):
    # Guard short-circuits before any DB write.
    res = verticals.create_record("restaurants", {"name": "American Indian Trading Post"})
    assert res["ok"] is False and res["error"] == "not_india_diaspora"


def test_scrapers_drop_excluded_candidates():
    from indo_usa_mcp.community.scraper import CommunityOverpassScraper
    from indo_usa_mcp.pipeline.scrapers.osm_overpass import OverpassScraper
    el = {"type": "node", "id": 1, "lat": 40.0, "lon": -74.0,
          "tags": {"name": "Native American Indian Center", "amenity": "community_centre"}}
    assert CommunityOverpassScraper()._to_candidate(el, "nyc_nj") is None
    el2 = {"type": "node", "id": 2, "lat": 40.0, "lon": -74.0,
           "tags": {"name": "American Indian Diner"}}
    assert OverpassScraper()._element_to_candidate(el2, "nyc_nj") is None
