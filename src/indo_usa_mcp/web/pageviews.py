"""First-party pageview counting: a tiny middleware that records each public HTML page view
server-side, so the admin Traffic page reflects real visits even when Google Analytics is blocked.
Best-effort + aggregate-only (no per-hit rows, no PII)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

# Don't count admin/api/owner/transactional routes — only public, human-facing pages.
_SKIP = ("/admin", "/api", "/portal", "/stripe", "/optout", "/claim", "/manage", "/upgrade",
         "/chat/", "/.well-known")


def _norm(path: str) -> str:
    """Collapse to the first two path segments to keep cardinality sane (city pages -> their category)."""
    if path == "/" or not path:
        return "/"
    segs = [s for s in path.split("/") if s][:2]
    return "/" + "/".join(segs)


class PageviewMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        try:
            path = request.url.path
            if (request.method == "GET" and resp.status_code == 200
                    and resp.headers.get("content-type", "").startswith("text/html")
                    and not path.startswith(_SKIP)):
                from .. import analytics
                analytics.log_pageview(_norm(path))
        except Exception:
            pass
        return resp
