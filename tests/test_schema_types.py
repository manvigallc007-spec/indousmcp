"""SEO review follow-up: vertical-specific schema.org @type (was hardcoded LocalBusiness everywhere),
noindex on genuinely-thin pages, and data-derived (never stuffed) keyword clauses in meta descriptions.
Pure unit tests for the seo.py helpers + a few TestClient checks against real local dev data."""

import re

from starlette.testclient import TestClient

from indo_usa_mcp.config import settings
from indo_usa_mcp.web import seo
from indo_usa_mcp.web.app import app
from indo_usa_mcp.web.landing import _page

_client = TestClient(app)


# --------------------------------------------------------------- seo.schema_type
def test_schema_type_maps_verticals_to_specific_types():
    assert seo.schema_type("restaurants") == "Restaurant"
    assert seo.schema_type("temples") == "PlaceOfWorship"
    assert seo.schema_type("groceries") == "GroceryStore"
    assert seo.schema_type("salons") == "HairSalon"
    assert seo.schema_type("legal") == "LegalService"


def test_schema_type_falls_back_to_local_business():
    # Unmapped/future vertical -> the safe generic default, never a KeyError.
    assert seo.schema_type("some_future_vertical") == "LocalBusiness"
    assert seo.schema_type("services") == "LocalBusiness"   # genuinely mixed -- intentional


# --------------------------------------------------------------- seo.top_facets / primary_facet
def test_top_facets_returns_most_common_first():
    rows = [{"cuisine_type": "South Indian"}, {"cuisine_type": "South Indian"},
            {"cuisine_type": "Gujarati"}, {"cuisine_type": "Punjabi"}]
    assert seo.top_facets(rows) == ["South Indian", "Gujarati", "Punjabi"]


def test_top_facets_empty_when_homogeneous():
    # Only one distinct value across every row -- not worth a clause (the vertical name already says it).
    rows = [{"cuisine_type": "South Indian"}, {"cuisine_type": "South Indian"}]
    assert seo.top_facets(rows) == []


def test_top_facets_empty_when_no_data():
    assert seo.top_facets([]) == []
    assert seo.top_facets([{"cuisine_type": None}]) == []


def test_primary_facet_returns_first_present_value():
    assert seo.primary_facet({"cuisine_type": "Gujarati", "religion": "hindu"}) == "Gujarati"
    assert seo.primary_facet({"cuisine_type": None, "religion": "hindu"}) == "hindu"
    assert seo.primary_facet({}) is None


# --------------------------------------------------------------- _page(noindex=...)
def test_page_noindex_emits_robots_meta():
    r = _page("T", "D", "<p>x</p>", noindex=True)
    assert '<meta name="robots" content="noindex,follow">' in r.body.decode()


def test_page_default_does_not_emit_robots_meta():
    r = _page("T", "D", "<p>x</p>")
    assert "noindex" not in r.body.decode()


# --------------------------------------------------------------- end-to-end (real app + local dev DB)
def test_restaurant_listing_json_ld_is_not_generic_local_business():
    r = _client.get("/browse/restaurants/ca/san-francisco")
    assert r.status_code == 200
    assert '"@type": "Restaurant"' in r.text
    assert '"@type": "LocalBusiness"' not in r.text


def test_temple_browse_uses_place_of_worship_when_present():
    # Only asserts IF there are results (dev DB content can vary) -- the schema_type unit tests above
    # are what actually pin the mapping; this just confirms it's wired into the real route.
    r = _client.get("/browse/temples/ca/fremont")
    assert r.status_code == 200
    if '"vertical"' in r.text or "results" in r.text.lower():
        assert '"@type": "LocalBusiness"' not in r.text or '"@type": "PlaceOfWorship"' in r.text


def test_empty_city_page_is_noindexed():
    r = _client.get("/browse/restaurants/tx/zzz-nonexistent-city-for-tests")
    assert r.status_code == 200
    assert '<meta name="robots" content="noindex,follow">' in r.text


def test_populated_city_page_is_not_noindexed():
    r = _client.get("/browse/restaurants/ca/san-francisco")
    assert r.status_code == 200
    assert "noindex" not in r.text


def test_multi_cuisine_city_description_gets_facet_clause():
    r = _client.get("/browse/restaurants/ca/san-francisco")
    m = re.search(r'<meta name="description" content="([^"]*)">', r.text)
    assert m and "Including " in m.group(1)
