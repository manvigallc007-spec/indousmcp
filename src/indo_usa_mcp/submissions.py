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
    res = verticals.create_record(sub["vertical"], payload)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "create_failed")}
    db.execute("UPDATE submissions SET status = 'approved', created_record_id = %s, "
               "reviewed_at = now() WHERE id = %s", (res["id"], sub_id))
    return {"ok": True, "vertical": sub["vertical"], "record_id": res["id"]}


def reject(sub_id: int) -> dict[str, Any]:
    db.execute("UPDATE submissions SET status = 'rejected', reviewed_at = now() "
               "WHERE id = %s AND status = 'pending'", (sub_id,))
    return {"ok": True}
