"""Enrich existing listings from their OWN website (schema.org + Open Graph + socials).

Most business sites already publish structured data we never read: schema.org JSON-LD
(rating, price, cuisine, telephone, email, menu, a photo, social links) and Open Graph
meta (a photo, a description). We already store each listing's ``website`` — this agent
fetches that page, extracts those signals, fills empty fields, records rating/photo/socials,
and refreshes the description + tags + embedding so the new data is searchable.

No third-party API and no paid service — only the listing's own public page. The parsing
functions (`extract`, `parse_jsonld`, …) are pure and unit-tested without any network.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from .config import settings

# Verticals that have a real website to scrape (all carry a `website` + enrichment columns).
FETCHABLE = ("restaurants", "temples", "groceries", "professionals", "salons", "events",
             "apparel", "sweets", "studios", "services", "community")

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
_META_RE = re.compile(r"<meta\s+([^>]+?)/?>", re.I | re.S)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_ATTR_RE = re.compile(r'([a-zA-Z:_-]+)\s*=\s*["\']([^"\']*)["\']')

# schema.org @types that identify the business node we care about.
_BIZ_TYPES = {
    "restaurant", "foodestablishment", "cafe", "bakery", "localbusiness", "store",
    "grocerystore", "organization", "hairsalon", "beautysalon", "healthandbeautybusiness",
    "medicalbusiness", "physician", "dentist", "hospital", "place", "placeofworship",
    "hindutemple", "church", "event",
}

# host fragment -> our social network key
_SOCIAL_HOSTS = {
    "instagram.com": "instagram", "facebook.com": "facebook", "fb.com": "facebook",
    "twitter.com": "twitter", "x.com": "twitter", "youtube.com": "youtube",
    "youtu.be": "youtube", "tiktok.com": "tiktok", "linkedin.com": "linkedin",
    "yelp.com": "yelp", "wa.me": "whatsapp",
}


# ----------------------------------------------------------------- pure parsing
def parse_jsonld(html: str) -> list[dict]:
    """Return every JSON-LD object on the page, flattened (handles arrays + @graph)."""
    nodes: list[dict] = []
    for m in _JSONLD_RE.finditer(html):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            try:  # tolerate stray newlines/control chars some CMSs emit
                data = json.loads(re.sub(r"[\x00-\x1f]+", " ", raw))
            except Exception:
                continue
        _flatten(data, nodes)
    return nodes


def _flatten(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        out.append(node)
        for v in node.values():
            _flatten(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten(v, out)


def _types(node: dict) -> set[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return {str(t).lower()} if t else set()


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def _url_of(v: Any) -> str | None:
    v = _first(v)
    if isinstance(v, dict):
        v = v.get("url") or v.get("@id") or v.get("contentUrl")
    return v if isinstance(v, str) and v.strip() else None


def parse_meta(html: str) -> dict[str, str]:
    """property/name -> content for every <meta> (first wins)."""
    out: dict[str, str] = {}
    for m in _META_RE.finditer(html):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(m.group(1))}
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            out.setdefault(key.lower(), attrs["content"])
    return out


def _add_social(sig: dict, url: Any) -> None:
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        return
    low = url.lower()
    for host, name in _SOCIAL_HOSTS.items():
        if host in low:
            sig.setdefault("socials", {}).setdefault(name, url.split("?")[0])
            return


def _from_jsonld(biz: dict, sig: dict, base_url: str) -> None:
    ar = _first(biz.get("aggregateRating"))
    if isinstance(ar, dict):
        try:
            rv = float(ar.get("ratingValue"))
            if 0 <= rv <= 5:
                sig["rating"] = round(rv, 2)
        except (TypeError, ValueError):
            pass
        try:
            sig["rating_count"] = int(ar.get("reviewCount") or ar.get("ratingCount"))
        except (TypeError, ValueError):
            pass
    pr = biz.get("priceRange")
    if isinstance(pr, str) and pr.strip():
        sig["price_range"] = pr.strip()[:20]
    img = _url_of(biz.get("image") or biz.get("photo") or biz.get("logo"))
    if img:
        sig["photo_url"] = urljoin(base_url, img)
    tel = biz.get("telephone")
    if isinstance(tel, str) and tel.strip():
        sig["phone"] = re.sub(r"^tel:", "", tel.strip(), flags=re.I)
    em = biz.get("email")
    if isinstance(em, str) and "@" in em:
        sig["email"] = re.sub(r"^mailto:", "", em.strip(), flags=re.I).split("?")[0]
    sc = biz.get("servesCuisine")
    cuisines = sc if isinstance(sc, list) else ([sc] if isinstance(sc, str) else [])
    ctags = sorted({c.strip().lower() for c in cuisines if isinstance(c, str) and c.strip()})
    if ctags:
        sig["cuisine_tags"] = ctags
    menu = _url_of(biz.get("hasMenu") or biz.get("menu"))
    if isinstance(menu, str) and menu.lower().startswith("http"):
        sig["menu_url"] = urljoin(base_url, menu)
    same = biz.get("sameAs")
    for u in (same if isinstance(same, list) else [same]):
        _add_social(sig, u)


def extract(html: str, base_url: str = "") -> dict[str, Any]:
    """Extract enrichment signals from a page. Pure: no network, never raises."""
    sig: dict[str, Any] = {}
    biz = next((n for n in parse_jsonld(html)
                if isinstance(n, dict) and _types(n) & _BIZ_TYPES), None)
    if biz:
        try:
            _from_jsonld(biz, sig, base_url)
        except Exception:
            pass
    meta = parse_meta(html)
    if "photo_url" not in sig and meta.get("og:image"):
        sig["photo_url"] = urljoin(base_url, meta["og:image"])
    desc = meta.get("og:description") or meta.get("description")
    if desc and desc.strip():
        sig["site_description"] = " ".join(desc.split())[:300]
    for m in _HREF_RE.finditer(html):
        u = m.group(1)
        if u.lower().startswith("mailto:") and "email" not in sig:
            addr = u[7:].split("?")[0].strip()
            if "@" in addr:
                sig["email"] = addr
        else:
            _add_social(sig, u)
    return sig


# ----------------------------------------------------------------- network + DB
def _fetch_and_extract(url: str) -> dict[str, Any]:
    resp = httpx.get(url, timeout=15, follow_redirects=True,
                     headers={"User-Agent": settings.scraper_user_agent})
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "").lower():
        return {}
    return extract(resp.text[:1_500_000], str(resp.url))


_SELECT = (
    "SELECT * FROM {table} WHERE deleted_at IS NULL AND is_active "
    "AND website IS NOT NULL AND website <> '' "
    "AND (web_enriched_at IS NULL OR web_enriched_at < now() - (%s || ' days')::interval) "
    "ORDER BY is_featured DESC, web_enriched_at NULLS FIRST, id LIMIT %s"
)


def enrich_vertical(vertical: str, limit: int = 40, max_age_days: int = 90) -> dict[str, Any]:
    """Fetch a batch of this vertical's websites and write back enrichment. Idempotent.

    Gap-fills empty scalars (phone/email/menu_url/price_range), always refreshes
    rating/photo/socials from the latest fetch, unions website cuisine into tags, and
    regenerates description + embedding. Stamps web_enriched_at on every attempt (even a
    dead site) so the agent rotates politely instead of re-hitting the same pages.
    """
    from . import db, describe, embeddings, tags as tagmod, verticals
    from .pipeline.ingest import _adapt

    table = verticals._table(vertical)  # registry-controlled name (safe in f-string)
    rows = db.query(_SELECT.format(table=table), (max_age_days, limit))
    fetched = enriched = failed = 0

    for r in rows:
        try:
            sig = _fetch_and_extract(r["website"])
            fetched += 1
        except Exception:
            sig, failed = {}, failed + 1

        colvals: dict[str, Any] = {}
        # gap-fill scalars only when currently empty
        for col in ("phone", "email", "menu_url", "price_range"):
            if sig.get(col) and not (r.get(col) or "").strip():
                colvals[col] = sig[col]
        # always refresh fresh signals
        if "rating" in sig:
            colvals["rating"] = sig["rating"]
        if "rating_count" in sig:
            colvals["rating_count"] = sig["rating_count"]
        if sig.get("photo_url"):
            colvals["photo_url"] = sig["photo_url"][:500]
        if sig.get("socials"):
            colvals["socials"] = sig["socials"]

        merged = {**r, **colvals}
        if sig:
            text_rec = {**merged,
                        "description": f"{merged.get('description') or ''} {sig.get('site_description', '')}"}
            new_tags = (set(r.get("tags") or []) | set(sig.get("cuisine_tags") or [])
                        | set(tagmod.extract(vertical, text_rec)))
            merged["tags"] = sorted(new_tags)[:25]
            merged["description"] = describe.describe(vertical, merged)
            colvals["tags"] = merged["tags"]
            colvals["description"] = merged["description"]
            enriched += 1

        sets, params = [], []
        for col, val in colvals.items():
            if col == "socials":
                sets.append("socials = %s::jsonb"); params.append(json.dumps(val))
            elif col == "tags":
                sets.append("tags = %s"); params.append(_adapt(val))
            else:
                sets.append(f"{col} = %s"); params.append(val)
        sets += ["web_enriched_at = now()", "updated_at = now()"]
        db.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = %s", params + [r["id"]])

        if sig and embeddings.enabled():
            db.execute(f"UPDATE {table} SET embedding = %s::vector WHERE id = %s",
                       (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(merged))),
                        r["id"]))
        time.sleep(0.4)  # politeness between third-party sites

    return {"vertical": vertical, "scanned": len(rows), "fetched": fetched,
            "enriched": enriched, "failed": failed}


def enrich_all(limit_per_vertical: int = 40, max_age_days: int = 90) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for v in FETCHABLE:
        try:
            out[v] = enrich_vertical(v, limit=limit_per_vertical, max_age_days=max_age_days)
        except Exception as exc:  # one vertical failing shouldn't halt the rest
            out[v] = {"vertical": v, "error": str(exc)}
    return out
