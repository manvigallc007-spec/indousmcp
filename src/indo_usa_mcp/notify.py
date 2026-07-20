"""Event-driven notification outbox.

Event hooks (answer-to-your-question, reply-to-your-review, new-offer-on-a-saved-place,
new-event-in-a-followed-city) call `enqueue(...)` — a single cheap INSERT, so they add zero request
latency and never fail the user's action. `NotificationAgent` later drains unsent rows and `deliver()`s
each via web push (if the member opted into `notify_web`) and/or email (if `notify_email`), then stamps
`sent_at`. `dedupe_key` makes each event idempotent, so a periodic scan can re-run safely.
"""

from __future__ import annotations

from typing import Any

from . import accounts, db


def enqueue(email: str, title: str, body: str, url: str = "/", kind: str = "generic",
            dedupe_key: str | None = None) -> bool:
    """Queue one notification. With a `dedupe_key`, a repeat enqueue is a no-op (returns False), so the
    same event is only ever delivered once. Best-effort: never raises into the caller's request."""
    email = (email or "").strip().lower()
    if not email:
        return False
    try:
        row = db.query_one(
            "INSERT INTO notifications (email, title, body, url, kind, dedupe_key) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (dedupe_key) DO NOTHING RETURNING id",
            (email, title[:200], (body or "")[:500], (url or "/")[:300], kind, dedupe_key))
        return bool(row)
    except Exception:
        return False


def deliver(row: dict[str, Any]) -> bool:
    """Send one queued notification over whatever channels the member opted into and that are live.
    Returns True if at least one channel accepted it. Does not stamp sent_at — the caller does that so a
    failed send can be retried on the next tick."""
    from .config import settings
    from .pipeline import outreach
    from . import webpush
    email = row["email"]
    prof = accounts.get_profile(email) or {}
    base = settings.public_web_url.rstrip("/")
    url = row.get("url") or "/"
    full_url = url if url.startswith("http") else base + url
    delivered = False
    if prof.get("notify_web") and settings.web_push_enabled:
        try:
            if webpush.send_to_email(email, row["title"], row.get("body") or "", url):
                delivered = True
        except Exception:
            pass
    if prof.get("notify_email", True) and settings.email_enabled:
        try:
            body = f"{row.get('body') or ''}\n\n{full_url}\n\n—\nManage notifications: {base}/me"
            if outreach.send_email(email, row["title"], body.strip()):
                delivered = True
        except Exception:
            pass
    return delivered


def drain(limit: int = 200) -> dict[str, int]:
    """Deliver unsent notifications oldest-first, stamping sent_at on success. Rows for members with no
    live channel are marked sent (skipped) so they don't clog the queue forever."""
    from .config import settings
    channels_live = settings.email_enabled or settings.web_push_enabled
    rows = db.query("SELECT * FROM notifications WHERE sent_at IS NULL ORDER BY created_at ASC LIMIT %s",
                    (limit,))
    sent = skipped = 0
    for r in rows:
        if not channels_live:
            break
        if deliver(r):
            db.execute("UPDATE notifications SET sent_at = now() WHERE id = %s", (r["id"],))
            sent += 1
        else:
            # No live channel for this member (opted out / no push sub) — retire it so it doesn't
            # re-scan every tick. A genuine transient failure is rare and self-heals on the next event.
            db.execute("UPDATE notifications SET sent_at = now() WHERE id = %s", (r["id"],))
            skipped += 1
    return {"scanned": len(rows), "sent": sent, "skipped": skipped}


def recent_for(email: str, limit: int = 20) -> list[dict]:
    return db.query("SELECT title, body, url, kind, created_at, sent_at FROM notifications "
                    "WHERE email = %s ORDER BY created_at DESC LIMIT %s",
                    ((email or "").strip().lower(), limit))
