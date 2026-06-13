"""Public read-only JSON search API: param handling, field projection, errors, rate limit. No DB."""

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp.config import settings
from indo_usa_mcp.web import api, app

_FAKE = {"count": 1, "query": "dosa", "ranking": "vector", "results": [
    {"vertical": "restaurants", "id": 7, "name": "Dosa Hut", "city": "Edison", "state": "NJ",
     "phone": "+1 732 555 0100", "latitude": 40.5, "longitude": -74.3, "rating": 4.6,
     "verified_ago": "verified 3 days ago", "confidence": 0.9, "embedding": "secret"}]}


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(api.verticals, "search_all", lambda *a, **k: _FAKE)
    api._HITS.clear()


def test_search_projects_public_fields_only():
    r = TestClient(app).get("/api/v1/search?q=dosa")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1 and data["ranking"] == "vector"
    row = data["results"][0]
    assert row["name"] == "Dosa Hut" and row["verified_ago"]
    # internal columns must not leak
    assert "id" not in row and "confidence" not in row and "embedding" not in row


def test_missing_query_is_400():
    assert TestClient(app).get("/api/v1/search").status_code == 400


def test_unknown_vertical_is_400():
    r = TestClient(app).get("/api/v1/search?q=x&vertical=spaceships")
    assert r.status_code == 400 and "valid" in r.json()


def test_vertical_scopes_to_one_query_fn(monkeypatch):
    from indo_usa_mcp import queries as r_queries

    def boom(*a, **k):
        raise AssertionError("search_all must not run when a vertical is given")
    monkeypatch.setattr(api.verticals, "search_all", boom)
    monkeypatch.setattr(r_queries, "search_restaurants_by_text",
                        lambda q, **k: {"ranking": "trigram",
                                        "results": [{"name": "Scoped", "city": "Iselin"}]})
    r = TestClient(app).get("/api/v1/search?q=dinner&vertical=restaurants")
    assert r.status_code == 200 and r.json()["results"][0]["name"] == "Scoped"


def test_verticals_list():
    data = TestClient(app).get("/api/v1/verticals").json()
    keys = {v["key"] for v in data["verticals"]}
    assert {"restaurants", "community"} <= keys


def test_docs_page_renders():
    r = TestClient(app).get("/api")
    assert r.status_code == 200 and "/api/v1/search" in r.text


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "api_rate_per_min", 1)
    api._HITS.clear()
    c = TestClient(app)
    assert c.get("/api/v1/search?q=dosa").status_code == 200
    assert c.get("/api/v1/search?q=dosa").status_code == 429
