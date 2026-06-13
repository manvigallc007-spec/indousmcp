"""Overpass call resilience: retry/backoff on 429/5xx, give up cleanly. No network."""

import pytest

import indo_usa_mcp.osm as osm


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._p = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._p


def test_overpass_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, **kw):
        calls["n"] += 1
        return _Resp(429) if calls["n"] < 3 else _Resp(200, {"elements": [1, 2]})
    monkeypatch.setattr(osm.httpx, "post", fake_post)
    monkeypatch.setattr(osm.time, "sleep", lambda *_: None)
    data = osm.overpass_post("q", 10, retries=3, base_delay=0)
    assert data["elements"] == [1, 2] and calls["n"] == 3   # retried twice, then succeeded


def test_overpass_gives_up_cleanly(monkeypatch):
    monkeypatch.setattr(osm.httpx, "post", lambda url, **kw: _Resp(504))
    monkeypatch.setattr(osm.time, "sleep", lambda *_: None)
    with pytest.raises(osm.OverpassError):
        osm.overpass_post("q", 10, retries=2, base_delay=0)
