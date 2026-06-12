"""Tests for admin gate, magic-link auth, vertical registry, reporting (no DB)."""

from starlette.testclient import TestClient

from indo_usa_mcp import reporting, verticals
from indo_usa_mcp.web import app
from indo_usa_mcp.web.auth import make_magic_token, verify_magic_token


def test_admin_requires_login():
    c = TestClient(app)
    r = c.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login"


def test_magic_token_roundtrip_and_rejections():
    t = make_magic_token("owner@example.com", ttl_minutes=5)
    assert verify_magic_token(t) == "owner@example.com"
    assert verify_magic_token(make_magic_token("x@y.com", ttl_minutes=-1)) is None  # expired
    assert verify_magic_token("garbage") is None
    tampered = t[:-1] + ("a" if t[-1] != "a" else "b")  # break the signature
    assert verify_magic_token(tampered) is None


def test_verticals_registry_integrity():
    assert {"restaurants", "temples", "groceries", "professionals"} <= set(verticals.VERTICALS)
    for cfg in verticals.VERTICALS.values():
        for key in ("label", "table", "queries", "edit_fields", "has_hours", "has_dietary", "update"):
            assert key in cfg
        assert callable(cfg["update"])


def test_portal_login_page_renders():
    assert TestClient(app).get("/portal/login").status_code == 200


def test_verticals_helpers_are_defined():
    # Guards against an edit dropping a function's `def` line (caused a Payments 500).
    for fn in ("featured_summary", "search_all", "merge_duplicates", "enhance_existing",
               "geo_summary", "normalize_geography"):
        assert callable(getattr(verticals, fn, None)), f"verticals.{fn} missing"


def test_report_render_text():
    metrics = {
        "health": {"agent_runs_24h": 1, "agent_errors_24h": 0, "open_alerts": 0,
                   "approvals_pending": 0, "feedback_pending": 0, "raw_backlog": {}},
        "growth": {"verticals": {"restaurants": {"total": 5, "new_today": 1, "claimed": 0, "featured": 0}},
                   "claims_today": 0, "featured_total": 0},
    }
    txt = reporting.render_text({"metrics": metrics, "deltas": {}})
    assert "daily report" in txt.lower()
    assert "restaurants" in txt
