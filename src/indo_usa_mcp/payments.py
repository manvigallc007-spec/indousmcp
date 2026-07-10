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


def _price_cents_for(days: int) -> int:
    """Price for a duration: the pricing table, else pro-rated from the base (defensive fallback)."""
    table = settings.featured_pricing_table
    if days in table:
        return table[days]
    return max(1, round(settings.stripe_price_cents * days / max(settings.featured_days, 1)))


def duration_options() -> list[dict[str, Any]]:
    """The purchasable durations — single source of truth for the onboarding + /upgrade pickers."""
    return [{"days": d, "price_cents": c, "label": f"{d} days — ${c / 100:.0f}"}
            for d, c in sorted(settings.featured_pricing_table.items())]


def _create_session(kind: str, metadata: dict, days: int) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "payments_disabled"}
    base = settings.public_web_url.rstrip("/")
    session = _stripe().checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": settings.stripe_currency,
                "product_data": {"name": f"Featured listing — {days} days"},
                "unit_amount": _price_cents_for(days),
            },
            "quantity": 1,
        }],
        metadata={**metadata, "kind": kind, "days": str(days)},
        success_url=f"{base}/upgrade/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/upgrade/cancel",
    )
    return {"ok": True, "url": session.url, "id": session.id}


def create_listing_upgrade_session(vertical: str, rec_id: int, days: int | None = None) -> dict[str, Any]:
    """Checkout for an ALREADY-LIVE listing's owner buying featured placement (any vertical)."""
    return _create_session("listing_upgrade",
                           {"vertical": vertical, "id": str(rec_id)}, days or settings.featured_days)


def create_submission_premium_session(sub_id: int, days: int | None = None) -> dict[str, Any]:
    """Checkout for a NOT-YET-LIVE owner submission — featured is applied only once approved."""
    return _create_session("submission_premium", {"id": str(sub_id)}, days or settings.featured_days)


def _attr(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a Stripe object (attribute access; v15 dropped dict .get()) OR from a plain
    dict (we build one to inject the session id before dispatch)."""
    val = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    return default if val is None else val


def _fulfill_listing_upgrade(vertical: str, rec_id: int, days: int) -> dict[str, Any]:
    from . import verticals  # lazy to avoid import cycle at module load
    verticals.set_featured(vertical, rec_id, days=days)   # generic — fixes the restaurant-only bug
    return {"ok": True, "featured": rec_id, "vertical": vertical, "days": days}


def _fulfill_submission_premium(sub_id: int, days: int, session_id: str | None) -> dict[str, Any]:
    """Stamp the paid duration on a submission. If it was ALREADY approved (a fast auto-approve agent
    or admin beat the webhook), apply the feature immediately — otherwise submissions.approve() will,
    when it runs. Either way the approval decision itself never sees payment (it happens first)."""
    from . import db, verticals
    sub = db.query_one("SELECT id, status, vertical, created_record_id FROM submissions WHERE id = %s",
                       (sub_id,))
    if not sub:
        return {"ok": False, "error": "no_submission"}
    db.execute("UPDATE submissions SET paid_featured_days = %s, stripe_session_id = %s WHERE id = %s",
               (days, session_id, sub_id))
    if sub["status"] == "approved" and sub.get("created_record_id"):
        verticals.set_featured(sub["vertical"], sub["created_record_id"], days=days)
        return {"ok": True, "featured_now": True, "days": days}
    return {"ok": True, "featured_now": False, "days": days}


def _fulfill_from_metadata(metadata: Any) -> dict[str, Any]:
    meta = metadata or {}
    kind = _attr(meta, "kind", "listing_upgrade")
    days = int(_attr(meta, "days", settings.featured_days) or settings.featured_days)
    session_id = _attr(meta, "session_id", None)
    if kind == "submission_premium":
        sub_id = int(_attr(meta, "id", 0) or 0)
        return _fulfill_submission_premium(sub_id, days, session_id) if sub_id \
            else {"ok": False, "error": "no_submission"}
    # listing_upgrade (default; also back-compat with any old restaurant_id-shaped metadata)
    vertical = _attr(meta, "vertical", "restaurants")
    rec_id = int(_attr(meta, "id", 0) or _attr(meta, "restaurant_id", 0) or 0)
    return _fulfill_listing_upgrade(vertical, rec_id, days) if rec_id \
        else {"ok": False, "error": "no_listing"}


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
    if _attr(s, "payment_status") != "paid":
        return {"ok": False, "error": "not_paid"}
    meta = dict(_attr(s, "metadata", {}) or {})          # Session metadata omits its own id
    meta["session_id"] = _attr(s, "id")
    return _fulfill_from_metadata(meta)


def recent_payments(limit: int = 20) -> list[dict[str, Any]]:
    """Recent Stripe Checkout sessions (read-only, for the admin payments view)."""
    if not enabled():
        return []
    try:
        listing = _stripe().checkout.Session.list(limit=limit)
    except Exception:
        return []
    out = []
    for s in getattr(listing, "data", []):
        out.append({
            "id": _attr(s, "id"),
            "amount": _attr(s, "amount_total", 0),
            "currency": _attr(s, "currency", ""),
            "status": _attr(s, "payment_status", ""),
            "created": _attr(s, "created", 0),
        })
    return out


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
        obj = event["data"]["object"]
        meta = dict(_attr(obj, "metadata", {}) or {})
        meta["session_id"] = _attr(obj, "id")
        return _fulfill_from_metadata(meta)
    return {"ok": True, "ignored": event["type"]}
