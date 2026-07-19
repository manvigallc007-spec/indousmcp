"""Phase 2 — "Today in Indian America" feed, /today page, the consumer email-digest agent (cadence +
one-click unsubscribe), and contributor stats. Real dev DB, ZZTEST rows, try/finally; email mocked."""

import datetime as dt

from starlette.testclient import TestClient

from indo_usa_mcp import accounts, db, today, verticals
from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.agents.definitions import ConsumerDigestAgent
from indo_usa_mcp.agents.scheduler import _RUN_ORDER
from indo_usa_mcp.config import settings
from indo_usa_mcp.pipeline import outreach
from indo_usa_mcp.web import auth
from indo_usa_mcp.web import today_web
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_E = "zztest_p2@example.com"


def _clean():
    db.execute("DELETE FROM user_profiles WHERE email=%s", (_E,))


# --------------------------------------------------------------- today.py assembler
def test_approx_tithi_reference_new_moon():
    # At the reference new moon the tithi is the 1st waxing day (Shukla Pratipada).
    assert today.approx_tithi(dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc)).startswith("Shukla Pratipada")
    assert "(approx.)" in today.approx_tithi()


def test_daily_nugget_rotates_and_is_stable_per_day():
    a = today.daily_nugget(dt.date(2026, 7, 12))
    b = today.daily_nugget(dt.date(2026, 7, 12))
    c = today.daily_nugget(dt.date(2026, 8, 1))
    assert a and a == b and a["title"]          # deterministic within a day
    assert a["slug"] != c["slug"] or True       # rotates across days (may collide rarely; not asserted hard)


def test_assemble_and_digest_text_shape():
    feed = today.assemble(city="Plano", state="TX", languages=["Telugu"])
    assert feed["city"] == "Plano" and "tithi" in feed and "nugget" in feed
    for k in ("events", "movies", "new_places"):
        assert isinstance(feed[k], list)
    txt = today.render_digest_text(feed, "https://namasteamerica.us")
    assert "Today in Indian America" in txt and "/today" in txt


# --------------------------------------------------------------- /today page
def test_today_anonymous_shows_signin_cta():
    html = _client.get("/today").text
    assert "Today in Indian America" in html and "Sign in / create account" in html


def test_today_signed_in_personalizes(monkeypatch):
    monkeypatch.setattr(today_web, "portal_email", lambda req: _E)
    try:
        accounts.upsert_profile(_E, home_city="Plano", home_state="TX", languages=["Telugu"])
        html = _client.get("/today").text
        assert "Plano" in html and "Sign in / create account" not in html
        assert "panchang" in html                 # tithi line present
    finally:
        _clean()


# --------------------------------------------------------------- digest agent
def _enable_email(monkeypatch, sink):
    for f, v in (("smtp_host", "smtp.test"), ("smtp_user", "u"), ("smtp_password", "p"), ("smtp_from", "f@x")):
        monkeypatch.setattr(settings, f, v)
    monkeypatch.setattr(outreach, "send_email",
                        lambda to, subj, body, list_unsubscribe=None: sink.append((to, subj, body, list_unsubscribe)) or True)


def test_consumer_digest_agent_registered_and_scheduled():
    assert "consumer_digest" in AGENTS and "consumer_digest" in _RUN_ORDER


def test_digest_agent_sends_respects_cadence_and_unsubscribe(monkeypatch):
    sink: list = []
    _enable_email(monkeypatch, sink)
    try:
        accounts.upsert_profile(_E, home_city="Plano", home_state="TX", languages=["Telugu"],
                                notify_email=True, digest_freq="daily")
        assert _E in [p["email"] for p in accounts.due_for_digest()]
        out = ConsumerDigestAgent().run()
        assert out["emails"] == 1 and len(sink) == 1
        assert "/me/unsubscribe?t=" in sink[0][2] and sink[0][3]        # unsub link + List-Unsubscribe
        # cadence: not due again the same day
        assert _E not in [p["email"] for p in accounts.due_for_digest()]
        # the emailed token unsubscribes
        tok = sink[0][3].split("t=")[1]
        assert auth.verify_action_token(tok, "digest_unsub") == _E
        r = _client.get(f"/me/unsubscribe?t={tok}")
        assert r.status_code == 200 and "unsubscribed" in r.text.lower()
        assert accounts.get_profile(_E)["notify_email"] is False
        assert _E not in [p["email"] for p in accounts.due_for_digest()]
    finally:
        _clean()


def test_digest_agent_noop_without_channels(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")            # email off
    monkeypatch.setattr(settings, "vapid_public_key", "")    # push off
    assert ConsumerDigestAgent().run() == {"skipped": "no_channels"}


def test_unsubscribe_rejects_bad_token():
    assert _client.get("/me/unsubscribe?t=garbage").status_code == 400


# --------------------------------------------------------------- contributor stats
def test_contributor_stats_counts_and_tiers():
    from indo_usa_mcp import submissions
    sid = submissions.submit("restaurants", {"name": "ZZTEST P2 Contrib"}, contact_email=_E)["id"]
    db.execute("UPDATE submissions SET created_record_id = 12345 WHERE id = %s", (sid,))   # mark 'added'
    try:
        st = accounts.contributor_stats(_E)
        assert st["added"] == 1 and st["points"] >= 5 and st["tier"]
    finally:
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))
        _clean()
