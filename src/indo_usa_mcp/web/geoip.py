"""Approximate a visitor's location from their IP — the fallback when the browser won't share GPS.

Lets the chatbot still show nearest-first results without the user typing a city. City-level only,
cached per IP, never raises, and skipped for private/loopback IPs. Uses a free, no-key service
(ipwho.is); if it's unavailable we simply return None and the chat asks for a city instead.
"""

from __future__ import annotations

import ipaddress
import time

import httpx

from ..config import settings

_CACHE: dict[str, tuple[float, tuple[float, float] | None]] = {}
_TTL = 6 * 3600.0  # cache per IP for 6h — only the first chat from an IP does a lookup


def _is_public(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return not (a.is_private or a.is_loopback or a.is_reserved or a.is_link_local
                    or a.is_unspecified)
    except ValueError:
        return False


def client_ip(request) -> str | None:
    """Real client IP, honoring X-Forwarded-For (first hop) when behind a proxy like Caddy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def approx_point(ip: str | None) -> tuple[float, float] | None:
    """(lat, lng) estimate for a public IP, or None. Cached; graceful on any failure."""
    if not settings.geoip_enabled or not ip or not _is_public(ip):
        return None
    now = time.time()
    hit = _CACHE.get(ip)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    point: tuple[float, float] | None = None
    try:
        r = httpx.get(f"https://ipwho.is/{ip}",
                      headers={"User-Agent": settings.scraper_user_agent}, timeout=4.0)
        if r.status_code == 200:
            d = r.json()
            if d.get("success") and d.get("latitude") is not None and d.get("longitude") is not None:
                point = (float(d["latitude"]), float(d["longitude"]))
    except Exception:
        point = None
    _CACHE[ip] = (now, point)
    return point
