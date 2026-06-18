"""Extract searchable keyword tags (dishes, attributes) from a record.

Tags improve both keyword filtering (agents can filter `tag="biryani"`) and embedding
recall (they're appended to the embedded text). Derived only from known fields — no guessing.
"""

from __future__ import annotations

import re

# canonical tag -> substrings that imply it (matched against name + description + cuisine).
_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "biryani": ("biryani", "biriyani", "briyani", "dum biryani", "kacchi", "hyderabadi", "ambur"),
    "dosa": ("dosa",),
    "idli": ("idli",),
    "chaat": ("chaat", "chat house", "golgappa", "pani puri"),
    "tandoori": ("tandoor",),
    "thali": ("thali",),
    "curry": ("curry",),
    "samosa": ("samosa",),
    "kebab": ("kebab", "kabob"),
    "sweets": ("sweet", "mithai", "halwa", "jalebi"),
    "chai": ("chai", "tea house"),
    "paratha": ("paratha",),
    "paneer": ("paneer",),
    "biriyani": (),  # alias collapsed above
    "buffet": ("buffet",),
    "catering": ("catering", "caterer", "cater", "party order", "bulk order"),
    "tiffin": ("tiffin", "dabba", "meal service", "lunch box", "meal plan"),
    "indo-chinese": ("indo chinese", "indo-chinese", "hakka", "manchurian", "schezwan"),
    "vegan": ("vegan",),
    "vegetarian": ("vegetarian", "pure veg", "shakahari"),
    "halal": ("halal", "zabiha"),
    "jain": ("jain",),
    "spices": ("spice", "masala"),
    "produce": ("produce", "vegetable", "subzi", "sabzi"),
    "frozen": ("frozen",),
    "supermarket": ("supermarket", "cash & carry", "cash and carry", "hypermarket"),
}


_SALON_TAGS: dict[str, tuple[str, ...]] = {
    "threading": ("thread",),
    "brows": ("brow", "eyebrow"),
    "henna": ("henna",),
    "mehndi": ("mehndi", "mehendi"),
    "bridal": ("bridal", "wedding"),
    "waxing": ("wax",),
    "facial": ("facial", "spa"),
    "hair": ("hair", "salon"),
    "makeup": ("makeup", "make-up", "glam"),
}


_APPAREL_TAGS: dict[str, tuple[str, ...]] = {
    "saree": ("saree", "sari", "saris"), "lehenga": ("lehenga", "lehnga"),
    "salwar": ("salwar", "anarkali"), "sherwani": ("sherwani",), "kurta": ("kurta", "kurti"),
    "bridal": ("bridal", "wedding", "dulhan"), "ethnic-wear": ("ethnic", "vastra", "pehnava"),
    "jewelry": ("jewel", "jewell", "bangle", "zari"), "gold": ("gold", "sona", "sonar"),
    "tailoring": ("tailor", "stitch", "alteration"), "textiles": ("fabric", "silk", "textile"),
}
_SWEETS_TAGS: dict[str, tuple[str, ...]] = {
    "mithai": ("mithai", "mishtan", "misthan", "sweet"), "halwa": ("halwa", "halwai"),
    "jalebi": ("jalebi",), "laddu": ("laddu", "ladoo"), "barfi": ("barfi", "burfi"),
    "rasmalai": ("rasmalai", "rasgulla", "rasagulla"), "gulab-jamun": ("gulab",),
    "bakery": ("bakery", "bakers", "pastry"), "eggless": ("eggless",), "kaju": ("kaju",),
}
_STUDIO_TAGS: dict[str, tuple[str, ...]] = {
    "yoga": ("yoga",), "bharatanatyam": ("bharatanatyam", "bharata", "bharat natyam", "natyam"),
    "kathak": ("kathak",), "kuchipudi": ("kuchipudi",), "odissi": ("odissi",),
    "dance": ("dance", "nritya", "nataraj", "abhinaya"), "tabla": ("tabla",),
    "sitar": ("sitar",), "veena": ("veena",), "carnatic": ("carnatic",),
    "hindustani": ("hindustani",), "music": ("music", "sangeet", "raga", "vocal"),
    "language": ("hindi", "tamil", "telugu", "language", "sanskrit"),
}
_SERVICE_TAGS: dict[str, tuple[str, ...]] = {
    "money-transfer": ("remit", "money transfer", "money2india", "xpress money", "ria money",
                       "western union", "wire transfer"),
    "forex": ("forex", "currency exchange", "bureau"), "bank": ("bank",),
    "immigration": ("immigration", "visa", "green card", "citizenship"),
    "travel": ("travel", "yatra", "tours", "flights", "airfare"),
    "tax": ("tax", "cpa", "accountant", "bookkeep"), "insurance": ("insurance",),
}


# Human-facing amenity / dietary / service chips (Part A patterns 8/10/14). Dish tags (biryani,
# dosa…) are intentionally omitted from display — they're implied by the search query itself.
_DISPLAY_TAGS: dict[str, str] = {
    "vegetarian": "🥗 Veg", "vegan": "🌱 Vegan", "halal": "☪️ Halal", "jain": "Jain",
    "gluten-free": "Gluten-free", "eggless": "Eggless",
    "delivery": "🛵 Delivery", "takeout": "🥡 Takeout", "catering": "🍱 Catering",
    "tiffin": "🍱 Tiffin", "buffet": "🍽️ Buffet", "reservations": "📅 Reservations",
    "outdoor-seating": "☀️ Outdoor seating", "drive-thru": "🚗 Drive-thru",
    "wheelchair-accessible": "♿ Accessible", "wifi": "📶 Wi-Fi", "air-conditioned": "❄️ A/C",
    "cards-accepted": "💳 Cards", "organic": "🌿 Organic", "smoke-free": "🚭 Smoke-free",
    "money-transfer": "💸 Money transfer", "immigration": "🛂 Immigration", "travel": "✈️ Travel",
}


def for_display(tags, limit: int = 6) -> list[str]:
    """Curated, human-friendly amenity/dietary/service chips from a record's tags (skips dish tags).
    These come from OSM attributes already captured at ingestion (see osm.attribute_tags)."""
    out: list[str] = []
    for t in (tags or []):
        lab = _DISPLAY_TAGS.get(str(t).lower())
        if lab and lab not in out:
            out.append(lab)
    return out[:limit]


# Common Indian languages (+ English) -> canonical Title-cased form, so owner/admin input stays tidy.
_LANG_CANON: dict[str, str] = {
    "telugu": "Telugu", "hindi": "Hindi", "tamil": "Tamil", "gujarati": "Gujarati",
    "punjabi": "Punjabi", "bengali": "Bengali", "kannada": "Kannada", "malayalam": "Malayalam",
    "marathi": "Marathi", "urdu": "Urdu", "english": "English", "odia": "Odia", "oriya": "Odia",
    "assamese": "Assamese", "konkani": "Konkani", "sanskrit": "Sanskrit", "nepali": "Nepali",
    "sindhi": "Sindhi", "bhojpuri": "Bhojpuri",
}


def parse_languages(value) -> list[str]:
    """Normalize owner/admin language input (a list, or a comma/semicolon/slash string) into a tidy,
    de-duplicated, Title-cased list. Unknown languages are kept (title-cased), not dropped."""
    items = ([str(x) for x in value] if isinstance(value, (list, tuple, set))
             else re.split(r"[,;/]+", str(value or "")))
    out: list[str] = []
    for raw in items:
        w = raw.strip()
        if not w:
            continue
        canon = _LANG_CANON.get(w.lower(), w.title())
        if canon not in out:
            out.append(canon)
    return out


def language_tags(langs) -> list[str]:
    """Searchable tags for spoken languages: 'Telugu' -> 'telugu-speaking' (folded into tags[])."""
    out: list[str] = []
    for lang in (langs or []):
        w = str(lang).strip().lower()
        if w and f"{w}-speaking" not in out:
            out.append(f"{w}-speaking")
    return out


def _match(text: str, table: dict[str, tuple[str, ...]]) -> set[str]:
    return {tag for tag, kws in table.items() if any(k in text for k in kws)}


def _from_keywords(text: str) -> list[str]:
    return [tag for tag, kws in _TAG_KEYWORDS.items() if kws and any(k in text for k in kws)]


def extract(vertical: str, rec: dict) -> list[str]:
    if vertical == "temples":
        # Temples: religious facets are the useful "tags".
        out = [rec.get("religion"), rec.get("denomination"), rec.get("deity"), rec.get("region_tag")]
        return sorted({str(x).lower() for x in out if x})
    if vertical == "professionals":
        out = [rec.get("profession_type"), rec.get("speciality")]
        return sorted({str(x).lower() for x in out if x})
    if vertical == "events":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "festival_specials")).lower()
        festivals = ("diwali", "holi", "navratri", "garba", "dandiya", "onam", "pongal",
                     "eid", "ganesh", "durga", "ugadi", "baisakhi", "dussehra", "raksha bandhan")
        found = {f for f in festivals if f in text}
        if rec.get("category"):
            found.add(rec["category"].lower())
        return sorted(found)
    if vertical == "salons":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "salon_type")).lower()
        found = {t for t, kws in _SALON_TAGS.items() if any(k in text for k in kws)}
        if rec.get("salon_type"):
            found.add(rec["salon_type"].lower())
        return sorted(found)
    if vertical == "apparel":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "store_type", "description")).lower()
        found = _match(text, _APPAREL_TAGS)
        if rec.get("store_type"):
            found.add(rec["store_type"].lower())
        return sorted(found)
    if vertical == "sweets":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "store_type", "description")).lower()
        found = _match(text, _SWEETS_TAGS) | {"sweets"}
        found.update(t.lower() for t in (rec.get("dietary_tags") or []))
        return sorted(found)
    if vertical == "studios":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "studio_type", "description")).lower()
        found = _match(text, _STUDIO_TAGS)
        if rec.get("studio_type"):
            found.add(rec["studio_type"].lower())
        return sorted(found)
    if vertical == "services":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "service_type", "description")).lower()
        found = _match(text, _SERVICE_TAGS)
        if rec.get("service_type"):
            found.add(rec["service_type"].lower())
        return sorted(found)
    if vertical == "community":
        out = [rec.get("org_type"), rec.get("region_tag")]
        return sorted({str(x).lower() for x in out if x})
    if vertical == "legal":
        out = [rec.get("legal_type"), rec.get("region_tag")]
        return sorted({str(x).lower() for x in out if x})
    if vertical == "education":
        out = [rec.get("edu_type"), rec.get("region_tag")]
        return sorted({str(x).lower() for x in out if x})
    if vertical == "realestate":
        out = [rec.get("realestate_type"), rec.get("region_tag")]
        return sorted({str(x).lower() for x in out if x})
    if vertical == "finance":
        out = [rec.get("finance_type"), rec.get("region_tag")]
        return sorted({str(x).lower() for x in out if x})

    text = " ".join(str(rec.get(f) or "") for f in (
        "name", "description", "cuisine_type", "store_type", "region_tag")).lower()
    tags = set(_from_keywords(text))
    tags.update(t.lower() for t in (rec.get("dietary_tags") or []))
    if rec.get("region_tag"):
        tags.add(rec["region_tag"].lower())
    return sorted(tags)[:15]
