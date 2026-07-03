"""Every indexable page must self-canonicalize (Search Console: 'Duplicate without user-selected
canonical' / a stray og:url pointing at a DIFFERENT page). Hits the real app + local dev DB (same
pattern as test_seo.py's /faq test) -- these are plain read-only GETs."""

import re

from starlette.testclient import TestClient

from indo_usa_mcp.config import settings
from indo_usa_mcp.web.app import app

_BASE = settings.public_web_url.rstrip("/")
_client = TestClient(app)


def _canonical(html_text: str) -> str | None:
    m = re.search(r'<link rel="canonical" href="([^"]*)">', html_text)
    return m.group(1) if m else None


def test_explore_canonicalizes_to_itself_not_home():
    # THE bug: /explore's only URL-identity signal (og:url) pointed at "/" -- a DIFFERENT page (the
    # chat homepage) with different content -- and it had no <link rel="canonical"> at all.
    r = _client.get("/explore")
    assert r.status_code == 200
    can = _canonical(r.text)
    assert can == f"{_BASE}/explore"
    assert f'content="{_BASE}/explore"' in r.text          # og:url now matches too
    assert can != f"{_BASE}/"                               # must NOT point at the chat homepage


def test_home_canonicalizes_to_itself():
    r = _client.get("/")
    assert r.status_code == 200
    assert _canonical(r.text) == f"{_BASE}/"


def test_browse_root_and_vertical_self_canonicalize():
    assert _canonical(_client.get("/browse").text) == f"{_BASE}/browse"
    assert _canonical(_client.get("/browse/restaurants").text) == f"{_BASE}/browse/restaurants"


def test_static_pages_self_canonicalize():
    for path in ("/insights", "/for-business", "/for-agents"):
        r = _client.get(path)
        assert r.status_code == 200
        assert _canonical(r.text) == f"{_BASE}{path}", path


def test_events_filters_canonicalize_to_base_not_the_query_variant():
    # Facet-navigation pattern (matches browse_city): a filtered URL must declare the BASE page as
    # canonical, so ?state=/?city=/?category= variants never compete with /events as duplicates.
    base_can = _canonical(_client.get("/events").text)
    filtered_can = _canonical(_client.get("/events?state=TX").text)
    assert base_can == f"{_BASE}/events" == filtered_can
