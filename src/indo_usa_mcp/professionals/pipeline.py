"""Professional pipeline: scrape -> raw -> clean/enrich/score -> canonical -> versioning."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .. import db, embeddings
from ..pipeline import clean as rclean
from ..pipeline.ingest import _adapt, _as_dict, _jsonable, _normalize
from .scraper import ProfessionalOverpassScraper

_CANONICAL_FIELDS = [
    "natural_key", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "profession_type", "speciality", "region_tag",
    "festival_specials", "description", "tags", "source_name", "source_url", "source_id",
    "confidence_score",
]
_DIFF_FIELDS = [f for f in _CANONICAL_FIELDS if f != "natural_key"]

# OSM speciality / name keywords -> a normalized speciality tag.
_SPECIALITIES = {
    "dentist": ("dentist", "dental", "orthodont"),
    "pediatrics": ("pediatric", "paediatric", "children"),
    "cardiology": ("cardio", "heart"),
    "dermatology": ("derma", "skin"),
    "gynaecology": ("gyn", "obstetric", "women"),
    "pharmacy": ("pharmacy", "drug", "rx"),
    "ophthalmology": ("eye", "ophthal", "optometr"),
    "ayurveda": ("ayurved",),
    "family_medicine": ("family", "primary care", "internal medicine", "physician"),
}


def _infer_speciality(text: str, ptype: str | None) -> str | None:
    for tag, kws in _SPECIALITIES.items():
        if any(k in text for k in kws):
            return tag
    if ptype == "dentist":
        return "dentist"
    if ptype == "pharmacy":
        return "pharmacy"
    return None


def clean_professional(c: dict) -> dict:
    name = (c.get("name") or "").strip()
    lat, lng = c.get("lat"), c.get("lng")
    haystack = " ".join(str(c.get(f) or "") for f in
                        ("name", "speciality", "profession_type", "address_full")).lower()
    city, state = rclean.fill_location(c.get("city"), c.get("state"), lat, lng)
    # Coordinate-less sources (e.g. NPPES) would all collide on a name-only key, so disambiguate
    # by city; coordinate-bearing sources (OSM) keep their original name+geo key.
    nk_seed = name if (lat is not None and lng is not None) else f"{name} {city or ''}".strip()
    rec = {
        "natural_key": rclean.natural_key(nk_seed, lat, lng),
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
        "profession_type": c.get("profession_type"),
        "speciality": (c.get("speciality") or _infer_speciality(haystack, c.get("profession_type"))),
        "region_tag": None,
        "festival_specials": None,
        "source_name": c.get("source_name"),
        "source_url": c.get("source_url"),
        "source_id": c.get("source_id"),
    }
    from .. import describe, tags as tagmod
    rec["tags"] = sorted(set(tagmod.extract("professionals", rec)) | set(c.get("extra_tags") or []))
    rec["description"] = describe.describe("professionals", rec)
    rec["confidence_score"] = _score(rec)
    return rec


def _score(rec: dict) -> float:
    weights = {"name": 0.3, "lat": 0.2, "address_full": 0.15, "profession_type": 0.1,
               "website": 0.1, "phone": 0.1, "city": 0.05}
    total = sum(w for f, w in weights.items() if rec.get(f) not in (None, "", [], {}))
    return round(min(total, 1.0), 3)


def scrape_to_raw(region: str) -> int:
    count = 0
    for c in ProfessionalOverpassScraper().scrape(region):
        db.execute(
            "INSERT INTO professional_raw (source_name, source_url, source_id, payload) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source_name, source_id) "
            "DO UPDATE SET payload = EXCLUDED.payload, scraped_at = now(), "
            "processed = false, processed_at = NULL",
            (c["source_name"], c.get("source_url"), c.get("source_id"), Jsonb(c)),
        )
        count += 1
    return count


def scrape_nppes_to_raw(state: str, limit_per: int = 200) -> int:
    """Pull Indian-American providers for a US state from the NPPES NPI registry into raw."""
    from .nppes import NppesScraper
    count = 0
    for c in NppesScraper().scrape(state, limit_per=limit_per):
        db.execute(
            "INSERT INTO professional_raw (source_name, source_url, source_id, payload) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source_name, source_id) "
            "DO UPDATE SET payload = EXCLUDED.payload, scraped_at = now(), "
            "processed = false, processed_at = NULL",
            (c["source_name"], c.get("source_url"), c.get("source_id"), Jsonb(c)),
        )
        count += 1
    return count


def process_raw() -> dict[str, int]:
    stats = {"processed": 0, "inserted": 0, "updated": 0, "unchanged": 0}
    for row in db.query("SELECT id, payload FROM professional_raw WHERE NOT processed ORDER BY id"):
        rec = clean_professional(_as_dict(row["payload"]))
        stats[_reconcile(rec)] += 1
        stats["processed"] += 1
        db.execute("UPDATE professional_raw SET processed = true, processed_at = now() WHERE id = %s",
                   (row["id"],))
    return stats


def _reconcile(rec: dict) -> str:
    existing = db.query_one("SELECT * FROM professionals WHERE natural_key = %s", (rec["natural_key"],))
    if existing is None:
        _insert(rec)
        return "inserted"
    if not existing["is_active"] and not existing["is_claimed"]:
        db.execute("UPDATE professionals SET is_active = true, updated_at = now() WHERE id = %s",
                   (existing["id"],))
    diff = {f: rec[f] for f in _DIFF_FIELDS
            if rec.get(f) not in (None, "", [], {}) and _normalize(existing.get(f)) != _normalize(rec.get(f))}
    if not diff:
        db.execute("UPDATE professionals SET last_seen_at = now() WHERE id = %s", (existing["id"],))
        return "unchanged"
    _update(existing, rec, diff)
    return "updated"


def _insert(rec: dict) -> None:
    cols = list(_CANONICAL_FIELDS)
    placeholders = ", ".join(["%s"] * len(cols))
    row = db.query_one(
        f"INSERT INTO professionals ({', '.join(cols)}, last_seen_at) "
        f"VALUES ({placeholders}, now()) RETURNING *",
        [_adapt(rec.get(c)) for c in cols],
    )
    _snapshot(row, f"insert from {rec.get('source_name')}")


def _update(existing: dict, rec: dict, diff: dict) -> None:
    new_version = existing["version"] + 1
    cols = list(diff.keys())
    assignments = ", ".join(f"{c} = %s" for c in cols)
    row = db.query_one(
        f"UPDATE professionals SET {assignments}, version = %s, updated_at = now(), "
        f"last_seen_at = now() WHERE id = %s RETURNING *",
        [_adapt(rec.get(c)) for c in cols] + [new_version, existing["id"]],
    )
    _snapshot(row, "update")


def _snapshot(row: dict, reason: str) -> None:
    db.execute(
        "INSERT INTO professional_versions (professional_id, version, data, change_reason) "
        "VALUES (%s, %s, %s, %s)",
        (row["id"], row["version"], Jsonb(_jsonable(row)), reason),
    )
    if embeddings.enabled():
        db.execute("UPDATE professionals SET embedding = %s::vector WHERE id = %s",
                   (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(row))), row["id"]))


def deactivate_stale(days: int = 120) -> dict[str, int]:
    rows = db.query(
        "SELECT id FROM professionals WHERE deleted_at IS NULL AND is_active "
        "AND NOT is_claimed AND last_seen_at < now() - (%s || ' days')::interval", (days,))
    for r in rows:
        db.execute("UPDATE professionals SET is_active = false, version = version + 1, "
                   "updated_at = now() WHERE id = %s", (r["id"],))
    return {"deactivated": len(rows)}
