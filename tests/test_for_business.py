"""The 'list your business' marketing page: renders, pitches the agent-first value, links to register."""

from starlette.testclient import TestClient

from indo_usa_mcp.web.app import app


def test_for_business_page_renders():
    r = TestClient(app).get("/for-business")
    assert r.status_code == 200
    t = r.text
    assert "List your business" in t
    assert "Model Context Protocol" in t           # the agent-first pitch
    assert "/portal/login" in t and "/submit" in t  # register + add-a-listing CTAs


def test_for_business_in_sitemap():
    assert "/for-business" in TestClient(app).get("/sitemap.xml").text
