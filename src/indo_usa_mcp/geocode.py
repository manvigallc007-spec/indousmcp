"""Geocoding helpers (free, no API key).

- Reverse (coords -> city/state): offline `reverse_geocoder` (bundled GeoNames data).
- Forward (address -> coords): OpenStreetMap Nominatim (online, free; max ~1 req/s, needs a
  descriptive User-Agent). Used to give address-only listings (admin-adds / owner submissions)
  coordinates so they're sortable by distance. Cached; degrades to None on any failure.
"""

from __future__ import annotations

import httpx

from .config import settings

_rg = None
_unavailable = False
_FWD_CACHE: dict[str, tuple[float, float] | None] = {}


def _census_geocode(query: str) -> tuple[float, float] | None:
    """Official US Census geocoder — free, no key, no rate limit; best on full street addresses."""
    try:
        r = httpx.get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
                      params={"address": query, "benchmark": "Public_AR_Current", "format": "json"},
                      headers={"User-Agent": settings.scraper_user_agent}, timeout=8.0)
        if r.status_code == 200:
            matches = (r.json().get("result", {}) or {}).get("addressMatches", []) or []
            if matches:
                c = matches[0].get("coordinates", {}) or {}
                if c.get("y") is not None and c.get("x") is not None:
                    return (float(c["y"]), float(c["x"]))   # y=lat, x=lng
    except Exception:
        pass
    return None


def _nominatim_geocode(query: str) -> tuple[float, float] | None:
    """OSM Nominatim — free; handles city/state-only queries the Census geocoder can't."""
    try:
        r = httpx.get("https://nominatim.openstreetmap.org/search",
                      params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
                      headers={"User-Agent": settings.scraper_user_agent}, timeout=8.0)
        if r.status_code == 200:
            data = r.json()
            if data:
                return (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception:
        pass
    return None


def coords_for(address: str | None = None, city: str | None = None, state: str | None = None,
               country: str = "USA") -> tuple[float, float] | None:
    """Forward-geocode a US address/locality to (lat, lng). Tries the official Census geocoder when
    a street address is present (free, fast, no rate limit), else OSM Nominatim. Cached; None on
    failure."""
    locality = [str(p).strip() for p in (address, city, state) if p and str(p).strip()]
    if not locality:   # nothing specific to geocode (country alone is useless) -> skip the call
        return None
    query = ", ".join(locality + ([country] if country else []))
    key = query.lower()
    if key in _FWD_CACHE:
        return _FWD_CACHE[key]
    has_street = any(ch.isdigit() for ch in (address or ""))   # Census needs a street address
    point = (_census_geocode(query) if has_street else None) or _nominatim_geocode(query)
    _FWD_CACHE[key] = point
    return point


def _geocoder():
    global _rg, _unavailable
    if _rg is None and not _unavailable:
        try:
            import reverse_geocoder  # noqa: lazy + heavy (loads a k-d tree on first use)
            _rg = reverse_geocoder
        except Exception:
            _unavailable = True
    return _rg


def city_state(lat, lng) -> tuple[str | None, str | None]:
    """Return (city, state_name) for a US coordinate, or (None, None) if unavailable."""
    if lat is None or lng is None:
        return (None, None)
    rg = _geocoder()
    if rg is None:
        return (None, None)
    try:
        r = rg.search([(float(lat), float(lng))], mode=1)[0]
        return (r.get("name") or None, r.get("admin1") or None)
    except Exception:
        return (None, None)
