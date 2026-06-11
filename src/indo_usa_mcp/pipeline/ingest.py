"""Orchestrates the pipeline: scrape -> raw, then raw -> canonical via approval.

Risk model (Phase 1):
  * insert of a brand-new restaurant            -> low risk
  * update to an unclaimed, non-featured listing -> low risk
  * update to a claimed or featured listing      -> high risk (always human-reviewed)

Low-risk changes with confidence >= AUTO_APPROVE_MIN_CONFIDENCE are auto-applied when
AUTO_APPROVE_LOW_RISK is true; everything else goes to the approval queue.
"""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from .. import db, embeddings
from ..config import settings
from . import clean
from .scrapers import SCRAPERS

# Canonical columns the pipeline writes (id/version/timestamps handled separately).
_CANONICAL_FIELDS = [
    "natural_key", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "menu_url", "hours_json", "cuisine_type", "region_tag",
    "dietary_tags", "price_range", "delivery_partners", "festival_specials",
    "source_name", "source_url", "source_id", "confidence_score",
]
# Fields compared when deciding whether an update is a no-op.
_DIFF_FIELDS = [f for f in _CANONICAL_FIELDS if f != "natural_key"]


# --------------------------------------------------------------------------- scrape
def scrape_to_raw(source: str, region: str) -> int:
    """Run a scraper and upsert observations into restaurant_raw. Returns row count."""
    scraper_cls = SCRAPERS.get(source)
    if scraper_cls is None:
        raise ValueError(f"Unknown source '{source}'. Known: {', '.join(SCRAPERS)}")

    count = 0
    for candidate in scraper_cls().scrape(region):
        db.execute(
            """
            INSERT INTO restaurant_raw (source_name, source_url, source_id, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_name, source_id)
            DO UPDATE SET payload = EXCLUDED.payload,
                          scraped_at = now(),
                          processed = false,
                          processed_at = NULL
            """,
            (
                candidate["source_name"],
                candidate.get("source_url"),
                candidate.get("source_id"),
                Jsonb(candidate),
            ),
        )
        count += 1
    return count


# -------------------------------------------------------------------------- process
def process_raw() -> dict[str, int]:
    """Process every unprocessed raw row into the canonical layer / approval queue."""
    stats = {"processed": 0, "auto_applied": 0, "queued": 0, "unchanged": 0}
    rows = db.query("SELECT id, payload FROM restaurant_raw WHERE NOT processed ORDER BY id")

    for row in rows:
        candidate = _as_dict(row["payload"])
        record = clean.clean(candidate)
        outcome = _reconcile(record, raw_id=row["id"])
        stats[outcome] += 1
        stats["processed"] += 1
        db.execute(
            "UPDATE restaurant_raw SET processed = true, processed_at = now() WHERE id = %s",
            (row["id"],),
        )
    return stats


def _reconcile(record: dict, raw_id: int | None) -> str:
    """Compare candidate against canonical and route it. Returns an outcome key."""
    existing = db.query_one(
        "SELECT * FROM restaurants WHERE natural_key = %s", (record["natural_key"],)
    )

    if existing is None:
        risk = "low"
        if _auto_ok(risk, record["confidence_score"]):
            _insert_canonical(record, change_reason=f"auto-insert from {record['source_name']}")
            return "auto_applied"
        _enqueue("insert", record, raw_id=raw_id, risk=risk, diff=None)
        return "queued"

    # Re-seen after being auto-deactivated -> it's back; reactivate (unless owner-controlled).
    if not existing["is_active"] and not existing["is_claimed"]:
        db.execute(
            "UPDATE restaurants SET is_active = true, updated_at = now() WHERE id = %s",
            (existing["id"],))
        existing["is_active"] = True

    diff = _diff(existing, record)
    if not diff:
        # Still a fresh sighting: refresh last_seen_at without a version bump.
        db.execute("UPDATE restaurants SET last_seen_at = now() WHERE id = %s", (existing["id"],))
        return "unchanged"

    risk = "high" if (existing["is_claimed"] or existing["is_featured"]) else "low"
    if _auto_ok(risk, record["confidence_score"]):
        _update_canonical(existing, record, diff, change_reason="auto-update")
        return "auto_applied"
    _enqueue("update", record, raw_id=raw_id, risk=risk, diff=diff, restaurant_id=existing["id"])
    return "queued"


def _auto_ok(risk: str, confidence: float) -> bool:
    return (
        settings.auto_approve_low_risk
        and risk == "low"
        and confidence >= settings.auto_approve_min_confidence
    )


# ------------------------------------------------------------------------ approvals
def _enqueue(
    change_type: str,
    record: dict,
    *,
    raw_id: int | None,
    risk: str,
    diff: dict | None,
    restaurant_id: int | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO approval_queue
            (restaurant_id, raw_id, change_type, natural_key, proposed, diff, risk, confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            restaurant_id,
            raw_id,
            change_type,
            record["natural_key"],
            Jsonb(record),
            Jsonb(diff) if diff is not None else None,
            risk,
            record["confidence_score"],
        ),
    )


def apply_approval(approval_id: int, reviewed_by: str = "human") -> None:
    """Approve a queued item and apply it to the canonical layer."""
    item = db.query_one("SELECT * FROM approval_queue WHERE id = %s", (approval_id,))
    if item is None:
        raise ValueError(f"No approval item #{approval_id}")
    if item["status"] != "pending":
        raise ValueError(f"Approval #{approval_id} is already {item['status']}")

    record = _as_dict(item["proposed"])
    if item["change_type"] == "insert":
        _insert_canonical(record, change_reason=f"approved insert #{approval_id}")
    else:
        existing = db.query_one(
            "SELECT * FROM restaurants WHERE natural_key = %s", (record["natural_key"],)
        )
        if existing is None:
            _insert_canonical(record, change_reason=f"approved insert #{approval_id}")
        else:
            diff = _diff(existing, record)
            _update_canonical(existing, record, diff, change_reason=f"approved update #{approval_id}")

    db.execute(
        "UPDATE approval_queue SET status='approved', reviewed_at=now(), reviewed_by=%s WHERE id=%s",
        (reviewed_by, approval_id),
    )


def enrich_existing() -> dict[str, int]:
    """Re-apply cultural inference (region_tag, dietary_tags) to canonical rows.

    Lets the expanded keyword set fill in restaurants that were scraped before, without
    re-scraping. Only fills gaps — never clears an existing region/dietary value.
    """
    rows = db.query(
        "SELECT * FROM restaurants WHERE deleted_at IS NULL "
        "AND (region_tag IS NULL OR dietary_tags = '{}')"
    )
    updated = 0
    for row in rows:
        text = " ".join(
            str(row.get(f) or "") for f in ("name", "cuisine_type", "address_full", "city")
        )
        diff: dict[str, Any] = {}
        if row.get("region_tag") is None:
            region = clean.infer_region(text)
            if region:
                diff["region_tag"] = region
        if not row.get("dietary_tags"):
            dietary = clean.infer_dietary(text)
            if dietary:
                diff["dietary_tags"] = dietary
        if diff:
            _update_canonical(row, {**row, **diff}, diff, change_reason="enrichment")
            updated += 1
    return {"scanned": len(rows), "enriched": updated}


# Fields an owner may edit on their own listing (after claiming).
OWNER_EDITABLE = {
    "phone", "email", "website", "menu_url", "address_full", "city", "state",
    "price_range", "cuisine_type", "region_tag", "festival_specials",
    "dietary_tags", "hours_json",
}


def apply_owner_edits(restaurant_id: int, edits: dict) -> dict[str, Any]:
    """Apply a verified owner's edits to their listing (trusted, versioned, immediate).

    Owner edits are protected from being silently overwritten: scraper updates to a
    claimed listing are routed to the approval queue, not auto-applied.
    """
    r = db.query_one(
        "SELECT * FROM restaurants WHERE id = %s AND deleted_at IS NULL", (restaurant_id,))
    if r is None:
        return {"ok": False, "error": "not_found"}
    diff = {}
    for k, v in edits.items():
        if k in OWNER_EDITABLE and _normalize(r.get(k)) != _normalize(v):
            diff[k] = v
    if not diff:
        return {"ok": True, "updated": 0}
    _update_canonical(r, {**r, **diff}, diff, change_reason="owner edit")
    return {"ok": True, "updated": len(diff), "fields": sorted(diff)}


def deactivate_stale(days: int = 60) -> dict[str, int]:
    """Mark unclaimed listings not re-seen in `days` as inactive (likely closed/gone).

    Claimed listings are left alone (the owner controls them). Reappearing in a later
    scrape reactivates a listing (handled in _reconcile).
    """
    rows = db.query(
        "SELECT * FROM restaurants WHERE deleted_at IS NULL AND is_active "
        "AND NOT is_claimed AND last_seen_at < now() - (%s || ' days')::interval",
        (days,),
    )
    for r in rows:
        new_version = r["version"] + 1
        db.execute(
            "UPDATE restaurants SET is_active = false, version = %s, updated_at = now() "
            "WHERE id = %s",
            (new_version, r["id"]),
        )
        db.execute(
            "INSERT INTO restaurant_versions (restaurant_id, version, data, change_reason) "
            "VALUES (%s, %s, %s, %s)",
            (r["id"], new_version,
             Jsonb(_jsonable({**r, "is_active": False, "version": new_version})),
             f"auto-deactivated: not seen in {days}d"),
        )
    return {"deactivated": len(rows)}


def summarize_approvals(limit: int = 100) -> dict[str, Any]:
    """Human-readable digest of the pending approval queue (Approval-Assistant agent).

    Turns raw queue rows into one-line summaries — what's changing, the risk, and (for
    new inserts) which high-value fields are missing — so a person can review fast.
    """
    rows = db.query(
        "SELECT * FROM approval_queue WHERE status = 'pending' "
        "ORDER BY risk DESC, confidence ASC, created_at LIMIT %s",
        (limit,),
    )
    items, by_risk, by_change = [], {"high": 0, "low": 0}, {"insert": 0, "update": 0}
    for a in rows:
        proposed = _as_dict(a["proposed"])
        name = proposed.get("name", "?")
        by_risk[a["risk"]] = by_risk.get(a["risk"], 0) + 1
        by_change[a["change_type"]] = by_change.get(a["change_type"], 0) + 1
        if a["change_type"] == "insert":
            missing = [f for f in ("phone", "website", "address_full") if not proposed.get(f)]
            tail = f" — missing {', '.join(missing)}" if missing else ""
            summary = (f"NEW '{name}' in {proposed.get('city') or '?'} "
                       f"(conf {a['confidence']}, {a['risk']} risk){tail}")
        else:
            fields = ", ".join((a.get("diff") or {}).keys()) or "—"
            summary = f"UPDATE '{name}' fields: {fields} ({a['risk']} risk)"
        items.append({
            "id": a["id"], "change_type": a["change_type"],
            "risk": a["risk"], "confidence": a["confidence"], "summary": summary,
        })
    return {"pending": len(rows), "by_risk": by_risk, "by_change": by_change, "items": items}


def set_featured(restaurant_id: int, days: int | None = 30) -> dict[str, Any]:
    """Mark a restaurant as a paid featured listing for `days` (None = permanent)."""
    if days is None:
        row = db.query_one(
            "UPDATE restaurants SET is_featured = true, featured_until = NULL, "
            "updated_at = now() WHERE id = %s AND deleted_at IS NULL "
            "RETURNING id, name, is_featured, featured_until",
            (restaurant_id,),
        )
    else:
        row = db.query_one(
            "UPDATE restaurants SET is_featured = true, "
            "featured_until = now() + (%s || ' days')::interval, updated_at = now() "
            "WHERE id = %s AND deleted_at IS NULL "
            "RETURNING id, name, is_featured, featured_until",
            (days, restaurant_id),
        )
    return row or {"error": "not_found", "id": restaurant_id}


def unset_featured(restaurant_id: int) -> dict[str, Any]:
    row = db.query_one(
        "UPDATE restaurants SET is_featured = false, featured_until = NULL, "
        "updated_at = now() WHERE id = %s RETURNING id, name, is_featured",
        (restaurant_id,),
    )
    return row or {"error": "not_found", "id": restaurant_id}


def backfill_embeddings(only_missing: bool = True) -> dict[str, int]:
    """(Re)compute embeddings for canonical rows. Used after enabling/changing a provider."""
    if not embeddings.enabled():
        return {"updated": 0, "skipped": "embeddings disabled"}
    where = "WHERE deleted_at IS NULL" + (" AND embedding IS NULL" if only_missing else "")
    rows = db.query(f"SELECT * FROM restaurants {where}")
    for row in rows:
        _write_embedding(row)
    return {"updated": len(rows)}


def reject_approval(approval_id: int, reviewed_by: str = "human") -> None:
    db.execute(
        "UPDATE approval_queue SET status='rejected', reviewed_at=now(), reviewed_by=%s "
        "WHERE id=%s AND status='pending'",
        (reviewed_by, approval_id),
    )


# ----------------------------------------------------------------- canonical writes
def _insert_canonical(record: dict, change_reason: str) -> int:
    cols = list(_CANONICAL_FIELDS)
    placeholders = ", ".join(["%s"] * len(cols))
    values = [_adapt(record.get(c)) for c in cols]
    row = db.query_one(
        f"INSERT INTO restaurants ({', '.join(cols)}, last_seen_at) "
        f"VALUES ({placeholders}, now()) RETURNING *",
        values,
    )
    _snapshot(row, change_reason)
    return row["id"]


def _update_canonical(existing: dict, record: dict, diff: dict, change_reason: str) -> None:
    new_version = existing["version"] + 1
    set_cols = list(diff.keys())
    assignments = ", ".join(f"{c} = %s" for c in set_cols)
    values = [_adapt(record.get(c)) for c in set_cols]
    values += [new_version, existing["id"]]
    row = db.query_one(
        f"UPDATE restaurants SET {assignments}, version = %s, "
        f"updated_at = now(), last_seen_at = now() WHERE id = %s RETURNING *",
        values,
    )
    _snapshot(row, change_reason)


def _snapshot(row: dict, change_reason: str) -> None:
    db.execute(
        "INSERT INTO restaurant_versions (restaurant_id, version, data, change_reason) "
        "VALUES (%s, %s, %s, %s)",
        (row["id"], row["version"], Jsonb(_jsonable(row)), change_reason),
    )
    _write_embedding(row)


def _write_embedding(row: dict) -> None:
    """Compute and store the row's semantic embedding (no-op if disabled)."""
    if not embeddings.enabled():
        return
    vec = embeddings.embed(embeddings.text_for(row))
    db.execute(
        "UPDATE restaurants SET embedding = %s::vector WHERE id = %s",
        (embeddings.to_vector_literal(vec), row["id"]),
    )


# ---------------------------------------------------------------------------- utils
def _diff(existing: dict, record: dict) -> dict[str, Any]:
    """Fields in `record` that differ from `existing` (ignoring None candidates)."""
    out: dict[str, Any] = {}
    for field in _DIFF_FIELDS:
        new = record.get(field)
        if new in (None, "", [], {}):
            continue  # never overwrite known data with an empty scrape
        if _normalize(existing.get(field)) != _normalize(new):
            out[field] = new
    return out


def _normalize(value: Any) -> Any:
    if isinstance(value, list):
        return sorted(value)
    return value


def _adapt(value: Any) -> Any:
    """Wrap dict/list-of-dict JSON columns for psycopg; pass arrays through."""
    if isinstance(value, dict):
        return Jsonb(value)
    return value


def _as_dict(payload: Any) -> dict:
    return payload if isinstance(payload, dict) else json.loads(payload)


def _jsonable(row: dict) -> dict:
    """Drop/convert non-JSON-serialisable values (datetimes, vectors) for snapshots."""
    out = {}
    for k, v in row.items():
        if k == "embedding":
            continue
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out
