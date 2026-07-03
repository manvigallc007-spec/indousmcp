"""Extract searchable attribute tags from raw OSM tags.

OSM carries lots of useful, filterable attributes (delivery, takeaway, outdoor seating,
wheelchair access, dietary, payment) that the scrapers can turn into tags — enriching both
keyword filtering (agents can filter tag="delivery") and embedding recall.
"""

from __future__ import annotations

import time

import httpx

from .config import settings


class OverpassError(RuntimeError):
    """Raised when Overpass stays unavailable after retries (so callers can degrade cleanly)."""


_RETRY_STATUS = {429, 502, 503, 504}


# --- diaspora guardrail -------------------------------------------------------------------
# This directory is for Indians FROM INDIA living in the USA. "Indian" is ambiguous, so these
# NAME signals mark the homonyms we must NOT ingest: American Indian / Native American (the main
# false positive), West Indian (Caribbean), and the "Indian" motorcycle/place brand. Matched as
# case-insensitive substrings of the name only, so genuine India-diaspora names are never hit.
_EXCLUDE_TERMS = (
    "american indian", "native american", "native indian", "amerindian",
    "first nations", "first nation", "indian reservation", "indian tribe", "indian tribal",
    "tribal council", "indian nation", "indigenous", "indian health service",
    "bureau of indian affairs", "indian affairs", "powwow", "pow wow", "pow-wow",
    "west indian", "indian motorcycle",
)


def is_excluded_name(name: str | None) -> bool:
    """True if a place NAME signals a non-India-diaspora 'Indian' (Native American / West Indian
    / 'Indian' brand). Scrapers and the manual-add path reject these so the directory stays
    focused on Indians from India living in the USA."""
    n = (name or "").lower()
    return any(term in n for term in _EXCLUDE_TERMS)


def overpass_post(query: str, timeout: float, retries: int = 3, base_delay: float = 5.0) -> dict:
    """POST an Overpass query with retry + exponential backoff on rate-limits/timeouts
    (429/502/503/504 and network timeouts). Returns parsed JSON. Raises OverpassError only
    after exhausting retries — so a transient blip slows a scrape down instead of crashing it.
    """
    headers = {"User-Agent": settings.scraper_user_agent}
    last = "unknown error"
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(settings.overpass_url, data={"data": query},
                              headers=headers, timeout=timeout)
            if resp.status_code in _RETRY_STATUS:
                last = f"HTTP {resp.status_code}"
            else:
                resp.raise_for_status()
                return resp.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = type(exc).__name__
        if attempt < retries:
            time.sleep(base_delay * (2 ** attempt))  # 5s, 10s, 20s
    raise OverpassError(f"Overpass unavailable after {retries + 1} attempts ({last})")


# osm key -> (our tag, accepted values)
_ATTR: dict[str, tuple[str, tuple[str, ...]]] = {
    "takeaway": ("takeout", ("yes", "only")),
    "delivery": ("delivery", ("yes",)),
    "outdoor_seating": ("outdoor-seating", ("yes",)),
    "wheelchair": ("wheelchair-accessible", ("yes", "limited")),
    "drive_through": ("drive-thru", ("yes",)),
    "internet_access": ("wifi", ("wlan", "yes", "wired")),
    "reservation": ("reservations", ("yes", "required", "recommended")),
    "air_conditioning": ("air-conditioned", ("yes",)),
    "organic": ("organic", ("yes", "only")),
    "smoking": ("smoke-free", ("no",)),
}
_DIET = {"diet:vegan": "vegan", "diet:vegetarian": "vegetarian",
         "diet:halal": "halal", "diet:jain": "jain", "diet:gluten_free": "gluten-free"}
_PAYMENT = ("payment:cards", "payment:credit_cards", "payment:debit_cards", "payment:visa")


def attribute_tags(tags: dict) -> list[str]:
    out: list[str] = []
    for key, (label, vals) in _ATTR.items():
        if (tags.get(key) or "").lower() in vals:
            out.append(label)
    for key, label in _DIET.items():
        if (tags.get(key) or "").lower() in ("yes", "only"):
            out.append(label)
    if any((tags.get(k) or "").lower() == "yes" for k in _PAYMENT):
        out.append("cards-accepted")
    return sorted(set(out))


# --- verification: look up OSM near an EXISTING listing's coordinates -----------------------
def nearby_named(lat: float, lng: float, radius_m: int = 300, timeout: float = 25.0) -> list[dict]:
    """Named OSM POIs within `radius_m` of a point — used to VERIFY a listing we got from another
    source (IRS/NPPES/submissions) against OpenStreetMap. Returns raw Overpass elements (each carries
    `tags` and `lat`/`lon` or `center`). Reuses `overpass_post` (retry/backoff). Raises OverpassError
    if Overpass stays down, so the caller can stop politely."""
    q = (f"[out:json][timeout:{int(timeout)}];\n"
         f'nwr(around:{int(radius_m)},{lat},{lng})["name"];\n'
         f"out center tags;")
    return overpass_post(q, timeout=timeout + 5).get("elements", []) or []


def contact_from_tags(tags: dict) -> dict:
    """Pull the enrichable contact facets from an OSM element's tags: phone, website, opening hours,
    and the attribute tags. Values are None/empty when absent so callers fill-missing only."""
    tags = tags or {}
    return {
        "phone": (tags.get("contact:phone") or tags.get("phone") or "").strip() or None,
        "website": (tags.get("contact:website") or tags.get("website") or "").strip() or None,
        "hours": (tags.get("opening_hours") or "").strip() or None,
        "tags": attribute_tags(tags),
    }
