"""Tranche 2 — event-driven notifications: the outbox (notify.py enqueue/deliver/drain, dedupe),
the event hooks (answer-to-your-question, reply-to-your-review), the periodic follow nudges (new offer
on a saved place, new event in a followed city), and the NotificationAgent wiring. Real dev DB, ZZTEST
rows, try/finally; email/push mocked (no network)."""

from starlette.testclient import TestClient

from indo_usa_mcp import accounts, db, notify, owner_content as oc, qa, reviews as rv, verticals
from indo_usa_mcp.agents.definitions import NotificationAgent
from indo_usa_mcp.agents.registry import AGENTS
from indo_usa_mcp.agents.scheduler import _RUN_ORDER
from indo_usa_mcp.config import settings
from indo_usa_mcp.web.app import app  # noqa: F401 (ensures app import path stays valid)

_ASKER = "zztest_notif_asker@example.com"
_ANSWERER = "zztest_notif_answerer@example.com"
_REVIEWER = "zztest_notif_reviewer@example.com"
_SAVER = "zztest_notif_saver@example.com"
_OWNER = "zztest_notif_owner@example.com"


def _clean():
    for e in (_ASKER, _ANSWERER, _REVIEWER, _SAVER, _OWNER):
        db.execute("DELETE FROM notifications WHERE email=%s", (e,))
        db.execute("DELETE FROM user_profiles WHERE email=%s", (e,))
    db.execute("DELETE FROM questions WHERE asker_email=%s", (_ASKER,))
    db.execute("DELETE FROM follows WHERE email=%s", (_SAVER,))
    db.execute("DELETE FROM saved_places WHERE email=%s", (_SAVER,))


# --------------------------------------------------------------- outbox core
def test_enqueue_is_idempotent_by_dedupe_key():
    _clean()
    try:
        assert notify.enqueue(_ASKER, "T", "b", kind="k", dedupe_key="zzt-dedupe-1") is True
        assert notify.enqueue(_ASKER, "T", "b", kind="k", dedupe_key="zzt-dedupe-1") is False  # dup dropped
        rows = notify.recent_for(_ASKER)
        assert len([r for r in rows if r["kind"] == "k"]) == 1
    finally:
        db.execute("DELETE FROM notifications WHERE dedupe_key='zzt-dedupe-1'")
        _clean()


def test_drain_delivers_via_email_and_stamps_sent(monkeypatch):
    _clean()
    sent = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")   # email_enabled needs host+user+pw
    monkeypatch.setattr(settings, "smtp_user", "u@example.com")
    monkeypatch.setattr(settings, "smtp_password", "pw")
    from indo_usa_mcp.pipeline import outreach
    monkeypatch.setattr(outreach, "send_email", lambda *a, **k: sent.append(a) or True)
    try:
        accounts.upsert_profile(_ASKER, notify_email=True, notify_web=False)
        notify.enqueue(_ASKER, "Hello", "body", url="/me", kind="generic", dedupe_key="zzt-drain-1")
        out = notify.drain()
        assert out["sent"] >= 1 and sent                            # our row delivered (count is global)
        row = next(r for r in notify.recent_for(_ASKER) if r["kind"] == "generic")
        assert row["sent_at"] is not None                          # stamped, won't re-send
    finally:
        db.execute("DELETE FROM notifications WHERE dedupe_key='zzt-drain-1'")
        _clean()


# --------------------------------------------------------------- hook: answer to your question
def test_answer_notifies_asker_not_self(monkeypatch):
    _clean()
    q = qa.create_question("ZZTEST where is the best chaat in Iselin?", asker_email=_ASKER)
    try:
        qa.add_answer(q["id"], "Try the place on Oak Tree Rd — amazing.", _ANSWERER)
        got = notify.recent_for(_ASKER)
        assert any(n["kind"] == "answer" and n["url"] == f"/q/{q['slug']}" for n in got)
        # self-answer must NOT notify
        before = len(notify.recent_for(_ASKER))
        qa.add_answer(q["id"], "Actually I found it myself, thanks.", _ASKER)
        assert len(notify.recent_for(_ASKER)) == before
    finally:
        db.execute("DELETE FROM answers WHERE question_id=%s", (q["id"],))
        db.execute("DELETE FROM questions WHERE id=%s", (q["id"],))
        _clean()


# --------------------------------------------------------------- hook: reply to your review
def test_review_reply_notifies_reviewer():
    _clean()
    rid = verticals.create_record("restaurants", {"name": "ZZTEST Notif Cafe", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7,
                                                  "email": _OWNER}, source="test")["id"]
    try:
        r = rv.submit("restaurants", rid, 4, body="Nice but slow.", name="Asha", email=_REVIEWER)
        db.execute("UPDATE reviews SET status='published' WHERE id=%s", (r["id"],))
        assert oc.reply_to_review(r["id"], "restaurants", rid, "Thanks — we've added staff.")["ok"]
        got = notify.recent_for(_REVIEWER)
        assert any(n["kind"] == "review_reply" and f"/listing/restaurants/{rid}" in n["url"] for n in got)
    finally:
        db.execute("DELETE FROM reviews WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
        _clean()


# --------------------------------------------------------------- periodic follow nudges
def test_agent_enqueues_saved_offer_and_followed_event():
    _clean()
    rid = verticals.create_record("restaurants", {"name": "ZZTEST Offer Cafe", "city": "Frisco",
                                                  "state": "TX", "lat": 33.1, "lng": -96.8,
                                                  "email": _OWNER}, source="test")["id"]
    ev = db.query_one(
        "INSERT INTO events (natural_key, name, city, state, status, is_active, start_at) "
        "VALUES ('zztest-notif-ev', 'ZZTEST Garba Night', 'Frisco', 'TX', 'approved', true, "
        "now() + interval '10 days') RETURNING id")
    try:
        accounts.save_place(_SAVER, "restaurants", rid)
        accounts.follow(_SAVER, "city", "Frisco, TX")
        oc.create_post("restaurants", rid, _OWNER, kind="offer", title="Free gulab jamun this week")
        # no channels -> agent still enqueues nudges, just doesn't deliver
        out = NotificationAgent().run()
        kinds = {n["kind"] for n in notify.recent_for(_SAVER)}
        assert "saved_offer" in kinds and "follow_event" in kinds
        assert out["offer_nudges"] >= 1 and out["event_nudges"] >= 1
        # re-run is idempotent (dedupe_key) -> no new rows
        n_before = len(notify.recent_for(_SAVER))
        NotificationAgent().run()
        assert len(notify.recent_for(_SAVER)) == n_before
    finally:
        db.execute("DELETE FROM owner_posts WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
        db.execute("DELETE FROM events WHERE id=%s", (ev["id"],))
        _clean()


# --------------------------------------------------------------- scheduling invariant
def test_notification_agent_is_registered_and_scheduled():
    assert "notification" in AGENTS
    assert "notification" in _RUN_ORDER          # in ALL_AGENTS but not _RUN_ORDER == never runs
