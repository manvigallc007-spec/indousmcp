"""In-house articles: short, AI-written roundups of recent India/NRI headlines.

These keep readers on-site instead of bouncing straight to an external publisher. Each roundup is
GROUNDED IN and CITES the real headlines it was built from (from the `news` table) and is clearly
labelled as an AI-written summary — we never present invented facts as original reporting. Because we
only hold headlines (not article bodies), the roundup summarizes *what's making news* and points
readers to the linked sources for the full story. ArticlesAgent calls `generate_due()` periodically.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from psycopg.types.json import Jsonb

from . import assistant, db, news
from .config import settings

# category -> human label (mirrors news._FEEDS so each news bucket can get a roundup)
CATEGORIES = {
    "community": "Community",
    "immigration": "Immigration & visas",
    "india-usa": "India–USA",
    "diaspora": "Diaspora",
    "business": "Business",
}
_MIN_HEADLINES = 4          # don't write a roundup from fewer than this
_REFRESH_HOURS = 24         # at most one roundup per category per day


def enabled() -> bool:
    return bool(settings.articles_enabled)


# --------------------------------------------------------------------------- read
def latest(limit: int = 12, category: str | None = None) -> list[dict]:
    try:
        if category:
            return db.query(
                "SELECT slug, title, dek, category, created_at FROM articles "
                "WHERE status='published' AND category=%s ORDER BY created_at DESC LIMIT %s",
                (category, limit))
        return db.query(
            "SELECT slug, title, dek, category, created_at FROM articles "
            "WHERE status='published' ORDER BY created_at DESC LIMIT %s", (limit,))
    except Exception:
        return []


def get(slug: str) -> dict | None:
    try:
        return db.query_one("SELECT * FROM articles WHERE slug=%s AND status='published'",
                            ((slug or "").strip(),))
    except Exception:
        return None


# --------------------------------------------------------------------------- generate
def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:60] or "article"
    slug = base
    n = 1
    while db.query_one("SELECT 1 FROM articles WHERE slug=%s", (slug,)):
        n += 1
        slug = f"{base}-{n}"
    return slug


_SYS = (
    "You are a careful news editor writing a SHORT roundup for {plat}, a guide for people from India "
    "living in the USA. You are given RECENT HEADLINES (titles + sources only — you do NOT have the "
    "article text). Write a concise, neutral roundup of what's making news on this theme, based ONLY on "
    "these headlines. Rules: do NOT invent facts, quotes, numbers, names or outcomes that aren't in the "
    "headlines; when details matter, tell readers to see the linked sources; no opinion or advice; plain, "
    "clear English. Length 130–220 words in 2–3 short paragraphs.\n"
    "Output EXACTLY in this format:\n"
    "TITLE: <a specific, non-clickbait title>\n"
    "DEK: <one sentence standfirst>\n"
    "BODY:\n<the roundup, paragraphs separated by a blank line>")


def _parse(text: str) -> tuple[str, str, str] | None:
    title = dek = ""
    body_lines: list[str] = []
    mode = None
    for line in (text or "").splitlines():
        up = line.strip()
        if up.upper().startswith("TITLE:"):
            title = up[6:].strip().strip('"'); mode = None
        elif up.upper().startswith("DEK:"):
            dek = up[4:].strip(); mode = None
        elif up.upper().startswith("BODY:"):
            mode = "body"
            rest = up[5:].strip()
            if rest:
                body_lines.append(rest)
        elif mode == "body":
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not title or len(body) < 60:
        return None
    return title[:200], dek[:300], body[:6000]


def generate_for(category: str) -> dict | None:
    """Write + store one roundup for `category` from its recent headlines. None if the LLM is inactive,
    there's too little news, or the model output can't be parsed."""
    if not (enabled() and assistant.llm_active()):
        return None
    heads = news.latest(limit=12, category=category)
    if len(heads) < _MIN_HEADLINES:
        return None
    label = CATEGORIES.get(category, category)
    listing = "\n".join(
        f"- {h['title']}" + (f" ({h['source']})" if h.get("source") else "") for h in heads)
    sys = _SYS.format(plat=settings.platform_name)
    user = f"Theme: {label}\nRecent headlines:\n{listing}"
    out = assistant.complete_text(sys, user)
    parsed = _parse(out or "")
    if not parsed:
        return None
    title, dek, body = parsed
    sources = [{"title": h["title"], "url": h["url"], "source": h.get("source")} for h in heads]
    slug = _slugify(title)
    try:
        db.execute(
            "INSERT INTO articles (slug, title, dek, body, category, sources) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (slug, title, dek or None, body, category, Jsonb(sources)))
    except Exception:
        return None
    return {"slug": slug, "title": title, "category": category}


def _category_is_due(category: str) -> bool:
    row = db.query_one(
        "SELECT max(created_at) AS last FROM articles WHERE category=%s AND status='published'",
        (category,))
    last = row["last"] if row else None
    if not last:
        return True
    age = datetime.datetime.now(datetime.timezone.utc) - last
    return age >= datetime.timedelta(hours=_REFRESH_HOURS)


def generate_due(max_new: int = 2) -> dict[str, Any]:
    """Generate roundups for whichever categories are due (stale + enough fresh headlines), capped at
    `max_new` per run so we stay light on LLM calls. No-op when disabled or the LLM is off."""
    if not (enabled() and assistant.llm_active()):
        return {"skipped": "inactive", "created": 0}
    created = 0
    for category in CATEGORIES:
        if created >= max_new:
            break
        try:
            if _category_is_due(category) and generate_for(category):
                created += 1
        except Exception:
            continue
    return {"created": created}
