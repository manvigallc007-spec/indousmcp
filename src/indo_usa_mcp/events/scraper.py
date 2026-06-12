"""Automated event ingestion from public iCalendar (.ics) feeds.

Temples, community orgs and universities publish events as public .ics calendars — the
standard, free, automatable source (events aren't in OSM). Agents fetch configured feed
URLs, parse upcoming VEVENTs, and hand them to the pipeline. Focused parser (no extra dep):
handles line folding, common DT forms, and the fields we use; ignores RRULE for v1.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Iterator

import httpx

from ..config import settings

_DT = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})Z?)?$")


def _feeds() -> list[str]:
    """Configured feeds (EVENT_ICAL_FEEDS) + auto-discovered feeds from org websites."""
    configured = [f.strip() for f in (settings.event_ical_feeds or "").split(",") if f.strip()]
    from .discovery import discovered_feeds
    return list(dict.fromkeys(configured + discovered_feeds()))


def _unfold(text: str) -> list[str]:
    """RFC5545 line unfolding: continuation lines begin with a space or tab."""
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _parse_dt(value: str) -> dt.datetime | None:
    m = _DT.match(value.strip())
    if not m:
        return None
    y, mo, d, hh, mi, ss = m.groups()
    try:
        return dt.datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0))
    except ValueError:
        return None


def _unescape(v: str) -> str:
    return v.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").replace("\\\\", "\\").strip()


class ICalScraper:
    source_name = "ical"

    def scrape(self, region: str = "") -> Iterator[dict]:  # region unused (feeds are nationwide)
        for url in _feeds():
            try:
                resp = httpx.get(url, headers={"User-Agent": settings.scraper_user_agent},
                                 timeout=settings.scraper_timeout_seconds, follow_redirects=True)
                resp.raise_for_status()
            except Exception:
                continue
            yield from self._parse(resp.text, url)

    def _parse(self, text: str, feed_url: str) -> Iterator[dict]:
        event: dict | None = None
        for line in _unfold(text):
            if line == "BEGIN:VEVENT":
                event = {}
            elif line == "END:VEVENT":
                cand = self._to_candidate(event or {}, feed_url)
                if cand is not None:
                    yield cand
                event = None
            elif event is not None and ":" in line:
                key, val = line.split(":", 1)
                prop = key.split(";", 1)[0].upper()
                if prop in ("SUMMARY", "DTSTART", "DTEND", "LOCATION", "DESCRIPTION", "URL", "UID"):
                    event[prop] = val

    def _to_candidate(self, e: dict, feed_url: str) -> dict | None:
        title = _unescape(e.get("SUMMARY", ""))
        start = _parse_dt(e.get("DTSTART", ""))
        if not title or start is None:
            return None
        # Skip past events at ingest time (lifecycle: only fetch upcoming).
        end = _parse_dt(e.get("DTEND", "")) if e.get("DTEND") else None
        if (end or start) < dt.datetime.now():
            return None
        return {
            "source_name": self.source_name,
            "source_url": _unescape(e.get("URL", "")) or feed_url,
            "source_id": f"{feed_url}#{e.get('UID', title + start.isoformat())}",
            "name": title,
            "start_at": start.isoformat(),
            "end_at": end.isoformat() if end else None,
            "venue_name": _unescape(e.get("LOCATION", "")) or None,
            "address_full": _unescape(e.get("LOCATION", "")) or None,
            "festival_specials": _unescape(e.get("DESCRIPTION", "")) or None,
            "website": _unescape(e.get("URL", "")) or None,
        }
