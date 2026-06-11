"""Normalize, enrich, deduplicate-fingerprint and score a candidate record.

Input is a source-agnostic dict produced by a scraper's `to_candidate()`. Output is
a canonical-shaped dict ready for the approval queue / canonical upsert.
"""

from __future__ import annotations

import re
import unicodedata

# Regional cuisine keywords -> region_tag. First match wins.
_REGION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Gujarati", ("gujarati", "kathiyawadi", "surti")),
    ("Punjabi", ("punjabi", "amritsar", "dhaba")),
    ("South Indian", ("south indian", "udupi", "dosa", "idli", "madras", "chettinad")),
    ("Telugu", ("telugu", "andhra", "hyderabad", "hyderabadi")),
    ("Tamil", ("tamil", "chettinad")),
    ("Bengali", ("bengali", "kolkata", "calcutta")),
    ("Kerala", ("kerala", "malabar", "mallu")),
    ("Indo-Chinese", ("indo chinese", "indo-chinese", "hakka")),
    ("Mughlai", ("mughlai", "mughal", "awadhi", "lucknow")),
    ("Rajasthani", ("rajasthani", "marwari")),
]

_DIETARY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("jain", ("jain",)),
    ("vegan", ("vegan",)),
    ("vegetarian", ("vegetarian", "veg ", "pure veg", "shakahari")),
    ("halal", ("halal", "zabiha")),
]


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_name(name: str) -> str:
    name = _strip_accents(name or "").lower()
    name = re.sub(r"[^a-z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"[^\d+]", "", phone)
    return digits or None


def natural_key(name: str, lat: float | None, lng: float | None) -> str:
    """Dedup fingerprint: normalized name + coords rounded to ~110m."""
    base = normalize_name(name)
    if lat is not None and lng is not None:
        return f"{base}@{round(lat, 3)},{round(lng, 3)}"
    return base


def _infer_region(text: str) -> str | None:
    for tag, keywords in _REGION_KEYWORDS:
        if any(k in text for k in keywords):
            return tag
    return None


def _infer_dietary(text: str) -> list[str]:
    tags = [tag for tag, keywords in _DIETARY_KEYWORDS if any(k in text for k in keywords)]
    return sorted(set(tags))


def clean(candidate: dict) -> dict:
    """Turn a raw candidate into a canonical-shaped, enriched record."""
    name = (candidate.get("name") or "").strip()
    lat = candidate.get("lat")
    lng = candidate.get("lng")

    haystack = " ".join(
        str(candidate.get(f) or "")
        for f in ("name", "cuisine_type", "address_full", "description")
    ).lower()

    record = {
        "natural_key": natural_key(name, lat, lng),
        "name": name,
        "address_full": (candidate.get("address_full") or "").strip() or None,
        "city": candidate.get("city"),
        "state": candidate.get("state"),
        "country": candidate.get("country") or "USA",
        "lat": lat,
        "lng": lng,
        "phone": normalize_phone(candidate.get("phone")),
        "website": candidate.get("website"),
        "menu_url": candidate.get("menu_url"),
        "hours_json": candidate.get("hours_json"),
        "cuisine_type": candidate.get("cuisine_type") or "Indian",
        "region_tag": candidate.get("region_tag") or _infer_region(haystack),
        "dietary_tags": candidate.get("dietary_tags") or _infer_dietary(haystack),
        "price_range": candidate.get("price_range"),
        "delivery_partners": candidate.get("delivery_partners") or [],
        "festival_specials": candidate.get("festival_specials"),
        "source_name": candidate.get("source_name"),
        "source_url": candidate.get("source_url"),
        "source_id": candidate.get("source_id"),
    }
    record["confidence_score"] = score(record)
    return record


def score(record: dict) -> float:
    """Confidence in [0, 1], weighted by completeness of high-value fields."""
    weights = {
        "name": 0.25,
        "lat": 0.15,
        "address_full": 0.15,
        "phone": 0.15,
        "website": 0.10,
        "city": 0.10,
        "cuisine_type": 0.10,
    }
    total = 0.0
    for field, weight in weights.items():
        value = record.get(field)
        if value not in (None, "", [], {}):
            total += weight
    return round(min(total, 1.0), 3)
