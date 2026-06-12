"""Tests for traffic-analytics wiring (no DB)."""


def test_tracking_installed_on_all_tools():
    import asyncio
    import indo_usa_mcp.server as s
    # Every registered tool fn should be the tracking wrapper (has __wrapped__).
    for name, tool in s.mcp._tool_manager._tools.items():
        assert hasattr(tool.fn, "__wrapped__"), f"{name} not tracked"
    assert len(asyncio.run(s.mcp.list_tools())) == 18


def test_traffic_route_registered():
    from indo_usa_mcp.web import app
    assert "/admin/traffic" in {r.path for r in app.routes}


def test_client_name_safe_without_context():
    import indo_usa_mcp.server as s
    # No active MCP request context -> returns None, never raises.
    assert s._client_name() is None
