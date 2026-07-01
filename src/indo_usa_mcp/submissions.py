"""Owner self-submitted listings + moderation queue.

Owners add their business via the public /submit form; it lands here as 'pending'. An admin
approves (which creates the live canonical record via verticals.create_record) or rejects.
Events are excluded — they're agent-managed. This is the zero-noise growth path: the people
who know a business best add it, with a human approving before it goes live.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from . import db, verticals

# Verticals an owner may submit (everything except agent-managed events).
SUBMITTABLE = [k for k in verticals.VERTICALS if k != "events"]


def submit(vertical: str, payload: dict, contact_email: str | None = None,
           note: str | None = None) -> dict[str, Any]:
    if vertical not in SUBMITTABLE:
        return {"ok": False, "error": "bad_vertical"}
    if not (payload.get("name") or "").strip():
        return {"ok": False, "error": "name_required"}
    row = db.query_one(
        "INSERT INTO submissions (vertical, payload, contact_email, note) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (vertical, Jsonb(payload), (contact_email or "").strip() or None,
         (note or "").strip() or None))
    return {"ok": True, "id": row["id"]}


def list_pending(limit: int = 100) -> list[dict]:
    return db.query(
        "SELECT id, vertical, payload, contact_email, note, created_at FROM submissions "
        "WHERE status = 'pending' ORDER BY created_at LIMIT %s", (limit,))


def list_for_owner(email: str, limit: int = 50) -> list[dict]:
    """A signed-in owner's own submissions (any status), newest first."""
    return db.query(
        "SELECT id, vertical, payload, status, created_at, created_record_id FROM submissions "
        "WHERE lower(contact_email) = lower(%s) ORDER BY created_at DESC LIMIT %s", (email, limit))


def delete_for_owner(sub_id: int, email: str) -> dict:
    """Let an owner delete their OWN still-pending submission (approved ones are live listings,
    managed via the portal/claim instead)."""
    row = db.query_one(
        "SELECT id FROM submissions WHERE id = %s AND lower(contact_email) = lower(%s) "
        "AND status = 'pending'", (sub_id, email))
    if not row:
        return {"ok": False}
    db.execute("DELETE FROM submissions WHERE id = %s", (sub_id,))
    return {"ok": True}


def summary() -> dict[str, int]:
    rows = db.query("SELECT status, count(*) AS n FROM submissions GROUP BY status")
    out = {r["status"]: r["n"] for r in rows}
    return {"pending": out.get("pending", 0), "approved": out.get("approved", 0),
            "rejected": out.get("rejected", 0)}


def approve(sub_id: int) -> dict[str, Any]:
    sub = db.query_one("SELECT * FROM submissions WHERE id = %s AND status = 'pending'", (sub_id,))
    if sub is None:
        return {"ok": False, "error": "not_found_or_reviewed"}
    payload = sub["payload"] if isinstance(sub["payload"], dict) else {}
    res = verticals.create_record(sub["vertical"], payload, source="submission")
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "create_failed")}
    db.execute("UPDATE submissions SET status = 'approved', created_record_id = %s, "
               "reviewed_at = now() WHERE id = %s", (res["id"], sub_id))
    return {"ok": True, "vertical": sub["vertical"], "record_id": res["id"]}


def reject(sub_id: int) -> dict[str, Any]:
    db.execute("UPDATE submissions SET status = 'rejected', reviewed_at = now() "
               "WHERE id = %s AND status = 'pending'", (sub_id,))
    return {"ok": True}


# Tokens that strongly signal an Indian / South-Asian business. Used ONLY to AUTO-approve the
# obvious, complete submissions; anything ambiguous stays pending for a human (no false auto-publish).
_INDIAN_TOKENS = (
    "indian", "india", "desi", "south asian", "punjabi", "gujarati", "tamil", "telugu", "bengali",
    "marathi", "kannada", "malayalam", "hyderabad", "andhra", "kerala", "mumbai", "bombay", "delhi",
    "chennai", "masala", "tandoor", "biryani", "dosa", "idli", "curry", "chaat", "tiffin", "mithai",
    "sweets", "namaste", "maharaja", "taj", "ganesh", "krishna", "shiva", "mandir", "temple",
    "gurdwara", "gurudwara", "swaminarayan", "jain", "sikh", "hindu", "ayurved", "saree", "sari",
    "mehndi", "henna", "bollywood", "patel", "shah", "sharma", "gupta", "reddy", "rao", "iyer",
    "nair", "menon", "singh", "kaur", "agarwal", "swad", "apna", "bharat", "jaipur", "rajasthan",
    "punjab", "gujarat",
)


def _high_confidence(payload: dict) -> bool:
    """A complete listing AND a clear Indian/South-Asian signal -> safe to auto-publish."""
    name = (payload.get("name") or "").strip()
    city = (payload.get("city") or "").strip()
    state = (payload.get("state") or "").strip()
    has_contact = any((payload.get(k) or "").strip()
                      for k in ("phone", "website", "email", "address", "address_full"))
    if not (name and city and state and has_contact):
        return False
    text = f"{name} {payload.get('description') or ''} {payload.get('cuisine_type') or ''}".lower()
    return any(tok in text for tok in _INDIAN_TOKENS)


def auto_approve_pending(limit: int = 50) -> dict[str, Any]:
    """Agentic queue-shrinker: auto-approve obviously-good, complete, clearly-Indian submissions;
    leave anything ambiguous for a human. Duplicates are rejected (already in the directory).
    Moderation can still remove anything later."""
    approved = dups = left = 0
    for sub in list_pending(limit):
        payload = sub["payload"] if isinstance(sub["payload"], dict) else {}
        if not _high_confidence(payload):
            left += 1
            continue
        res = approve(sub["id"])
        if res.get("ok"):
            approved += 1
        elif res.get("error") == "duplicate":
            reject(sub["id"])
            dups += 1
        else:
            left += 1
    return {"auto_approved": approved, "duplicates_rejected": dups, "left_for_human": left}
