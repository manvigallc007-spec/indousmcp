"""Reusable schema.org JSON-LD builders (SEO rich results + AI answer engines).

These complement the schema already emitted elsewhere (Organization, WebSite+SearchAction,
LocalBusiness/AggregateRating, ItemList, Event). Output is a ready-to-embed <script> tag with the
unsafe '<' escaped so the JSON can't break out into the HTML.
"""

from __future__ import annotations

import json
import re


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
