"""Tests for iCal feed discovery link extraction + agent wiring (no network/DB)."""

import indo_usa_mcp.events.discovery as discovery
from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.agents.scheduler import _RUN_ORDER
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
    assert "event_feed_discovery" in _RUN_ORDER   # registered alone isn't enough -- must be scheduled


def test_sites_sql_scans_community_orgs():
    # The vertical that actually holds cultural associations/sangams/mandals -- the highest-signal
    # source for "events from the Indians-from-India community" -- must be in the scan pool.
    assert "FROM community" in discovery._SITES_SQL


class _Resp:
    def __init__(self, status_code=200, text="", url="https://x.org/", ctype="text/html"):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = {"content-type": ctype}


def test_find_ics_from_homepage_skips_subpath_probe(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return _Resp(text='<a href="/cal.ics">iCal</a>', url="https://x.org/")
    monkeypatch.setattr(discovery.httpx, "get", fake_get)
    monkeypatch.setattr(discovery.time, "sleep", lambda *a: None)
    assert discovery._find_ics("https://x.org/") == "https://x.org/cal.ics"
    assert len(calls) == 1                          # found on homepage -> no sub-path probes made


def test_find_ics_falls_back_to_calendar_subpath(monkeypatch):
    # Homepage has no direct link (common: the calendar is only linked from a nav item, not the
    # homepage body) -- must try a common sub-path before giving up.
    def fake_get(url, **kw):
        if url.rstrip("/") == "https://x.org":
            return _Resp(text="<a href='/about'>About</a>", url="https://x.org/")
        if "events" in url:
            return _Resp(text='<a href="/events/feed.ics">iCal</a>', url="https://x.org/events")
        return _Resp(text="")
    monkeypatch.setattr(discovery.httpx, "get", fake_get)
    monkeypatch.setattr(discovery.time, "sleep", lambda *a: None)
    assert discovery._find_ics("https://x.org") == "https://x.org/events/feed.ics"


def test_find_ics_returns_none_when_nothing_found(monkeypatch):
    monkeypatch.setattr(discovery.httpx, "get", lambda url, **kw: _Resp(text="<a href='/about'>x</a>"))
    monkeypatch.setattr(discovery.time, "sleep", lambda *a: None)
    assert discovery._find_ics("https://x.org") is None


def test_find_ics_survives_network_error(monkeypatch):
    def fake_get(url, **kw):
        raise discovery.httpx.ConnectError("dns fail")
    monkeypatch.setattr(discovery.httpx, "get", fake_get)
    assert discovery._find_ics("https://dead.example") is None
