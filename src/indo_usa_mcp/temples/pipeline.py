"""Temple pipeline: scrape -> raw -> clean/enrich/score -> canonical -> versioning.

Mirrors the restaurant pipeline but for the temples table. Reuses shared helpers
(name/phone normalization, embeddings, generic diff/json adapters).
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .. import db, embeddings
from ..pipeline import clean as rclean
from ..pipeline.ingest import _adapt, _as_dict, _jsonable, _normalize
from .scraper import TempleOverpassScraper

_CANONICAL_FIELDS = [
    "natural_key", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "religion", "denomination", "deity",
    "region_tag", "festival_specials", "description", "tags", "source_name", "source_url",
    "source_id", "confidence_score",
]
_DIFF_FIELDS = [f for f in _CANONICAL_FIELDS if f != "natural_key"]

# Signature terms -> region_tag (culturally meaningful, conservative).
_REGION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Punjabi", ("gurdwara", "sikh", "singh sabha", "khalsa")),
    ("Gujarati", ("swaminarayan", "baps", "shree", "haveli")),
    ("Jain", ("jain", "derasar")),
    ("Telugu", ("venkateswara", "balaji", "tirupati", "annamayya")),
    ("Tamil", ("murugan", "ayyappa", "meenakshi", "siva vishnu", "ganesha temple")),
    ("South Indian", ("sri ", "saibaba", "shirdi")),
]
# Primary deity from the name.
_DEITIES = [
    "venkateswara", "balaji", "ganesha", "ganesh", "shiva", "siva", "vishnu", "durga",
    "hanuman", "murugan", "ayyappa", "krishna", "rama", "lakshmi", "saraswati",
    "meenakshi", "swaminarayan", "mahavir", "shirdi sai", "saibaba", "kali",
]


def _infer_region(text: str, religion: str | None) -> str | None:
    if religion == "sikh":
        return "Punjabi"
    if religion == "jain":
        return "Jain"
    for tag, keywords in _REGION_RULES:
        if any(k in text for k in keywords):
            return tag
    return None


def _infer_deity(text: str) -> str | None:
    for d in _DEITIES:
        if d in text:
            return d.title()
    return None


def clean_temple(c: dict) -> dict:
    name = (c.get("name") or "").strip()
    lat, lng = c.get("lat"), c.get("lng")
    religion = (c.get("religion") or None)
    haystack = " ".join(
        str(c.get(f) or "") for f in ("name", "denomination", "religion", "address_full")
    ).lower()
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
        "religion": religion,
        "denomination": c.get("denomination"),
        "deity": _infer_deity(haystack),
        "region_tag": _infer_region(haystack, religion),
        "festival_specials": c.get("festival_specials"),
        "source_name": c.get("source_name"),
        "source_url": c.get("source_url"),
        "source_id": c.get("source_id"),
    }
    from .. import describe, tags as tagmod
    rec["tags"] = sorted(set(tagmod.extract("temples", rec)) | set(c.get("extra_tags") or []))
    rec["description"] = describe.describe("temples", rec)
    rec["confidence_score"] = _score(rec)
    return rec


def _score(rec: dict) -> float:
    weights = {"name": 0.25, "lat": 0.2, "address_full": 0.15, "religion": 0.15,
               "website": 0.1, "phone": 0.1, "city": 0.05}
    total = sum(w for f, w in weights.items() if rec.get(f) not in (None, "", [], {}))
    return round(min(total, 1.0), 3)


# ----------------------------------------------------------------- scrape & process
def _raw_upsert(c: dict) -> None:
    db.execute(
        "INSERT INTO temple_raw (source_name, source_url, source_id, payload) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (source_name, source_id) "
        "DO UPDATE SET payload = EXCLUDED.payload, scraped_at = now(), "
        "processed = false, processed_at = NULL",
        (c["source_name"], c.get("source_url"), c.get("source_id"), Jsonb(c)),
    )


def scrape_to_raw(region: str) -> int:
    count = 0
    for c in TempleOverpassScraper().scrape(region):
        _raw_upsert(c)
        count += 1
    return count


def scrape_wikidata_to_raw() -> int:
    """Add notable US Hindu temples from Wikidata (CC0) into temple_raw."""
    import sys

    from .wikidata import WikidataTempleScraper
    scraper = WikidataTempleScraper()
    count = 0
    for c in scraper.scrape():
        _raw_upsert(c)
        count += 1
    if count == 0 and scraper.last_error:  # never hide a systemic failure as a silent 0
        print(f"  Wikidata temples warning: {scraper.last_error}", file=sys.stderr)
    return count


def process_raw() -> dict[str, int]:
    stats = {"processed": 0, "inserted": 0, "updated": 0, "unchanged": 0}
    for row in db.query("SELECT id, payload FROM temple_raw WHERE NOT processed ORDER BY id"):
        rec = clean_temple(_as_dict(row["payload"]))
        stats[_reconcile(rec)] += 1
        stats["processed"] += 1
        db.execute("UPDATE temple_raw SET processed = true, processed_at = now() WHERE id = %s",
                   (row["id"],))
    return stats


def _reconcile(rec: dict) -> str:
    existing = db.query_one("SELECT * FROM temples WHERE natural_key = %s", (rec["natural_key"],))
    if existing is None:
        _insert(rec)
        return "inserted"
    if not existing["is_active"] and not existing["is_claimed"]:
        db.execute("UPDATE temples SET is_active = true, updated_at = now() WHERE id = %s",
                   (existing["id"],))
    diff = {f: rec[f] for f in _DIFF_FIELDS
            if rec.get(f) not in (None, "", [], {}) and _normalize(existing.get(f)) != _normalize(rec.get(f))}
    if not diff:
        db.execute("UPDATE temples SET last_seen_at = now() WHERE id = %s", (existing["id"],))
        return "unchanged"
    _update(existing, rec, diff)
    return "updated"


def _insert(rec: dict) -> None:
    cols = list(_CANONICAL_FIELDS)
    placeholders = ", ".join(["%s"] * len(cols))
    row = db.query_one(
        f"INSERT INTO temples ({', '.join(cols)}, last_seen_at) "
        f"VALUES ({placeholders}, now()) RETURNING *",
        [_adapt(rec.get(c)) for c in cols],
    )
    _snapshot(row, f"insert from {rec.get('source_name')}")


def _update(existing: dict, rec: dict, diff: dict) -> None:
    new_version = existing["version"] + 1
    cols = list(diff.keys())
    assignments = ", ".join(f"{c} = %s" for c in cols)
    row = db.query_one(
        f"UPDATE temples SET {assignments}, version = %s, updated_at = now(), "
        f"last_seen_at = now() WHERE id = %s RETURNING *",
        [_adapt(rec.get(c)) for c in cols] + [new_version, existing["id"]],
    )
    _snapshot(row, "update")


def _snapshot(row: dict, reason: str) -> None:
    db.execute(
        "INSERT INTO temple_versions (temple_id, version, data, change_reason) "
        "VALUES (%s, %s, %s, %s)",
        (row["id"], row["version"], Jsonb(_jsonable(row)), reason),
    )
    if embeddings.enabled():
        text = embeddings.text_for(row)
        db.execute("UPDATE temples SET embedding = %s::vector WHERE id = %s",
                   (embeddings.to_vector_literal(embeddings.embed(text)), row["id"]))


def deactivate_stale(days: int = 90) -> dict[str, int]:
    rows = db.query(
        "SELECT id, version FROM temples WHERE deleted_at IS NULL AND is_active "
        "AND NOT is_claimed AND last_seen_at < now() - (%s || ' days')::interval", (days,))
    for r in rows:
        db.execute("UPDATE temples SET is_active = false, version = version + 1, "
                   "updated_at = now() WHERE id = %s", (r["id"],))
    return {"deactivated": len(rows)}
