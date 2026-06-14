"""Census ACS demographics: parse ACS rows, upsert, graceful queries, /insights page. No network/DB."""

from starlette.testclient import TestClient

import indo_usa_mcp.demographics as D
from indo_usa_mcp.web import app


def test_int_handles_census_sentinels():
    assert D._int("1500") == 1500
    assert D._int("-666666666") is None     # ACS "no data" sentinel
    assert D._int(None) is None and D._int("x") is None


def test_refresh_parses_and_upserts(monkeypatch):
    class _R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [["NAME", "B02015_002E", "B01003_001E", "state"],
                    ["New Jersey", "450000", "9000000", "34"]]
    monkeypatch.setattr(D.httpx, "get", lambda *a, **k: _R())
    saved = []
    monkeypatch.setattr(D.db, "execute", lambda sql, params=None: saved.append(params))
    out = D.refresh(year="2022")
    assert out["upserted"] >= 1 and not out["errors"]
    assert any(p and p[3] == 450000 for p in saved)   # indian_population captured


def test_top_is_graceful_without_db(monkeypatch):
    monkeypatch.setattr(D.db, "query",
                        lambda *a, **k: (_ for _ in ()).throw(Exception("no db")))
    assert D.top("metro") == []


def test_insights_page_renders():
    r = TestClient(app).get("/insights")
    assert r.status_code == 200 and "by the numbers" in r.text.lower()
