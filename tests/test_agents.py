"""Registry-level tests for the agent layer (no DB calls)."""

from indo_usa_mcp.agents import AGENTS, get_agent
from indo_usa_mcp.agents.scheduler import DEFAULT_SCHEDULE, _RUN_ORDER


def test_expected_agents_registered():
    expected = {"discovery", "scraper", "cleaner", "outreach", "submission", "monitoring"}
    assert expected <= set(AGENTS)


def test_every_agent_has_name_and_interval():
    for name, agent in AGENTS.items():
        assert agent.name == name
        assert agent.default_interval_s > 0


def test_get_agent_unknown_raises():
    try:
        get_agent("does-not-exist")
    except ValueError as exc:
        assert "Unknown agent" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_order_only_references_real_agents():
    assert set(_RUN_ORDER) <= set(AGENTS)
    assert set(DEFAULT_SCHEDULE) == set(AGENTS)
