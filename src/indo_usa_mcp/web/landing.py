"""Public, crawlable directory pages — distribution for SEO + AI answer engines.

Server-rendered, indexable pages per (category × city), with schema.org JSON-LD so Google
and AI answer engines (ChatGPT/Perplexity/Gemini) can surface and cite real listings. Plus
sitemap.xml, robots.txt, and an llms.txt that points AI agents at the MCP tools.

No auth, no DB writes — read-only over active listings.
"""

from __future__ import annotations

import html
import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from .. import db, verticals
from ..config import settings

_BRAND = "#c1440e"
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


def _unslug(s: str) -> str:
    return (s or "").replace("-", " ").strip()


def _base() -> str:
    return settings.public_web_url.rstrip("/")


def _page(title: str, desc: str, body: str, jsonld: str = "", status: int = 200) -> HTMLResponse:
    plat = html.escape(settings.platform_name)
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
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
 .lc{{background:#fff;border:1px solid #ececec;border-left:4px solid {_BRAND};border-radius:12px;
   padding:14px 16px;margin:10px 0}}
 .lc h3{{margin:0 0 4px;font-size:17px}} .lc p{{margin:5px 0;color:#4b5563;font-size:14px}}
 .lc .meta{{color:#6b7280;font-size:13px}} .lc .feat{{color:#b45309;font-weight:600}}
 .lc .ver{{color:#1565c0;font-weight:600}}
 .cta{{background:{_BRAND};color:#fff;padding:11px 18px;border-radius:10px;display:inline-block;margin-top:8px}}
 nav.crumbs{{font-size:13px;margin-bottom:14px}}
</style></head><body>
<header><a href="/">{plat}</a> &nbsp;·&nbsp; <a href="/browse">Browse</a> &nbsp;·&nbsp; <a href="/chat">Ask the assistant</a></header>
<main>{body}</main></body></html>"""
    return HTMLResponse(doc, status_code=status)


def _label(v: str) -> str:
    return verticals.VERTICALS.get(v, {}).get("label", v)


# ---------------------------------------------------------------- browse indexes
def browse_root(request: Request) -> HTMLResponse:
    chips = "".join(
        f"<a class='chip' href='{'/events' if v == 'events' else '/browse/' + v}'>"
        f"{html.escape(cfg['label'])}</a>" for v, cfg in verticals.VERTICALS.items())
    body = ("<h1>Browse the Indian-American directory</h1>"
            "<p class='muted'>Find restaurants, temples, groceries, events and more by city, "
            "across the USA.</p>"
            f"<div class='chips'>{chips}</div>"
            "<p style='margin-top:18px'><a class='cta' href='/events'>📅 Upcoming events &amp; festivals →</a></p>")
    return _page(f"Browse · {settings.platform_name}",
                 "Browse Indian-American businesses, temples and events by category and city.", body)


def browse_vertical(request: Request) -> HTMLResponse:
    v = request.path_params["vertical"]
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    if v == "events":  # events are date-based — send to the calendar
        return RedirectResponse("/events", status_code=307)
    rows = verticals.geo_summary(v)  # states with active counts
    items = "".join(
        f"<a class='chip' href='/browse/{v}/{_slug(r['state'])}'>{html.escape(r['state'])} "
        f"<span class='muted'>({r['n']})</span></a>" for r in rows if r["state"] and r["state"] != "(unknown)")
    body = (f"<nav class='crumbs'><a href='/browse'>Browse</a> › {html.escape(_label(v))}</nav>"
            f"<h1>Indian {html.escape(_label(v))} in the USA</h1>"
            "<p class='muted'>Pick a state to see cities.</p>"
            f"<div class='chips'>{items}</div>")
    return _page(f"Indian {_label(v)} in the USA · {settings.platform_name}",
                 f"Browse Indian {_label(v)} across the USA by state and city.", body)


def browse_state(request: Request) -> HTMLResponse:
    v, state = request.path_params["vertical"], _unslug(request.path_params["state"])
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    rows = verticals.geo_summary(v, state)  # cities in this state
    items = "".join(
        f"<a class='chip' href='/browse/{v}/{_slug(state)}/{_slug(r['city'])}'>{html.escape(r['city'])} "
        f"<span class='muted'>({r['n']})</span></a>" for r in rows if r["city"] and r["city"] != "(unknown)")
    label = _label(v)
    body = (f"<nav class='crumbs'><a href='/browse'>Browse</a> › "
            f"<a href='/browse/{v}'>{html.escape(label)}</a> › {html.escape(state.upper())}</nav>"
            f"<h1>Indian {html.escape(label)} in {html.escape(state.upper())}</h1>"
            "<p class='muted'>Pick a city.</p>"
            f"<div class='chips'>{items or '<span class=muted>No listings yet.</span>'}</div>")
    return _page(f"Indian {label} in {state.upper()} · {settings.platform_name}",
                 f"Browse Indian {label} in {state.upper()} by city.", body)


def _listings(v: str, state: str, city: str, limit: int = 200) -> list[dict]:
    table = verticals._table(v)
    return db.query(
        f"SELECT name, address_full, city, state, lat, lng, phone, website, description, "
        f"is_claimed, {_FEATURED} AS is_featured FROM {table} WHERE deleted_at IS NULL AND is_active "
        f"AND LOWER(state) = LOWER(%s) AND LOWER(city) = LOWER(%s) "
        f"ORDER BY {_FEATURED} DESC, confidence_score DESC LIMIT %s", (state, city, limit))


def browse_city(request: Request) -> HTMLResponse:
    v = request.path_params["vertical"]
    state = _unslug(request.path_params["state"])
    city = _unslug(request.path_params["city"])
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    rows = _listings(v, state, city)
    label = _label(v)
    loc = f"{city.title()}, {state.upper()}"
    h1 = f"Indian {label} in {loc}"

    cards, ld_items = "", []
    for i, r in enumerate(rows, 1):
        addr = ", ".join(x for x in (r.get("address_full"),) if x) or loc
        feat = " <span class='feat'>★ Featured</span>" if r.get("is_featured") else ""
        feat += " <span class='ver'>✓ Owner-verified</span>" if r.get("is_claimed") else ""
        links = " · ".join(
            x for x in (
                (f"<a href='{html.escape(r['website'])}' rel='nofollow'>Website</a>" if r.get("website") else ""),
                (f"<a href='tel:{html.escape(r['phone'])}'>{html.escape(r['phone'])}</a>" if r.get("phone") else ""),
            ) if x)
        cards += (f"<div class='lc'><h3>{i}. {html.escape(r['name'])}{feat}</h3>"
                  f"<div class='meta'>{html.escape(addr)}</div>"
                  + (f"<p>{html.escape((r.get('description') or '')[:220])}</p>" if r.get("description") else "")
                  + (f"<div class='meta'>{links}</div>" if links else "") + "</div>")
        item = {"@type": "ListItem", "position": i, "item": {
            "@type": "LocalBusiness", "name": r["name"],
            "address": {"@type": "PostalAddress", "addressLocality": r.get("city"),
                        "addressRegion": r.get("state"), "streetAddress": r.get("address_full")},
        }}
        if r.get("phone"):
            item["item"]["telephone"] = r["phone"]
        if r.get("website"):
            item["item"]["url"] = r["website"]
        if r.get("lat") and r.get("lng"):
            item["item"]["geo"] = {"@type": "GeoCoordinates", "latitude": r["lat"], "longitude": r["lng"]}
        ld_items.append(item)

    if not rows:
        body = (f"<h1>{html.escape(h1)}</h1><p class='muted'>No listings here yet — "
                f"<a href='/submit'>add one</a> or <a href='/chat'>ask the assistant</a>.</p>")
        return _page(f"{h1} · {settings.platform_name}", f"Indian {label} in {loc}.", body)

    jsonld = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                         "name": h1, "numberOfItems": len(rows), "itemListElement": ld_items})
    body = (f"<nav class='crumbs'><a href='/browse'>Browse</a> › "
            f"<a href='/browse/{v}'>{html.escape(label)}</a> › "
            f"<a href='/browse/{v}/{_slug(state)}'>{html.escape(state.upper())}</a> › {html.escape(city.title())}</nav>"
            f"<h1>{html.escape(h1)}</h1>"
            f"<p class='muted'>{len(rows)} listing{'s' if len(rows) != 1 else ''}. "
            f"<a href='/chat'>Ask {html.escape(settings.assistant_name)}</a> for personalized picks.</p>"
            f"{cards}<p><a class='cta' href='/chat'>Ask the assistant →</a></p>")
    return _page(f"{h1} · {settings.platform_name} ({len(rows)})",
                 f"Directory of {len(rows)} Indian {label} in {loc} — addresses, phone, websites.",
                 body, jsonld=jsonld)


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
    urls = [f"{base}/", f"{base}/browse", f"{base}/chat", f"{base}/events"]
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
    body = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{html.escape(u)}</loc></url>" for u in urls) + "</urlset>")
    return Response(body, media_type="application/xml")


def robots(request: Request) -> Response:
    return Response(f"User-agent: *\nAllow: /\nSitemap: {_base()}/sitemap.xml\n",
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
const C='dc-shell-v1';
const SHELL=['/','/chat','/browse','/events','/icon.svg','/manifest.webmanifest'];
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


def llms_txt(request: Request) -> Response:
    base = _base()
    cats = "\n".join(f"- {cfg['label']}: {base}/browse/{v}" for v, cfg in verticals.VERTICALS.items())
    txt = (f"# {settings.platform_name}\n\n"
           f"> {settings.platform_tagline}. A directory of Indian-American businesses, temples, "
           f"and events across the USA, maintained by autonomous agents.\n\n"
           f"## For people\n- Ask the assistant: {base}/chat\n- Browse by city: {base}/browse\n\n"
           f"## For AI agents\nThis directory is also a Model Context Protocol (MCP) server with "
           f"structured tools (get_indian_restaurants, search_all, get_indian_temples, …) returning "
           f"JSON listings with address, geo, hours and contact. Prefer those tools for accurate, "
           f"current data over scraping these HTML pages.\n\n"
           f"## Categories\n{cats}\n")
    return Response(txt, media_type="text/plain")


routes = [
    Route("/browse", browse_root, methods=["GET"]),
    Route("/events", events_page, methods=["GET"]),
    Route("/browse/{vertical}", browse_vertical, methods=["GET"]),
    Route("/browse/{vertical}/{state}", browse_state, methods=["GET"]),
    Route("/browse/{vertical}/{state}/{city}", browse_city, methods=["GET"]),
    Route("/sitemap.xml", sitemap, methods=["GET"]),
    Route("/robots.txt", robots, methods=["GET"]),
    Route("/llms.txt", llms_txt, methods=["GET"]),
    Route("/manifest.webmanifest", manifest, methods=["GET"]),
    Route("/sw.js", service_worker, methods=["GET"]),
]
