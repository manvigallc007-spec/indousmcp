"""Owner-initiated business lookup — prefill a new listing from PRIMARY public sources only.

When a signed-in owner types their business name + state + city, we try to fill the rest for them
to verify: OpenStreetMap (Nominatim) for the named place's address / coords / website / phone /
hours, then the business's OWN website (via web_enrich) for a photo and extra details. We never
query third-party commercial directories — this is the same legal line as the data-source policy.
Everything degrades gracefully to "just what the owner typed" on any failure.
"""

from __future__ import annotations

import json
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


def lookup(name: str, city: str, state: str, vertical: str | None = None,
           website: str | None = None) -> dict[str, Any]:
    """Best-effort prefill for the vendor onboarding form. Never raises. A `website` the owner typed
    is preferred over one OSM happens to know — this is what makes 'paste your website' actually work."""
    out = _parse_place(_nominatim_place(name, city, state), name, city, state)
    typed = (website or "").strip()
    if typed:
        out["website"] = typed
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
            # Structured facets the scraper already parses (previously discarded) — better than an
            # LLM guess where available, and feeds ai_fill's prompt where not.
            if sig.get("site_description"):
                out["site_description"] = sig["site_description"]
            if sig.get("menu_url"):
                out["menu_url"] = sig["menu_url"]
            if sig.get("price_range"):
                out["price_range"] = sig["price_range"]
            if sig.get("cuisine_tags"):          # e.g. ["south indian","chettinad"] -> "South Indian"
                out["cuisine_type"] = ", ".join(c.title() for c in sig["cuisine_tags"][:2])
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


# ------------------------------------------------------------------- LLM structured field-fill
# ONLY categorical/descriptive fields may be LLM-filled. Contact + location facts (phone, email,
# website, address, city, state, menu_url) are NEVER in this set — asking a model to invent a phone
# number or street address would violate the grounded-only rule the codebase enforces everywhere.
# Allow-list (fail-safe: a field not here simply isn't AI-filled — the owner types it, no harm).
_AI_FILL_TARGETABLE = frozenset({
    "cuisine_type", "region_tag", "price_range", "festival_specials", "religion", "denomination",
    "deity", "store_type", "profession_type", "speciality", "salon_type", "studio_type",
    "service_type", "org_type", "legal_type", "edu_type", "realestate_type", "finance_type",
})
_FIELD_HINTS: dict[str, str] = {
    "cuisine_type": 'the cuisine style/region, e.g. "North Indian", "South Indian", "Gujarati"',
    "region_tag": 'the Indian regional community it serves, e.g. "Gujarati", "Punjabi", "Telugu"',
    "price_range": 'price level as "$", "$$", or "$$$"',
    "festival_specials": "any festival/seasonal specialty mentioned, else empty",
    "religion": 'the religion, e.g. "Hindu", "Sikh", "Jain"',
    "denomination": "the denomination or tradition, if any",
    "deity": "the primary deity, if a temple",
    "store_type": 'the kind of store, e.g. "grocery", "sweets", "jewelry", "apparel"',
    "profession_type": 'the profession, e.g. "doctor", "dentist", "lawyer", "accountant"',
    "speciality": "the specialty within the profession",
    "salon_type": 'the kind of salon, e.g. "hair", "threading", "spa"',
    "studio_type": 'the kind of studio, e.g. "yoga", "dance", "music"',
    "service_type": 'the kind of service, e.g. "travel", "money transfer", "immigration"',
    "org_type": 'the kind of organization, e.g. "cultural association", "sangam", "mandal"',
    "legal_type": 'the legal specialty, e.g. "immigration", "family law"',
    "edu_type": 'the kind of education, e.g. "tutoring", "language school", "test prep"',
    "realestate_type": 'the real-estate specialty, e.g. "realtor", "mortgage broker"',
    "finance_type": 'the finance specialty, e.g. "CPA", "tax preparer", "financial advisor"',
    "dietary_tags": "comma-separated from {vegetarian, vegan, halal, jain}, or empty",
    "languages": "comma-separated languages served, or empty",
}
_AI_FILL_SYS = (
    "You help prefill an intake form for a US directory of Indian-American businesses. You are given a "
    "business name, category, location, and maybe a short excerpt from its own website. Use ONLY the "
    "information given below — never invent, guess, or assume anything not present in it. Fill ONLY the "
    "requested fields; if a field can't be determined from what's given, use an empty string. Output "
    "STRICT JSON ONLY: one object with exactly the requested keys and no others — no markdown fences, "
    "no explanation, no extra text.")


def _strip_json(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def ai_fill(vertical: str, record: dict) -> dict:
    """LLM-fill the CATEGORICAL fields still missing on a prefilled record (grounded, allow-listed).
    No-op without an LLM. Returns the record (possibly with more fields); never raises."""
    from . import assistant, verticals
    if not assistant.llm_active() or vertical not in verticals.VERTICALS:
        return record
    cfg = verticals.VERTICALS[vertical]

    def _empty(f):
        v = record.get(f)
        return not (str(v).strip() if v is not None else "")
    missing = [f for f in cfg["edit_fields"] if f in _AI_FILL_TARGETABLE and _empty(f)]
    if cfg.get("has_dietary") and _empty("dietary_tags"):
        missing.append("dietary_tags")
    if _empty("languages"):
        missing.append("languages")
    if not missing:
        return record

    lines = [f"Business name: {record.get('name', '')}",
             f"Category: {cfg['label']}",
             f"Location: {record.get('city', '')}, {record.get('state', '')}"]
    if record.get("site_description"):
        lines.append(f"Website excerpt: {record['site_description']}")
    lines.append("\nFill these fields as a JSON object:")
    for f in missing:
        lines.append(f"- {f}: {_FIELD_HINTS.get(f, f'the value for {f}')}")
    try:
        raw = assistant.complete_text(_AI_FILL_SYS, "\n".join(lines))
        parsed = json.loads(_strip_json(raw or ""))
    except Exception:
        return record
    if not isinstance(parsed, dict):
        return record
    for f in missing:                            # merge ONLY requested, non-empty keys (drop the rest)
        val = parsed.get(f)
        if isinstance(val, str) and val.strip():
            record[f] = val.strip()
    return record
