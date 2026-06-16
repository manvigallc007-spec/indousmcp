"""Expanded Terms/Privacy + portal engagement (items 9, 10). Content pages render DB-free."""

from starlette.testclient import TestClient

from indo_usa_mcp.web.app import app

c = TestClient(app)


def test_privacy_discloses_analytics_and_sections():
    t = c.get("/privacy").text
    assert "Google Analytics" in t and "opt out" in t.lower()
    for s in ("Information we collect", "Data retention", "Your choices", "Security"):
        assert s in t, s


def test_terms_has_key_sections():
    t = c.get("/terms").text
    for s in ("Information only", "Accounts", "Your submissions", "Acceptable use",
              "Limitation of liability"):
        assert s in t, s


def test_contact_invites_data_requests():
    t = c.get("/contact").text
    assert "<form" in t and "data you'd like us to add" in t and "mailto:" not in t
