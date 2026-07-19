"""Free browser push notifications (Web Push / VAPID) for the Today digest.

Gated on a VAPID keypair being configured (settings.web_push_enabled); a no-op otherwise, so the
feature is dormant until an operator opts in. Never raises to callers. Dead endpoints (the browser
unsubscribed / expired) are pruned when the push service returns 404/410.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from . import db
from .config import settings


def enabled() -> bool:
    return settings.web_push_enabled


def generate_keys() -> tuple[str, str]:
    """Generate a VAPID keypair. Returns (public_key, private_key) ready for .env:
    public = base64url uncompressed point (the browser's applicationServerKey);
    private = base64 of the PEM (single-line, kept secret). One-time setup via `cli vapid-keys`."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    priv = ec.generate_private_key(ec.SECP256R1())
    raw_pub = priv.public_key().public_bytes(serialization.Encoding.X962,
                                             serialization.PublicFormat.UncompressedPoint)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    public = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
    private = base64.b64encode(pem).decode()
    return public, private


def _private_pem() -> str:
    """The VAPID private key PEM. Stored base64-encoded in env to keep .env single-line; if it already
    looks like a PEM, use it as-is."""
    raw = settings.vapid_private_key.strip()
    if "BEGIN" in raw:
        return raw
    try:
        return base64.b64decode(raw).decode("utf-8")
    except Exception:
        return raw


# --------------------------------------------------------------------------- subscriptions
def subscribe(email: str, subscription: dict) -> bool:
    """Store a PushSubscription (endpoint + p256dh + auth) for a member. Returns False on bad input."""
    endpoint = (subscription or {}).get("endpoint")
    keys = (subscription or {}).get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not (endpoint and p256dh and auth):
        return False
    db.execute(
        "INSERT INTO push_subscriptions (email, endpoint, p256dh, auth) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (endpoint) DO UPDATE SET email=EXCLUDED.email, p256dh=EXCLUDED.p256dh, "
        "auth=EXCLUDED.auth", ((email or "").strip().lower(), endpoint, p256dh, auth))
    return True


def unsubscribe(endpoint: str) -> None:
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", ((endpoint or "").strip(),))


def has_subscription(email: str) -> bool:
    return bool(db.query_one("SELECT 1 FROM push_subscriptions WHERE lower(email)=lower(%s) LIMIT 1",
                             ((email or "").strip(),)))


# --------------------------------------------------------------------------- sending
def _send_one(sub: dict, payload: dict) -> str:
    """Send to a single subscription. Returns 'ok' | 'gone' (prune) | 'fail'. Never raises."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"],
                               "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=json.dumps(payload),
            vapid_private_key=_private_pem(),
            vapid_claims={"sub": settings.vapid_subject, "exp": int(time.time()) + 12 * 3600})
        return "ok"
    except WebPushException as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        return "gone" if code in (404, 410) else "fail"
    except Exception:
        return "fail"


def send_to_email(email: str, title: str, body: str, url: str = "/today") -> int:
    """Push a notification to all of a member's subscribed devices. Prunes dead ones. Returns #sent."""
    if not enabled():
        return 0
    payload = {"title": title, "body": body, "url": url}
    sent = 0
    for s in db.query("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE lower(email)=lower(%s)",
                      ((email or "").strip(),)):
        outcome = _send_one(s, payload)
        if outcome == "ok":
            sent += 1
        elif outcome == "gone":
            unsubscribe(s["endpoint"])
    return sent
