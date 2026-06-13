"""SEO/landing surfaces: browse root, llms.txt, robots.txt, slug helpers. No DB needed."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import app, landing


def test_slug_roundtrip():
    assert landing._slug("Jersey City") == "jersey-city"
    assert landing._unslug("jersey-city") == "jersey city"


def test_browse_root_lists_categories():
    r = TestClient(app).get("/browse")
    assert r.status_code == 200 and "/browse/restaurants" in r.text and "/browse/temples" in r.text


def test_llms_txt_points_at_mcp():
    r = TestClient(app).get("/llms.txt")
    assert r.status_code == 200 and "Model Context Protocol" in r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert "/browse/restaurants" in r.text


def test_robots_has_sitemap():
    r = TestClient(app).get("/robots.txt")
    assert r.status_code == 200 and "Sitemap:" in r.text and "/sitemap.xml" in r.text


def test_unknown_vertical_404():
    assert TestClient(app).get("/browse/notavertical").status_code == 404
