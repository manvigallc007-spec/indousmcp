"""Tests for the Stripe payments module + web routes (no real Stripe calls / no DB)."""

from starlette.testclient import TestClient

from indo_usa_mcp import payments
from indo_usa_mcp.web import app


def test_payments_disabled_by_default():
    # No STRIPE_SECRET_KEY configured -> manual mode.
    assert payments.enabled() is False
    assert payments.create_checkout_session(1)["error"] == "payments_disabled"
    assert payments.handle_webhook(b"{}", "sig")["error"] == "payments_disabled"


def test_payment_routes_registered():
    paths = {(r.path, tuple(sorted(r.methods - {"HEAD"}))) for r in app.routes}
    assert ("/upgrade", ("GET",)) in paths
    assert ("/upgrade/success", ("GET",)) in paths
    assert ("/stripe/webhook", ("POST",)) in paths


def test_upgrade_unavailable_when_disabled():
    client = TestClient(app)
    r = client.get("/upgrade?id=1")
    assert r.status_code == 503  # payments not enabled


def test_success_and_cancel_pages_render():
    client = TestClient(app)
    assert client.get("/upgrade/success").status_code == 200
    assert client.get("/upgrade/cancel").status_code == 200


def test_webhook_rejected_when_disabled():
    client = TestClient(app)
    r = client.post("/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 400
