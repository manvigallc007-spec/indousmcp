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
from . import clean, compliance


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
    out = []
    for r in rows:
        r["_channel"] = _pick_channel(r)
        r["_requires_human"] = _requires_human(r)
        target = _target_for(r, r["_channel"]) if r["_channel"] else None
        if target and compliance.is_suppressed(target):
            continue  # respect opt-outs / bounces
        out.append(r)
    return out


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
def create_claim(record_id: int, channel: str, contact_target: str | None = None,
                 vertical: str = "restaurants") -> dict:
    """Create a pending claim with a single-use token; returns claim row + link. Works for any vertical
    (restaurants also set restaurant_id for back-compat with the legacy FK/agent)."""
    token = secrets.token_urlsafe(24)
    rest_id = record_id if vertical == "restaurants" else None
    row = db.query_one(
        "INSERT INTO claims (restaurant_id, vertical, record_id, token, channel, contact_target, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'pending') "
        "RETURNING id, vertical, record_id, token, channel, status, expires_at",
        (rest_id, vertical, record_id, token, channel, contact_target),
    )
    row["claim_link"] = claim_link(record_id, token, vertical)
    return row


def claim_link(record_id: int, token: str, vertical: str = "restaurants") -> str:
    qs = urlencode({"type": vertical, "id": record_id, "token": token})
    return f"{settings.claim_base_url}?{qs}"


def whatsapp_link(phone: str | None, message: str) -> str | None:
    """A free click-to-send wa.me link with the message pre-filled (no paid API).

    Tapping it opens WhatsApp to the restaurant's number with the text ready to send.
    """
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None
    return f"https://wa.me/{digits}?{urlencode({'text': message})}"


def owner_listing(token: str) -> dict | None:
    """Full listing row for a *claimed* token — the owner's listing to manage (any vertical)."""
    from .. import verticals
    c = db.query_one("SELECT vertical, record_id FROM claims WHERE token = %s AND status = 'claimed'",
                     (token,))
    if not c or c["vertical"] not in verticals.VERTICALS:
        return None
    return db.query_one(
        f"SELECT * FROM {verticals._table(c['vertical'])} WHERE id = %s AND deleted_at IS NULL",
        (c["record_id"],))


def claim_status(token: str) -> dict | None:
    """Look up a claim by token, joined to its listing in the right vertical (for the claim page).
    Keeps `restaurant_id`/`restaurant_name` aliases so existing callers keep working."""
    from .. import verticals
    c = db.query_one("SELECT id, token, status, expires_at, vertical, record_id FROM claims "
                     "WHERE token = %s", (token,))
    if not c or c["vertical"] not in verticals.VERTICALS:
        return None
    r = db.query_one(f"SELECT id, name, city, state FROM {verticals._table(c['vertical'])} "
                     f"WHERE id = %s", (c["record_id"],))
    if not r:
        return None
    return {**c, "restaurant_id": c["record_id"], "restaurant_name": r["name"],
            "listing_name": r["name"], "city": r["city"], "state": r["state"]}


def verify_claim(token: str, owner_email: str | None = None, owner_phone: str | None = None) -> dict:
    """Owner-facing: verify a token and grant ownership of the listing (any vertical).

    Returns {"ok": bool, vertical, record_id, ...}. Marks the claim claimed and flips is_claimed on
    the listing's own table.
    """
    from .. import verticals
    claim = db.query_one("SELECT * FROM claims WHERE token = %s", (token,))
    if claim is None:
        return {"ok": False, "error": "invalid_token"}
    if claim["status"] in ("claimed", "revoked"):
        return {"ok": False, "error": f"claim_{claim['status']}"}
    expired = db.query_one("SELECT now() > %s AS expired", (claim["expires_at"],))
    if expired and expired["expired"]:
        db.execute("UPDATE claims SET status='expired' WHERE id=%s", (claim["id"],))
        return {"ok": False, "error": "expired"}
    vertical, record_id = claim["vertical"], claim["record_id"]
    if vertical not in verticals.VERTICALS:
        return {"ok": False, "error": "bad_vertical"}

    db.execute(
        "UPDATE claims SET status='claimed', owner_email=%s, owner_phone=%s, "
        "verified_at=now(), claimed_at=now() WHERE id=%s",
        ((owner_email or "").strip().lower() or None, owner_phone, claim["id"]),
    )
    verticals.set_claimed(vertical, record_id, True)
    return {"ok": True, "vertical": vertical, "record_id": record_id,
            "restaurant_id": record_id, "claim_id": claim["id"]}


# ----------------------------------------------------------------------- messaging
def draft_message(restaurant: dict, claim_link_url: str, channel: str,
                  opt_out_url: str | None = None) -> str:
    """A personalized, honest outreach message — CAN-SPAM shaped.

    No impersonation; a clear unsubscribe (one-click link when available, else reply); and
    the platform's physical postal address appended when configured (required for email).
    """
    name = restaurant.get("name", "your restaurant")
    city = restaurant.get("city")
    where = f" in {city}" if city else ""
    platform = settings.platform_name
    greeting = "Hello" if channel in ("email", "form") else "Hi"

    if opt_out_url:
        optout = f"Don't want these emails? Unsubscribe instantly: {opt_out_url}"
    else:
        optout = "If you'd prefer not to be listed or contacted, just reply and we'll remove you."
    postal = settings.outreach_postal_address.strip()
    postal_line = f"\n{platform} · {postal}" if postal else ""

    return (
        f"{greeting} {name} team,\n\n"
        f"We list {name}{where} on {platform}, a directory that helps people "
        f"(and AI assistants) discover Indian restaurants across the USA. Your "
        f"restaurant is already listed from public data — we'd love for you to "
        f"claim it for free to keep details (hours, menu, photos) accurate.\n\n"
        f"Claim your listing here:\n{claim_link_url}\n\n"
        f"There's no cost to claim. {optout}\n\n"
        f"— The {platform} team ({settings.outreach_contact_email})"
        f"{postal_line}"
    )


def send_email(to_address: str, subject: str, body: str,
               list_unsubscribe: str | None = None) -> bool:
    """Send one email via SMTP. Returns False (no-op) when SMTP isn't configured.

    Designed for free providers (e.g. Gmail SMTP + an app password). No cost. When a
    `list_unsubscribe` URL is given, sets RFC 8058 one-click unsubscribe headers so Gmail/
    Outlook show a native "Unsubscribe" button (better deliverability + compliance).
    """
    if not settings.email_enabled:
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.outreach_contact_email
    msg["To"] = to_address
    msg["Subject"] = subject
    if list_unsubscribe:
        msg["List-Unsubscribe"] = f"<{list_unsubscribe}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
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
            (restaurant_id, claim_id, channel, contact_target, message, status, requires_human, sent_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 'sent' THEN now() ELSE NULL END)
        RETURNING id
        """,
        (restaurant_id, claim_id, channel, contact_target, message, status, requires_human, status),
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
    # Compliance gate + slow-ramp daily quota, evaluated once per run.
    can_send = settings.outreach_compliant
    quota = compliance.remaining_quota() if can_send else 0
    for r in find_unclaimed(limit=limit, min_confidence=min_confidence):
        channel = r["_channel"]
        if channel is None:
            continue
        target = _target_for(r, channel)
        opt_out_url = compliance.opt_out_link(target) if (target and channel == "email") else None
        claim = create_claim(r["id"], channel, target)
        message = draft_message(r, claim["claim_link"], channel, opt_out_url)
        requires_human = r["_requires_human"]
        flagged += int(requires_human)

        # Auto-deliver only via email, to non-human targets, only when compliant and under
        # the daily cap. Otherwise the message is drafted and left for human review.
        sent = False
        if (channel == "email" and target and not requires_human and can_send and quota > 0):
            try:
                sent = send_email(target, subject, message, list_unsubscribe=opt_out_url)
            except Exception:  # delivery failure shouldn't abort the batch
                sent = False
            if sent:
                quota -= 1
        sent_count += int(sent)

        outreach_id = record_outreach(
            r["id"], claim["id"], channel, target, message, requires_human,
            status="sent" if sent else "drafted",
        )
        item = {
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
        # Free one-tap send link for WhatsApp targets (no paid API).
        if channel == "whatsapp":
            item["whatsapp_link"] = whatsapp_link(target, message)
        items.append(item)
    return {
        "drafted": len(items),
        "sent": sent_count,
        "email_enabled": settings.email_enabled,
        "compliant": can_send,
        "gate": compliance.gate_status(),
        "requires_human": flagged,
        "items": items,
    }
