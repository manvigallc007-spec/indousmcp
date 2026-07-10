"""Stripe payments: generalized (all verticals) checkout + race-safe submission-premium fulfillment.
Stripe is mocked (no test-mode key wired); DB-touching tests use ZZTEST rows + try/finally."""

import types

from starlette.testclient import TestClient

from indo_usa_mcp import db, payments, submissions
from indo_usa_mcp.web import app

_client = TestClient(app)


def _enable(monkeypatch):
    monkeypatch.setattr(payments.settings, "stripe_secret_key", "sk_test_x")


def _fake_stripe_create(capture):
    def create(**kw):
        capture["kw"] = kw
        return types.SimpleNamespace(url="https://stripe.test/checkout", id="cs_test_123")
    return types.SimpleNamespace(checkout=types.SimpleNamespace(Session=types.SimpleNamespace(create=create)))


# --------------------------------------------------------------- disabled-by-default (unchanged)
def test_payments_disabled_by_default():
    assert payments.enabled() is False
    assert payments.create_listing_upgrade_session("restaurants", 1)["error"] == "payments_disabled"
    assert payments.create_submission_premium_session(1)["error"] == "payments_disabled"
    assert payments.handle_webhook(b"{}", "sig")["error"] == "payments_disabled"
    assert payments.fulfill_session("cs_test_x")["error"] == "payments_disabled"


def test_payment_routes_registered():
    paths = {(r.path, tuple(sorted(r.methods - {"HEAD"}))) for r in app.routes}
    assert ("/upgrade", ("GET",)) in paths
    assert ("/upgrade/checkout", ("POST",)) in paths
    assert ("/stripe/webhook", ("POST",)) in paths


def test_upgrade_unavailable_when_disabled():
    assert _client.get("/upgrade?id=1").status_code == 503


def test_success_and_cancel_pages_render():
    assert _client.get("/upgrade/success").status_code == 200
    assert _client.get("/upgrade/cancel").status_code == 200


def test_webhook_rejected_when_disabled():
    r = _client.post("/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 400


# --------------------------------------------------------------- pricing / session metadata
def test_duration_options_reflects_pricing_table(monkeypatch):
    monkeypatch.setattr(payments.settings, "featured_pricing", "30:3000,90:7500")
    opts = payments.duration_options()
    assert [o["days"] for o in opts] == [30, 90]
    assert opts[1]["price_cents"] == 7500 and "$75" in opts[1]["label"]


def test_listing_upgrade_session_has_generic_metadata(monkeypatch):
    _enable(monkeypatch)
    cap = {}
    monkeypatch.setattr(payments, "_stripe", lambda: _fake_stripe_create(cap))
    out = payments.create_listing_upgrade_session("groceries", 5, days=90)
    assert out["ok"] and out["url"] == "https://stripe.test/checkout"
    assert cap["kw"]["metadata"] == {"vertical": "groceries", "id": "5", "kind": "listing_upgrade",
                                     "days": "90"}
    assert cap["kw"]["line_items"][0]["price_data"]["unit_amount"] == payments.settings.featured_pricing_table[90]


def test_submission_premium_session_metadata(monkeypatch):
    _enable(monkeypatch)
    cap = {}
    monkeypatch.setattr(payments, "_stripe", lambda: _fake_stripe_create(cap))
    payments.create_submission_premium_session(42, days=30)
    assert cap["kw"]["metadata"] == {"id": "42", "kind": "submission_premium", "days": "30"}


# --------------------------------------------------------------- fulfillment (the bug + the race)
def test_fulfill_listing_upgrade_uses_generic_set_featured(monkeypatch):
    # Regression for the confirmed bug: fulfillment must feature the RIGHT vertical's table, not
    # hardcode restaurants.
    calls = {}
    monkeypatch.setattr("indo_usa_mcp.verticals.set_featured",
                        lambda vertical, rec_id, days=None: calls.update(v=vertical, id=rec_id, days=days))
    payments._fulfill_from_metadata({"kind": "listing_upgrade", "vertical": "temples", "id": "9", "days": "30"})
    assert calls == {"v": "temples", "id": 9, "days": 30}


def test_fulfill_submission_premium_stamps_pending_row():
    res = submissions.submit("restaurants", {"name": "ZZTEST Pay Pending"}, contact_email="z@z.com")
    sid = res["id"]
    try:
        out = payments._fulfill_submission_premium(sid, 90, "cs_sess_1")
        assert out["featured_now"] is False              # still pending -> not featured yet
        row = db.query_one("SELECT paid_featured_days, stripe_session_id, status FROM submissions "
                           "WHERE id = %s", (sid,))
        assert row["paid_featured_days"] == 90 and row["stripe_session_id"] == "cs_sess_1"
        assert row["status"] == "pending"
    finally:
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))


def test_fulfill_submission_premium_applies_immediately_if_already_approved(monkeypatch):
    # THE RACE: an auto-approve agent/admin approved the submission before the webhook fulfilled ->
    # paid_featured_days was still NULL then, so fulfillment must feature the live listing NOW.
    import indo_usa_mcp.embeddings as emb
    monkeypatch.setattr(emb, "enabled", lambda: False)
    db.execute("DELETE FROM restaurants WHERE name = 'ZZTEST Pay Approved'")
    from indo_usa_mcp import verticals
    rec = verticals.create_record("restaurants", {"name": "ZZTEST Pay Approved", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7}, source="test")
    res = submissions.submit("restaurants", {"name": "ZZTEST Pay Approved"}, contact_email="z@z.com")
    sid = res["id"]
    db.execute("UPDATE submissions SET status='approved', created_record_id=%s WHERE id=%s",
               (rec["id"], sid))
    try:
        out = payments._fulfill_submission_premium(sid, 30, "cs_sess_2")
        assert out["featured_now"] is True
        row = db.query_one("SELECT is_featured, featured_until FROM restaurants WHERE id = %s", (rec["id"],))
        assert row["is_featured"] is True and row["featured_until"] is not None
    finally:
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))
        db.execute("DELETE FROM restaurants WHERE id = %s", (rec["id"],))


def test_handle_webhook_dispatches_and_stamps_session_id(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(payments.settings, "stripe_webhook_secret", "whsec")
    res = submissions.submit("restaurants", {"name": "ZZTEST Pay Webhook"}, contact_email="z@z.com")
    sid = res["id"]
    obj = types.SimpleNamespace(id="cs_live_777",
                                metadata={"kind": "submission_premium", "id": str(sid), "days": "90"})
    event = {"type": "checkout.session.completed", "data": {"object": obj}}
    monkeypatch.setattr(payments, "_stripe", lambda: types.SimpleNamespace(
        Webhook=types.SimpleNamespace(construct_event=lambda p, s, sec: event)))
    try:
        payments.handle_webhook(b"{}", "sig")
        row = db.query_one("SELECT stripe_session_id, paid_featured_days FROM submissions WHERE id=%s", (sid,))
        assert row["stripe_session_id"] == "cs_live_777" and row["paid_featured_days"] == 90
    finally:
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))


# --------------------------------------------------------------- /upgrade picker (enabled path)
def _for_sale(monkeypatch):
    monkeypatch.setattr(payments.settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(payments.settings, "featured_sales_enabled", True)


def test_upgrade_shows_duration_picker_without_days(monkeypatch):
    _for_sale(monkeypatch)
    r = _client.get("/upgrade?id=5&vertical=temples")
    assert r.status_code == 200
    assert "Feature your listing" in r.text and "30 days" in r.text and "365 days" in r.text


def test_upgrade_checkout_redirects_to_stripe(monkeypatch):
    _for_sale(monkeypatch)
    monkeypatch.setattr(payments, "create_listing_upgrade_session",
                        lambda v, i, d: {"ok": True, "url": "https://stripe.test/go"})
    r = _client.post("/upgrade/checkout", data={"id": "5", "vertical": "temples", "days": "90"},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "https://stripe.test/go"


def test_upgrade_checkout_rejects_invalid_days(monkeypatch):
    _for_sale(monkeypatch)
    r = _client.post("/upgrade/checkout", data={"id": "5", "vertical": "temples", "days": "45"})
    assert r.status_code == 400
