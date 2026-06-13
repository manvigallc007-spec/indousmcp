"""Broken-link detector — keep dead URLs out of the directory (trust).

Probes each listing's `website`; only a **definitive** dead result (HTTP 404/410 or a DNS/
connection failure) counts a "strike", and the URL is removed only after **2 strikes** across
runs — never on a single transient blip (timeouts, 5xx, 403/429 are ignored). Polite + batched.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from . import db, verticals
from .config import settings

_VERTICALS = list(verticals.VERTICALS)  # all carry a `website` column


def _probe(url: str) -> str:
    """'ok' | 'dead' | 'unknown' (transient/blocked — don't penalise)."""
    headers = {"User-Agent": settings.scraper_user_agent}
    try:
        r = httpx.head(url, timeout=10, follow_redirects=True, headers=headers)
        if r.status_code in (401, 403, 405):  # some servers refuse HEAD — confirm with GET
            r = httpx.get(url, timeout=12, follow_redirects=True, headers=headers)
        code = r.status_code
        if code in (404, 410):
            return "dead"
        if code < 400:
            return "ok"
        return "unknown"  # 403/429/5xx etc. — could be transient or bot-blocking
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return "dead"      # DNS not found / connection refused (after redirects)
    except Exception:
        return "unknown"   # read timeouts, TLS quirks, etc. — be conservative


def check_links(limit_per_vertical: int = 50, max_age_days: int = 14) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for v in _VERTICALS:
        t = verticals._table(v)
        rows = db.query(
            f"SELECT id, website FROM {t} WHERE deleted_at IS NULL AND is_active "
            f"AND website IS NOT NULL AND website <> '' "
            f"AND (link_checked_at IS NULL OR link_checked_at < now() - (%s || ' days')::interval) "
            f"ORDER BY link_checked_at NULLS FIRST, id LIMIT %s", (max_age_days, limit_per_vertical))
        checked = cleared = 0
        for r in rows:
            status = _probe(r["website"])
            if status == "ok":
                db.execute(f"UPDATE {t} SET link_strikes = 0, link_checked_at = now() WHERE id = %s",
                           (r["id"],))
            elif status == "dead":
                row = db.query_one(
                    f"UPDATE {t} SET link_strikes = link_strikes + 1, link_checked_at = now() "
                    f"WHERE id = %s RETURNING link_strikes", (r["id"],))
                if row and row["link_strikes"] >= 2:  # confirmed dead -> drop the URL
                    db.execute(f"UPDATE {t} SET website = NULL, updated_at = now() WHERE id = %s",
                               (r["id"],))
                    cleared += 1
            else:  # transient/blocked — just record we looked, don't strike
                db.execute(f"UPDATE {t} SET link_checked_at = now() WHERE id = %s", (r["id"],))
            checked += 1
            time.sleep(0.3)  # politeness between third-party sites
        out[v] = {"checked": checked, "cleared": cleared}
    return out
