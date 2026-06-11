"""Stripe payments for featured listings (blueprint §8).

Flow: owner hits /upgrade?id=N -> Stripe Checkout -> they pay -> Stripe calls our
webhook -> we auto-feature the restaurant. The webhook (signature-verified) is the
source of truth for fulfillment, not the browser redirect.

Disabled by default: with no STRIPE_SECRET_KEY set, the system stays in manual mode
(you run `cli feature` after collecting payment however you like).
"""

from __future__ import annotations

from typing import Any

from .config import settings


def enabled() -> bool:
    return settings.payments_enabled


def _stripe():
    import stripe  # lazy: only needed when payments are configured

    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_checkout_session(restaurant_id: int, days: int | None = None) -> dict[str, Any]:
    """Create a Stripe Checkout session for a featured-listing purchase."""
    if not enabled():
        return {"ok": False, "error": "payments_disabled"}
    days = days or settings.featured_days
    base = settings.public_web_url.rstrip("/")
    session = _stripe().checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": settings.stripe_currency,
                "product_data": {"name": f"Featured listing — {days} days"},
                "unit_amount": settings.stripe_price_cents,
            },
            "quantity": 1,
        }],
        metadata={"restaurant_id": str(restaurant_id), "days": str(days)},
        success_url=f"{base}/upgrade/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/upgrade/cancel",
    )
    return {"ok": True, "url": session.url, "id": session.id}


def _fulfill(restaurant_id: int, days: int) -> dict[str, Any]:
    from .pipeline import ingest  # lazy to avoid import cycle at module load

    ingest.set_featured(restaurant_id, days=days)
    return {"ok": True, "featured": restaurant_id, "days": days}


def fulfill_session(session_id: str) -> dict[str, Any]:
    """Fulfill a paid Checkout session by its id (used on the success redirect).

    Lets the flow work without a webhook (handy for test mode / no HTTPS). The webhook
    remains the robust path for production; both are idempotent enough (set the flag).
    """
    if not enabled():
        return {"ok": False, "error": "payments_disabled"}
    if not session_id:
        return {"ok": False, "error": "no_session"}
    try:
        s = _stripe().checkout.Session.retrieve(session_id)
    except Exception as exc:
        return {"ok": False, "error": "lookup_failed", "detail": str(exc)}
    if s.get("payment_status") != "paid":
        return {"ok": False, "error": "not_paid"}
    meta = s.get("metadata") or {}
    rid = int(meta.get("restaurant_id", 0) or 0)
    days = int(meta.get("days", settings.featured_days) or settings.featured_days)
    return _fulfill(rid, days) if rid else {"ok": False, "error": "no_restaurant"}


def handle_webhook(payload: bytes, sig_header: str) -> dict[str, Any]:
    """Verify a Stripe webhook and fulfill featured-listing purchases (idempotent)."""
    if not enabled():
        return {"ok": False, "error": "payments_disabled"}
    try:
        event = _stripe().Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret)
    except Exception as exc:  # bad signature / malformed -> reject
        return {"ok": False, "error": "invalid_signature", "detail": str(exc)}

    if event["type"] == "checkout.session.completed":
        meta = (event["data"]["object"].get("metadata") or {})
        rid = int(meta.get("restaurant_id", 0) or 0)
        days = int(meta.get("days", settings.featured_days) or settings.featured_days)
        if rid:
            return _fulfill(rid, days)
    return {"ok": True, "ignored": event["type"]}
