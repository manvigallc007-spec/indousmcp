"""Security hardening for the web app: response security headers + a tiny per-IP login throttle.

Defence-in-depth. CSP allows the app's own inline styles/scripts (every page ships inline CSS/JS)
while blocking external script/connect sources and framing — our primary XSS defence remains output
escaping. HSTS is emitted only when the request actually arrived over HTTPS (behind Caddy TLS).
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings


def _build_csp() -> str:
    """CSP allows our own inline CSS/JS; external sources are opened ONLY for features we actually
    use — Google Analytics (when GOOGLE_ANALYTICS_ID is set) and Cloudflare Turnstile (when keys
    are set). Without those, scripts/connections stay locked to 'self'. Output escaping is still
    our primary XSS defence."""
    script = ["'self'", "'unsafe-inline'"]
    connect = ["'self'"]
    frame: list[str] = []
    if settings.google_analytics_id:                       # gtag.js + its data beacons
        script.append("https://www.googletagmanager.com")
        connect += ["https://www.google-analytics.com", "https://*.google-analytics.com",
                    "https://*.analytics.google.com", "https://www.googletagmanager.com"]
    if settings.turnstile_enabled:                         # captcha widget + its iframe
        script.append("https://challenges.cloudflare.com")
        frame.append("https://challenges.cloudflare.com")
    parts = [
        "default-src 'self'", "base-uri 'self'", "frame-ancestors 'none'", "object-src 'none'",
        "img-src 'self' data: https:", "style-src 'self' 'unsafe-inline'",
        f"script-src {' '.join(script)}", f"connect-src {' '.join(connect)}", "form-action 'self'",
    ]
    if frame:
        parts.append(f"frame-src {' '.join(frame)}")
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("Content-Security-Policy", _build_csp())
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Allow the page's OWN mic (voice search / Hindi-Telugu dictation) + geolocation ("near me").
        h.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=(self)")
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
