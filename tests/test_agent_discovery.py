"""Agent discovery surface: robots welcomes AI crawlers, llms.txt + /for-agents advertise MCP,
OpenAPI + .well-known descriptors are valid. No DB needed (all static/config-driven)."""

from starlette.testclient import TestClient

from indo_usa_mcp.web.app import app

c = TestClient(app)


def test_robots_welcomes_ai_crawlers():
    t = c.get("/robots.txt").text
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert bot in t, bot
    assert "Sitemap:" in t


def test_llms_txt_advertises_mcp_and_api():
    t = c.get("/llms.txt").text
    assert "/mcp" in t and "streamable-http" in t
    assert "/api/v1/search" in t and "/for-agents" in t and "/openapi.json" in t


def test_for_agents_page_renders():
    r = c.get("/for-agents")
    assert r.status_code == 200
    assert "mcpServers" in r.text and "streamable-http" in r.text and "/api/v1/search" in r.text


def test_openapi_spec_valid():
    r = c.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/search" in spec["paths"]
    params = {p["name"] for p in spec["paths"]["/api/v1/search"]["get"]["parameters"]}
    assert {"q", "city", "state", "vertical", "limit"} <= params


def test_ai_plugin_manifest():
    m = c.get("/.well-known/ai-plugin.json").json()
    assert m["auth"]["type"] == "none" and m["api"]["url"].endswith("/openapi.json")


def test_mcp_well_known_descriptor():
    d = c.get("/.well-known/mcp.json").json()
    assert d["transport"] == "streamable-http" and d["url"].endswith("/mcp")
    assert "search_all" in d["tool_patterns"]


def test_for_agents_in_sitemap():
    assert "/for-agents" in c.get("/sitemap.xml").text
