"""First-party pageview log: path normalization, middleware only counts public HTML. No live DB."""

from starlette.testclient import TestClient

import indo_usa_mcp.analytics as analytics
import indo_usa_mcp.web.pageviews as pv
from indo_usa_mcp.web.app import app


def test_norm_path_collapses_to_two_segments():
    assert pv._norm("/") == "/"
    assert pv._norm("/about") == "/about"
    assert pv._norm("/browse/restaurants/NJ/Edison") == "/browse/restaurants"
    assert pv._norm("/insights") == "/insights"


def test_log_pageview_upserts(monkeypatch):
    seen = []
    monkeypatch.setattr(analytics.db, "execute", lambda sql, params=None: seen.append(params))
    analytics.log_pageview("/browse/restaurants")
    assert seen and seen[0][0] == "/browse/restaurants"


def test_middleware_counts_public_html_only(monkeypatch):
    logged = []
    monkeypatch.setattr(analytics, "log_pageview", lambda p: logged.append(p))
    c = TestClient(app)
    c.get("/about")          # public HTML -> counted
    c.get("/admin")          # admin -> skipped
    c.get("/health")         # JSON, not text/html -> skipped
    c.get("/sitemap.xml")    # xml -> skipped
    assert "/about" in logged
    assert not any(p.startswith("/admin") for p in logged)
    assert "/health" not in logged and "/sitemap" not in str(logged)
