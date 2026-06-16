"""Auto-reply to routine messages; sensitive ones always escalate. No live DB/LLM."""

import indo_usa_mcp.inbox as inbox
from indo_usa_mcp.config import settings


def test_sensitive_detection():
    assert inbox.is_sensitive({"subject": "Refund request", "body": "I want my money back"})
    assert inbox.is_sensitive({"body": "I need immigration / visa advice"})
    assert inbox.is_sensitive({"body": "press inquiry from a journalist"})
    assert not inbox.is_sensitive({"body": "What are your hours and is it free?"})


def test_sensitive_is_never_routine(monkeypatch):
    # even if the LLM existed, a sensitive message must never be marked routine (auto-send blocked)
    monkeypatch.setattr(inbox, "compose_draft", lambda m: "draft")
    res = inbox.draft_and_classify({"subject": "lawsuit", "body": "I will sue you"})
    assert res["routine"] is False


def test_draft_and_classify_no_llm():
    # default config has no LLM -> no auto draft, not routine
    res = inbox.draft_and_classify({"subject": "hi", "body": "what are your hours"})
    assert res == {"reply": None, "routine": False}


def test_auto_reply_flag_default_on():
    assert settings.auto_reply_routine is True       # the operator can flip it off in .env
