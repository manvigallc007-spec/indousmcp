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


_AMENITY_LABELS = {
    "delivery": "delivery", "takeout": "takeout", "outdoor-seating": "outdoor seating",
    "wheelchair-accessible": "wheelchair accessible", "wifi": "free wifi",
    "cards-accepted": "cards accepted", "drive-thru": "drive-thru",
    "reservations": "reservations", "organic": "organic",
}


def _amenities(rec: dict) -> str:
    present = [lab for tag, lab in _AMENITY_LABELS.items() if tag in (rec.get("tags") or [])]
    return f" Amenities: {', '.join(present)}." if present else ""


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
    return s + _amenities(rec) + _hours(rec)


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
    return s + _amenities(rec) + _hours(rec)


def _professional(rec: dict) -> str:
    ptype = (rec.get("profession_type") or "healthcare provider").replace("_", " ")
    kind = {"doctors": "doctor", "dentist": "dentist", "clinic": "clinic",
            "pharmacy": "pharmacy"}.get(ptype, ptype)
    s = f"{rec.get('name', 'This practice')} is {_a(kind)} {kind} (Indian-American){_loc(rec)}."
    if rec.get("speciality"):
        s += f" Speciality: {rec['speciality'].replace('_', ' ')}."
    return s + _hours(rec)


def _salon(rec: dict) -> str:
    services = [t for t in (rec.get("tags") or [])
               if t in ("threading", "henna", "mehndi", "brows", "bridal", "waxing",
                        "facial", "hair", "makeup")]
    s = f"{rec.get('name', 'This salon')} is an Indian beauty salon{_loc(rec)}."
    if services:
        s += f" Services: {', '.join(services)}."
    return s + _amenities(rec) + _hours(rec)


def _event(rec: dict) -> str:
    cat = rec.get("category") or "community"
    s = f"{rec.get('name', 'This event')} is {_a(cat)} {cat} event"
    if rec.get("venue_name"):
        s += f" at {rec['venue_name']}"
    s += _loc(rec) + "."
    start = rec.get("start_at")
    if start is not None:
        when = start.strftime("%B %d, %Y") if hasattr(start, "strftime") else str(start)[:10]
        s += f" Date: {when}."
    if rec.get("organizer"):
        s += f" Organizer: {rec['organizer']}."
    return s


_BUILDERS = {"restaurants": _restaurant, "temples": _temple, "groceries": _grocery,
             "professionals": _professional, "salons": _salon, "events": _event}


def describe(vertical: str, rec: dict) -> str:
    builder = _BUILDERS.get(vertical, _restaurant)
    return " ".join(builder(rec).split())
