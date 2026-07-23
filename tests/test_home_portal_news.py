"""Homepage portal (nripage-style feed below the Dost hero) + the news feed (module, RSS parsing with
network mocked, /news page, agent registration). Real dev DB, ZZTEST rows, try/finally."""

from starlette.testclient import TestClient

from indo_usa_mcp import db, news, verticals
from indo_usa_mcp.agents.registry import AGENTS
from indo_usa_mcp.agents.scheduler import _RUN_ORDER
from indo_usa_mcp.web import homeportal
from indo_usa_mcp.web.app import app

_client = TestClient(app)


# --------------------------------------------------------------- portal
def test_homepage_renders_portal_below_hero():
    html = _client.get("/").text
    assert "homeportal" in html and "Explore the data" in html      # portal block present
    assert 'id="welcome"' in html and "I'm" in html                 # hero still intact above it
    assert "/insights" in html and "/employers" in html and "/leaderboard" in html


def test_portal_render_is_safe_and_has_sections():
    out = homeportal.render()
    assert "homeportal" in out
    # deep-data tiles are always present (static), so the portal is never empty
    assert "Explore the data" in out


def test_portal_newest_business_shows_up():
    rid = verticals.create_record("restaurants", {"name": "ZZTEST Portal Biz", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7},
                                  source="test")["id"]
    try:
        out = homeportal.render()
        assert "Newly added businesses" in out and f"/listing/restaurants/{rid}" in out
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- news module
_SAMPLE_RSS = b"""<?xml version='1.0'?><rss><channel>
<item><title>Indian Americans mark a milestone - The Sample Times</title>
<link>https://example.com/zztest-news-1</link>
<pubDate>Wed, 22 Jul 2026 10:00:00 GMT</pubDate>
<source url='https://example.com'>The Sample Times</source></item>
<item><title>H-1B changes explained - Visa Daily</title>
<link>https://example.com/zztest-news-2</link>
<pubDate>Tue, 21 Jul 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_feed_strips_source_from_title():
    items = news._parse_feed(_SAMPLE_RSS)
    assert len(items) == 2
    a = items[0]
    assert a["title"] == "Indian Americans mark a milestone" and a["source"] == "The Sample Times"
    assert a["url"] == "https://example.com/zztest-news-1" and a["published_at"] is not None
    # source folded out of the title even when there's no <source> element
    assert items[1]["title"] == "H-1B changes explained" and items[1]["source"] == "Visa Daily"


def test_fetch_and_store_upserts_and_latest_reads(monkeypatch):
    class _Resp:
        content = _SAMPLE_RSS
        def raise_for_status(self): pass
    monkeypatch.setattr(news.httpx, "get", lambda *a, **k: _Resp())
    try:
        r = news.fetch_and_store()
        assert r["inserted"] >= 2                       # first run inserts our two sample items
        r2 = news.fetch_and_store()
        assert r2["inserted"] == 0                       # dedupe on URL -> nothing new
        latest = news.latest(5)
        assert any(a["url"] == "https://example.com/zztest-news-1" for a in latest)
    finally:
        db.execute("DELETE FROM news_articles WHERE url LIKE 'https://example.com/zztest-news-%'")


def test_news_page_and_category_filter(monkeypatch):
    class _Resp:
        content = _SAMPLE_RSS
        def raise_for_status(self): pass
    monkeypatch.setattr(news.httpx, "get", lambda *a, **k: _Resp())
    try:
        news.fetch_and_store()
        r = _client.get("/news")
        assert r.status_code == 200 and "Latest news for Indians" in r.text
        assert "Indian Americans mark a milestone" in r.text
        assert _client.get("/news?cat=immigration").status_code == 200
    finally:
        db.execute("DELETE FROM news_articles WHERE url LIKE 'https://example.com/zztest-news-%'")


def test_news_agent_registered_and_scheduled():
    assert "news" in AGENTS and "news" in _RUN_ORDER
