"""Query synonym / alias expansion.

People — especially by voice — say the same thing many ways: "mandir" for temple, "OBGYN" for
gynecologist, "kirana" for grocery, "dabba" for tiffin, "biriyani" for biryani. We append the
canonical English term for any alias found in the query, so it (a) routes to the right category
(see assistant._guess_vertical / _VERTICAL_HINTS) and (b) embeds with strong semantic signal for the
fastembed vector search. Conservative — well-known, unambiguous aliases only; we never remove the
user's own words.
"""

from __future__ import annotations

# canonical term -> aliases. Canonicals are the plain English words search/embeddings know best.
# Avoid ambiguous short tokens (e.g. "md" = Maryland, "gp") and generic words ("store", "hotel").
_ALIASES: dict[str, tuple[str, ...]] = {
    "temple": ("mandir", "mandhir", "devalayam", "devasthanam", "kovil", "koil", "alayam"),
    "gurdwara": ("gurudwara", "sikh temple"),
    "mosque": ("masjid",),
    "jain temple": ("derasar", "basadi"),
    "doctor": ("physician", "practitioner"),
    "gynecologist": ("obgyn", "ob-gyn", "ob gyn", "gynaecologist", "womens doctor", "women's doctor"),
    "pediatrician": ("paediatrician", "child specialist", "kids doctor", "children's doctor",
                     "childrens doctor"),
    "dentist": ("dental clinic",),
    "pharmacy": ("chemist", "drug store", "drugstore", "medical store"),
    "grocery": ("kirana", "kirana store", "provision store", "indian store", "desi store",
                "indian groceries", "asian grocery"),
    "supermarket": ("cash and carry", "hypermarket"),
    "restaurant": ("eatery", "dhaba", "tiffin center", "tiffin centre"),
    "biryani": ("biriyani", "briyani", "dum biryani"),
    "dosa": ("dosai", "thosai"),
    "tiffin": ("dabba", "meal service", "lunch service", "lunch box"),
    "sweets": ("mithai", "sweet shop", "halwai"),
    "salon": ("parlour", "beauty parlour", "beauty parlor"),
    "accountant": ("cpa", "tax preparer", "tax consultant", "tax filing", "bookkeeper"),
    "immigration lawyer": ("immigration attorney", "visa lawyer", "green card lawyer", "h1b lawyer",
                           "h-1b lawyer"),
    "lawyer": ("attorney", "advocate", "vakil"),
    "realtor": ("real estate agent", "realestate agent", "real estate broker"),
    "yoga": ("yoga studio", "yoga class"),
    "dance class": ("bharatanatyam", "kuchipudi", "kathak"),
    "tutoring": ("tutor", "coaching", "tuition"),
    "money transfer": ("remittance", "send money to india", "money2india"),
    "jewelry": ("jewellery", "jeweller", "gold shop"),
    "saree": ("sari", "saree shop", "sari shop"),
    "priest": ("pandit", "pujari", "purohit", "panditji", "pandit ji"),
    "association": ("samaj", "sangam", "mandal", "sabha"),
    # dishes & food (normalize spellings + map a specific dish to a searchable term)
    "chaat": ("pani puri", "panipuri", "gol gappa", "golgappa", "puchka", "bhel puri", "bhelpuri",
              "sev puri", "sevpuri", "dahi puri"),
    "vada pav": ("vadapav", "wada pav"),
    "idli": ("idly",),
    "uttapam": ("uthappam", "uttappam"),
    "paratha": ("parantha", "parotta", "porotta"),
    "kebab": ("kabab", "seekh kebab", "kakori"),
    "chai": ("masala chai", "masala tea", "cutting chai"),
    "halal meat": ("zabiha", "halal butcher"),
    "mehndi": ("henna", "mehendi", "heena"),
    "langar": ("langar hall",),
    # apparel
    "lehenga": ("lehnga", "ghagra", "lehenga choli"),
    "salwar kameez": ("salwar", "shalwar", "salwar suit", "punjabi suit"),
    "kurta": ("kurti", "kurta pajama"),
    # professionals (specific -> general)
    "cardiologist": ("heart doctor", "heart specialist"),
    "dermatologist": ("skin doctor", "skin specialist"),
    "optometrist": ("eye doctor", "eye specialist", "optician"),
    "orthopedic": ("bone doctor", "orthopaedic surgeon"),
    # services
    "travel agent": ("travel agency", "tours and travels"),
}

# alias -> canonical, longest alias first so multi-word phrases match before their parts.
_ALIAS_TO_CANON: list[tuple[str, str]] = sorted(
    ((a, c) for c, al in _ALIASES.items() for a in al), key=lambda kv: -len(kv[0]))


def expand(query: str) -> str:
    """Append the canonical term for any whole-word alias in the query. Never removes user words;
    caps additions to keep the query focused. Returns the query unchanged when nothing matches."""
    if not query or len(query) > 300:
        return query
    low = " " + query.lower() + " "
    added: list[str] = []
    for alias, canon in _ALIAS_TO_CANON:
        if canon in low:                              # canonical already present -> skip its aliases
            continue
        if (" " + alias + " ") in low:                # whole-word alias match
            added.append(canon)
            low += canon + " "                        # reflect it so dupes/related aliases are skipped
            if len(added) >= 4:
                break
    return (query + " " + " ".join(added)) if added else query
