"""Auto-discover iCalendar feeds on the websites of orgs already in our database.

An agent scans org websites (temples, restaurants, …) for public calendar (.ics / webcal /
Google-Calendar) links and records them, so the event scraper picks them up automatically —
no manual feed configuration. Polite: rate-limited, capped batch per run, re-scans monthly.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from .. import db
from ..config import settings

_HREF = re.compile(r"""(?:href|content)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Websites to scan, drawn from every vertical — temples first (most likely to publish a
# community event calendar), then the rest.
_SITES_SQL = """
SELECT website FROM (
    SELECT website, min(pri) AS pri FROM (
        SELECT website, 1 AS pri FROM temples       WHERE website IS NOT NULL AND deleted_at IS NULL
        UNION ALL SELECT website, 2 FROM restaurants   WHERE website IS NOT NULL AND deleted_at IS NULL
        UNION ALL SELECT website, 2 FROM groceries     WHERE website IS NOT NULL AND deleted_at IS NULL
        UNION ALL SELECT website, 3 FROM professionals WHERE website IS NOT NULL AND deleted_at IS NULL
        UNION ALL SELECT website, 3 FROM salons        WHERE website IS NOT NULL AND deleted_at IS NULL
    ) u GROUP BY website
) s
WHERE website NOT IN (
    SELECT site_url FROM event_feed_sources WHERE last_scanned > now() - interval '30 days')
ORDER BY pri
LIMIT %s
"""


def extract_ics_links(html: str, base_url: str) -> list[str]:
    """Find iCalendar feed URLs in a page (.ics, webcal:, format=ical), resolved absolute."""
    out: list[str] = []
    for m in _HREF.finditer(html):
        u = m.group(1).strip()
        low = u.lower()
        if low.endswith(".ics") or low.startswith("webcal:") or "format=ical" in low \
                or ("calendar.google.com/calendar/ical" in low):
            if low.startswith("webcal:"):
                u = "https:" + u[len("webcal:"):]
            out.append(urljoin(base_url, u))
    return list(dict.fromkeys(out))[:3]


def discover_feeds(limit: int = 30) -> dict[str, Any]:
    """Scan a batch of un-checked org websites for calendar feeds; record what's found."""
    scanned = found = 0
    for row in db.query(_SITES_SQL, (limit,)):
        site = row["website"]
        ics = None
        try:
            resp = httpx.get(site, timeout=15, follow_redirects=True,
                             headers={"User-Agent": settings.scraper_user_agent})
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                links = extract_ics_links(resp.text, str(resp.url))
                ics = links[0] if links else None
        except Exception:
            pass
        db.execute(
            "INSERT INTO event_feed_sources (site_url, ics_url, found, last_scanned) "
            "VALUES (%s, %s, %s, now()) ON CONFLICT (site_url) DO UPDATE "
            "SET ics_url = EXCLUDED.ics_url, found = EXCLUDED.found, last_scanned = now()",
            (site, ics, ics is not None))
        scanned += 1
        found += int(ics is not None)
        time.sleep(0.5)  # politeness between third-party sites
    return {"scanned": scanned, "feeds_found": found}


def discovered_feeds() -> list[str]:
    try:
        return [r["ics_url"] for r in db.query(
            "SELECT ics_url FROM event_feed_sources WHERE found AND active AND ics_url IS NOT NULL")]
    except Exception:
        return []
