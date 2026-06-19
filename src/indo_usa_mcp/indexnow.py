"""IndexNow — instantly tell Bing / Copilot / Yandex (and other IndexNow engines) when pages change.

Free, no account: we publish a key file at /{key}.txt and POST the changed URLs. Enable by setting
INDEXNOW_KEY in .env to a random 16-32 char hex string; blank = disabled and every call is a no-op
that never raises (so it can sit safely in the ingest/agent path).
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .config import settings

_ENDPOINT = "https://api.indexnow.org/indexnow"


def enabled() -> bool:
    return bool((settings.indexnow_key or "").strip())


def _base() -> str:
    return settings.public_web_url.rstrip("/")


def _is_public(host: str) -> bool:
    return bool(host) and host != "localhost" and not host.startswith(("localhost:", "127.", "0.0.0.0"))


def submit(urls) -> dict:
    """POST changed URLs to IndexNow. No-op (and never raises) when disabled, when the base URL is
    local, or when no on-site URLs are given. Dedupes, keeps only our own host, caps at 10k."""
    key = (settings.indexnow_key or "").strip()
    base = _base()
    host = urlparse(base).netloc
    urls = [u for u in dict.fromkeys(urls or []) if u.startswith(base)][:10000]
    if not key or not urls or not _is_public(host):
        return {"submitted": 0, "skipped": True}
    payload = {"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": urls}
    try:
        r = httpx.post(_ENDPOINT, json=payload, timeout=10.0,
                       headers={"Content-Type": "application/json; charset=utf-8"})
        return {"submitted": len(urls), "status": r.status_code}
    except Exception as exc:                      # network is best-effort; never break the caller
        return {"submitted": 0, "error": str(exc)}


def recent_listing_urls(hours: int = 24, limit: int = 2000) -> list[str]:
    """Public /listing URLs for listings created or updated in the last `hours` — the pages IndexNow
    should refresh. Bounded; resilient to any missing table/column."""
    from . import db, verticals
    base = _base()
    out: list[str] = []
    for v in verticals.VERTICALS:
        if v == "events":
            continue
        try:
            rows = db.query(
                f"SELECT id FROM {verticals._table(v)} WHERE deleted_at IS NULL AND is_active "
                f"AND updated_at > now() - interval '{int(hours)} hours' "
                f"ORDER BY updated_at DESC LIMIT %s", (limit,))
        except Exception:
            rows = []
        out += [f"{base}/listing/{v}/{r['id']}" for r in rows]
    return out[:limit]


def ping_recent(hours: int = 24) -> dict:
    """Submit recently-changed listing URLs (used by the cleaner agent). No-op unless enabled."""
    if not enabled():
        return {"submitted": 0, "skipped": True}
    return submit(recent_listing_urls(hours=hours))
