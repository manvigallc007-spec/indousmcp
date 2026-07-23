"""Latest India/NRI news for the homepage portal + /news.

Aggregates headlines from the FREE Google News RSS search feeds (no API key, no signup) for a curated
set of queries relevant to Indians from India living in the USA. We store only the headline, source and
link — never the article body — and always link out to the source (standard aggregator behaviour).
NewsAgent refreshes this periodically; fetching is best-effort and never raises into a request.
"""

from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import Any

import httpx

from . import db
from .config import settings

# category -> Google News search query. Kept tight + India/NRI-focused so the feed stays relevant.
_FEEDS = {
    "community": "Indian Americans community USA",
    "immigration": "H-1B visa OR green card Indians USA",
    "india-usa": "India United States relations",
    "diaspora": "Indian diaspora USA news",
    "business": "Indian American business OR entrepreneurs USA",
}
_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
_RETENTION_DAYS = 30


def enabled() -> bool:
    return bool(settings.news_enabled)


def latest(limit: int = 8, category: str | None = None) -> list[dict]:
    """Most-recent headlines (newest first). Never raises — returns [] if the table isn't there yet."""
    try:
        if category:
            return db.query(
                "SELECT title, url, source, category, published_at FROM news_articles "
                "WHERE category = %s ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT %s",
                (category, limit))
        return db.query(
            "SELECT title, url, source, category, published_at FROM news_articles "
            "ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT %s", (limit,))
    except Exception:
        return []


def _parse_pubdate(s: str | None):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None


def _parse_feed(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Extract (title, url, source, published_at) items from a Google News RSS document."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        src_el = item.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        # Google News titles are usually "Headline - Source"; strip the trailing source for a clean title.
        if not source and " - " in title:
            title, _, source = title.rpartition(" - ")
        elif source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)]
        out.append({"title": title.strip()[:300], "url": link,
                    "source": (source or None), "published_at": _parse_pubdate(item.findtext("pubDate"))})
    return out


def fetch_and_store(per_feed: int = 12) -> dict[str, int]:
    """Pull every curated feed, upsert new headlines (dedupe on URL), prune old rows. Best-effort:
    a failing feed is skipped, never fatal. Returns {fetched, inserted, pruned}."""
    if not enabled():
        return {"skipped": 1, "fetched": 0, "inserted": 0, "pruned": 0}
    fetched = inserted = 0
    headers = {"User-Agent": settings.scraper_user_agent}
    for category, query in _FEEDS.items():
        try:
            r = httpx.get(_RSS.format(q=quote(query)), headers=headers, timeout=20.0,
                          follow_redirects=True)
            r.raise_for_status()
            items = _parse_feed(r.content)[:per_feed]
        except Exception:
            continue
        for it in items:
            fetched += 1
            try:
                row = db.query_one(
                    "INSERT INTO news_articles (title, url, source, category, published_at) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (url) DO NOTHING RETURNING id",
                    (it["title"], it["url"], it["source"], category, it["published_at"]))
                if row:
                    inserted += 1
            except Exception:
                continue
    pruned = 0
    try:
        res = db.query_one(
            f"WITH d AS (DELETE FROM news_articles WHERE created_at < now() - interval '{_RETENTION_DAYS} days' "
            "RETURNING 1) SELECT count(*) AS n FROM d")
        pruned = int(res["n"]) if res else 0
    except Exception:
        pass
    return {"fetched": fetched, "inserted": inserted, "pruned": pruned}
