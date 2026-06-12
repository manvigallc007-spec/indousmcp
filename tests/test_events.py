"""Tests for the events vertical: iCal parsing, cleaning, lifecycle wiring (no DB)."""

from indo_usa_mcp import describe, verticals
from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.events import pipeline as events
from indo_usa_mcp.events.scraper import ICalScraper

_ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-1
SUMMARY:Diwali Mela 2099
DTSTART:20991108T180000
DTEND:20991108T220000
LOCATION:Community Center\\, Edison\\, NJ
DESCRIPTION:Annual Diwali celebration with garba and dandiya
URL:https://example.com/diwali
END:VEVENT
BEGIN:VEVENT
UID:past-1
SUMMARY:Old Holi 2020
DTSTART:20200310T120000
END:VEVENT
END:VCALENDAR"""


def test_ical_parses_and_drops_past():
    cands = list(ICalScraper()._parse(_ICS, "https://feed"))
    assert len(cands) == 1  # the 2020 event is in the past -> filtered at ingest
    c = cands[0]
    assert c["name"] == "Diwali Mela 2099"
    assert c["start_at"].startswith("2099-11-08")
    assert "Edison" in (c["venue_name"] or "")


def test_clean_event_enriches():
    rec = events.clean_event({
        "name": "Navratri Garba Night", "start_at": "2099-10-05T19:00:00",
        "city": "Edison", "state": "NJ", "venue_name": "Town Hall", "source_name": "ical"})
    assert rec["category"] in ("garba", "festival")
    assert "garba" in rec["tags"]
    assert "event" in rec["description"].lower() and "Edison, NJ" in rec["description"]
    assert rec["natural_key"].endswith("@edison")
    assert rec["confidence_score"] > 0.5  # complete -> would auto-approve


def test_events_registered_everywhere():
    assert "events" in verticals.VERTICALS
    assert "events" in describe._BUILDERS
    assert "event_scraper" in AGENTS and "event_cleaner" in AGENTS


def test_event_mcp_tools_registered():
    import asyncio
    import indo_usa_mcp.server as s
    names = [t.name for t in asyncio.run(s.mcp.list_tools())]
    assert "get_indian_events" in names and "search_events_by_text" in names
