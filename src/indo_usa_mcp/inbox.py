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


# Topics that must NEVER be auto-answered — always kept for human approval, regardless of the LLM.
_SENSITIVE = (
    "lawyer", "attorney", "legal", "lawsuit", "sue ", "sued", "court", "refund", "charge",
    "billing", "payment", "invoice", "complaint", "scam", "fraud", "privacy", "gdpr", "ccpa",
    "delete my", "remove my", "take down", "press", "media", "journalist", "reporter",
    "partner", "partnership", "invest", "sponsor", "acquire", "acquisition", "urgent",
    "emergency", "police", "subpoena", "defam", "visa", "immigration", "tax", "medical",
)


def is_sensitive(m: dict) -> bool:
    t = f"{m.get('subject') or ''} {m.get('body') or ''}".lower()
    return any(tok in t for tok in _SENSITIVE)


def draft_and_classify(m: dict) -> dict:
    """Draft a reply AND judge whether it's routine + safe to send automatically. Sensitive topics
    are never routine (kept for a human). Returns {'reply': str|None, 'routine': bool}."""
    if is_sensitive(m):
        return {"reply": compose_draft(m), "routine": False}
    from . import assistant
    from .config import settings
    if not assistant.llm_active():
        return {"reply": None, "routine": False}
    plat = settings.platform_name
    system = (
        f"You are the support assistant for {plat}, a free directory & AI guide for Indians from "
        "India in the USA. Two tasks. (1) CLASSIFY the message: output exactly 'ROUTINE' on the "
        "first line if it is a simple, low-risk question you can fully and safely answer on your own "
        "(general info: what the site is, is it free, hours/location, how to add/claim/fix a listing, "
        "where data comes from, a thank-you), or 'REVIEW' if it needs a human (complaints, refunds/"
        "payments, legal/tax/immigration/medical advice, removal/privacy/legal requests, "
        "partnerships/press, or anything sensitive or that you're unsure about). When in doubt, "
        "say REVIEW. (2) Then a blank line, then a warm, concise reply (<= 120 words). To add or fix "
        "a business, point them to /portal/register or /submit. Don't give legal/tax/medical advice. "
        f"Sign off '— The {plat} team'.")
    user = (f"From: {m.get('name') or 'A visitor'}\nSubject: {m.get('subject') or '(none)'}\n\n"
            f"{m.get('body') or ''}")
    txt = assistant.complete_text(system, user)
    if not txt:
        return {"reply": None, "routine": False}
    first, _, rest = txt.partition("\n")
    routine = first.strip().upper().startswith("ROUTINE")
    reply = (rest.strip() or txt.strip())
    return {"reply": reply, "routine": routine}


def mark_auto_replied(mid: int, reply: str) -> None:
    db.execute("UPDATE contact_messages SET draft_reply = %s, status = 'auto_replied', "
               "reply_sent_at = now() WHERE id = %s", [reply, mid])


def recent_replies(limit: int = 12) -> list[dict]:
    """Recently answered messages (human + auto) — your reference copy of what went out."""
    try:
        return db.query("SELECT * FROM contact_messages WHERE status IN ('replied','auto_replied') "
                        "ORDER BY reply_sent_at DESC NULLS LAST LIMIT %s", [limit])
    except Exception:
        return []


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
