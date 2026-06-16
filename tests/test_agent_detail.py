"""Agent detail route is registered + admin-gated."""

from starlette.testclient import TestClient

from indo_usa_mcp.web.app import app

c = TestClient(app)


def test_agent_detail_route_gated():
    r = c.get("/admin/agents/scraper", follow_redirects=False)
    assert r.status_code in (302, 303)          # registered + redirects to login when not admin


def test_messages_route_still_gated():
    assert c.get("/admin/messages?show=auto", follow_redirects=False).status_code in (302, 303)
