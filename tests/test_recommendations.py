"""Recommendations agent heuristics (no DB)."""

from indo_usa_mcp import recommendations as rec


def test_vertical_matching():
    assert rec._match_vertical("gujarati thali near me") == "restaurants"
    assert rec._match_vertical("bharatanatyam class") == "studios"
    assert rec._match_vertical("indian wedding photographer") is None  # -> new_topic


def test_metro_mapping_no_false_substring():
    assert rec._metro_for("Plano", "TX") is None        # 'la' must NOT match 'Plano'
    assert rec._metro_for("Atlanta", "GA") == "atlanta"  # whole-token metro name still matches
    assert rec._metro_for("Dallas", "TX") == "dallas"
    assert rec._metro_for("San Francisco", "CA") == "bay_area"


def test_recommendation_agent_registered():
    from indo_usa_mcp.agents.registry import AGENTS
    from indo_usa_mcp.agents.scheduler import _RUN_ORDER
    assert "recommendation" in AGENTS and "recommendation" in _RUN_ORDER
