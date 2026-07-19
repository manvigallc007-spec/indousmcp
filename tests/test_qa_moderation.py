"""Admin moderation for community Q&A: flagged questions/answers wait as 'pending' and can be
approved/rejected from /admin/qa. Real dev DB, ZZTEST rows, try/finally; admin gate mocked."""

from starlette.testclient import TestClient

from indo_usa_mcp import db, qa
from indo_usa_mcp.web import admin as admin_mod
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_ASKER = "zztest_qamod@example.com"


def _clean():
    db.execute("DELETE FROM questions WHERE asker_email=%s", (_ASKER,))
    db.execute("DELETE FROM questions WHERE title LIKE 'ZZTEST %'")


def _pending_question():
    # a link in the title trips the spam screen -> status 'pending'
    return qa.create_question("ZZTEST claim visit http://spam.example.com now for deals!!!",
                              asker_email=_ASKER)


# --------------------------------------------------------------- qa.py moderation
def test_moderate_question_publish_and_reject():
    try:
        r = _pending_question()
        assert r["status"] == "pending"
        assert any(q["id"] == r["id"] for q in qa.list_pending_questions())
        qa.moderate_question(r["id"], True)
        assert db.query_one("SELECT status FROM questions WHERE id=%s", (r["id"],))["status"] == "published"
        assert not any(q["id"] == r["id"] for q in qa.list_pending_questions())

        r2 = _pending_question()
        qa.moderate_question(r2["id"], False)
        assert db.query_one("SELECT status FROM questions WHERE id=%s", (r2["id"],))["status"] == "rejected"
    finally:
        _clean()


def test_moderate_answer_publish_bumps_count():
    q = qa.create_question("ZZTEST which temple has the best Ugadi event in Dallas area?", asker_email=_ASKER)
    try:
        a = qa.add_answer(q["id"], "Check the Karya Siddhi visit http://x.com temple", "ans@example.com")
        assert a["status"] == "pending"                     # link -> held
        assert any(x["id"] == a["id"] for x in qa.list_pending_answers())
        assert qa.pending_count() >= 1
        qa.moderate_answer(a["id"], True)
        assert db.query_one("SELECT status FROM answers WHERE id=%s", (a["id"],))["status"] == "published"
        assert db.query_one("SELECT answer_count FROM questions WHERE id=%s", (q["id"],))["answer_count"] == 1
    finally:
        db.execute("DELETE FROM answers WHERE question_id=%s", (q["id"],))
        _clean()


# --------------------------------------------------------------- admin page + actions
def test_admin_qa_page_lists_and_acts(monkeypatch):
    monkeypatch.setattr(admin_mod, "require_admin", lambda request: None)
    q = _pending_question()
    try:
        html = _client.get("/admin/qa").text
        assert "ZZTEST claim" in html and "flagged:" in html and "Approve" in html
        r = _client.post("/admin/qa", data={"id": str(q["id"]), "op": "approve_q"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin/qa"
        assert db.query_one("SELECT status FROM questions WHERE id=%s", (q["id"],))["status"] == "published"
    finally:
        _clean()


def test_admin_qa_requires_auth():
    r = _client.get("/admin/qa", follow_redirects=False)
    assert r.status_code in (302, 303) and "/admin/login" in r.headers["location"]
