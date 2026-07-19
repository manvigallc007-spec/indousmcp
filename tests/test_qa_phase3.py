"""Phase 3 — Ask-the-community Q&A: qa.py core (moderation reuse, Dost auto-answer, voting), the web
surface (/ask, /questions, /q/{slug}, QAPage JSON-LD), sitemap + Today + contributor-stats integration.
Real dev DB, ZZTEST rows, try/finally; login simulated via portal_email; LLM inactive in tests."""

from starlette.testclient import TestClient

from indo_usa_mcp import accounts, db, qa, today
from indo_usa_mcp.web import qa_web
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_E = "zztest_p3@example.com"


def _clean():
    db.execute("DELETE FROM questions WHERE asker_email=%s", (_E,))
    db.execute("DELETE FROM questions WHERE title LIKE 'ZZTEST %'")


# --------------------------------------------------------------- qa.py
def test_create_question_screens_and_slugs():
    try:
        r = qa.create_question("ZZTEST where is the best dosa in Edison NJ?", asker_email=_E, city="Edison")
        assert r["ok"] and r["status"] == "published" and r["slug"].endswith(str(r["id"]))
        assert qa.create_question("short")["error"] == "too_short"
        # a link -> screened to pending (reuses reviews._screen)
        spam = qa.create_question("ZZTEST visit http://spam.example.com for cheap deals!!!!")
        assert spam["status"] == "pending"
    finally:
        _clean()


def test_answers_and_voting_toggle():
    r = qa.create_question("ZZTEST Telugu tiffin center near Frisco?", asker_email=_E)
    try:
        a = qa.add_answer(r["id"], "Try Tiffins & More on Main St — great pesarattu.", "answerer@example.com")
        assert a["ok"] and a["status"] == "published"
        assert qa.add_answer(r["id"], "x", "z@z.com")["error"] == "too_short"
        v = qa.vote_answer(a["id"], "voter@example.com")
        assert v["voted"] is True and v["upvotes"] == 1
        assert qa.vote_answer(a["id"], "voter@example.com")["upvotes"] == 0     # toggle off
        got = qa.get_question(r["slug"])
        assert got["answer_count"] == 1 and len(got["answers"]) == 1
    finally:
        _clean()


def test_unanswered_and_trending():
    r = qa.create_question("ZZTEST which gurdwara has langar on Sundays in Plano?", asker_email=_E)
    try:
        assert any(u["slug"] == r["slug"] for u in qa.unanswered())     # no human answer yet
        qa.add_answer(r["id"], "The one on Legacy Dr has langar every Sunday noon.", "a@b.com")
        assert not any(u["slug"] == r["slug"] for u in qa.unanswered())  # now answered
        assert any(t["slug"] == r["slug"] for t in qa.trending())
    finally:
        _clean()


# --------------------------------------------------------------- web surface
def test_questions_public_ask_requires_login():
    assert _client.get("/questions").status_code == 200
    r = _client.get("/ask", follow_redirects=False)
    assert r.status_code == 303 and "/portal/login" in r.headers["location"]


def test_ask_answer_flow_and_jsonld(monkeypatch):
    monkeypatch.setattr(qa_web, "portal_email", lambda req: _E)
    try:
        r = _client.post("/ask", data={"title": "ZZTEST best sweets shop for Diwali in Jersey City?",
                                       "body": "Need kaju katli.", "vertical": "sweets", "city": "Jersey City",
                                       "state": "NJ"}, follow_redirects=False)
        assert r.status_code == 303 and "/q/" in r.headers["location"]
        slug = r.headers["location"].split("/q/")[1]
        d = _client.get(f"/q/{slug}").text
        assert "Diwali" in d and '"@type": "QAPage"' in d and "Post answer" in d
        _client.post(f"/q/{slug}/answer", data={"body": "Rasoi on Newark Ave has fresh kaju katli."},
                     follow_redirects=False)
        assert "Rasoi on Newark Ave" in _client.get(f"/q/{slug}").text
    finally:
        _clean()


def test_ask_pending_shows_review_message(monkeypatch):
    monkeypatch.setattr(qa_web, "portal_email", lambda req: _E)
    try:
        r = _client.post("/ask", data={"title": "ZZTEST spam http://x.com buy now!!!!!"},
                         follow_redirects=False)
        assert r.status_code == 200 and "under review" in r.text.lower()
    finally:
        _clean()


# --------------------------------------------------------------- integrations
def test_sitemap_includes_questions():
    r = qa.create_question("ZZTEST is there an Indian grocery in downtown Austin?", asker_email=_E)
    try:
        sm = _client.get("/sitemap.xml").text
        assert "/questions" in sm and f"/q/{r['slug']}" in sm
    finally:
        _clean()


def test_today_feed_includes_trending_questions():
    r = qa.create_question("ZZTEST where to buy diyas in Seattle?", asker_email=_E)
    try:
        feed = today.assemble(city="Seattle")
        assert any(q["slug"] == r["slug"] for q in feed.get("questions", []))
        txt = today.render_digest_text(feed, "https://x")
        assert "Community questions" in txt
    finally:
        _clean()


def test_contributor_stats_counts_qa():
    r = qa.create_question("ZZTEST which temple celebrates Ugadi big in Dallas?", asker_email=_E)
    try:
        qa.add_answer(r["id"], "The Karya Siddhi Hanuman temple has a big Ugadi event.", _E)
        st = accounts.contributor_stats(_E)
        assert st["asked"] == 1 and st["answered"] == 1 and st["points"] >= 3
    finally:
        _clean()
        db.execute("DELETE FROM answers WHERE author_email=%s", (_E,))
