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


def test_num_handles_sentinels():
    assert D._num("152000") == 152000.0 and D._num("3.5") == 3.5
    assert D._num("-666666666") is None and D._num(None) is None and D._num("x") is None


def _mock_get(monkeypatch, header, *rows):
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return [header, *rows]
    monkeypatch.setattr(D.httpx, "get", lambda *a, **k: _R())


def test_refresh_languages_rolls_up_to_national(monkeypatch):
    codes = list(D._LANG_VARS)                      # the 9 estimate variables, in request order
    header = ["NAME", *codes, "state"]
    # Hindi (B16001_048E) is first in _LANG_VARS; give two states so the US roll-up sums them.
    row1 = ["New Jersey", *["10000" if c == "B16001_048E" else "0" for c in codes], "34"]
    row2 = ["Texas", *["15000" if c == "B16001_048E" else "0" for c in codes], "48"]
    _mock_get(monkeypatch, header, row1, row2)
    saved = []
    monkeypatch.setattr(D.db, "execute", lambda sql, params=None: saved.append(params))
    out = D.refresh_languages(year="2022")
    assert out["ok"]
    hindi = [p for p in saved if p[3] == "lang:hindi"]
    assert any(p[0] == "state:34" and p[4] == 10000 for p in hindi)      # per-state
    assert any(p[0] == "us" and p[4] == 25000 for p in hindi)            # national roll-up


def test_refresh_profile_skips_without_key(monkeypatch):
    monkeypatch.setattr(D.settings, "census_api_key", "")
    assert D.refresh_profile()["skipped"] == "no_census_api_key"


def test_refresh_profile_computes_percentages(monkeypatch):
    monkeypatch.setattr(D.settings, "census_api_key", "testkey")
    header = ["NAME", "S0201_001E", "S0201_214E", "S0201_235E", "S0201_018E", "S0201_159E",
              "S0201_099E", "S0201_090E", "S0201_177E", "S0201_176E", "state"]
    row = ["United States", "4000000", "152000", "75000", "38", "3.5",
           "2000000", "2800000", "1500000", "2000000", "1"]
    _mock_get(monkeypatch, header, row)
    saved = []
    monkeypatch.setattr(D.db, "execute", lambda sql, params=None: saved.append(params))
    out = D.refresh_profile(year="2022")
    assert out["ok"] and out["us"]
    assert any(p[3] == "median_household_income" and p[4] == 152000.0 for p in saved)
    assert any(p[3] == "pct_bachelors_plus" and p[4] == 71.4 for p in saved)   # 2.0M/2.8M
    assert any(p[3] == "pct_prof_occupations" and p[4] == 75.0 for p in saved)


def test_facts_and_languages_graceful_without_db(monkeypatch):
    monkeypatch.setattr(D.db, "query",
                        lambda *a, **k: (_ for _ in ()).throw(Exception("no db")))
    assert D.facts("us") == {} and D.languages("us") == []


def test_insights_page_renders():
    r = TestClient(app).get("/insights")
    assert r.status_code == 200 and "by the numbers" in r.text.lower()
