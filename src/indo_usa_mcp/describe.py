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


def _apparel(rec: dict) -> str:
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    st = (rec.get("store_type") or "store").replace("_", " ")
    kind = {"jewelry": "jewelry store", "fabric": "fabric & textile store",
            "tailor": "tailoring shop", "boutique": "ethnic-wear boutique"}.get(st, "clothing store")
    s = f"{rec.get('name', 'This shop')} is {_a(region or 'Indian')} {region}Indian {kind}{_loc(rec)}."
    services = [t for t in (rec.get("tags") or [])
                if t in ("bridal", "saree", "lehenga", "gold", "jewelry", "tailoring", "textiles")]
    if services:
        s += f" Specializes in {', '.join(services)}."
    return s + _amenities(rec) + _hours(rec)


def _sweets(rec: dict) -> str:
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    st = rec.get("store_type") or "sweets"
    kind = {"bakery": "bakery", "pastry": "bakery"}.get(st, "sweets shop (mithai)")
    s = f"{rec.get('name', 'This shop')} is {_a(region or 'Indian')} {region}Indian {kind}{_loc(rec)}."
    diet = rec.get("dietary_tags") or []
    if diet:
        s += f" Offers {', '.join(diet)} options."
    return s + _amenities(rec) + _hours(rec)


def _studio(rec: dict) -> str:
    disc = (rec.get("studio_type") or "cultural").replace("_", " ")
    kind = {"yoga": "yoga studio", "dance": "Indian classical dance school",
            "music": "Indian music school", "language": "language school"}.get(disc, "cultural studio")
    s = f"{rec.get('name', 'This studio')} is {_a(kind)} {kind}{_loc(rec)}."
    disciplines = [t for t in (rec.get("tags") or [])
                   if t in ("yoga", "bharatanatyam", "kathak", "kuchipudi", "odissi", "tabla",
                            "sitar", "carnatic", "hindustani", "dance", "music")]
    if disciplines:
        s += f" Classes: {', '.join(disciplines)}."
    return s + _hours(rec)


def _service(rec: dict) -> str:
    st = (rec.get("service_type") or "service").replace("_", " ")
    kind = {"money transfer": "money transfer / remittance service", "bank": "bank",
            "immigration": "immigration & visa service", "travel": "travel agency",
            "tax": "tax & accounting service", "insurance": "insurance service"}.get(st, f"{st} service")
    s = f"{rec.get('name', 'This business')} is {_a(kind)} {kind} serving the Indian community{_loc(rec)}."
    return s + _hours(rec)


def _community(rec: dict) -> str:
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    ot = (rec.get("org_type") or "organization").replace("_", " ")
    kind = {"association": "community association", "cultural center": "cultural center",
            "student org": "student organization"}.get(ot, "community organization")
    s = (f"{rec.get('name', 'This organization')} is {_a(region or kind)} {region}"
         f"Indian-American {kind}{_loc(rec)}.")
    return s + _hours(rec)


def _legal(rec: dict) -> str:
    lt = (rec.get("legal_type") or "attorney").replace("_", " ")
    kind = {"immigration": "immigration law firm", "law firm": "law firm",
            "attorney": "attorney / law office"}.get(lt, "law office")
    s = (f"{rec.get('name', 'This firm')} is {_a(kind)} {kind} serving the Indian-American "
         f"community{_loc(rec)}.")
    return s + _hours(rec)


def _education(rec: dict) -> str:
    et = (rec.get("edu_type") or "school").replace("_", " ")
    region = f"{rec['region_tag']} " if rec.get("region_tag") else ""
    kind = {"language school": "language & heritage school", "heritage": "Indian heritage school",
            "tutoring": "tutoring & coaching center", "school": "school"}.get(et, "education center")
    s = (f"{rec.get('name', 'This center')} is {_a(region or kind)} {region}Indian-American "
         f"{kind}{_loc(rec)}.")
    return s + _hours(rec)


def _realestate(rec: dict) -> str:
    rt = (rec.get("realestate_type") or "agent").replace("_", " ")
    kind = {"agency": "real-estate agency", "mortgage": "mortgage & home-loan service",
            "agent": "real-estate agent"}.get(rt, "real-estate service")
    s = (f"{rec.get('name', 'This business')} is {_a(kind)} {kind} serving the Indian-American "
         f"community{_loc(rec)}.")
    return s + _hours(rec)


def _finance(rec: dict) -> str:
    ft = (rec.get("finance_type") or "accountant").replace("_", " ")
    kind = {"cpa": "CPA (certified public accountant)", "tax": "tax & accounting service",
            "financial advisor": "financial advisory service",
            "accountant": "accounting service"}.get(ft, "finance service")
    s = (f"{rec.get('name', 'This firm')} is {_a(kind)} {kind} serving the Indian-American "
         f"community{_loc(rec)}.")
    return s + _hours(rec)


_BUILDERS = {"restaurants": _restaurant, "temples": _temple, "groceries": _grocery,
             "professionals": _professional, "salons": _salon, "events": _event,
             "apparel": _apparel, "sweets": _sweets, "studios": _studio, "services": _service,
             "community": _community, "legal": _legal, "education": _education,
             "realestate": _realestate, "finance": _finance}


def _rating(rec: dict) -> str:
    r = rec.get("rating")
    if not r:
        return ""
    n = rec.get("rating_count")
    return f" Rated {r}/5 from {n} reviews." if n else f" Rated {r}/5."


def describe(vertical: str, rec: dict) -> str:
    builder = _BUILDERS.get(vertical, _restaurant)
    return " ".join((builder(rec) + _rating(rec)).split())
