"""Anti-spam / CAN-SPAM compliance helpers for outreach.

Three things keep listing-claim outreach on the right side of spam:
  * Suppression  — anyone who opts out (or bounces) is permanently excluded.
  * One-click opt-out — a stateless HMAC-signed unsubscribe link (no per-send token table)
    plus a List-Unsubscribe header, so removal is honored instantly.
  * Throttle      — a small daily send cap so volume ramps slowly, not in a blast.

The signing reuses ``settings.secret_key`` (same secret as the magic-links). Opt-out links
deliberately do NOT expire — an unsubscribe must always work.
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode

from .. import db
from ..config import settings


# ------------------------------------------------------------------ normalization
def normalize_contact(contact: str | None) -> str:
    """Canonical key for a contact: lower-cased email, or digits-only phone."""
    c = (contact or "").strip()
    if "@" in c:
        return c.lower()
    digits = "".join(ch for ch in c if ch.isdigit())
    return digits or c.lower()


# --------------------------------------------------------------- opt-out tokens
def _sign(raw: str) -> str:
    return hmac.new(settings.secret_key.encode(), raw.encode(), sha256).hexdigest()[:32]


def opt_out_token(contact: str) -> str:
    return _sign("optout|" + normalize_contact(contact))


def verify_opt_out(contact: str, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(token, opt_out_token(contact))


def opt_out_link(contact: str) -> str:
    c = normalize_contact(contact)
    qs = urlencode({"c": c, "t": opt_out_token(c)})
    return f"{settings.public_web_url.rstrip('/')}/optout?{qs}"


# --------------------------------------------------------------- suppression list
def suppress(contact: str, reason: str = "optout", channel: str | None = None,
            note: str | None = None) -> None:
    db.execute(
        "INSERT INTO outreach_suppression (contact, channel, reason, note) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (contact) DO UPDATE "
        "SET reason = EXCLUDED.reason, channel = COALESCE(EXCLUDED.channel, outreach_suppression.channel)",
        (normalize_contact(contact), channel, reason, note))


def is_suppressed(contact: str | None) -> bool:
    if not contact:
        return False
    row = db.query_one("SELECT 1 AS x FROM outreach_suppression WHERE contact = %s",
                       (normalize_contact(contact),))
    return row is not None


def suppression_count() -> int:
    row = db.query_one("SELECT count(*) AS n FROM outreach_suppression")
    return row["n"] if row else 0


# ---------------------------------------------------------------------- throttle
def sends_today() -> int:
    """Outreach messages actually sent (not just drafted) since midnight UTC."""
    row = db.query_one(
        "SELECT count(*) AS n FROM outreach_log "
        "WHERE status = 'sent' AND created_at::date = (now() AT TIME ZONE 'utc')::date")
    return row["n"] if row else 0


def remaining_quota() -> int:
    return max(0, settings.outreach_daily_send_cap - sends_today())


# ------------------------------------------------------------------- gate summary
def gate_status() -> dict[str, Any]:
    """Why outreach can or can't auto-send right now — surfaced in admin + run output."""
    blockers = []
    if not settings.email_enabled:
        blockers.append("SMTP not configured")
    if not settings.outreach_postal_address.strip():
        blockers.append("OUTREACH_POSTAL_ADDRESS not set (required by CAN-SPAM)")
    return {
        "can_send": settings.outreach_compliant,
        "blockers": blockers,
        "daily_cap": settings.outreach_daily_send_cap,
        "sent_today": sends_today(),
        "remaining_today": remaining_quota(),
        "suppressed": suppression_count(),
    }
