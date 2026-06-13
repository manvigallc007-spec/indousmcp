"""Stale-data lifecycle wiring (no DB)."""

from indo_usa_mcp import lifecycle, verticals


def test_events_excluded_from_lifecycle():
    vs = lifecycle._verticals()
    assert "events" not in vs and "restaurants" in vs
    assert set(vs) == set(verticals.VERTICALS) - {"events"}


def test_lifecycle_and_linkcheck_agents_registered():
    from indo_usa_mcp.agents.registry import AGENTS
    from indo_usa_mcp.agents.scheduler import _RUN_ORDER
    for a in ("lifecycle", "link_check"):
        assert a in AGENTS and a in _RUN_ORDER
