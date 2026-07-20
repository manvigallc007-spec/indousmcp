"""Web push (VAPID): key generation, subscription storage, sending (pywebpush mocked) with dead-endpoint
pruning, the /push routes + /me enable button, and the digest agent's push channel. Real dev DB,
ZZTEST rows, try/finally; no real network."""

import types

import pywebpush
from starlette.testclient import TestClient

from indo_usa_mcp import accounts, db, webpush
from indo_usa_mcp.agents.definitions import ConsumerDigestAgent
from indo_usa_mcp.config import settings
from indo_usa_mcp.web import me as me_mod
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_E = "zztest_push@example.com"
_SUB = {"endpoint": "https://push.example.com/zztest-ep",
        "keys": {"p256dh": "BLc4xRzKlKORKWlbdgFaBrrPK3ydWAHo4M0gs0i1oEKgPpWC5cW8OCzVrOQRv-1npXRWtLwHtED-XdaAt_lXPIU",
                 "auth": "4vQK-SEmxKcNjg8OW9-VmA"}}


def _enable(monkeypatch):
    pub, priv = webpush.generate_keys()
    monkeypatch.setattr(settings, "vapid_public_key", pub)
    monkeypatch.setattr(settings, "vapid_private_key", priv)


def _clean():
    db.execute("DELETE FROM push_subscriptions WHERE email=%s", (_E,))
    db.execute("DELETE FROM user_profiles WHERE email=%s", (_E,))


# --------------------------------------------------------------- keys + gate
def test_generate_keys_shape_and_enabled(monkeypatch):
    pub, priv = webpush.generate_keys()
    assert len(pub) > 80 and "BEGIN" in __import__("base64").b64decode(priv).decode()
    assert webpush.enabled() is False                 # blank by default
    _enable(monkeypatch)
    assert webpush.enabled() is True


# --------------------------------------------------------------- subscriptions
def test_subscribe_validates_and_dedups():
    try:
        assert webpush.subscribe(_E, _SUB) is True
        assert webpush.subscribe(_E, _SUB) is True     # same endpoint -> upsert, no dup
        assert db.query_one("SELECT count(*) AS n FROM push_subscriptions WHERE email=%s", (_E,))["n"] == 1
        assert webpush.has_subscription(_E) is True
        assert webpush.subscribe(_E, {"endpoint": "x"}) is False       # missing keys
        webpush.unsubscribe(_SUB["endpoint"])
        assert webpush.has_subscription(_E) is False
    finally:
        _clean()


# --------------------------------------------------------------- sending + pruning
def test_send_to_email_and_prune(monkeypatch):
    _enable(monkeypatch)
    webpush.subscribe(_E, _SUB)
    try:
        calls = []
        monkeypatch.setattr(pywebpush, "webpush", lambda **kw: calls.append(kw))
        assert webpush.send_to_email(_E, "Today", "Diwali is in 5 days", "/today") == 1
        assert "Diwali" in calls[0]["data"] and calls[0]["vapid_claims"]["sub"]

        # a 410 from the push service -> the dead subscription is pruned
        def gone(**kw):
            raise pywebpush.WebPushException("gone", response=types.SimpleNamespace(status_code=410))
        monkeypatch.setattr(pywebpush, "webpush", gone)
        assert webpush.send_to_email(_E, "x", "y") == 0
        assert webpush.has_subscription(_E) is False
    finally:
        _clean()


def test_send_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    assert webpush.send_to_email(_E, "x", "y") == 0


# --------------------------------------------------------------- /push routes + /me button
def test_push_subscribe_requires_login(monkeypatch):
    monkeypatch.setattr(me_mod, "portal_email", lambda req: None)
    r = _client.post("/push/subscribe", json={"subscription": _SUB})
    assert r.status_code == 401


def test_push_subscribe_stores(monkeypatch):
    monkeypatch.setattr(me_mod, "portal_email", lambda req: _E)
    try:
        r = _client.post("/push/subscribe", json={"subscription": _SUB})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert webpush.has_subscription(_E) is True
    finally:
        _clean()


def test_me_shows_enable_button_only_when_enabled(monkeypatch):
    monkeypatch.setattr(me_mod, "portal_email", lambda req: _E)
    try:
        assert "Enable notifications" not in _client.get("/me").text   # disabled by default
        _enable(monkeypatch)
        html = _client.get("/me").text
        assert "Enable notifications" in html and "pushManager" in html
    finally:
        _clean()


def test_due_for_digest_skips_undeliverable_channels():
    try:
        accounts.upsert_profile(_E, home_city="Plano", notify_email=True, notify_web=False, digest_freq="daily")
        assert _E in [p["email"] for p in accounts.due_for_digest()]                 # email deliverable
        # SMTP off + no push subscription -> their only channel is dead, so don't churn today.assemble
        assert _E not in [p["email"] for p in accounts.due_for_digest(email_ok=False, push_ok=True)]
        assert _E not in [p["email"] for p in accounts.due_for_digest(email_ok=False, push_ok=False)]
    finally:
        _clean()


def test_service_worker_has_push_handler():
    sw = _client.get("/sw.js").text
    assert "'push'" in sw and "showNotification" in sw and "notificationclick" in sw


# --------------------------------------------------------------- digest agent push channel
def test_digest_agent_sends_push(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "smtp_host", "")                     # email off -> push-only path
    sent = []
    monkeypatch.setattr(webpush, "send_to_email",
                        lambda email, title, body, url="/today": sent.append((email, title, body)) or 1)
    try:
        accounts.upsert_profile(_E, home_city="Plano", notify_email=False, notify_web=True, digest_freq="daily")
        assert _E in [p["email"] for p in accounts.due_for_digest()]
        out = ConsumerDigestAgent().run()
        assert out["pushes"] == 1 and sent and sent[0][0] == _E
        assert _E not in [p["email"] for p in accounts.due_for_digest()]   # cadence marked
    finally:
        _clean()
