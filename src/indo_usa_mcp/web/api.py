"""Public read-only JSON search API.

A plain-HTTP companion to the MCP server, so AI agents and websites that can't speak MCP can
still query the directory:

  GET /api/v1/search?q=...&city=&state=&vertical=&lat=&lng=&limit=  -> JSON
  GET /api/v1/verticals                                             -> the category list
  GET /api                                                          -> human/agent-readable docs

No auth, no writes, only active listings — same data the MCP tools and chatbot serve, ranked by
the shared hybrid ranking (see ranking.py). Per-IP rate limited as a light abuse guard.
"""

from __future__ import annotations

import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .. import verticals
from ..config import settings

_HITS: dict[str, list[float]] = {}

# Stable, documented output fields. We project onto these so internal/DB columns never leak and
# the contract stays predictable for third-party consumers.
_PUBLIC_FIELDS = (
    "vertical", "name", "city", "state", "address", "phone", "website",
    "latitude", "longitude", "rating", "rating_count", "tags", "description",
    "distance_miles", "is_featured", "is_claimed", "open_now", "verified_ago",
)


def _rate_ok(ip: str) -> bool:
    now = time.time()
    window = [t for t in _HITS.get(ip, []) if now - t < 60]
    if len(window) >= settings.api_rate_per_min:
        _HITS[ip] = window
        return False
    window.append(now)
    _HITS[ip] = window
    return True


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _public_row(r: dict) -> dict:
    return {k: r[k] for k in _PUBLIC_FIELDS if r.get(k) is not None}


def search(request: Request) -> JSONResponse:
    ip = (request.client.host if request.client else "?") or "?"
    if not _rate_ok(ip):
        return JSONResponse({"error": "rate_limited",
                             "message": "Too many requests — slow down a moment."}, status_code=429)

    qp = request.query_params
    query = (qp.get("q") or qp.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "missing_query",
                             "message": "Pass ?q=<what you're looking for>."}, status_code=400)

    city = (qp.get("city") or "").strip() or None
    state = (qp.get("state") or "").strip() or None
    vertical = (qp.get("vertical") or "").strip() or None
    lat, lng = _float(qp.get("lat")), _float(qp.get("lng"))
    try:
        limit = max(1, min(50, int(qp.get("limit") or 20)))
    except ValueError:
        limit = 20

    if vertical and vertical not in verticals.VERTICALS:
        return JSONResponse(
            {"error": "unknown_vertical", "message": f"Unknown vertical '{vertical}'.",
             "valid": list(verticals.VERTICALS)}, status_code=400)

    point = (lat, lng) if lat is not None and lng is not None else None
    if vertical:
        fn = getattr(verticals.VERTICALS[vertical]["queries"], f"search_{vertical}_by_text", None)
        if fn is None:  # e.g. events use date-first listing, not text-rank
            return JSONResponse({"error": "unsupported_vertical",
                                 "message": f"'{vertical}' is not text-searchable here."}, status_code=400)
        res = fn(query, city=city, state=state, limit=limit, point=point)
        for r in res["results"]:
            r.setdefault("vertical", vertical)
    else:
        res = verticals.search_all(query, city=city, state=state, limit=limit,
                                   lat=lat, lng=lng)

    rows = [_public_row(r) for r in res.get("results", [])]
    return JSONResponse({
        "query": query, "count": len(rows), "ranking": res.get("ranking"),
        "vertical": vertical, "results": rows,
    })


def verticals_list(request: Request) -> JSONResponse:
    return JSONResponse({"verticals": [
        {"key": k, "label": cfg["label"]} for k, cfg in verticals.VERTICALS.items()]})


_DOCS = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API · {plat}</title>
<style>body{{font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2430;
max-width:760px;margin:0 auto;padding:32px 20px}}code,pre{{font-family:ui-monospace,Menlo,Consolas,monospace}}
pre{{background:#f6f4f1;border:1px solid #ececec;border-radius:10px;padding:14px;overflow:auto}}
h1{{margin:0 0 4px}}.muted{{color:#6b7280}}table{{border-collapse:collapse;width:100%;margin:8px 0}}
td,th{{border:1px solid #ececec;padding:6px 10px;text-align:left;font-size:14px}}a{{color:#c1440e}}</style>
</head><body>
<h1>{plat} — Public Search API</h1>
<p class="muted">Read-only JSON over the live directory. No auth. Rate limit: {rate}/min per IP.
AI agents: prefer the MCP server (structured tools); this HTTP API is for clients that can't speak MCP.</p>
<h2><code>GET /api/v1/search</code></h2>
<table><tr><th>Param</th><th>Notes</th></tr>
<tr><td><code>q</code></td><td><b>required.</b> Free text, e.g. <code>vegetarian thali</code></td></tr>
<tr><td><code>city</code>, <code>state</code></td><td>optional location filter (e.g. <code>state=NJ</code>)</td></tr>
<tr><td><code>vertical</code></td><td>optional — scope to one category ({verts})</td></tr>
<tr><td><code>lat</code>, <code>lng</code></td><td>optional — enables proximity ranking + <code>distance_miles</code></td></tr>
<tr><td><code>limit</code></td><td>optional, 1–50 (default 20)</td></tr></table>
<pre>curl "{base}/api/v1/search?q=south+indian+breakfast&state=NJ&limit=5"</pre>
<pre>{{
  "query": "south indian breakfast",
  "count": 5,
  "ranking": "vector",
  "results": [
    {{"vertical": "restaurants", "name": "Dosa Hut", "city": "Edison", "state": "NJ",
     "phone": "+1 732 555 0100", "website": "https://...", "rating": 4.6,
     "latitude": 40.5, "longitude": -74.3, "verified_ago": "verified 3 days ago"}}
  ]
}}</pre>
<h2><code>GET /api/v1/verticals</code></h2>
<p>Lists the category keys you can pass to <code>?vertical=</code>.</p>
<p class="muted">See also <a href="/llms.txt">/llms.txt</a> · <a href="/chat">chat</a> · <a href="/browse">browse</a></p>
</body></html>"""


def docs(request: Request) -> HTMLResponse:
    base = settings.public_web_url.rstrip("/")
    return HTMLResponse(_DOCS.format(
        plat=settings.platform_name, rate=settings.api_rate_per_min, base=base,
        verts=", ".join(verticals.VERTICALS)))


routes = [
    Route("/api", docs, methods=["GET"]),
    Route("/api/v1/search", search, methods=["GET"]),
    Route("/api/v1/verticals", verticals_list, methods=["GET"]),
]
