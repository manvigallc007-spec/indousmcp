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
