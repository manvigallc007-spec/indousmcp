"""Auto-approval of high-confidence submissions + the report escalation digest. No live DB."""

import indo_usa_mcp.reporting as reporting
import indo_usa_mcp.submissions as subs
from indo_usa_mcp.agents.definitions import SubmissionReviewAgent
from indo_usa_mcp.config import settings


def test_high_confidence_gate():
    good = {"name": "Patel Brothers Grocery", "city": "Edison", "state": "NJ", "phone": "732-555-0100"}
    assert subs._high_confidence(good) is True
    # complete but no Indian signal -> NOT auto-approved (stays for a human)
    assert subs._high_confidence({"name": "Sunrise Cafe", "city": "Edison", "state": "NJ",
                                  "phone": "x"}) is False
    # Indian signal but incomplete (no contact/location) -> not auto-approved
    assert subs._high_confidence({"name": "Bombay Spice"}) is False


def test_auto_approve_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "auto_approve_submissions", False)
    assert SubmissionReviewAgent().run().get("skipped") == "disabled"


def test_auto_approve_only_publishes_high_confidence(monkeypatch):
    pending = [
        {"id": 1, "vertical": "groceries",
         "payload": {"name": "Apna Bazar Indian Grocery", "city": "Iselin", "state": "NJ", "phone": "1"}},
        {"id": 2, "vertical": "restaurants",
         "payload": {"name": "Joe's Diner", "city": "Edison", "state": "NJ", "phone": "2"}},  # ambiguous
    ]
    approved = []
    monkeypatch.setattr(subs, "list_pending", lambda limit=50: pending)
    monkeypatch.setattr(subs, "approve", lambda sid: approved.append(sid) or {"ok": True, "id": sid})
    out = subs.auto_approve_pending()
    assert out["auto_approved"] == 1 and out["left_for_human"] == 1
    assert approved == [1]                       # only the clearly-Indian, complete one


def test_report_digest_leads_with_attention():
    report = {"metrics": {"health": {"escalations": [{"severity": "critical", "message": "SMTP off"}],
                                     "messages_pending": 3, "approvals_pending": 0,
                                     "submissions_pending": 0, "feedback_pending": 0,
                                     "agent_runs_24h": 5, "agent_errors_24h": 0, "open_alerts": 1,
                                     "tool_calls_24h": 9, "raw_backlog": {}},
                          "growth": {"verticals": {}, "claims_today": 0, "featured_total": 0}},
              "deltas": {}}
    text = reporting.render_text(report)
    assert "NEEDS YOUR ATTENTION" in text and "SMTP off" in text and "3 contact message" in text
