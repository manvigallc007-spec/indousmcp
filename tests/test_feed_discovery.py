"""Tests for iCal feed discovery link extraction + agent wiring (no network/DB)."""

from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.events.discovery import extract_ics_links


def test_extracts_ics_webcal_and_google_calendar():
    html = """
      <a href="/calendar/events.ics">Subscribe</a>
      <a href="webcal://temple.org/cal.ics">iCal</a>
      <a href="https://calendar.google.com/calendar/ical/abc%40group.calendar.google.com/public/basic.ics">GCal</a>
      <a href="/about">About</a>
      <a href="https://x.org/feed.xml">RSS</a>
    """
    links = extract_ics_links(html, "https://temple.org/home")
    assert "https://temple.org/calendar/events.ics" in links       # relative resolved
    assert "https://temple.org/cal.ics" in links                   # webcal -> https
    assert any("calendar.google.com" in u and u.endswith("basic.ics") for u in links)
    assert all(not u.endswith("feed.xml") and "/about" not in u for u in links)


def test_no_calendar_links_returns_empty():
    assert extract_ics_links("<a href='/menu'>Menu</a>", "https://x.com") == []


def test_feed_discovery_agent_registered():
    assert "event_feed_discovery" in AGENTS
