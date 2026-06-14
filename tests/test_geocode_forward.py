"""Forward geocoding (address -> coords via Nominatim): parse, cache, graceful failure. No network."""

import indo_usa_mcp.geocode as gc


def test_empty_query_returns_none():
    assert gc.coords_for() is None
    assert gc.coords_for(address="", city="", state="") is None


def test_nominatim_fallback_parses_and_caches(monkeypatch):
    gc._FWD_CACHE.clear()
    calls = {"n": 0}

    class _R:
        status_code = 200

        def json(self):
            return [{"lat": "40.5187", "lon": "-74.4121"}]   # Nominatim shape

    def fake_get(*a, **k):
        calls["n"] += 1
        return _R()
    monkeypatch.setattr(gc.httpx, "get", fake_get)
    pt = gc.coords_for(address="123 Oak St", city="Edison", state="NJ")
    assert pt == (40.5187, -74.4121)
    n_after = calls["n"]
    gc.coords_for(address="123 Oak St", city="Edison", state="NJ")   # cached -> no new calls
    assert calls["n"] == n_after


def test_census_used_for_street_address(monkeypatch):
    gc._FWD_CACHE.clear()

    def fake_get(url, **k):
        if "census.gov" in url:
            class _C:
                status_code = 200

                def json(self):
                    return {"result": {"addressMatches": [{"coordinates": {"x": -74.41, "y": 40.52}}]}}
            return _C()
        raise AssertionError("Census matched, so Nominatim must not be called")
    monkeypatch.setattr(gc.httpx, "get", fake_get)
    assert gc.coords_for(address="123 Oak St", city="Edison", state="NJ") == (40.52, -74.41)


def test_forward_geocode_no_match_is_none(monkeypatch):
    gc._FWD_CACHE.clear()

    class _R:
        status_code = 200

        def json(self):
            return []
    monkeypatch.setattr(gc.httpx, "get", lambda *a, **k: _R())
    assert gc.coords_for(city="Nowheresville", state="ZZ") is None


def test_forward_geocode_failure_is_graceful(monkeypatch):
    gc._FWD_CACHE.clear()
    monkeypatch.setattr(gc.httpx, "get",
                        lambda *a, **k: (_ for _ in ()).throw(gc.httpx.ConnectError("offline")))
    assert gc.coords_for(city="Dallas", state="TX") is None
