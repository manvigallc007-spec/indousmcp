"""CSP must allow Google Analytics / Turnstile when configured, else GA can't load or send (the
"analytics not updating" bug). Locked down to 'self' otherwise."""

from starlette.testclient import TestClient

import indo_usa_mcp.web.security as sec
from indo_usa_mcp.config import settings
from indo_usa_mcp.web.app import app


def test_csp_locked_down_without_features(monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_id", "")
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", "")
    csp = sec._build_csp()
    assert "googletagmanager" not in csp and "cloudflare" not in csp
    assert "script-src 'self' 'unsafe-inline'" in csp and "connect-src 'self'" in csp


def test_csp_allows_ga_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_id", "G-TEST123")
    csp = sec._build_csp()
    assert "https://www.googletagmanager.com" in csp        # gtag.js can load
    assert "https://www.google-analytics.com" in csp        # hits can be sent (connect-src)


def test_csp_allows_turnstile_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "turnstile_site_key", "x")
    monkeypatch.setattr(settings, "turnstile_secret_key", "y")
    csp = sec._build_csp()
    assert "challenges.cloudflare.com" in csp and "frame-src" in csp


def test_response_header_reflects_ga(monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_id", "G-TEST123")
    r = TestClient(app).get("/health")
    assert "googletagmanager.com" in r.headers.get("content-security-policy", "")
