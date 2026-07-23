"""Friendly, branded 404 / 500 pages + a lightweight health check for uptime monitors."""

from __future__ import annotations

import html

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from ..config import settings

# Self-contained (no DB / heavy imports) so the 500 handler itself can never fail.
_ERR_TMPL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{code} · {plat}</title><link rel="icon" type="image/svg+xml" href="/icon.svg">
<meta name="theme-color" content="#e8772e"><style>
body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:#faf8f4;color:#222b33;
 min-height:100vh;margin:0;padding:0}}
.box{{max-width:460px;margin:8vh auto;text-align:center;padding:24px}}
.logo{{width:64px;height:64px;border-radius:18px;margin:0 auto 14px;display:grid;
 place-items:center;font-size:32px;background:linear-gradient(135deg,#ffd9a0,#ffb56b)}}
h1{{font-size:56px;margin:0;color:#e8772e;line-height:1}}h2{{font-size:20px;margin:8px 0 10px}}
p{{color:#667085;line-height:1.55;margin:0 0 14px}}
a.btn{{display:inline-block;background:#e8772e;color:#fff;border-radius:10px;padding:11px 22px;font-weight:600;text-decoration:none}}
.links{{margin-top:14px;font-size:14px}}.links a{{color:#0f9b8e;margin:0 8px;text-decoration:none}}
{navcss}
</style></head><body>{nav}<div class="box"><div class="logo">🪷</div>
<h1>{code}</h1><h2>{title}</h2><p>{message}</p>
<a class="btn" href="/">💬 Ask {aname}</a>
<div class="links"><a href="/browse">Browse</a> · <a href="/about">About</a> · <a href="/contact">Contact</a></div>
</div></body></html>"""


def _error_page(code: int, title: str, message: str) -> str:
    # Lazily pull the shared nav; never let it break the (esp. 500) error page.
    try:
        from .common import NAV_CSS, nav_html
        nav, navcss = nav_html(), NAV_CSS
    except Exception:
        nav, navcss = "", ""
    return _ERR_TMPL.format(code=code, title=html.escape(title), message=html.escape(message),
                            plat=html.escape(settings.platform_name),
                            aname=html.escape(settings.assistant_name), nav=nav, navcss=navcss)


def not_found(request: Request, exc: Exception) -> HTMLResponse:
    return HTMLResponse(_error_page(
        404, "Page not found",
        "We couldn't find that page. Try asking Dost, or browse the directory."), status_code=404)


def server_error(request: Request, exc: Exception) -> HTMLResponse:
    return HTMLResponse(_error_page(
        500, "Something went wrong",
        "An unexpected error occurred on our side. Please try again in a moment."), status_code=500)


def health(request: Request) -> JSONResponse:
    """200 = the web app is up. Includes a quick DB reachability flag for readiness checks."""
    db_ok = True
    try:
        from .. import db
        db.query_one("SELECT 1 AS ok")
    except Exception:
        db_ok = False
    return JSONResponse({"status": "ok", "service": settings.platform_name, "db": db_ok})


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/healthz", health, methods=["GET"]),
]
