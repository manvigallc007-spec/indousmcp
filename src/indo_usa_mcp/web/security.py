"""Security hardening for the web app: response security headers + a tiny per-IP login throttle.

Defence-in-depth. CSP allows the app's own inline styles/scripts (every page ships inline CSS/JS)
while blocking external script/connect sources and framing — our primary XSS defence remains output
escaping. HSTS is emitted only when the request actually arrived over HTTPS (behind Caddy TLS).
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

# 'unsafe-inline' is required because pages embed inline <style>/<script>; we still lock down the
# sources scripts/data can come from, framing, and the base URI.
_CSP = (
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
    "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("Content-Security-Policy", _CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":  # only meaningful over TLS
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp


# --- tiny per-IP throttle for login brute-force (separate from the chat/api limiters) ---
_ATTEMPTS: dict[str, list[float]] = {}


def too_many_attempts(ip: str, limit: int = 8, window: float = 300.0) -> bool:
    now = time.time()
    xs = [t for t in _ATTEMPTS.get(ip, []) if now - t < window]
    _ATTEMPTS[ip] = xs
    return len(xs) >= limit


def record_attempt(ip: str) -> None:
    _ATTEMPTS.setdefault(ip, []).append(time.time())


def clear_attempts(ip: str) -> None:
    _ATTEMPTS.pop(ip, None)
