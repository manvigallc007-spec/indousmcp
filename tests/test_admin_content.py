"""Admin routes for movies/employers/knowledge: unauthenticated gate + authenticated CRUD flow.

No existing test in this codebase authenticates a real admin session via TestClient (the login flow
needs ADMIN_PASSWORD + a signed session cookie); every other admin test either checks the
unauthenticated redirect only, or calls page functions directly. Here, `require_admin` is monkeypatched
to bypass the login gate for the authenticated-flow tests, isolating what's actually under test (the
CRUD behavior) from session/cookie plumbing -- same idea as this codebase's other narrow monkeypatches
of a single gate/check function."""

from starlette.testclient import TestClient

import indo_usa_mcp.web.admin_content as ac
from indo_usa_mcp import db
from indo_usa_mcp.web.app import app

_client = TestClient(app)


def test_unauthenticated_redirects_to_login():
    for path in ("/admin/movies", "/admin/employers", "/admin/knowledge"):
        r = _client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin/login", path


def _bypass_auth(monkeypatch):
    monkeypatch.setattr(ac, "require_admin", lambda request: None)


def test_movies_admin_flow(monkeypatch):
    _bypass_auth(monkeypatch)
    db.execute("DELETE FROM movies WHERE tmdb_id = 999900002")
    row = db.query_one("INSERT INTO movies (tmdb_id, title, language) VALUES "
                       "(999900002, 'ZZTEST Content Movie', 'Hindi') RETURNING id")
    mid = row["id"]
    try:
        assert "ZZTEST Content Movie" in _client.get("/admin/movies").text
        detail = _client.get(f"/admin/movies/{mid}")
        assert detail.status_code == 200
        assert "Save edits" in detail.text and "Deactivate" in detail.text

        r = _client.post(f"/admin/movies/{mid}/action", data={"op": "deactivate"},
                         follow_redirects=False)
        assert r.status_code == 303
        assert "Reactivate" in _client.get(f"/admin/movies/{mid}").text   # state visibly flipped
    finally:
        db.execute("DELETE FROM movies WHERE id = %s", (mid,))


def test_employers_admin_flow(monkeypatch):
    _bypass_auth(monkeypatch)
    db.execute("DELETE FROM h1b_sponsors WHERE employer = 'ZZTEST CONTENT CORP'")
    row = db.query_one("INSERT INTO h1b_sponsors (employer, display_name, certified) VALUES "
                       "('ZZTEST CONTENT CORP', 'ZZTest Content Corp', 5) RETURNING id")
    sid = row["id"]
    try:
        assert "ZZTest Content Corp" in _client.get("/admin/employers").text
        detail = _client.get(f"/admin/employers/{sid}")
        assert detail.status_code == 200 and "Save edits" in detail.text

        _client.post(f"/admin/employers/{sid}/action", data={"op": "deactivate"})
        assert "Reactivate" in _client.get(f"/admin/employers/{sid}").text
    finally:
        db.execute("DELETE FROM h1b_sponsors WHERE id = %s", (sid,))


def test_knowledge_admin_flow(monkeypatch):
    _bypass_auth(monkeypatch)
    from indo_usa_mcp import knowledge
    db.execute("DELETE FROM kb_documents WHERE source_ref = 'zztest-content-flow'")
    doc_id = knowledge.upsert_document(
        source_type="article", source_ref="zztest-content-flow", content="ZZTEST content flow body.",
        title="ZZTest Content Flow")["document_id"]
    try:
        assert "ZZTest Content Flow" in _client.get("/admin/knowledge").text
        detail = _client.get(f"/admin/knowledge/{doc_id}")
        assert detail.status_code == 200
        assert "Save edits" in detail.text
        assert "ZZTEST content flow body." in detail.text     # content shown read-only
        assert "readonly" in detail.text                       # ...and marked as such

        _client.post(f"/admin/knowledge/{doc_id}/action", data={"op": "deactivate"})
        assert "Reactivate" in _client.get(f"/admin/knowledge/{doc_id}").text
    finally:
        db.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))
