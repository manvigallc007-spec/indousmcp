"""Feedback Agent: process field corrections from agents/users (blueprint agent #5).

Flow: submit_correction() stores a pending row -> the Feedback agent's apply_pending()
applies safe corrections to unclaimed/unfeatured listings (with versioning), and routes
corrections to claimed/featured listings to 'needs_review' for a human.

Only a whitelist of scalar fields is correctable; identity fields (name, coordinates,
natural_key) are never auto-changed.
"""

from __future__ import annotations

from typing import Any

from .. import db
from . import ingest

# Scalar fields a correction may target. Excludes identity + structured fields.
CORRECTABLE_FIELDS = {
    "phone", "email", "website", "menu_url", "address_full", "city", "state",
    "region_tag", "price_range", "cuisine_type", "festival_specials",
}


def submit_correction(
    restaurant_id: int, field: str, value: str | None,
    reason: str = "", source: str = "agent",
) -> dict[str, Any]:
    """Record a proposed correction. Returns {ok, feedback_id|error}."""
    if field not in CORRECTABLE_FIELDS:
        return {"ok": False, "error": "field_not_correctable",
                "field": field, "allowed": sorted(CORRECTABLE_FIELDS)}
    exists = db.query_one(
        "SELECT 1 FROM restaurants WHERE id = %s AND deleted_at IS NULL", (restaurant_id,))
    if exists is None:
        return {"ok": False, "error": "restaurant_not_found", "id": restaurant_id}

    row = db.query_one(
        "INSERT INTO feedback (restaurant_id, field, proposed_value, reason, source) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (restaurant_id, field, value, reason, source),
    )
    return {"ok": True, "feedback_id": row["id"], "status": "pending"}


def apply_pending(limit: int = 200) -> dict[str, int]:
    """Apply pending corrections. Safe ones land immediately; risky ones await review."""
    rows = db.query(
        "SELECT * FROM feedback WHERE status = 'pending' ORDER BY created_at LIMIT %s",
        (limit,),
    )
    applied = needs_review = rejected = 0
    for fb in rows:
        r = db.query_one(
            "SELECT * FROM restaurants WHERE id = %s AND deleted_at IS NULL",
            (fb["restaurant_id"],),
        )
        if r is None:
            _resolve(fb["id"], "rejected")
            rejected += 1
            continue
        # Corrections to claimed/featured listings always go to a human.
        if r["is_claimed"] or r["is_featured"]:
            _resolve(fb["id"], "needs_review")
            needs_review += 1
            continue
        diff = {fb["field"]: fb["proposed_value"]}
        ingest._update_canonical(
            r, {**r, **diff}, diff, change_reason=f"feedback #{fb['id']} ({fb['source']})")
        _resolve(fb["id"], "applied")
        applied += 1
    return {"scanned": len(rows), "applied": applied,
            "needs_review": needs_review, "rejected": rejected}


def _resolve(feedback_id: int, status: str) -> None:
    db.execute(
        "UPDATE feedback SET status = %s, resolved_at = now() WHERE id = %s",
        (status, feedback_id),
    )
