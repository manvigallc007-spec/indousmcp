"""Outreach Agent + claiming flow (blueprint §7).

Pipeline:
  find_unclaimed() -> create_claim() (token + link) -> draft_message() -> log as 'drafted'

Sending is intentionally NOT automated here: actual channel delivery (email/WhatsApp/
Instagram) needs provider integrations, and high-value targets are routed to a human.
Owners later call verify_claim() (via the future claim web page) to take ownership.

Guardrails honoured:
  * No spam   — per-restaurant cooldown + one open claim at a time.
  * No impersonation — messages clearly come from the platform, with opt-out.
  * Human role — chains / featured / high-value targets flagged requires_human.
"""

from __future__ import annotations

import secrets
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

from .. import db
from ..config import settings
from . import clean


# ----------------------------------------------------------------- target finding
def find_unclaimed(limit: int = 20, min_confidence: float = 0.5) -> list[dict[str, Any]]:
    """Active, unclaimed restaurants with a usable contact, outside the cooldown."""
    rows = db.query(
        """
        SELECT r.* FROM restaurants r
        WHERE r.deleted_at IS NULL
          AND r.is_active
          AND NOT r.is_claimed
          AND r.confidence_score >= %s
          AND (r.phone IS NOT NULL OR r.website IS NOT NULL)
          -- no currently-open claim
          AND NOT EXISTS (
              SELECT 1 FROM claims c
              WHERE c.restaurant_id = r.id
                AND c.status IN ('pending','sent','verified')
          )
          -- outside the anti-spam cooldown window
          AND NOT EXISTS (
              SELECT 1 FROM outreach_log o
              WHERE o.restaurant_id = r.id
                AND o.created_at > now() - (%s || ' days')::interval
          )
        ORDER BY r.confidence_score DESC
        LIMIT %s
        """,
        (min_confidence, settings.outreach_cooldown_days, limit),
    )
    for r in rows:
        r["_channel"] = _pick_channel(r)
        r["_requires_human"] = _requires_human(r)
    return rows


def _pick_channel(restaurant: dict) -> str | None:
    """Choose the best available outreach channel from known contact fields.

    Email is preferred when present (it's the only channel we can auto-deliver).
    """
    if restaurant.get("email"):
        return "email"
    if restaurant.get("phone"):
        return "whatsapp"
    if restaurant.get("website"):
        return "form"
    return None


def _requires_human(restaurant: dict) -> bool:
    """Chains, featured, and high-confidence/high-value targets go to a human."""
    if restaurant.get("is_featured"):
        return True
    norm = clean.normalize_name(restaurant.get("name") or "")
    twin = db.query_one(
        "SELECT count(*) AS n FROM restaurants WHERE deleted_at IS NULL "
        "AND lower(regexp_replace(name, '[^a-zA-Z0-9]+', ' ', 'g')) LIKE %s",
        (f"%{norm}%",),
    )
    return bool(twin and twin["n"] >= 3)  # appears 3+ times -> likely a chain


# ------------------------------------------------------------------------- claiming
def create_claim(restaurant_id: int, channel: str, contact_target: str | None = None) -> dict:
    """Create a pending claim with a single-use token; returns claim row + link."""
    token = secrets.token_urlsafe(24)
    row = db.query_one(
        """
        INSERT INTO claims (restaurant_id, token, channel, contact_target, status)
        VALUES (%s, %s, %s, %s, 'pending')
        RETURNING id, restaurant_id, token, channel, status, expires_at
        """,
        (restaurant_id, token, channel, contact_target),
    )
    row["claim_link"] = claim_link(restaurant_id, token)
    return row


def claim_link(restaurant_id: int, token: str) -> str:
    qs = urlencode({"type": "restaurant", "id": restaurant_id, "token": token})
    return f"{settings.claim_base_url}?{qs}"


def claim_status(token: str) -> dict | None:
    """Look up a claim by token, joined to its restaurant (for the claim web page)."""
    return db.query_one(
        "SELECT c.id, c.token, c.status, c.expires_at, "
        "r.id AS restaurant_id, r.name AS restaurant_name, r.city, r.state "
        "FROM claims c JOIN restaurants r ON r.id = c.restaurant_id "
        "WHERE c.token = %s",
        (token,),
    )


def verify_claim(token: str, owner_email: str | None = None, owner_phone: str | None = None) -> dict:
    """Owner-facing: verify a token and grant ownership of the restaurant.

    Returns {"ok": bool, ...}. Marks the claim claimed and flips restaurants.is_claimed.
    """
    claim = db.query_one("SELECT * FROM claims WHERE token = %s", (token,))
    if claim is None:
        return {"ok": False, "error": "invalid_token"}
    if claim["status"] in ("claimed", "revoked"):
        return {"ok": False, "error": f"claim_{claim['status']}"}
    expired = db.query_one("SELECT now() > %s AS expired", (claim["expires_at"],))
    if expired and expired["expired"]:
        db.execute("UPDATE claims SET status='expired' WHERE id=%s", (claim["id"],))
        return {"ok": False, "error": "expired"}

    db.execute(
        "UPDATE claims SET status='claimed', owner_email=%s, owner_phone=%s, "
        "verified_at=now(), claimed_at=now() WHERE id=%s",
        (owner_email, owner_phone, claim["id"]),
    )
    db.execute(
        "UPDATE restaurants SET is_claimed=true, updated_at=now() WHERE id=%s",
        (claim["restaurant_id"],),
    )
    return {"ok": True, "restaurant_id": claim["restaurant_id"], "claim_id": claim["id"]}


# ----------------------------------------------------------------------- messaging
def draft_message(restaurant: dict, claim_link_url: str, channel: str) -> str:
    """A personalized, honest outreach message. No impersonation, includes opt-out."""
    name = restaurant.get("name", "your restaurant")
    city = restaurant.get("city")
    where = f" in {city}" if city else ""
    platform = settings.platform_name
    greeting = "Hello" if channel in ("email", "form") else "Hi"

    return (
        f"{greeting} {name} team,\n\n"
        f"We list {name}{where} on {platform}, a directory that helps people "
        f"(and AI assistants) discover Indian restaurants across the USA. Your "
        f"restaurant is already listed from public data — we'd love for you to "
        f"claim it for free to keep details (hours, menu, photos) accurate.\n\n"
        f"Claim your listing here:\n{claim_link_url}\n\n"
        f"There's no cost to claim. If you'd prefer not to be listed or contacted, "
        f"just reply and we'll remove you.\n\n"
        f"— The {platform} team ({settings.outreach_contact_email})"
    )


def send_email(to_address: str, subject: str, body: str) -> bool:
    """Send one email via SMTP. Returns False (no-op) when SMTP isn't configured.

    Designed for free providers (e.g. Gmail SMTP + an app password). No cost.
    """
    if not settings.email_enabled:
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.outreach_contact_email
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    return True


def record_outreach(
    restaurant_id: int,
    claim_id: int | None,
    channel: str,
    contact_target: str | None,
    message: str,
    requires_human: bool,
    status: str = "drafted",
) -> int:
    row = db.query_one(
        """
        INSERT INTO outreach_log
            (restaurant_id, claim_id, channel, contact_target, message, status, requires_human)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (restaurant_id, claim_id, channel, contact_target, message, status, requires_human),
    )
    if claim_id is not None:
        db.execute("UPDATE claims SET status='sent' WHERE id=%s", (claim_id,))
    return row["id"]


def _target_for(restaurant: dict, channel: str) -> str | None:
    return {
        "email": restaurant.get("email"),
        "whatsapp": restaurant.get("phone"),
        "form": restaurant.get("website"),
    }.get(channel)


# ---------------------------------------------------------------- orchestration
def run_outreach(limit: int = 20, min_confidence: float = 0.5) -> dict[str, Any]:
    """Find unclaimed restaurants, create claims, draft messages, log them.

    Drafts for high-value/chain targets are flagged `requires_human` and left for a
    person to review/send; the rest are ready for an automated channel to deliver.
    """
    items, flagged, sent_count = [], 0, 0
    subject = f"Claim your free listing on {settings.platform_name}"
    for r in find_unclaimed(limit=limit, min_confidence=min_confidence):
        channel = r["_channel"]
        if channel is None:
            continue
        target = _target_for(r, channel)
        claim = create_claim(r["id"], channel, target)
        message = draft_message(r, claim["claim_link"], channel)
        requires_human = r["_requires_human"]
        flagged += int(requires_human)

        # Auto-deliver only via email, only to non-human targets, only if SMTP is set up.
        sent = False
        if channel == "email" and target and not requires_human and settings.email_enabled:
            try:
                sent = send_email(target, subject, message)
            except Exception:  # delivery failure shouldn't abort the batch
                sent = False
        sent_count += int(sent)

        outreach_id = record_outreach(
            r["id"], claim["id"], channel, target, message, requires_human,
            status="sent" if sent else "drafted",
        )
        items.append(
            {
                "outreach_id": outreach_id,
                "restaurant_id": r["id"],
                "name": r["name"],
                "channel": channel,
                "contact_target": target,
                "requires_human": requires_human,
                "sent": sent,
                "claim_link": claim["claim_link"],
                "message": message,
            }
        )
    return {
        "drafted": len(items),
        "sent": sent_count,
        "email_enabled": settings.email_enabled,
        "requires_human": flagged,
        "items": items,
    }
