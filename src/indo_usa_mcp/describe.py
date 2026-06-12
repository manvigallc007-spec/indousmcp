"""Generate a concise natural-language description per record.

LLM agents (and embeddings) retrieve far better on prose than on concatenated fields.
This builds one honest sentence from the structured data — no fabrication, only what's known.
"""

from __future__ import annotations


def _a(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _loc(rec: dict) -> str:
    parts = [p for p in (rec.get("city"), rec.get("state")) if p]
    return " in " + ", ".join(parts) if parts else ""


def _hours(rec: dict) -> str:
    h = rec.get("hours_json")
    raw = h.get("raw") if isinstance(h, dict) else None
    return f" Hours: {raw}." if raw else ""


def _restaurant(rec: dict) -> str:
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    cuisine = rec.get("cuisine_type") or "Indian"
    s = f"{rec.get('name', 'This restaurant')} is {_a(region or 'Indian')} {region}Indian restaurant{_loc(rec)}."
    if cuisine and cuisine.lower() not in ("indian",):
        s += f" Cuisine: {cuisine}."
    diet = rec.get("dietary_tags") or []
    if diet:
        s += f" Offers {', '.join(diet)} options."
    if rec.get("price_range"):
        s += f" Price: {rec['price_range']}."
    if rec.get("festival_specials"):
        s += f" Festival specials: {rec['festival_specials']}."
    return s + _hours(rec)


def _temple(rec: dict) -> str:
    rel = rec.get("religion") or "Hindu"
    kind = {"sikh": "Sikh gurdwara", "jain": "Jain temple"}.get(rel, "Hindu temple")
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    s = f"{rec.get('name', 'This temple')} is {_a(region or kind)} {region}{kind}{_loc(rec)}."
    if rec.get("denomination"):
        s += f" Denomination: {rec['denomination']}."
    if rec.get("deity"):
        s += f" Primary deity: {rec['deity']}."
    return s + _hours(rec)


def _grocery(rec: dict) -> str:
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    st = rec.get("store_type") or "store"
    s = f"{rec.get('name', 'This store')} is {_a(region or 'Indian')} {region}Indian grocery {st}{_loc(rec)}."
    diet = rec.get("dietary_tags") or []
    if diet:
        s += f" Carries {', '.join(diet)} products."
    return s + _hours(rec)


_BUILDERS = {"restaurants": _restaurant, "temples": _temple, "groceries": _grocery}


def describe(vertical: str, rec: dict) -> str:
    builder = _BUILDERS.get(vertical, _restaurant)
    return " ".join(builder(rec).split())
