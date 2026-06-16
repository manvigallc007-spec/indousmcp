"""Contact-form inbox.

The website shows NO public email address — the only inbound channel is the /contact form, which
lands here. An agent (ContactReplyAgent) drafts a reply per message using the free LLM; an admin
reviews/edits and explicitly approves before anything is sent. No PII beyond what the sender typed.
"""

from __future__ import annotations

from typing import Any

from . import db


def create_message(name: str, email: str, subject: str, body: str, ip: str | None = None) -> dict:
    row = db.query_one(
        "INSERT INTO contact_messages (name, email, subject, body, ip) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        [(name or "").strip()[:120], (email or "").strip().lower()[:200],
         (subject or "").strip()[:200], (body or "").strip()[:5000], ip])
    return {"ok": True, "id": row["id"] if row else None}


def list_messages(status: str | None = None, limit: int = 100) -> list[dict]:
    try:
        if status:
            return db.query("SELECT * FROM contact_messages WHERE status = %s "
                            "ORDER BY created_at DESC LIMIT %s", [status, limit])
        return db.query("SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT %s", [limit])
    except Exception:
        return []


def get_message(mid: int) -> dict | None:
    try:
        return db.query_one("SELECT * FROM contact_messages WHERE id = %s", [mid])
    except Exception:
        return None


def set_draft(mid: int, draft: str) -> None:
    db.execute("UPDATE contact_messages SET draft_reply = %s, "
               "status = CASE WHEN status = 'new' THEN 'drafted' ELSE status END WHERE id = %s",
               [draft, mid])


def mark_replied(mid: int) -> None:
    db.execute("UPDATE contact_messages SET status = 'replied', reply_sent_at = now() WHERE id = %s",
               [mid])


def set_status(mid: int, status: str) -> None:
    db.execute("UPDATE contact_messages SET status = %s WHERE id = %s", [status, mid])


def pending_for_draft(limit: int = 20) -> list[dict]:
    """New messages without an AI draft yet (the agent's work queue)."""
    return db.query("SELECT * FROM contact_messages WHERE status = 'new' "
                    "ORDER BY created_at LIMIT %s", [limit])


def compose_draft(m: dict) -> str | None:
    """Draft a reply to a contact message with the free LLM. None if the LLM is off (admin writes
    it manually). The draft is NEVER sent automatically — a human approves it in Admin -> Messages."""
    from . import assistant
    from .config import settings
    plat = settings.platform_name
    system = (f"You are the friendly support assistant for {plat}, a free directory and AI guide for "
              "Indians from India in the USA. Draft a warm, concise reply (<= 120 words) to the "
              "visitor's message below. Be specific and helpful. To add or fix a business, point "
              "them to register at /portal/register or use /submit. For data we don't have yet, "
              "thank them and say we'll look into adding it. Do NOT give legal, tax, or medical "
              f"advice — suggest a qualified professional. Sign off as '— The {plat} team'. Write "
              "ONLY the reply body, ready to send.")
    user = (f"From: {m.get('name') or 'A visitor'}\nSubject: {m.get('subject') or '(none)'}\n\n"
            f"{m.get('body') or ''}")
    txt = assistant.complete_text(system, user)
    return txt.strip() if txt else None


def counts() -> dict[str, int]:
    try:
        rows = db.query("SELECT status, count(*) AS n FROM contact_messages GROUP BY status")
        return {r["status"]: int(r["n"]) for r in rows}
    except Exception:
        return {}
