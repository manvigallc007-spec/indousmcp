"""Tests for WhatsApp links, nationwide region, and approval-assistant wiring (no DB)."""

from urllib.parse import parse_qs, urlparse

from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.pipeline import outreach
from indo_usa_mcp.pipeline.scrapers.metros import SCRAPE_REGIONS, state_for


# --- WhatsApp click-to-send links ---
def test_whatsapp_link_digits_and_prefilled_text():
    link = outreach.whatsapp_link("+1 (408) 555-0101", "Hi there!")
    parsed = urlparse(link)
    assert parsed.netloc == "wa.me"
    assert parsed.path == "/14085550101"
    assert parse_qs(parsed.query)["text"] == ["Hi there!"]


def test_whatsapp_link_none_without_number():
    assert outreach.whatsapp_link(None, "x") is None
    assert outreach.whatsapp_link("no-digits", "x") is None


# --- Nationwide region ---
def test_usa_is_a_scrape_region():
    assert "usa" in SCRAPE_REGIONS
    # Nationwide relies on source-provided state, not a metro default.
    assert state_for("usa", lat=40.0, lng=-100.0) is None


# --- Approval-Assistant agent registered ---
def test_approval_assistant_agent_registered():
    assert "approval_assistant" in AGENTS
