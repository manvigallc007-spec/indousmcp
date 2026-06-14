"""Static info pages: render with full meta, footer/ODbL attribution, and appear in the sitemap."""

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp.web import app

_PATHS = ["/about", "/privacy", "/terms", "/contact", "/faq"]


@pytest.mark.parametrize("path", _PATHS)
def test_static_page_renders_with_meta(path):
    r = TestClient(app).get(path)
    assert r.status_code == 200
    t = r.text
    assert "<title>" in t and 'name="description"' in t
    assert 'rel="canonical"' in t and 'property="og:title"' in t
    assert "OpenStreetMap" in t            # ODbL attribution in the footer
    assert "/privacy" in t and "/contact" in t   # footer cross-links


def test_privacy_covers_location_and_optout():
    t = TestClient(app).get("/privacy").text.lower()
    assert "location" in t and "ip" in t and "unsubscribe" in t


def test_static_pages_in_sitemap():
    sm = TestClient(app).get("/sitemap.xml").text
    for p in _PATHS:
        assert p in sm
