"""IndexNow submission (config-gated, fire-and-forget) + the llms-full.txt AI export. No live DB."""

from starlette.testclient import TestClient

import indo_usa_mcp.indexnow as ix
from indo_usa_mcp.web.app import app


def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(ix.settings, "indexnow_key", "")
    assert ix.enabled() is False
    assert ix.submit(["https://namasteamerica.us/listing/restaurants/1"])["skipped"] is True


def test_skips_local_base(monkeypatch):
    monkeypatch.setattr(ix.settings, "indexnow_key", "k" * 16)
    monkeypatch.setattr(ix.settings, "public_web_url", "http://localhost:8080")
    assert ix.submit(["http://localhost:8080/listing/restaurants/1"])["skipped"] is True


def test_submit_builds_payload_and_filters(monkeypatch):
    monkeypatch.setattr(ix.settings, "indexnow_key", "deadbeefcafef00d")
    monkeypatch.setattr(ix.settings, "public_web_url", "https://namasteamerica.us")
    captured = {}

    class _Resp:
        status_code = 200

    def fake_post(url, json=None, timeout=None, headers=None):
        captured["url"], captured["json"] = url, json
        return _Resp()

    monkeypatch.setattr(ix.httpx, "post", fake_post)
    res = ix.submit([
        "https://namasteamerica.us/listing/restaurants/1",
        "https://namasteamerica.us/listing/restaurants/1",   # duplicate -> collapsed
        "https://evil.example.com/x",                        # off-site -> dropped
    ])
    assert res == {"submitted": 1, "status": 200}
    body = captured["json"]
    assert body["host"] == "namasteamerica.us"
    assert body["key"] == "deadbeefcafef00d"
    assert body["keyLocation"] == "https://namasteamerica.us/deadbeefcafef00d.txt"
    assert body["urlList"] == ["https://namasteamerica.us/listing/restaurants/1"]


def test_submit_never_raises_on_network_error(monkeypatch):
    monkeypatch.setattr(ix.settings, "indexnow_key", "deadbeefcafef00d")
    monkeypatch.setattr(ix.settings, "public_web_url", "https://namasteamerica.us")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(ix.httpx, "post", boom)
    out = ix.submit(["https://namasteamerica.us/listing/restaurants/1"])
    assert out["submitted"] == 0 and "error" in out      # swallowed, caller never breaks


def test_llms_full_txt_exports_articles():
    r = TestClient(app).get("/llms-full.txt")
    assert r.status_code == 200
    assert "knowledge export for AI agents" in r.text
    assert "Diwali" in r.text          # a curated knowledge article is included
    assert "/mcp" in r.text            # points agents at the live MCP server
