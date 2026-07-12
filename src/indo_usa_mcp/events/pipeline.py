"""Event pipeline: agents fetch iCal feeds -> raw -> clean/score -> approval routing.

Fully automated ingestion. High-confidence events auto-approve; the rest land as `pending`
for an admin to approve/reject. Past events are kept and date-filtered (not deleted); a
maintenance step purges very old ones.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from psycopg.types.json import Jsonb

from .. import db, embeddings
from ..config import settings
from ..pipeline import clean as rclean
from ..pipeline.ingest import _adapt, _as_dict, _jsonable, _normalize
from .scraper import ICalScraper

_CANONICAL_FIELDS = [
    "natural_key", "name", "description", "tags", "category", "organizer", "venue_name",
    "start_at", "end_at", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "region_tag", "festival_specials",
    "source_name", "source_url", "source_id", "confidence_score",
]
_DIFF_FIELDS = [f for f in _CANONICAL_FIELDS if f != "natural_key"]

_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("garba", ("garba", "dandiya", "raas")),
    ("festival", ("diwali", "holi", "navratri", "onam", "pongal", "eid", "ganesh",
                  "durga puja", "ugadi", "baisakhi", "dussehra", "mela", "festival")),
    ("puja", ("puja", "pooja", "aarti", "abhishek", "havan")),
    ("concert", ("concert", "live", "tour", "sangeet", "mehfil", "ghazal")),
    ("dance", ("kathak", "bharatanatyam", "odissi", "classical dance")),
    ("workshop", ("workshop", "class", "yoga", "seminar")),
]


def _parse_dt(v) -> dt.datetime | None:
    if v is None or isinstance(v, dt.datetime):
        return v
    try:
        return dt.datetime.fromisoformat(str(v))
    except ValueError:
        return None


def _infer_category(text: str) -> str | None:
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in text for k in kws):
            return cat
    return None


def clean_event(c: dict) -> dict:
    name = (c.get("name") or c.get("title") or "").strip()
    start_at, end_at = _parse_dt(c.get("start_at")), _parse_dt(c.get("end_at"))
    lat, lng = c.get("lat"), c.get("lng")
    city, state = rclean.fill_location(c.get("city"), c.get("state"), lat, lng)
    text = " ".join(str(c.get(f) or "") for f in ("name", "festival_specials", "venue_name")).lower()
    day = start_at.date().isoformat() if start_at else ""
    rec = {
        "natural_key": f"{rclean.normalize_name(name)}@{day}@{(city or '').lower()}",
        "name": name,
        "category": (c.get("category") or "").lower() or _infer_category(text),
        "organizer": c.get("organizer"),
        "venue_name": c.get("venue_name"),
        "start_at": start_at,
        "end_at": end_at,
        "address_full": (c.get("address_full") or "").strip() or None,
        "city": city,
        "state": state,
        "country": c.get("country") or "USA",
        "lat": lat,
        "lng": lng,
        "phone": rclean.normalize_phone(c.get("phone")),
        "email": (c.get("email") or "").strip().lower() or None,
        "website": c.get("website"),
        "region_tag": c.get("region_tag"),
        "festival_specials": (c.get("festival_specials") or "")[:500] or None,
        "source_name": c.get("source_name") or "ical",
        "source_url": c.get("source_url"),
        "source_id": c.get("source_id"),
    }
    from .. import describe, tags as tagmod
    rec["description"] = describe.describe("events", rec)
    rec["tags"] = tagmod.extract("events", rec)
    rec["confidence_score"] = _score(rec)
    return rec


def _score(rec: dict) -> float:
    weights = {"name": 0.3, "start_at": 0.25, "city": 0.15, "venue_name": 0.1,
               "category": 0.1, "website": 0.1}
    total = sum(w for f, w in weights.items() if rec.get(f) not in (None, "", [], {}))
    return round(min(total, 1.0), 3)


# ----------------------------------------------------------------- scrape & process
def scrape_to_raw(region: str = "") -> int:
    count = 0
    for c in ICalScraper().scrape(region):
        db.execute(
            "INSERT INTO event_raw (source_name, source_url, source_id, payload) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source_name, source_id) "
            "DO UPDATE SET payload = EXCLUDED.payload, scraped_at = now(), "
            "processed = false, processed_at = NULL",
            (c["source_name"], c.get("source_url"), c.get("source_id"), Jsonb(c)))
        count += 1
    return count


def process_raw() -> dict[str, int]:
    stats = {"processed": 0, "auto_approved": 0, "pending": 0, "updated": 0}
    for row in db.query("SELECT id, payload FROM event_raw WHERE NOT processed ORDER BY id"):
        rec = clean_event(_as_dict(row["payload"]))
        if rec["name"] and rec["start_at"] is not None:
            stats[_reconcile(rec)] += 1
        stats["processed"] += 1
        db.execute("UPDATE event_raw SET processed = true, processed_at = now() WHERE id = %s",
                   (row["id"],))
    return stats


def _reconcile(rec: dict) -> str:
    existing = db.query_one("SELECT * FROM events WHERE natural_key = %s", (rec["natural_key"],))
    if existing is None:
        # High-confidence events go live; the rest await admin approval.
        status = "approved" if rec["confidence_score"] >= settings.auto_approve_min_confidence else "pending"
        _insert(rec, status)
        return "auto_approved" if status == "approved" else "pending"
    diff = {f: rec[f] for f in _DIFF_FIELDS
            if rec.get(f) not in (None, "", [], {}) and _normalize(existing.get(f)) != _normalize(rec.get(f))}
    if diff:
        _update(existing, rec, diff)
        return "updated"
    db.execute("UPDATE events SET last_seen_at = now() WHERE id = %s", (existing["id"],))
    return "updated"


def _insert(rec: dict, status: str) -> None:
    cols = list(_CANONICAL_FIELDS)
    placeholders = ", ".join(["%s"] * len(cols))
    row = db.query_one(
        f"INSERT INTO events ({', '.join(cols)}, status, last_seen_at) "
        f"VALUES ({placeholders}, %s, now()) RETURNING *",
        [_adapt(rec.get(c)) for c in cols] + [status])
    _snapshot(row, f"ingest ({status})")


def _update(existing: dict, rec: dict, diff: dict) -> None:
    new_version = existing["version"] + 1
    cols = list(diff.keys())
    assignments = ", ".join(f"{c} = %s" for c in cols)
    row = db.query_one(
        f"UPDATE events SET {assignments}, version = %s, updated_at = now(), "
        f"last_seen_at = now() WHERE id = %s RETURNING *",
        [_adapt(rec.get(c)) for c in cols] + [new_version, existing["id"]])
    _snapshot(row, "update")


def submit_flyer_event(c: dict) -> dict[str, Any]:
    """Insert a flyer-sourced event. ALWAYS lands as 'pending' -- unlike _reconcile()'s scraped-feed
    path, this never auto-approves regardless of confidence_score, because it's LLM-vision-derived
    from a user upload rather than a trusted iCal feed. Lands in the same /admin/events pending queue
    (events.pending()/set_status()) with zero new admin UI."""
    rec = clean_event({**c, "source_name": c.get("source_name") or "flyer_upload"})
    if not rec["name"] or rec["start_at"] is None:
        return {"ok": False, "error": "missing_required_fields"}
    existing = db.query_one("SELECT id FROM events WHERE natural_key = %s", (rec["natural_key"],))
    if existing:
        return {"ok": False, "error": "duplicate_event", "event_id": existing["id"]}
    _insert(rec, "pending")
    row = db.query_one("SELECT id FROM events WHERE natural_key = %s", (rec["natural_key"],))
    return {"ok": True, "id": row["id"]}


def _snapshot(row: dict, reason: str) -> None:
    db.execute(
        "INSERT INTO event_versions (event_id, version, data, change_reason) VALUES (%s, %s, %s, %s)",
        (row["id"], row["version"], Jsonb(_jsonable(row)), reason))
    if embeddings.enabled():
        db.execute("UPDATE events SET embedding = %s::vector WHERE id = %s",
                   (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(row))), row["id"]))


# ------------------------------------------------------------------ admin approval
def set_status(event_id: int, status: str) -> None:
    db.execute("UPDATE events SET status = %s, updated_at = now() WHERE id = %s", (status, event_id))


def pending(limit: int = 100) -> list[dict]:
    return db.query(
        "SELECT id, name, category, venue_name, city, state, start_at, confidence_score, source_url "
        "FROM events WHERE status = 'pending' AND deleted_at IS NULL ORDER BY start_at LIMIT %s",
        (limit,))


def purge_old(days: int = 550) -> dict[str, int]:
    """Soft-delete events that ended more than `days` ago (retention; default ~18 months)."""
    rows = db.query(
        "SELECT id FROM events WHERE deleted_at IS NULL "
        "AND COALESCE(end_at, start_at) < now() - (%s || ' days')::interval", (days,))
    for r in rows:
        db.execute("UPDATE events SET deleted_at = now() WHERE id = %s", (r["id"],))
    return {"purged": len(rows)}
