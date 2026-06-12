"""Apparel / Sweets / Studios / Services verticals: registry, describe, tags, scraper build. No DB."""

import pytest

from indo_usa_mcp import describe, tags, verticals

_NEW = ["apparel", "sweets", "studios", "services"]


def test_registered_in_verticals():
    for v in _NEW:
        assert v in verticals.VERTICALS
        cfg = verticals.VERTICALS[v]
        for key in ("label", "table", "queries", "edit_fields", "update"):
            assert key in cfg
        assert callable(cfg["update"])
        # the cross-vertical search_all expects a search_<key>_by_text on each queries module
        assert hasattr(cfg["queries"], f"search_{v}_by_text")


@pytest.mark.parametrize("vertical,rec,want_tag", [
    ("apparel", {"name": "Utsav Saree Palace", "city": "Edison", "state": "NJ",
                 "store_type": "clothes"}, "saree"),
    ("sweets", {"name": "Bikaner Sweets", "city": "Iselin", "state": "NJ",
                "store_type": "confectionery"}, "mithai"),
    ("studios", {"name": "Nrityalaya Bharatanatyam", "city": "Fremont", "state": "CA",
                 "studio_type": "dance"}, "bharatanatyam"),
    ("services", {"name": "Xpress Money Transfer", "city": "Jersey City", "state": "NJ",
                  "service_type": "money_transfer"}, "money-transfer"),
])
def test_describe_and_tags(vertical, rec, want_tag):
    rec["tags"] = tags.extract(vertical, rec)
    assert want_tag in rec["tags"]
    d = describe.describe(vertical, rec)
    assert rec["name"] in d and rec["city"] in d


def test_scraper_query_templates_build():
    # The studios/services scrapers build a multi-key Overpass block from a bbox; ensure the
    # f-string/format plumbing produces a query string without raising.
    from indo_usa_mcp.studios.scraper import _block as sblock, _NAMES as snames
    from indo_usa_mcp.services.scraper import _block as vblock, _NAMES as vnames
    assert "name" in sblock(1, 2, 3, 4).format(names=snames)
    assert "name" in vblock(1, 2, 3, 4).format(names=vnames)
