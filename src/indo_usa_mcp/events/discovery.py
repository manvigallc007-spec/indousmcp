"""Auto-discover iCalendar feeds on the websites of orgs already in our database.

An agent scans org websites (temples, community associations, restaurants, …) for public calendar
(.ics / webcal / Google-Calendar) links — on the homepage, then a couple common calendar sub-paths
if needed — and records them, so the event scraper picks them up automatically. No manual feed
configuration. Polite: rate-limited, capped batch per run, re-scans monthly.
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

# Websites to scan, drawn from every vertical — temples and community associations (sangams,
# mandals, cultural centers: the orgs that actually RUN diaspora community events) come first as the
# highest-yield sources, then the rest.
_SITES_SQL = """
SELECT website FROM (
    SELECT website, min(pri) AS pri FROM (
        SELECT website, 1 AS pri FROM temples       WHERE website IS NOT NULL AND deleted_at IS NULL
        UNION ALL SELECT website, 1 FROM community     WHERE website IS NOT NULL AND deleted_at IS NULL
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


# Common paths for an org's events/calendar page, tried when the homepage itself has no direct
# .ics link. Many WordPress ("The Events Calendar" plugin) / Squarespace sites link their calendar
# only from a nav item, not the homepage body, so the link never appears in `extract_ics_links` on
# the homepage HTML alone. One extra polite GET, only when the homepage came up empty.
_CALENDAR_PATHS = ("events", "calendar", "events-calendar")


def _find_ics(site: str) -> str | None:
    """The first iCal feed for a site: check the homepage, then a couple common calendar sub-paths
    if the homepage has none. Returns None (not an error) if nothing is found — most sites simply
    don't publish one, which is expected and not penalized."""
    try:
        resp = httpx.get(site, timeout=15, follow_redirects=True,
                         headers={"User-Agent": settings.scraper_user_agent})
    except Exception:
        return None
    if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
        return None
    links = extract_ics_links(resp.text, str(resp.url))
    if links:
        return links[0]
    for path in _CALENDAR_PATHS:
        try:
            sub = httpx.get(urljoin(str(resp.url), path), timeout=15, follow_redirects=True,
                            headers={"User-Agent": settings.scraper_user_agent})
        except Exception:
            continue
        if sub.status_code == 200 and "text/html" in sub.headers.get("content-type", ""):
            links = extract_ics_links(sub.text, str(sub.url))
            if links:
                return links[0]
        time.sleep(0.3)  # politeness between sub-page probes on the SAME site
    return None


def discover_feeds(limit: int = 30) -> dict[str, Any]:
    """Scan a batch of un-checked org websites for calendar feeds; record what's found."""
    scanned = found = 0
    for row in db.query(_SITES_SQL, (limit,)):
        site = row["website"]
        ics = _find_ics(site)
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
