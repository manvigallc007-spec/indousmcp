"""Normalize, enrich, deduplicate-fingerprint and score a candidate record.

Input is a source-agnostic dict produced by a scraper's `to_candidate()`. Output is
a canonical-shaped dict ready for the approval queue / canonical upsert.
"""

from __future__ import annotations

import re
import unicodedata

# Regional cuisine keywords -> region_tag. First match wins. Includes signature
# dishes/terms so generically-named restaurants still get a cultural tag.
_REGION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Gujarati", ("gujarati", "kathiyawadi", "surti", "kathiawadi", "dhokla", "thali house")),
    ("Punjabi", ("punjabi", "amritsar", "amritsari", "dhaba", "sardar", "pind", "lassi")),
    ("South Indian", ("south indian", "udupi", "dosa", "idli", "sambar", "uttapam",
                       "vada", "madras", "saravana", "tiffin", "woodlands")),
    ("Telugu", ("telugu", "andhra", "hyderabad", "hyderabadi", "godavari")),
    ("Tamil", ("tamil", "chettinad", "ponnusamy")),
    ("Bengali", ("bengali", "kolkata", "calcutta", "bengal")),
    ("Kerala", ("kerala", "malabar", "mallu", "thattukada")),
    ("Indo-Chinese", ("indo chinese", "indo-chinese", "hakka", "schezwan", "manchurian")),
    ("Mughlai", ("mughlai", "mughal", "awadhi", "lucknow", "nawab", "kebab", "biryani")),
    ("Rajasthani", ("rajasthani", "marwari")),
    ("North Indian", ("north indian", "tandoor", "tandoori", "curry house", "chaat",
                       "butter chicken", "naan", "masala")),
]

_DIETARY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("jain", ("jain",)),
    ("vegan", ("vegan",)),
    ("vegetarian", ("vegetarian", "veg ", "pure veg", "shakahari")),
    ("halal", ("halal", "zabiha")),
]


_US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
_STATE_CODES = set(_US_STATES.values())


def normalize_state(state: str | None) -> str | None:
    """Return the 2-letter USPS code for a US state ('California' -> 'CA'); pass through else."""
    if not state:
        return None
    s = state.strip()
    if s.upper() in _STATE_CODES:
        return s.upper()
    return _US_STATES.get(s.lower(), s)


def normalize_city(city: str | None) -> str | None:
    """Trim and title-case a city name ('  fremont ' -> 'Fremont')."""
    if not city:
        return None
    c = re.sub(r"\s+", " ", city).strip()
    return c.title() if c.islower() or c.isupper() else c


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


def infer_region(text: str) -> str | None:
    text = (text or "").lower()
    for tag, keywords in _REGION_KEYWORDS:
        if any(k in text for k in keywords):
            return tag
    return None


def infer_dietary(text: str) -> list[str]:
    text = (text or "").lower()
    tags = [tag for tag, keywords in _DIETARY_KEYWORDS if any(k in text for k in keywords)]
    return sorted(set(tags))


# Back-compat internal aliases.
_infer_region = infer_region
_infer_dietary = infer_dietary


def clean(candidate: dict) -> dict:
    """Turn a raw candidate into a canonical-shaped, enriched record."""
    name = (candidate.get("name") or "").strip()
    lat = candidate.get("lat")
    lng = candidate.get("lng")

    haystack = " ".join(
        str(candidate.get(f) or "")
        for f in ("name", "cuisine_type", "address_full", "description")
    ).lower()
    city, state = fill_location(candidate.get("city"), candidate.get("state"), lat, lng)

    record = {
        "natural_key": natural_key(name, lat, lng),
        "name": name,
        "address_full": (candidate.get("address_full") or "").strip() or None,
        "city": city,
        "state": state,
        "country": candidate.get("country") or "USA",
        "lat": lat,
        "lng": lng,
        "phone": normalize_phone(candidate.get("phone")),
        "email": (candidate.get("email") or "").strip().lower() or None,
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
    from .. import describe
    record["description"] = describe.describe("restaurants", record)
    record["confidence_score"] = score(record)
    return record


def fill_location(city, state, lat, lng) -> tuple:
    """Normalize city/state; reverse-geocode from coordinates to fill any gaps."""
    city, state = normalize_city(city), normalize_state(state)
    if (not city or not state) and lat is not None and lng is not None:
        from .. import geocode
        gc, gs = geocode.city_state(lat, lng)
        city = city or normalize_city(gc)
        state = state or normalize_state(gs)
    return city, state


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
