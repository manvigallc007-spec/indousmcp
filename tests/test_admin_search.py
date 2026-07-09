"""Unified cross-entity admin search (/admin/data, no vertical param): a directory + router across
every vertical, events, movies, employers, and knowledge -- never edits anything itself, only links
into each entry's own canonical edit page."""

from starlette.testclient import TestClient

import indo_usa_mcp.embeddings as emb
import indo_usa_mcp.web.admin as admin_mod
from indo_usa_mcp import db, verticals
from indo_usa_mcp.web.app import app

_client = TestClient(app)


def _bypass_auth(monkeypatch):
    monkeypatch.setattr(admin_mod, "require_admin", lambda request: None)


def test_unauthenticated_redirects_to_login():
    r = _client.get("/admin/data", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_no_query_shows_directory_with_live_counts(monkeypatch):
    _bypass_auth(monkeypatch)
    r = _client.get("/admin/data")
    assert r.status_code == 200
    for label in ("Restaurants", "Temples", "Movies", "Employers", "Knowledge"):
        assert label in r.text


def test_search_finds_a_vertical_row_and_links_to_its_own_edit_page(monkeypatch):
    _bypass_auth(monkeypatch)
    monkeypatch.setattr(emb, "enabled", lambda: False)
    name = "ZZTEST Unified Search Restaurant"
    db.execute("DELETE FROM restaurants WHERE name = %s", (name,))
    res = verticals.create_record(
        "restaurants", {"name": name, "city": "Plano", "state": "TX", "lat": 33.02, "lng": -96.7},
        source="test")
    assert res.get("ok"), res
    rec_id = res["id"]
    try:
        r = _client.get("/admin/data", params={"q": "ZZTEST Unified Search"})
        assert r.status_code == 200
        assert "Restaurants" in r.text
        assert f"/admin/data/restaurants/{rec_id}" in r.text
    finally:
        db.execute("DELETE FROM restaurants WHERE id = %s", (rec_id,))


def test_search_finds_movie_employer_and_kb_grouped_under_their_own_sections(monkeypatch):
    _bypass_auth(monkeypatch)
    from indo_usa_mcp import knowledge
    db.execute("DELETE FROM movies WHERE tmdb_id = 999900003")
    m = db.query_one("INSERT INTO movies (tmdb_id, title) VALUES (999900003, 'ZZTEST Search Movie') "
                     "RETURNING id")
    db.execute("DELETE FROM h1b_sponsors WHERE employer = 'ZZTEST SEARCH CORP'")
    s = db.query_one("INSERT INTO h1b_sponsors (employer, display_name) VALUES "
                     "('ZZTEST SEARCH CORP', 'ZZTest Search Corp') RETURNING id")
    db.execute("DELETE FROM kb_documents WHERE source_ref = 'zztest-search-doc'")
    doc_id = knowledge.upsert_document(source_type="article", source_ref="zztest-search-doc",
                                       content="ZZTEST search doc body.",
                                       title="ZZTest Search Doc")["document_id"]
    try:
        r_movie = _client.get("/admin/data", params={"q": "ZZTEST Search Movie"})
        assert f"/admin/movies/{m['id']}" in r_movie.text and "Movies" in r_movie.text

        r_emp = _client.get("/admin/data", params={"q": "ZZTEST SEARCH CORP"})
        assert f"/admin/employers/{s['id']}" in r_emp.text and "Employers" in r_emp.text

        r_kb = _client.get("/admin/data", params={"q": "ZZTest Search Doc"})
        assert f"/admin/knowledge/{doc_id}" in r_kb.text and "Knowledge" in r_kb.text
    finally:
        db.execute("DELETE FROM movies WHERE id = %s", (m["id"],))
        db.execute("DELETE FROM h1b_sponsors WHERE id = %s", (s["id"],))
        db.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))


def test_search_omits_empty_groups(monkeypatch):
    _bypass_auth(monkeypatch)
    r = _client.get("/admin/data", params={"q": "zzznonexistent-query-matches-nothing-anywhere"})
    assert r.status_code == 200
    assert "No matches." in r.text
