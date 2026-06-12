"""Extract searchable keyword tags (dishes, attributes) from a record.

Tags improve both keyword filtering (agents can filter `tag="biryani"`) and embedding
recall (they're appended to the embedded text). Derived only from known fields — no guessing.
"""

from __future__ import annotations

# canonical tag -> substrings that imply it (matched against name + description + cuisine).
_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "biryani": ("biryani", "biriyani"),
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
    "catering": ("catering", "caterer"),
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
    if vertical == "salons":
        text = " ".join(str(rec.get(f) or "") for f in ("name", "salon_type")).lower()
        found = {t for t, kws in _SALON_TAGS.items() if any(k in text for k in kws)}
        if rec.get("salon_type"):
            found.add(rec["salon_type"].lower())
        return sorted(found)

    text = " ".join(str(rec.get(f) or "") for f in (
        "name", "description", "cuisine_type", "store_type", "region_tag")).lower()
    tags = set(_from_keywords(text))
    tags.update(t.lower() for t in (rec.get("dietary_tags") or []))
    if rec.get("region_tag"):
        tags.add(rec["region_tag"].lower())
    return sorted(tags)[:15]
