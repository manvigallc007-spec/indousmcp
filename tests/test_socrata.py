"""Socrata importer: cuisine mode (NYC) + new name-match mode (Chicago/SF). No network."""

import indo_usa_mcp.pipeline.scrapers.socrata as soc


def test_new_cities_configured():
    for k in ("nyc_restaurants", "chicago_restaurants", "sf_restaurants"):
        assert k in soc.SOCRATA_SOURCES, k
    assert soc.SOCRATA_SOURCES["chicago_restaurants"]["name_match"] is True
    assert "cuisine_col" not in soc.SOCRATA_SOURCES["sf_restaurants"]


def test_name_match_candidate_no_cuisine_field():
    sc = soc.SocrataScraper("chicago_restaurants")
    cand = sc._to_candidate({"dba_name": "viceroy of india", "address": "2516 W Devon Ave",
                             "city": "CHICAGO", "latitude": "41.99", "longitude": "-87.69"})
    assert cand["name"] == "Viceroy Of India" and cand["state"] == "IL"
    assert cand["cuisine_type"] == "South Asian"          # no cuisine field -> default
    assert cand["source_name"] == "socrata_chicago"
    assert cand["source_id"] and cand["lat"] == 41.99     # composite id, coords parsed


def test_cuisine_mode_still_works():
    sc = soc.SocrataScraper("nyc_restaurants")
    cand = sc._to_candidate({"dba": "Dosa Hut", "cuisine_description": "Indian", "boro": "Queens",
                             "building": "1", "street": "Main St", "camis": "123"})
    assert cand["cuisine_type"] == "Indian" and cand["source_id"] == "123"
    assert cand["source_name"] == "socrata_nyc"
