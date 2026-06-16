"""Operations page + agent escalation helpers (agentic admin). No live DB needed for these."""

from starlette.testclient import TestClient

from indo_usa_mcp.agents.definitions import MonitoringAgent
from indo_usa_mcp.web import admin
from indo_usa_mcp.web.app import app


def test_every_is_human_readable():
    assert admin._every(86400) == "daily"
    assert admin._every(3600) == "hourly"
    assert admin._every(1800) == "every 30 min"
    assert admin._every(604800) == "weekly"
    assert admin._every(2592000) == "monthly"
    assert admin._every(259200) == "every 3 days"


def test_ops_page_requires_login():
    r = TestClient(app).get("/admin/ops", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_monitor_manages_human_escalation_kinds():
    # The supervisor owns (raises + auto-resolves) the human-attention escalations.
    for kind in ("messages_waiting", "smtp_unconfigured", "submissions_pending",
                 "approval_backlog", "feedback_pending", "agent_failure"):
        assert kind in MonitoringAgent.MANAGED, kind
