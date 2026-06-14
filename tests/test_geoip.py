"""IP-based location fallback: private IPs skipped, public parsed, failures graceful. No network."""

import indo_usa_mcp.web.geoip as g


def test_private_and_missing_ips_return_none():
    assert g.approx_point(None) is None
    assert g.approx_point("127.0.0.1") is None
    assert g.approx_point("10.0.0.5") is None
    assert g.approx_point("not-an-ip") is None


def test_public_ip_parses_and_caches(monkeypatch):
    g._CACHE.clear()
    calls = {"n": 0}

    class _R:
        status_code = 200

        def json(self):
            return {"success": True, "latitude": 40.7, "longitude": -74.0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _R()
    monkeypatch.setattr(g.httpx, "get", fake_get)
    assert g.approx_point("8.8.8.8") == (40.7, -74.0)
    assert g.approx_point("8.8.8.8") == (40.7, -74.0)   # served from cache
    assert calls["n"] == 1                               # only one network call


def test_lookup_failure_is_graceful(monkeypatch):
    g._CACHE.clear()
    monkeypatch.setattr(g.httpx, "get",
                        lambda *a, **k: (_ for _ in ()).throw(g.httpx.ConnectError("offline")))
    assert g.approx_point("8.8.8.8") is None
