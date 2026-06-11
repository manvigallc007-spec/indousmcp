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
    "phone", "website", "menu_url", "hours_json", "cuisine_type", "region_tag",
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
