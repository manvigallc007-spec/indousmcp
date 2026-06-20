"""Public, crawlable directory pages — distribution for SEO + AI answer engines.

Server-rendered, indexable pages per (category × city), with schema.org JSON-LD so Google
and AI answer engines (ChatGPT/Perplexity/Gemini) can surface and cite real listings. Plus
sitemap.xml, robots.txt, and an llms.txt that points AI agents at the MCP tools.

No auth, no DB writes — read-only over active listings.
"""

from __future__ import annotations

import html
import json
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from .. import db, tags as tagsmod, verticals
from ..config import settings
from . import i18n, seo
from .chat import _CAT_BLURB, _CAT_COLOR, _CAT_ICON
from .common import analytics_tag

_BRAND = "#c1440e"
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"

# Shared CSS for the category identity (rich cards + category header band). Reused on the
# home page and every browse page so categories look consistent everywhere.
CATEGORY_CSS = """
.catgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:12px;margin:16px 0}
.catcard{display:flex;align-items:center;gap:13px;background:#fff;border:1px solid #ececec;
 border-radius:14px;padding:15px;color:#1f2430;transition:.15s}
.catcard:hover{border-color:var(--c);transform:translateY(-2px);box-shadow:0 8px 20px rgba(0,0,0,.07)}
.catcard .cc-ic{width:46px;height:46px;border-radius:12px;display:grid;place-items:center;font-size:24px;
 background:#f4f2f0;background:color-mix(in srgb,var(--c) 16%,#fff);flex:0 0 auto}
.catcard .cc-tx{display:flex;flex-direction:column;line-height:1.3;min-width:0}
.catcard .cc-tx b{font-size:15px} .catcard .cc-n{color:var(--c);font-size:12px;font-weight:700}
.catcard .cc-bl{color:#6b7280;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cathead{display:flex;align-items:center;gap:14px;border:1px solid #ececec;border-left:5px solid var(--c);
 background:color-mix(in srgb,var(--c) 8%,#fff);border-radius:14px;padding:14px 16px;margin:6px 0 18px}
.cathead .ch-ic{width:46px;height:46px;border-radius:12px;display:grid;place-items:center;font-size:25px;background:#fff}
.cathead b{font-size:21px;line-height:1.15}
"""


def _counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for v in verticals.VERTICALS:
        try:
            out[v] = db.query_one(
                f"SELECT count(*) AS n FROM {verticals._table(v)} "
                f"WHERE deleted_at IS NULL AND is_active")["n"]
        except Exception:
            out[v] = 0
    return out


def category_grid() -> str:
    """Rich category cards (icon + name + live count + blurb) — used on home and /browse."""
    counts = _counts()
    cells = []
    for v, cfg in verticals.VERTICALS.items():
        href = "/events" if v == "events" else f"/browse/{v}"
        n = counts.get(v, 0)
        cells.append(
            f"<a class='catcard' href='{href}' style='--c:{_CAT_COLOR.get(v, '#777')}'>"
            f"<span class='cc-ic'>{_CAT_ICON.get(v, '•')}</span>"
            f"<span class='cc-tx'><b>{html.escape(cfg['label'])}</b>"
            f"<span class='cc-n'>{n} listing{'s' if n != 1 else ''}</span>"
            f"<span class='cc-bl'>{html.escape(_CAT_BLURB.get(v, ''))}</span></span></a>")
    return f"<div class='catgrid'>{''.join(cells)}</div>"


def _cathead(v: str) -> str:
    return (f"<div class='cathead' style='--c:{_CAT_COLOR.get(v, '#777')}'>"
            f"<span class='ch-ic'>{_CAT_ICON.get(v, '•')}</span>"
            f"<span><b>{html.escape(_label(v))}</b><br>"
            f"<span class='muted'>{html.escape(_CAT_BLURB.get(v, ''))}</span></span></div>")


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


def _unslug(s: str) -> str:
    return (s or "").replace("-", " ").strip()


def _base() -> str:
    return settings.public_web_url.rstrip("/")


def _page(title: str, desc: str, body: str, jsonld: str = "", status: int = 200,
          canonical: str = "", image: str = "") -> HTMLResponse:
    plat = html.escape(settings.platform_name)
    # Escape "<" so a listing name containing "</script>" can't break out of the JSON-LD block.
    ld = (f'<script type="application/ld+json">{jsonld.replace("<", chr(92) + "u003c")}</script>'
          if jsonld else "")
    can = (f'<link rel="canonical" href="{html.escape(canonical)}">'
           f'<meta property="og:url" content="{html.escape(canonical)}">' if canonical else "")
    img_meta = (f'<meta property="og:image" content="{html.escape(image)}">'
                f'<meta name="twitter:card" content="summary_large_image">'
                f'<meta name="twitter:image" content="{html.escape(image)}">' if image else "")
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
{can}<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">{img_meta}
{analytics_tag()}
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#c1440e">
<script>if('serviceWorker' in navigator){{window.addEventListener('load',function(){{navigator.serviceWorker.register('/sw.js').catch(function(){{}})}})}}</script>
{ld}
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
   color:#1f2430;background:#f6f4f1;line-height:1.55}}
 header{{background:#fff;border-bottom:1px solid #ececec;padding:13px 20px}}
 header a{{color:#1f2430;text-decoration:none;font-weight:700}}
 main{{max-width:900px;margin:0 auto;padding:26px 20px 50px}}
 h1{{font-size:27px;margin:0 0 6px}} .muted{{color:#6b7280}}
 a{{color:{_BRAND};text-decoration:none}}
 .chips{{display:flex;flex-wrap:wrap;gap:9px;margin:16px 0}}
 .chip{{background:#fff;border:1px solid #e2e0dd;border-radius:999px;padding:8px 13px;font-size:14px}}
 .fbar{{background:#fff;border:1px solid #ececec;border-radius:14px;padding:12px 14px;margin:14px 0;
   display:flex;flex-wrap:wrap;gap:14px;align-items:center}}
 .fgrp{{display:flex;flex-wrap:wrap;gap:7px;align-items:center}}
 .flabel{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#98a2b3;font-weight:700;margin-right:2px}}
 .fbar .chip{{padding:5px 11px;font-size:13px;cursor:pointer}}
 .fsort{{display:inline-flex;align-items:center;gap:6px;margin:0}}
 .fsort select{{border:1px solid #e2e0dd;border-radius:8px;padding:6px 9px;font:inherit;font-size:13px;background:#fff}}
 .lc{{background:#fff;border:1px solid #ececec;border-left:4px solid {_BRAND};border-radius:12px;
   padding:14px 16px;margin:10px 0}}
 .lc h3{{margin:0 0 4px;font-size:17px}} .lc p{{margin:5px 0;color:#4b5563;font-size:14px}}
 .lc .meta{{color:#6b7280;font-size:13px}} .lc .feat{{color:#b45309;font-weight:600}}
 .feats{{display:flex;flex-wrap:wrap;gap:5px;margin:7px 0 2px}}
 .fchip{{background:#f3efe9;border:1px solid #e7e0d6;border-radius:999px;padding:2px 9px;font-size:12px;color:#5b6470}}
 .lc .ver{{color:#1565c0;font-weight:600}} .lc .rate{{color:#b45309;font-weight:600}}
 .cta{{background:{_BRAND};color:#fff;padding:11px 18px;border-radius:10px;display:inline-block;margin-top:8px}}
 nav.crumbs{{font-size:13px;margin-bottom:14px}}
{CATEGORY_CSS}
</style></head><body>
<header><a href="/" style="display:inline-flex;align-items:center;gap:9px"><img src="/logo" alt="{plat}" style="height:34px;width:auto;max-width:160px;border-radius:8px">{plat}</a> &nbsp;·&nbsp; <a href="/browse">Browse</a> &nbsp;·&nbsp; <a href="/chat">Ask {settings.assistant_name}</a></header>
<main>{body}</main></body></html>"""
    return HTMLResponse(doc, status_code=status)


def _label(v: str) -> str:
    return verticals.VERTICALS.get(v, {}).get("label", v)


# ---------------------------------------------------------------- browse indexes
def browse_root(request: Request) -> HTMLResponse:
    tr = i18n.t(request)
    body = (f"<h1>{html.escape(tr['browse'])}</h1>"
            f"<p class='muted'>{html.escape(tr['browse_intro'])}</p>"
            f"{category_grid()}"
            "<p style='margin-top:6px'><a class='cta' href='/events'>📅 Upcoming events &amp; festivals →</a></p>")
    return _page(f"Browse · {settings.platform_name}",
                 "Browse Indian-American businesses, temples and events by category and city.", body)


def browse_vertical(request: Request) -> HTMLResponse:
    v = request.path_params["vertical"]
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    if v == "events":  # events are date-based — send to the calendar
        return RedirectResponse("/events", status_code=307)
    tr = i18n.t(request)
    rows = verticals.geo_summary(v)  # states with active counts
    items = "".join(
        f"<a class='chip' href='/browse/{v}/{_slug(r['state'])}'>{html.escape(r['state'])} "
        f"<span class='muted'>({r['n']})</span></a>" for r in rows if r["state"] and r["state"] != "(unknown)")
    body = (f"<nav class='crumbs'><a href='/browse'>{html.escape(tr['browse'])}</a> › {html.escape(_label(v))}</nav>"
            f"{_cathead(v)}"
            f"<p class='muted'>{html.escape(tr['pick_state'])}</p>"
            f"<div class='chips'>{items}</div>")
    return _page(f"Indian {_label(v)} in the USA · {settings.platform_name}",
                 f"Browse Indian {_label(v)} across the USA by state and city.", body)


def browse_state(request: Request) -> HTMLResponse:
    v, state = request.path_params["vertical"], _unslug(request.path_params["state"])
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    tr = i18n.t(request)
    rows = verticals.geo_summary(v, state)  # cities in this state
    items = "".join(
        f"<a class='chip' href='/browse/{v}/{_slug(state)}/{_slug(r['city'])}'>{html.escape(r['city'])} "
        f"<span class='muted'>({r['n']})</span></a>" for r in rows if r["city"] and r["city"] != "(unknown)")
    label = _label(v)
    body = (f"<nav class='crumbs'><a href='/browse'>{html.escape(tr['browse'])}</a> › "
            f"<a href='/browse/{v}'>{html.escape(label)}</a> › {html.escape(state.upper())}</nav>"
            f"{_cathead(v)}"
            f"<h1>Indian {html.escape(label)} in {html.escape(state.upper())}</h1>"
            f"<p class='muted'>{html.escape(tr['pick_city'])}</p>"
            f"<div class='chips'>{items or ('<span class=muted>' + html.escape(tr['no_listings']) + '</span>')}</div>")
    return _page(f"Indian {label} in {state.upper()} · {settings.platform_name}",
                 f"Browse Indian {label} in {state.upper()} by city.", body)


_RATING_EXPR = "GREATEST(COALESCE(community_rating,0), COALESCE(rating,0))"
_SORTS = {
    "best": f"{_FEATURED} DESC, {_RATING_EXPR} DESC, confidence_score DESC",
    "rating": f"{_RATING_EXPR} DESC, (COALESCE(community_rating_count,0)+COALESCE(rating_count,0)) DESC",
    "name": "name ASC",
    "new": "id DESC",
}


def _listings(v: str, state: str, city: str, *, region=None, lang=None, diet=None, min_rating=None,
              q=None, sort: str = "best", limit: int = 200) -> list[dict]:
    table = verticals._table(v)
    where = ["deleted_at IS NULL", "is_active", "LOWER(state) = LOWER(%s)", "LOWER(city) = LOWER(%s)"]
    params: list = [state, city]
    if region:
        where.append("LOWER(region_tag) = LOWER(%s)"); params.append(region)
    if lang:
        where.append("%s = ANY(languages)"); params.append(lang)
    if diet and verticals.VERTICALS[v].get("has_dietary"):
        where.append("%s = ANY(dietary_tags)"); params.append(diet)
    if min_rating:
        where.append(f"{_RATING_EXPR} >= %s"); params.append(min_rating)
    if q:
        where.append("name ILIKE %s"); params.append(f"%{q}%")
    order = _SORTS.get(sort, _SORTS["best"])
    return db.query(
        f"SELECT id, name, address_full, city, state, lat, lng, phone, website, description, tags, "
        f"languages, is_claimed, rating, rating_count, community_rating, community_rating_count, "
        f"photo_url, {_FEATURED} AS is_featured "
        f"FROM {table} WHERE {' AND '.join(where)} "
        f"ORDER BY {order} LIMIT %s", params + [limit])


def _facets(v: str, state: str, city: str) -> dict[str, list]:
    """Distinct region / language / dietary values present for this (vertical, city) — so the filter
    bar only offers options that actually have matches."""
    table = verticals._table(v)
    base = (f"FROM {table} WHERE deleted_at IS NULL AND is_active "
            f"AND LOWER(state)=LOWER(%s) AND LOWER(city)=LOWER(%s)")

    def _q(sql: str) -> list:
        try:
            return [r["x"] for r in db.query(sql, (state, city)) if r["x"]]
        except Exception:
            return []
    out = {
        "region": _q(f"SELECT DISTINCT region_tag AS x {base} AND region_tag IS NOT NULL ORDER BY 1"),
        "lang": _q(f"SELECT DISTINCT unnest(languages) AS x {base} ORDER BY 1"),
        "diet": (_q(f"SELECT DISTINCT unnest(dietary_tags) AS x {base} ORDER BY 1")
                 if verticals.VERTICALS[v].get("has_dietary") else []),
    }
    return out


def _filter_qs(current: dict, **changes) -> str:
    """Build a ?query-string from the active filters with some keys changed/cleared (None = clear)."""
    params = {k: v for k, v in {**current, **changes}.items() if v}
    return ("?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())) if params else ""


def _filter_bar(path: str, facets: dict, current: dict) -> str:
    """Toggle chips (region / language / dietary) + a sort dropdown. Each chip preserves the other
    active filters; clicking an active chip clears it."""
    on = "background:#c1440e;color:#fff;border-color:#c1440e"

    def group(key: str, label: str, values: list) -> str:
        if not values:
            return ""
        chips = ""
        for val in values:
            active = (current.get(key) or "").lower() == val.lower()
            href = path + _filter_qs(current, **{key: None if active else val})
            chips += (f"<a class='chip' href='{html.escape(href)}'"
                      + (f" style='{on}'" if active else "") + f">{html.escape(val)}</a>")
        return f"<div class='fgrp'><span class='flabel'>{label}</span>{chips}</div>"

    bar = group("region", "Cuisine/Region", facets["region"]) + group("diet", "Dietary", facets["diet"]) \
        + group("lang", "Language", facets["lang"])
    if not bar:
        return ""
    hidden = "".join(f"<input type='hidden' name='{k}' value='{html.escape(str(v))}'>"
                     for k, v in current.items() if v and k != "sort")
    opts = "".join(
        f"<option value='{k}'" + (" selected" if current.get("sort", "best") == k else "") + f">{lbl}</option>"
        for k, lbl in (("best", "Top picks"), ("rating", "Highest rated"), ("name", "A–Z"), ("new", "Newest")))
    sort = (f"<form method='get' class='fsort'>{hidden}"
            f"<label class='flabel'>Sort</label>"
            f"<select name='sort' onchange='this.form.submit()'>{opts}</select></form>")
    clear = (f" <a class='chip' href='{html.escape(path)}'>✕ Clear</a>"
             if any(current.get(k) for k in ("region", "lang", "diet")) else "")
    return (f"<div class='fbar'>{bar}<div class='fgrp'>{sort}{clear}</div></div>")


def _listing_cards(v: str, rows: list[dict], tr: dict, *, numbered: bool = True) -> tuple[str, list]:
    """Listing cards + schema.org ItemList items for a set of rows. Shared by the browse-city and
    best-of pages so they stay visually + structurally identical (only the ordering differs)."""
    dr = html.escape(tr["details_reviews"])
    cards, ld_items = "", []
    for i, r in enumerate(rows, 1):
        loc = ", ".join(x for x in ((r.get("city") or "").title(), (r.get("state") or "").upper()) if x)
        addr = (r.get("address_full") or "").strip() or loc
        feat = f" <span class='feat'>★ {html.escape(tr['featured'])}</span>" if r.get("is_featured") else ""
        feat += f" <span class='ver'>✓ {html.escape(tr['owner_verified'])}</span>" if r.get("is_claimed") else ""
        links = " · ".join(
            x for x in (
                (f"<a href='{html.escape(r['website'])}' rel='nofollow'>Website</a>" if r.get("website") else ""),
                (f"<a href='tel:{html.escape(r['phone'])}'>{html.escape(r['phone'])}</a>" if r.get("phone") else ""),
            ) if x)
        crate = (f"<span class='rate'>★ {r['community_rating']:.1f} "
                 f"({r['community_rating_count'] or 0} {html.escape(tr['community'])})</span>") \
            if r.get("community_rating") else ""
        wrate = (f"<span class='muted'>★ {r['rating']}"
                 + (f" ({r['rating_count']})" if r.get("rating_count") else "")
                 + f" {html.escape(tr['from_web'])}</span>") \
            if r.get("rating") else ""
        rate = " · ".join(x for x in (crate, wrate) if x)
        name_html = f"<a href='/listing/{v}/{r['id']}'>{html.escape(r['name'])}</a>"
        feats = tagsmod.for_display(r.get("tags"), limit=8)
        feats_html = ("<div class='feats'>" + "".join(
            f"<span class='fchip'>{html.escape(x)}</span>" for x in feats) + "</div>") if feats else ""
        langs_html = (f"<div class='meta' style='color:#0f766e;font-weight:600'>🗣 {html.escape(tr['speaks'])}: "
                      f"{html.escape(', '.join(r['languages']))}</div>") if r.get("languages") else ""
        rank = f"{i}. " if numbered else ""
        thumb = (f"<img src='{html.escape(r['photo_url'])}' alt='{html.escape(r['name'])}' "
                 f"loading='lazy' onerror='this.remove()' style='float:right;width:84px;height:84px;"
                 f"object-fit:cover;border-radius:10px;margin:0 0 6px 12px'>") if r.get("photo_url") else ""
        cards += (f"<div class='lc'>{thumb}<h3>{rank}{name_html}{feat}</h3>"
                  f"<div class='meta'>{html.escape(addr)} {rate}</div>"
                  + (f"<p>{html.escape((r.get('description') or '')[:220])}</p>" if r.get("description") else "")
                  + langs_html
                  + feats_html
                  + (f"<div class='meta'>{links} · <a href='/listing/{v}/{r['id']}'>{dr}</a></div>"
                     if links else f"<div class='meta'><a href='/listing/{v}/{r['id']}'>{dr}</a></div>")
                  + "</div>")
        biz = {"@type": "LocalBusiness", "name": r["name"],
               "address": {"@type": "PostalAddress", "addressLocality": r.get("city"),
                           "addressRegion": r.get("state"), "streetAddress": r.get("address_full")}}
        if r.get("photo_url"):
            biz["image"] = r["photo_url"]
        if r.get("phone"):
            biz["telephone"] = r["phone"]
        if r.get("lat") and r.get("lng"):
            biz["geo"] = {"@type": "GeoCoordinates", "latitude": r["lat"], "longitude": r["lng"]}
        if r.get("community_rating"):       # prefer first-party community rating when present
            biz["aggregateRating"] = {"@type": "AggregateRating",
                                      "ratingValue": round(r["community_rating"], 1),
                                      "reviewCount": r.get("community_rating_count") or 1}
        elif r.get("rating"):
            ar = {"@type": "AggregateRating", "ratingValue": r["rating"]}
            if r.get("rating_count"):
                ar["reviewCount"] = r["rating_count"]
            biz["aggregateRating"] = ar
        biz["url"] = f"{_base()}/listing/{v}/{r['id']}"
        ld_items.append({"@type": "ListItem", "position": i, "item": biz})
    return cards, ld_items


def browse_city(request: Request) -> HTMLResponse:
    v = request.path_params["vertical"]
    state = _unslug(request.path_params["state"])
    city = _unslug(request.path_params["city"])
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    tr = i18n.t(request)
    qp = request.query_params
    current = {"region": qp.get("region") or None, "lang": qp.get("lang") or None,
               "diet": qp.get("diet") or None,
               "sort": qp.get("sort") if qp.get("sort") in _SORTS else "best"}
    filtered = any(current.get(k) for k in ("region", "lang", "diet"))
    rows = _listings(v, state, city, region=current["region"], lang=current["lang"],
                     diet=current["diet"], sort=current["sort"])
    label = _label(v)
    loc = f"{city.title()}, {state.upper()}"
    h1 = f"Indian {label} in {loc}"
    canon = f"{_base()}/browse/{v}/{_slug(state)}/{_slug(city)}"
    path = f"/browse/{v}/{_slug(state)}/{_slug(city)}"
    crumbs = (f"<nav class='crumbs'><a href='/browse'>{html.escape(tr['browse'])}</a> › "
              f"<a href='/browse/{v}'>{html.escape(label)}</a> › "
              f"<a href='/browse/{v}/{_slug(state)}'>{html.escape(state.upper())}</a> › "
              f"{html.escape(city.title())}</nav>")
    fbar = _filter_bar(path, _facets(v, state, city), current)

    if not rows:
        if filtered:                                  # filters just didn't match -> keep the bar
            body = (crumbs + _cathead(v) + f"<h1>{html.escape(h1)}</h1>" + fbar
                    + f"<p class='muted'>No matches for these filters. "
                    f"<a href='{html.escape(path)}'>Clear filters</a> or "
                    f"<a href='/chat'>{html.escape(tr['ask_picks'])}</a>.</p>")
            return _page(f"{h1} · {settings.platform_name}", f"Indian {label} in {loc}.", body, canonical=canon)
        body = (f"<h1>{html.escape(h1)}</h1><p class='muted'>{html.escape(tr['no_listings'])} "
                f"<a href='/submit'>{html.escape(tr['add_business'])}</a> · "
                f"<a href='/chat'>{html.escape(tr['ask_picks'])}</a></p>")
        return _page(f"{h1} · {settings.platform_name}", f"Indian {label} in {loc}.", body, canonical=canon)

    cards, ld_items = _listing_cards(v, rows, tr)
    jsonld = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                         "name": h1, "numberOfItems": len(rows), "itemListElement": ld_items})
    best_link = (f" · <a href='/best/{v}/{_slug(state)}/{_slug(city)}'>🏆 Best-rated</a>"
                 if len(rows) >= 3 and not filtered else "")
    body = (crumbs + _cathead(v) + f"<h1>{html.escape(h1)}</h1>"
            f"<p class='muted'>{len(rows)} result{'s' if len(rows) != 1 else ''} · "
            f"<a href='/chat'>{html.escape(tr['ask_picks'])}</a>{best_link}</p>"
            f"{fbar}{cards}<p><a class='cta' href='/chat'>{html.escape(tr['ask_picks'])} →</a></p>")
    og_img = next((x.get("photo_url") for x in rows if x.get("photo_url")), "")
    return _page(f"{h1} · {settings.platform_name} ({len(rows)})",
                 f"Directory of {len(rows)} Indian {label} in {loc} — addresses, phone, websites.",
                 body, jsonld=jsonld, canonical=canon, image=og_img)


def _best_listings(v: str, state: str, city: str, limit: int = 15) -> list[dict]:
    """Top listings for a (vertical, city), ranked: featured, then best rating (community or web),
    then review volume, then confidence."""
    table = verticals._table(v)
    return db.query(
        f"SELECT id, name, address_full, city, state, lat, lng, phone, website, description, tags, "
        f"languages, is_claimed, rating, rating_count, community_rating, community_rating_count, "
        f"photo_url, {_FEATURED} AS is_featured "
        f"FROM {table} WHERE deleted_at IS NULL AND is_active "
        f"AND LOWER(state) = LOWER(%s) AND LOWER(city) = LOWER(%s) "
        f"ORDER BY {_FEATURED} DESC, "
        f"GREATEST(COALESCE(community_rating, 0), COALESCE(rating, 0)) DESC, "
        f"(COALESCE(community_rating_count, 0) + COALESCE(rating_count, 0)) DESC, "
        f"confidence_score DESC LIMIT %s", (state, city, limit))


def best_city(request: Request) -> HTMLResponse:
    """'Best Indian <category> in <City>' — a curated, share-friendly Top-N ranked by ratings.
    The page humans drop in WhatsApp groups and that captures 'best ... in ...' long-tail search."""
    import datetime
    v = request.path_params["vertical"]
    state = _unslug(request.path_params["state"])
    city = _unslug(request.path_params["city"])
    if v not in verticals.VERTICALS or v == "events":
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    tr = i18n.t(request)
    rows = _best_listings(v, state, city)
    if len(rows) < 3:    # too thin to be a credible 'best' list -> the full browse page instead
        return RedirectResponse(f"/browse/{v}/{_slug(state)}/{_slug(city)}", status_code=307)

    label = _label(v)
    loc = f"{city.title()}, {state.upper()}"
    year = datetime.date.today().year
    h1 = f"Best Indian {label} in {loc} ({year})"
    canon = f"{_base()}/best/{v}/{_slug(state)}/{_slug(city)}"
    cards, ld_items = _listing_cards(v, rows, tr)
    crumbs_ld = seo.breadcrumb_jsonld([
        ("Browse", f"{_base()}/browse"), (label, f"{_base()}/browse/{v}"),
        (state.upper(), f"{_base()}/browse/{v}/{_slug(state)}"), (f"Best in {city.title()}", canon)])
    jsonld = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                         "name": h1, "numberOfItems": len(rows), "itemListElement": ld_items})
    body = (crumbs_ld
            + f"<nav class='crumbs'><a href='/browse'>{html.escape(tr['browse'])}</a> › "
            f"<a href='/browse/{v}'>{html.escape(label)}</a> › "
            f"<a href='/browse/{v}/{_slug(state)}'>{html.escape(state.upper())}</a> › "
            f"Best in {html.escape(city.title())}</nav>"
            f"{_cathead(v)}"
            f"<h1>{html.escape(h1)}</h1>"
            f"<p class='muted'>Top {len(rows)} Indian {html.escape(label.lower())} in {html.escape(loc)}, "
            f"ranked by community &amp; web ratings. "
            f"<a href='/browse/{v}/{_slug(state)}/{_slug(city)}'>See all</a> · "
            f"<a href='/chat'>{html.escape(tr['ask_picks'])}</a></p>"
            f"{cards}<p><a class='cta' href='/chat'>{html.escape(tr['ask_picks'])} →</a></p>")
    og_img = next((x.get("photo_url") for x in rows if x.get("photo_url")), "")
    return _page(f"{h1} · {settings.platform_name}",
                 f"The best Indian {label.lower()} in {loc} ({year}) — top-rated picks with ratings, "
                 f"addresses, phone and websites, ranked by community and web reviews.",
                 body, jsonld=jsonld, canonical=canon, image=og_img)


def _when(dt) -> str:
    if not hasattr(dt, "strftime"):
        return str(dt)[:16]
    return dt.strftime("%a, %b %d, %Y · %I:%M %p")


def events_page(request: Request) -> HTMLResponse:
    """Public upcoming-events / festival calendar (chronological), with schema.org Event JSON-LD."""
    from ..events import queries as eq
    state = request.query_params.get("state") or None
    city = request.query_params.get("city") or None
    category = request.query_params.get("category") or None
    res = eq.get_indian_events(city=city, state=state, category=category, limit=80)
    rows = res.get("results", [])
    where = ", ".join(x for x in (city, (state.upper() if state else None)) if x) or "the USA"
    h1 = f"Upcoming Indian-American events in {where}"

    if not rows:
        body = (f"<h1>{html.escape(h1)}</h1><p class='muted'>No upcoming events listed yet — "
                f"<a href='/chat'>ask the assistant</a> or check back soon. Organizers: publish a "
                f"public calendar (.ics) and our agents pick it up automatically.</p>")
        return _page(f"{h1} · {settings.platform_name}", "Upcoming Indian-American festivals and events.", body)

    cards, graph = "", []
    for r in rows:
        loc = ", ".join(x for x in (r.get("venue_name"), r.get("city"), r.get("state")) if x)
        cat = f" <span class='feat'>{html.escape(r['category'])}</span>" if r.get("category") else ""
        link = f"<a href='{html.escape(r['website'])}' rel='nofollow'>details</a>" if r.get("website") else ""
        cards += (f"<div class='lc'><div class='meta'>{html.escape(_when(r.get('start_at')))}</div>"
                  f"<h3>{html.escape(r['name'])}{cat}</h3>"
                  + (f"<div class='meta'>📍 {html.escape(loc)}</div>" if loc else "")
                  + (f"<p>{html.escape((r.get('description') or '')[:200])}</p>" if r.get("description") else "")
                  + (f"<div class='meta'>{link}</div>" if link else "") + "</div>")
        ev = {"@type": "Event", "name": r["name"]}
        if hasattr(r.get("start_at"), "isoformat"):
            ev["startDate"] = r["start_at"].isoformat()
        if hasattr(r.get("end_at"), "isoformat"):
            ev["endDate"] = r["end_at"].isoformat()
        if r.get("venue_name") or r.get("city"):
            ev["location"] = {"@type": "Place", "name": r.get("venue_name") or r.get("city"),
                              "address": ", ".join(x for x in (r.get("address_full"), r.get("city"),
                                                               r.get("state")) if x)}
        if r.get("website"):
            ev["url"] = r["website"]
        graph.append(ev)

    jsonld = json.dumps({"@context": "https://schema.org", "@graph": graph})
    body = (f"<nav class='crumbs'><a href='/browse'>Browse</a> › Events</nav>"
            f"<h1>{html.escape(h1)}</h1>"
            f"<p class='muted'>{len(rows)} upcoming · festivals, garba, concerts, pujas and more. "
            f"<a href='/chat'>Ask {html.escape(settings.assistant_name)}</a> what's on near you.</p>"
            f"{cards}")
    return _page(f"{h1} · {settings.platform_name}",
                 f"Upcoming Indian-American festivals & events in {where} — dates, venues, details.",
                 body, jsonld=jsonld)


# -------------------------------------------------------------- crawler files
def sitemap(request: Request) -> Response:
    base = _base()
    urls = [f"{base}/", f"{base}/browse", f"{base}/explore", f"{base}/events", f"{base}/insights",
            f"{base}/for-business", f"{base}/for-agents", f"{base}/submit", f"{base}/about",
            f"{base}/privacy", f"{base}/terms", f"{base}/contact", f"{base}/faq"]
    urls += [f"{base}/browse/{v}" for v in verticals.VERTICALS]
    # All (vertical × city) pages that actually have active listings.
    for v in verticals.VERTICALS:
        try:
            rows = db.query(
                f"SELECT DISTINCT state, city FROM {verticals._table(v)} "
                f"WHERE deleted_at IS NULL AND is_active AND city IS NOT NULL AND state IS NOT NULL")
        except Exception:
            rows = []
        for r in rows:
            urls.append(f"{base}/browse/{v}/{_slug(r['state'])}/{_slug(r['city'])}")
    # 'Best of' pages — only (vertical × city) with enough listings to make a credible ranking.
    for v in verticals.VERTICALS:
        if v == "events":
            continue
        try:
            rows = db.query(
                f"SELECT state, city FROM {verticals._table(v)} "
                f"WHERE deleted_at IS NULL AND is_active AND city IS NOT NULL AND state IS NOT NULL "
                f"GROUP BY state, city HAVING count(*) >= 5")
        except Exception:
            rows = []
        for r in rows:
            urls.append(f"{base}/best/{v}/{_slug(r['state'])}/{_slug(r['city'])}")
    # Per-listing detail pages (reviews live here). Bounded per vertical to keep the file sane.
    for v in verticals.VERTICALS:
        if v == "events":
            continue
        try:
            ids = db.query(f"SELECT id FROM {verticals._table(v)} WHERE deleted_at IS NULL "
                           f"AND is_active ORDER BY id LIMIT 5000")
        except Exception:
            ids = []
        urls += [f"{base}/listing/{v}/{r['id']}" for r in ids]
    body = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{html.escape(u)}</loc></url>" for u in urls) + "</urlset>")
    return Response(body, media_type="application/xml")


def robots(request: Request) -> Response:
    # Agent-first: explicitly welcome AI crawlers & answer engines (we WANT to be indexed/cited).
    bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "anthropic-ai", "Claude-Web",
            "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot",
            "Amazonbot", "cohere-ai", "Bingbot", "Googlebot"]
    stanzas = [f"User-agent: {b}\nAllow: /" for b in bots]
    stanzas.append("User-agent: *\nAllow: /")
    return Response("\n\n".join(stanzas) + f"\n\nSitemap: {_base()}/sitemap.xml\n",
                    media_type="text/plain")


# ------------------------------------------------------------------------ PWA
def manifest(request: Request) -> Response:
    data = {
        "name": settings.platform_name, "short_name": settings.platform_name[:12],
        "description": settings.platform_tagline,
        "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#f6f4f1", "theme_color": "#c1440e",
        "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml",
                   "purpose": "any maskable"}],
    }
    return Response(json.dumps(data), media_type="application/manifest+json")


_SW_JS = """
const C='na-shell-v6';
const SHELL=['/','/browse','/events','/icon.svg','/manifest.webmanifest'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const req=e.request; if(req.method!=='GET') return;
  const p=new URL(req.url).pathname;
  if(p.startsWith('/chat/api')||p.startsWith('/admin')||p.startsWith('/portal')) return; // never cache dynamic/auth
  e.respondWith(
    fetch(req).then(res=>{const cp=res.clone();caches.open(C).then(c=>c.put(req,cp));return res;})
              .catch(()=>caches.match(req).then(m=>m||caches.match('/')))
  );
});
"""


def service_worker(request: Request) -> Response:
    return Response(_SW_JS, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


def insights(request: Request) -> HTMLResponse:
    from .. import demographics
    metros, states = demographics.top("metro", 15), demographics.top("state", 12)
    title = "Indian America by the numbers"
    desc = ("Where Indian-Americans live across the USA — top metros and states by Asian-Indian "
            "population, from public U.S. Census data.")
    if not metros and not states:
        body = (f"<h1>{title}</h1><p class='muted'>Population insights are being prepared — "
                "check back soon. Meanwhile, <a href='/chat'>Ask Dost</a> or "
                "<a href='/browse'>browse the directory</a>.</p>")
        return _page(title, desc, body)
    th = "padding:8px 12px;border-bottom:2px solid #e7c3b6;text-align:left"
    td = "padding:7px 12px;border-bottom:1px solid #efe9e1"
    tdr = td + ";text-align:right"

    def _rows(items):
        return "".join(f"<tr><td style='{td}'>{html.escape(r['name'])}</td>"
                       f"<td style='{tdr}'>{(r['indian_population'] or 0):,}</td></tr>" for r in items)
    total = (demographics.summary().get("total_indian") or 0)

    # Income / education / work (Census Selected Population Profile for Asian-Indian alone).
    f = demographics.facts("us")

    def _stat(metric, fmt):
        r = f.get(metric)
        if not r or r.get("value") is None:
            return ""
        v = fmt(r["value"])
        return (f"<div style='flex:1 1 150px;background:#fbf6ef;border:1px solid #efe1d2;"
                f"border-radius:12px;padding:14px 16px'><div style='font-size:24px;font-weight:700;"
                f"color:#b4530f'>{v}</div><div class='muted' style='font-size:13px'>"
                f"{html.escape(r['label'])}</div></div>")
    cards = "".join([
        _stat("median_household_income", lambda v: f"${v:,.0f}"),
        _stat("pct_bachelors_plus", lambda v: f"{v:.0f}%"),
        _stat("pct_prof_occupations", lambda v: f"{v:.0f}%"),
        _stat("per_capita_income", lambda v: f"${v:,.0f}"),
        _stat("median_age", lambda v: f"{v:.0f} yrs"),
    ])
    profile_html = ""
    if cards:
        profile_html = (
            "<h2 style='margin-top:26px'>Income, education &amp; work</h2>"
            "<div style='display:flex;flex-wrap:wrap;gap:12px'>" + cards + "</div>"
            "<p class='muted' style='margin-top:8px'>Asian-Indian population, U.S. Census ACS "
            "Selected Population Profile.</p>")

    langs = demographics.languages("us")
    langs_html = ""
    if langs:
        chips = "".join(
            f"<span style='display:inline-block;background:#eef6f4;border:1px solid #cfe6e0;"
            f"border-radius:999px;padding:5px 12px;margin:0 6px 8px 0;font-size:14px'>"
            f"{html.escape(r['label'])} <b>{int(r['value']):,}</b></span>"
            for r in langs if r["value"])
        langs_html = ("<h2 style='margin-top:26px'>Languages spoken at home</h2>"
                      f"<div>{chips}</div><p class='muted' style='margin-top:4px'>Speakers of "
                      "Indian &amp; South-Asian languages nationwide (U.S. Census ACS).</p>")

    body = (
        f"<h1>{title}</h1>"
        f"<p class='lead'>Where Indian-Americans live across the USA, from the U.S. Census Bureau "
        f"(American Community Survey). Roughly <b>{total:,}</b> people of Asian-Indian origin "
        f"nationwide.</p>"
        f"{profile_html}{langs_html}"
        f"<h2 style='margin-top:26px'>Top metro areas</h2><table style='border-collapse:collapse;width:100%'>"
        f"<tr><th style='{th}'>Metro area</th><th style='{th};text-align:right'>Asian-Indian population</th></tr>"
        f"{_rows(metros)}</table>"
        f"<h2 style='margin-top:24px'>Top states</h2><table style='border-collapse:collapse;width:100%'>"
        f"<tr><th style='{th}'>State</th><th style='{th};text-align:right'>Asian-Indian population</th></tr>"
        f"{_rows(states)}</table>"
        f"<p class='muted' style='margin-top:18px'>Source: U.S. Census Bureau, ACS 5-year "
        f"(aggregated, public data).</p>"
        f"<p><a href='/chat'>Ask Dost to find Indian places near you →</a></p>")
    return _page(title, desc, body)


def llms_txt(request: Request) -> Response:
    base = _base()
    cats = "\n".join(f"- {cfg['label']}: {base}/browse/{v}" for v, cfg in verticals.VERTICALS.items())
    txt = (f"# {settings.platform_name}\n\n"
           f"> {settings.platform_tagline}. A directory of Indian-American businesses, temples, "
           f"and events across the USA, maintained by autonomous agents.\n\n"
           f"## For people\n- Ask the assistant: {base}/chat\n- Browse by city: {base}/browse\n\n"
           f"## For AI agents\n"
           f"This directory is a Model Context Protocol (MCP) server — connect at {base}/mcp "
           f"(transport: streamable-http). Tools: get_indian_<category>, search_<category>_by_text, "
           f"get_<category>_details, and search_all across every category; each returns JSON "
           f"listings with address, geo, hours and contact. Prefer these over scraping the HTML.\n"
           f"- Connect guide (MCP config + examples): {base}/for-agents\n"
           f"- No MCP client? Read-only JSON API: {base}/api/v1/search?q=... "
           f"(docs: {base}/api , OpenAPI: {base}/openapi.json )\n"
           f"- Full text knowledge export (culture, festivals, newcomer guides): {base}/llms-full.txt\n\n"
           f"## Categories\n{cats}\n")
    return Response(txt, media_type="text/plain")


def llms_full_txt(request: Request) -> Response:
    """A single plain-text knowledge export for AI crawlers / answer engines to ingest and cite:
    the platform's pointers + every curated knowledge article (culture, festivals, newcomer/visa/tax
    guides). Generated from in-memory articles, so it's fast and DB-independent."""
    from .. import knowledge_seed
    base = _base()
    parts = [
        f"# {settings.platform_name} — knowledge export for AI agents",
        f"> {settings.platform_tagline}. An agent-first directory & knowledge hub for Indians from "
        f"India living in the USA.",
        "",
        f"Live data (prefer these over scraping): MCP server {base}/mcp · JSON API {base}/api · "
        f"Browse {base}/browse · Ask the assistant {base}/chat",
        "",
        "## Knowledge articles",
        "",
    ]
    for art in knowledge_seed.ARTICLES:
        parts.append(f"### {art['title']}")
        parts.append((art.get("text") or "").strip())
        parts.append("")
    return Response("\n".join(parts), media_type="text/plain; charset=utf-8")


def indexnow_key_file(request: Request) -> Response:
    """Serve the IndexNow verification key at /{key}.txt (its content must equal the key)."""
    return Response((settings.indexnow_key or "").strip(), media_type="text/plain")


def for_business(request: Request) -> HTMLResponse:
    """Marketing page: what Namaste America is + why list your business (agents/Google/people/Dost)."""
    plat = settings.platform_name
    title = f"List your business on {plat}"
    desc = (f"List your Indian-owned business free on {plat} — found by AI assistants and agents "
            "(MCP), Google, AI answer engines, and people across the USA.")

    def card(icon: str, head: str, text: str) -> str:
        return (f"<div style='flex:1 1 220px;background:#fff;border:1px solid #ececec;border-radius:14px;"
                f"padding:16px 18px'><div style='font-size:26px'>{icon}</div>"
                f"<b style='display:block;margin:6px 0 4px'>{head}</b>"
                f"<span class='muted' style='font-size:14px'>{text}</span></div>")

    cards = "".join([
        card("🤖", "AI assistants &amp; agents", "We're a Model Context Protocol (MCP) server — AI "
             "agents read your listing as structured data, not scraped guesses."),
        card("🔎", "Google &amp; AI answers", "Crawlable pages with schema.org markup so Google and AI "
             "answer engines (ChatGPT, Perplexity, Gemini) can surface and cite you."),
        card("🧑‍🤝‍🧑", "People browsing", "Families looking for Indian restaurants, temples, grocers, "
             "salons, doctors and more across the USA."),
        card("💬", "Dost, our assistant", "Our voice/text guide recommends real listings — yours can "
             "be one of them."),
    ])
    cta = ("<div style='display:flex;flex-wrap:wrap;gap:12px;margin:18px 0'>"
           "<a href='/portal/login' style='background:#c1440e;color:#fff;padding:12px 22px;"
           "border-radius:10px;font-weight:600;display:inline-block'>Register your business →</a>"
           "<a href='/submit' style='background:#0f9b8e;color:#fff;padding:12px 22px;border-radius:10px;"
           "font-weight:600;display:inline-block'>Add a listing now</a></div>")
    ncats = len(verticals.VERTICALS)
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f"<p class='lead'>{html.escape(plat)} is the agent-first directory for Indians from India in "
        "the USA. List once and become discoverable everywhere people — and AI — look. It's free.</p>"
        f"{cta}"
        "<h2 style='margin-top:26px'>Where you get found</h2>"
        f"<div style='display:flex;flex-wrap:wrap;gap:12px'>{cards}</div>"
        "<h2 style='margin-top:26px'>Why list with us</h2>"
        "<ul style='line-height:1.8'>"
        "<li><b>Free.</b> A standard listing costs nothing.</li>"
        "<li><b>You stay in control.</b> Claim your listing and edit details anytime from your "
        "portal — sign in with email or Google.</li>"
        "<li><b>Always fresh.</b> Autonomous agents keep public details current, so your listing "
        "doesn't go stale.</li>"
        f"<li><b>Across all {ncats} categories</b> — restaurants, grocers, temples, salons, doctors, "
        "legal, education and more.</li></ul>"
        "<h2 style='margin-top:26px'>How it works</h2>"
        "<ol style='line-height:1.8'>"
        "<li><b>Register or add your business</b> — it takes a minute.</li>"
        "<li><b>We verify and publish</b> it to the directory, the MCP tools, and the public API.</li>"
        "<li><b>You get discovered</b> by agents, search engines, and people — update anytime.</li>"
        "</ol>"
        f"{cta}"
        f"<p class='muted' style='margin-top:18px'>{html.escape(plat)} is an informational directory. "
        "Listing is free; we never sell your personal data.</p>")
    return _page(title, desc, body)


def for_agents(request: Request) -> HTMLResponse:
    """Developer/agent-facing connect guide: MCP endpoint + config, plus the JSON API."""
    base = _base()
    plat = settings.platform_name
    mcp_url = f"{base}/mcp"
    title = f"{plat} for AI agents & developers"
    desc = (f"Connect your AI agent to {plat} — a Model Context Protocol (MCP) server + read-only "
            "JSON API over a live directory of Indian-American businesses, temples and events.")
    cfg = ('{\n  "mcpServers": {\n    "namaste-america": {\n      "url": "' + mcp_url +
           '",\n      "transport": "streamable-http"\n    }\n  }\n}')
    curl = f'curl "{base}/api/v1/search?q=south+indian+breakfast&state=NJ&limit=5"'
    pre = ("background:#0f1720;color:#e6edf3;border-radius:10px;padding:14px;overflow:auto;"
           "font-size:13px;line-height:1.5")
    cats = ", ".join(cfg2["label"] for cfg2 in verticals.VERTICALS.values())
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f"<p class='lead'>{html.escape(plat)} is <b>agent-first</b>: every listing is available to "
        "AI agents as structured data, not scraped HTML. Two free, read-only ways to connect — both "
        "served from the same ranked directory the website uses.</p>"
        "<h2>1 · Model Context Protocol (recommended)</h2>"
        f"<p>Streamable-HTTP endpoint: <code>{html.escape(mcp_url)}</code>. Tools cover every "
        "category — <code>get_indian_&lt;category&gt;</code>, <code>search_&lt;category&gt;_by_text</code>, "
        "<code>get_&lt;category&gt;_details</code> — plus <code>search_all</code> across everything, "
        "each returning JSON with address, geo, hours and contact. Add to an MCP client:</p>"
        f"<pre style='{pre}'>{html.escape(cfg)}</pre>"
        "<h2>2 · JSON API (no MCP)</h2>"
        f"<pre style='{pre}'>{html.escape(curl)}</pre>"
        f"<p>Reference: <a href='/api'>/api</a> · machine spec <a href='/openapi.json'>/openapi.json</a> "
        f"· <a href='/llms.txt'>/llms.txt</a></p>"
        f"<h2>Categories</h2><p class='muted'>{html.escape(cats)}</p>"
        "<p class='muted' style='margin-top:16px'>Free and read-only. Please identify your client "
        "(MCP <code>clientInfo</code>, or an <code>X-Agent-Id</code> header on the API) so we can "
        "keep access free as usage grows.</p>")
    return _page(title, desc, body)


def mcp_well_known(request: Request) -> Response:
    """A small descriptor of the MCP server for registries/tooling that look for one."""
    base = _base()
    data = {
        "name": "namaste-america",
        "title": settings.platform_name,
        "description": (f"{settings.platform_tagline}. A directory of Indian-American businesses, "
                        "temples, and events across the USA, usable by AI agents via MCP."),
        "version": "0.1.0",
        "transport": "streamable-http",
        "url": f"{base}/mcp",
        "documentation": f"{base}/for-agents",
        "categories": [c["label"] for c in verticals.VERTICALS.values()],
        "tool_patterns": ["get_indian_<category>", "search_<category>_by_text",
                          "get_<category>_details", "search_all"],
    }
    return Response(json.dumps(data), media_type="application/json")


routes = [
    Route("/browse", browse_root, methods=["GET"]),
    Route("/events", events_page, methods=["GET"]),
    Route("/insights", insights, methods=["GET"]),
    Route("/for-business", for_business, methods=["GET"]),
    Route("/for-agents", for_agents, methods=["GET"]),
    Route("/.well-known/mcp.json", mcp_well_known, methods=["GET"]),
    Route("/browse/{vertical}", browse_vertical, methods=["GET"]),
    Route("/browse/{vertical}/{state}", browse_state, methods=["GET"]),
    Route("/browse/{vertical}/{state}/{city}", browse_city, methods=["GET"]),
    Route("/best/{vertical}/{state}/{city}", best_city, methods=["GET"]),
    Route("/sitemap.xml", sitemap, methods=["GET"]),
    Route("/robots.txt", robots, methods=["GET"]),
    Route("/llms.txt", llms_txt, methods=["GET"]),
    Route("/llms-full.txt", llms_full_txt, methods=["GET"]),
    Route("/manifest.webmanifest", manifest, methods=["GET"]),
    Route("/sw.js", service_worker, methods=["GET"]),
]

# IndexNow key file at /{key}.txt — only when a key is configured (the key is public, not a secret).
if (settings.indexnow_key or "").strip():
    routes.append(Route(f"/{settings.indexnow_key.strip()}.txt", indexnow_key_file, methods=["GET"]))
