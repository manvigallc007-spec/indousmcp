"""Owner-initiated business lookup — prefill a new listing from PRIMARY public sources only.

When a signed-in owner types their business name + state + city, we try to fill the rest for them
to verify: OpenStreetMap (Nominatim) for the named place's address / coords / website / phone /
hours, then the business's OWN website (via web_enrich) for a photo and extra details. We never
query third-party commercial directories — this is the same legal line as the data-source policy.
Everything degrades gracefully to "just what the owner typed" on any failure.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import settings


def _nominatim_place(name: str, city: str, state: str) -> dict | None:
    """Look up a NAMED place on OSM Nominatim with address + extra tags (website/phone/hours)."""
    q = ", ".join(p for p in (name, city, state, "USA") if p and p.strip())
    try:
        r = httpx.get("https://nominatim.openstreetmap.org/search",
                      params={"q": q, "format": "json", "limit": 1, "countrycodes": "us",
                              "addressdetails": 1, "extratags": 1},
                      headers={"User-Agent": settings.scraper_user_agent}, timeout=8.0)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


def _parse_place(place: dict | None, name: str, city: str, state: str) -> dict[str, Any]:
    """Pure: turn a Nominatim result into our candidate fields. Falls back to what the owner typed."""
    out: dict[str, Any] = {"name": (name or "").strip(),
                           "city": (city or "").strip(), "state": (state or "").strip()}
    if not place:
        return out
    try:
        out["lat"], out["lng"] = float(place["lat"]), float(place["lon"])
    except (KeyError, TypeError, ValueError):
        pass
    addr = place.get("address") or {}
    street = " ".join(x for x in (addr.get("house_number"), addr.get("road")) if x)
    if street:
        out["address_full"] = street
    if not out["city"]:
        out["city"] = addr.get("city") or addr.get("town") or addr.get("village") or ""
    ex = place.get("extratags") or {}
    if ex.get("website") or ex.get("contact:website"):
        out["website"] = ex.get("website") or ex.get("contact:website")
    if ex.get("phone") or ex.get("contact:phone"):
        out["phone"] = ex.get("phone") or ex.get("contact:phone")
    if ex.get("opening_hours"):
        out["hours"] = ex["opening_hours"]
    return out


def lookup(name: str, city: str, state: str, vertical: str | None = None) -> dict[str, Any]:
    """Best-effort prefill for the vendor onboarding form. Never raises."""
    out = _parse_place(_nominatim_place(name, city, state), name, city, state)
    if out.get("website"):                       # enrich from the business's OWN page
        try:
            from . import web_enrich
            sig = web_enrich._fetch_and_extract(out["website"])
            if sig.get("photo_url"):
                out["photo_url"] = sig["photo_url"]
            if sig.get("phone") and not out.get("phone"):
                out["phone"] = sig["phone"]
            if sig.get("email"):
                out["email"] = sig["email"]
        except Exception:
            pass
    if not out.get("lat"):                       # fallback: geocode the locality for coords
        try:
            from . import geocode
            pt = geocode.coords_for(out.get("address_full"), out.get("city"), out.get("state"))
            if pt:
                out["lat"], out["lng"] = pt
        except Exception:
            pass
    return out
