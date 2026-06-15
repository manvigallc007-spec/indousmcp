"""Finance pipeline: scrape -> raw -> clean/enrich/score -> canonical -> versioning."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from .. import db, embeddings
from ..pipeline import clean as rclean
from ..pipeline.ingest import _adapt, _as_dict, _jsonable, _normalize
from .scraper import FinanceOverpassScraper

_CANONICAL_FIELDS = [
    "natural_key", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "finance_type", "region_tag",
    "festival_specials", "description", "tags", "source_name", "source_url", "source_id",
    "confidence_score",
]
_DIFF_FIELDS = [f for f in _CANONICAL_FIELDS if f != "natural_key"]

_REGIONS = ("Telugu", "Tamil", "Gujarati", "Marathi", "Bengali", "Kannada", "Malayalee",
            "Malayali", "Punjabi", "Hindi", "Odia", "Konkani", "Sindhi")


def _finance_type(name: str, raw_type: str | None) -> str:
    n = (name or "").lower()
    if any(k in n for k in ("cpa", "certified public")):
        return "cpa"
    if "tax" in n:
        return "tax"
    if any(k in n for k in ("wealth", "financial", "investment", "advisor", "advisory", "capital")):
        return "financial_advisor"
    raw = (raw_type or "").lower()
    if raw in ("tax_advisor",):
        return "tax"
    if raw in ("financial_advisor", "financial"):
        return "financial_advisor"
    return raw or "accountant"


def _region(name: str) -> str | None:
    n = (name or "").lower()
    for r in _REGIONS:
        if r.lower() in n:
            return "Malayalee" if r == "Malayali" else r
    return None


def clean_finance(c: dict) -> dict:
    name = (c.get("name") or "").strip()
    lat, lng = c.get("lat"), c.get("lng")
    city, state = rclean.fill_location(c.get("city"), c.get("state"), lat, lng)
    rec = {
        "natural_key": rclean.natural_key(name, lat, lng),
        "name": name,
        "address_full": (c.get("address_full") or "").strip() or None,
        "city": city,
        "state": state,
        "country": c.get("country") or "USA",
        "lat": lat,
        "lng": lng,
        "phone": rclean.normalize_phone(c.get("phone")),
        "email": (c.get("email") or "").strip().lower() or None,
        "website": c.get("website"),
        "hours_json": rclean._with_hours(c.get("hours_json")),
        "finance_type": _finance_type(name, c.get("finance_type")),
        "region_tag": _region(name),
        "festival_specials": None,
        "source_name": c.get("source_name"),
        "source_url": c.get("source_url"),
        "source_id": c.get("source_id"),
    }
    from .. import describe, tags as tagmod
    rec["tags"] = sorted(set(tagmod.extract("finance", rec)) | set(c.get("extra_tags") or []))
    rec["description"] = describe.describe("finance", rec)
    rec["confidence_score"] = _score(rec)
    return rec


def _score(rec: dict) -> float:
    weights = {"name": 0.3, "lat": 0.2, "address_full": 0.2, "website": 0.1,
               "phone": 0.1, "city": 0.1}
    total = sum(w for f, w in weights.items() if rec.get(f) not in (None, "", [], {}))
    return round(min(total, 1.0), 3)


def scrape_to_raw(region: str) -> int:
    count = 0
    for c in FinanceOverpassScraper().scrape(region):
        db.execute(
            "INSERT INTO finance_raw (source_name, source_url, source_id, payload) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source_name, source_id) "
            "DO UPDATE SET payload = EXCLUDED.payload, scraped_at = now(), "
            "processed = false, processed_at = NULL",
            (c["source_name"], c.get("source_url"), c.get("source_id"), Jsonb(c)),
        )
        count += 1
    return count


def process_raw() -> dict[str, int]:
    stats = {"processed": 0, "inserted": 0, "updated": 0, "unchanged": 0}
    for row in db.query("SELECT id, payload FROM finance_raw WHERE NOT processed ORDER BY id"):
        rec = clean_finance(_as_dict(row["payload"]))
        stats[_reconcile(rec)] += 1
        stats["processed"] += 1
        db.execute("UPDATE finance_raw SET processed = true, processed_at = now() WHERE id = %s",
                   (row["id"],))
    return stats


def _reconcile(rec: dict) -> str:
    existing = db.query_one("SELECT * FROM finance WHERE natural_key = %s", (rec["natural_key"],))
    if existing is None:
        _insert(rec)
        return "inserted"
    if not existing["is_active"] and not existing["is_claimed"] and rclean.is_publishable(rec):
        db.execute("UPDATE finance SET is_active = true, updated_at = now() WHERE id = %s",
                   (existing["id"],))
    diff = {f: rec[f] for f in _DIFF_FIELDS
            if rec.get(f) not in (None, "", [], {}) and _normalize(existing.get(f)) != _normalize(rec.get(f))}
    if not diff:
        db.execute("UPDATE finance SET last_seen_at = now() WHERE id = %s", (existing["id"],))
        return "unchanged"
    _update(existing, rec, diff)
    return "updated"


def _insert(rec: dict) -> None:
    cols = list(_CANONICAL_FIELDS)
    placeholders = ", ".join(["%s"] * len(cols))
    row = db.query_one(
        f"INSERT INTO finance ({', '.join(cols)}, is_active, last_seen_at) "
        f"VALUES ({placeholders}, %s, now()) RETURNING *",
        [_adapt(rec.get(c)) for c in cols] + [rclean.is_publishable(rec)],
    )
    _snapshot(row, f"insert from {rec.get('source_name')}")


def _update(existing: dict, rec: dict, diff: dict) -> None:
    new_version = existing["version"] + 1
    cols = list(diff.keys())
    assignments = ", ".join(f"{c} = %s" for c in cols)
    row = db.query_one(
        f"UPDATE finance SET {assignments}, version = %s, updated_at = now(), "
        f"last_seen_at = now() WHERE id = %s RETURNING *",
        [_adapt(rec.get(c)) for c in cols] + [new_version, existing["id"]],
    )
    _snapshot(row, "update")


def _snapshot(row: dict, reason: str) -> None:
    db.execute(
        "INSERT INTO finance_versions (finance_id, version, data, change_reason) "
        "VALUES (%s, %s, %s, %s)",
        (row["id"], row["version"], Jsonb(_jsonable(row)), reason),
    )
    if embeddings.enabled():
        db.execute("UPDATE finance SET embedding = %s::vector WHERE id = %s",
                   (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(row))), row["id"]))


def deactivate_stale(days: int = 180) -> dict[str, int]:
    rows = db.query(
        "SELECT id FROM finance WHERE deleted_at IS NULL AND is_active "
        "AND NOT is_claimed AND last_seen_at < now() - (%s || ' days')::interval", (days,))
    for r in rows:
        db.execute("UPDATE finance SET is_active = false, version = version + 1, "
                   "updated_at = now() WHERE id = %s", (r["id"],))
    return {"deactivated": len(rows)}
