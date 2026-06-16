"""Google Analytics (GA4) tag — off by default, injected into public pages when configured."""

from starlette.testclient import TestClient

from indo_usa_mcp.config import settings
from indo_usa_mcp.web import common
from indo_usa_mcp.web.app import app


def test_analytics_tag_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_id", "")
    assert common.analytics_tag() == ""


def test_analytics_tag_renders_when_set(monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_id", "G-TEST12345")
    tag = common.analytics_tag()
    assert "googletagmanager.com/gtag/js?id=G-TEST12345" in tag
    assert "gtag('config','G-TEST12345')" in tag


def test_public_pages_include_tag_only_when_set(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(settings, "google_analytics_id", "")
    assert "googletagmanager.com/gtag" not in client.get("/").text          # homepage off
    assert "googletagmanager.com/gtag" not in client.get("/insights").text  # content page off
    monkeypatch.setattr(settings, "google_analytics_id", "G-TEST12345")
    assert "id=G-TEST12345" in client.get("/").text                         # homepage (chat.py)
    assert "id=G-TEST12345" in client.get("/insights").text                 # content (landing._page)
