"""Free, key-less web retrieval for the chatbot's general-info fallback.

When the directory can't answer a *relevant* question, we pull a few short text snippets from
Wikipedia and DuckDuckGo (both free, no API key, no metered service) to GROUND an LLM answer in
plain English. The LLM only rephrases these snippets — it must not invent business listings.

Never raises: every fetch is wrapped and returns [] on error/timeout, so the chat degrades
gracefully (the assistant then says it isn't sure and suggests adding the listing).
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from .config import settings

_TIMEOUT = 6.0


def _headers() -> dict:
    # Wikipedia's API policy requires a descriptive User-Agent; reuse the scraper one.
    return {"User-Agent": settings.scraper_user_agent}


def _wikipedia(query: str) -> list[dict]:
    """Best-matching Wikipedia article's intro extract."""
    try:
        r = httpx.get("https://en.wikipedia.org/w/api.php",
                      params={"action": "query", "list": "search", "srsearch": query,
                              "format": "json", "srlimit": 1},
                      headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            return []
        title = hits[0]["title"]
        s = httpx.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
            headers=_headers(), timeout=_TIMEOUT)
        s.raise_for_status()
        d = s.json()
        text = (d.get("extract") or "").strip()
        if not text:
            return []
        return [{"source": "Wikipedia", "title": d.get("title") or title, "text": text,
                 "url": (d.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")}]
    except Exception:
        return []


def _duckduckgo(query: str) -> list[dict]:
    """DuckDuckGo Instant-Answer abstract (sparse — only entity-like queries return text)."""
    try:
        r = httpx.get("https://api.duckduckgo.com/",
                      params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                      headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        d = r.json()
        text = (d.get("AbstractText") or "").strip()
        if text:
            return [{"source": "DuckDuckGo", "title": d.get("Heading") or query, "text": text,
                     "url": d.get("AbstractURL") or ""}]
        for t in d.get("RelatedTopics", []):
            if isinstance(t, dict) and (t.get("Text") or "").strip():
                return [{"source": "DuckDuckGo", "title": query, "text": t["Text"].strip(),
                         "url": t.get("FirstURL") or ""}]
        return []
    except Exception:
        return []


def lookup(query: str, max_snippets: int = 3) -> list[dict]:
    """Up to `max_snippets` deduped {source,title,text,url} snippets. [] if nothing/offline."""
    query = (query or "").strip()
    if not query:
        return []
    out = _wikipedia(query) + _duckduckgo(query)
    seen: set[str] = set()
    res: list[dict] = []
    for s in out:
        key = s["text"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        res.append(s)
        if len(res) >= max_snippets:
            break
    return res
