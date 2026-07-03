"""Reusable schema.org JSON-LD builders (SEO rich results + AI answer engines).

These complement the schema already emitted elsewhere (Organization, WebSite+SearchAction,
LocalBusiness/AggregateRating, ItemList, Event). Output is a ready-to-embed <script> tag with the
unsafe '<' escaped so the JSON can't break out into the HTML.
"""

from __future__ import annotations

import json
import re
from collections import Counter

# vertical -> the schema.org sub-type that best fits it. A generic "LocalBusiness" is valid schema.org
# but misses out on richer SERP treatment (cuisine/price/hours snippets) that a specific type unlocks.
# "services" stays generic on purpose — it's genuinely a mixed bag (remittance, travel, consulates...)
# with no single closer schema.org type. Unmapped/future verticals fall back to LocalBusiness, never KeyError.
SCHEMA_TYPE: dict[str, str] = {
    "restaurants": "Restaurant", "temples": "PlaceOfWorship", "groceries": "GroceryStore",
    "professionals": "MedicalBusiness", "salons": "HairSalon", "apparel": "Store", "sweets": "Store",
    "studios": "ExerciseGym", "services": "LocalBusiness", "community": "Organization",
    "legal": "LegalService", "education": "EducationalOrganization", "realestate": "RealEstateAgent",
    "finance": "FinancialService", "events": "Event",
}


def schema_type(vertical: str) -> str:
    return SCHEMA_TYPE.get(vertical, "LocalBusiness")


# Category-ish fields worth surfacing in a meta description when a page's listings share them — the
# same field set ranking._CAT_FIELDS treats as a listing's "category identity" (cuisine, religion,
# specialty, ...). Kept as a literal copy (not an import) to avoid a web -> ranking -> db import chain
# for what's a tiny, stable constant.
_FACET_FIELDS = ("cuisine_type", "store_type", "salon_type", "studio_type", "service_type",
                 "profession_type", "speciality", "religion", "denomination", "region_tag", "category")


def facet_select_cols(table_columns: set[str]) -> list[str]:
    """Which _FACET_FIELDS actually exist on a given vertical's table (e.g. `cuisine_type` on
    restaurants, `religion` on temples) -- for splicing into a hand-written column-list SELECT (the
    query helpers list columns explicitly rather than `SELECT *`, so a facet column has to be added
    explicitly too, or top_facets()/primary_facet() have nothing to read)."""
    return [c for c in _FACET_FIELDS if c in table_columns]


def top_facets(rows: list[dict], k: int = 3) -> list[str]:
    """The k most common non-null category values across a page's listings (e.g. cuisines on a
    restaurant city page) — for a short, DATA-DERIVED meta-description clause instead of a static
    injected keyword list, so it's always accurate and never stuffing. Returns [] when there's nothing
    worth mentioning (fewer than 2 distinct values -- the vertical name already says enough)."""
    counts: Counter[str] = Counter()
    for r in rows or []:
        for f in _FACET_FIELDS:
            v = (r.get(f) or "").strip() if isinstance(r.get(f), str) else None
            if v:
                counts[v] += 1
    if len(counts) < 2:
        return []
    return [v for v, _ in counts.most_common(k)]


def primary_facet(row: dict) -> str | None:
    """The single most relevant category value on ONE listing (e.g. its cuisine or religion) — for a
    listing detail page, where (unlike a multi-row browse page) any present facet is new, useful
    information regardless of whether it's the page's only one."""
    for f in _FACET_FIELDS:
        v = row.get(f)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def jsonld_script(obj) -> str:
    """Serialize an object to a safe application/ld+json <script> tag."""
    payload = json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'


_TAGS = re.compile(r"<[^>]+>")


def _plain(text: str) -> str:
    """Strip HTML tags + collapse whitespace, so an answer can be reused as schema text."""
    return re.sub(r"\s+", " ", _TAGS.sub(" ", text or "")).strip()


def faq_jsonld(pairs) -> str:
    """FAQPage from (question, answer_html) pairs — earns 'People also ask' results and is the
    format AI answer engines quote most. Answers are reduced to plain text for the schema."""
    return jsonld_script({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": _plain(q),
             "acceptedAnswer": {"@type": "Answer", "text": _plain(a)}}
            for q, a in pairs
        ],
    })


def breadcrumb_jsonld(items) -> str:
    """BreadcrumbList from (name, absolute_url) pairs — lets search engines show breadcrumb trails
    (better CTR) on browse / list / detail pages."""
    return jsonld_script({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(items, 1)
        ],
    })
