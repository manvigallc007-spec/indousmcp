"""Security hardening: response headers on every page, admin-login throttle, JSON-LD XSS escape."""

from starlette.testclient import TestClient

from indo_usa_mcp.config import settings
from indo_usa_mcp.web import app
from indo_usa_mcp.web import security


def test_security_headers_present():
    r = TestClient(app).get("/chat")
    h = r.headers
    assert "content-security-policy" in h
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "referrer-policy" in h and "permissions-policy" in h


def test_hsts_only_over_https():
    c = TestClient(app)
    assert "strict-transport-security" not in c.get("/").headers           # plain http
    r = c.get("/", headers={"x-forwarded-proto": "https"})
    assert "strict-transport-security" in r.headers                        # behind TLS proxy


def test_admin_login_throttled(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")
    security._ATTEMPTS.clear()
    c = TestClient(app)
    # 8 wrong attempts allowed, then throttled
    for _ in range(8):
        assert c.post("/admin/login", data={"password": "nope"}).status_code in (401, 303)
    assert c.post("/admin/login", data={"password": "nope"}).status_code == 429


def test_landing_jsonld_escapes_script_breakout():
    # A listing name containing "</script>" must not break out of the JSON-LD block.
    from indo_usa_mcp.web import landing
    body = landing._page("T", "d", "<p>body</p>", jsonld='{"name": "</script><b>x</b>"}').body.decode()
    assert "</script><b>x" not in body     # the malicious closer is neutralized
    assert "\\u003c/script" in body        # escaped form present instead
