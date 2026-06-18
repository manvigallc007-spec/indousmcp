"""Community reviews: visitor-submitted star ratings + text reviews, moderated.

A visitor leaves a 1-5 star rating (+ optional text) on a listing via /listing/<vertical>/<id>.
A clean review is auto-published immediately; anything that looks like spam / advertising / abuse /
off-topic is held as 'pending' and escalated to an admin (Admin -> Reviews). Published reviews roll
up into the listing's SEPARATE community_rating columns — never the web-harvested `rating` (which
web_enrich.py overwrites from each business's own website).

Mirrors the submit -> moderate -> publish flow in submissions.py and the LLM screen in inbox.py.
"""

from __future__ import annotations

import re
from typing import Any

from . import db, verticals
from .config import settings

# Verticals a visitor can review (everything except agent-managed, date-based events).
REVIEWABLE = [k for k in verticals.VERTICALS if k != "events"]

# A review that hits any of these is HELD for a human (not auto-published). Reviews are public
# reputation content, so we err toward holding: links (ad/spam), contact spam, and clear abuse.
_LINK_RE = re.compile(r"https?://|www\.|\b[\w.-]+\.(?:com|net|org|io|biz|info|ru|cn|xyz|shop|store|link)\b",
                      re.I)
# Compact, non-exhaustive list — used only to FLAG for review (never to silently drop).
_BANNED = (
    "fuck", "shit", "bitch", "asshole", "cunt", "nigger", "faggot", "retard", "whore",
    "viagra", "cialis", "casino", "porn", "xxx", "escort", "bitcoin", "crypto", "forex",
    "make money", "work from home", "weight loss", "click here", "free gift", "loan offer",
)


def _listing(vertical: str, listing_id: int) -> dict | None:
    """The active listing being reviewed (name shown on the form/thank-you), or None."""
    if vertical not in verticals.VERTICALS:
        return None
    try:
        return db.query_one(
            f"SELECT id, name, city, state FROM {verticals._table(vertical)} "
            f"WHERE id = %s AND deleted_at IS NULL AND is_active", [listing_id])
    except Exception:
        return None


def _llm_screen(text: str, name: str = "") -> bool:
    """Ask the free LLM whether a review is safe to publish now. True = publish, False = hold.
    Any failure (LLM off/errored) returns True — the deterministic checks already passed, so we
    keep the auto-publish promise (LLM-offline never blocks an otherwise-clean review)."""
    from . import assistant
    if not assistant.llm_active():
        return True
    plat = settings.platform_name
    system = (
        f"You moderate user reviews for {plat}, a directory of Indian-American businesses. Decide if "
        "the review is safe to PUBLISH immediately. Output exactly 'PUBLISH' if it is a genuine, "
        "on-topic review (praise OR fair criticism of the business, its food, or its service), or "
        "'REVIEW' if it is spam/advertising, hate speech, harassment or a personal attack, clearly "
        "off-topic, fake/nonsense, or contains someone's private data. When in doubt, say REVIEW. "
        "Output ONLY the one word.")
    user = f"Reviewer: {name or 'Anonymous'}\nReview: {text}"
    try:
        out = assistant.complete_text(system, user)
    except Exception:
        return True
    if not out:
        return True
    return not out.strip().upper().startswith("REVIEW")


def _screen(body: str, name: str = "") -> tuple[bool, str | None]:
    """Decide if a review is clean enough to auto-publish. Returns (ok, reason). Cheap deterministic
    checks first, then an optional LLM judgement for the ambiguous middle."""
    text = (body or "").strip()
    low = text.lower()
    if settings.review_min_chars and len(text) < settings.review_min_chars:
        return False, "too_short"
    if len(text) > settings.review_max_chars:
        return False, "too_long"
    if text and _LINK_RE.search(text):
        return False, "contains_link"
    hit = next((w for w in _BANNED if w in low), None)
    if hit:
        return False, f"flagged_word:{hit}"
    if re.search(r"(.)\1{6,}", low):                      # crude spam: long char run (aaaaaaaa)
        return False, "spammy"
    if text and not _llm_screen(text, name):
        return False, "llm_flagged"
    return True, None


def submit(vertical: str, listing_id: int, rating: Any, body: str = "", title: str | None = None,
           name: str | None = None, email: str | None = None, ip: str | None = None,
           source: str = "web") -> dict[str, Any]:
    """Validate + screen a review, then store it published (clean) or pending (held). Recomputes the
    listing's community rating on publish. Returns {'ok', 'id', 'status'} or {'ok': False, 'error'}."""
    if not settings.reviews_enabled:
        return {"ok": False, "error": "reviews_disabled"}
    if vertical not in REVIEWABLE:
        return {"ok": False, "error": "bad_vertical"}
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_rating"}
    if not (1 <= rating <= 5):
        return {"ok": False, "error": "bad_rating"}
    try:
        listing_id = int(listing_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "listing_not_found"}
    if _listing(vertical, listing_id) is None:
        return {"ok": False, "error": "listing_not_found"}

    body = (body or "").strip()[: settings.review_max_chars + 1]
    name = (name or "").strip()[:120] or None
    email = (email or "").strip().lower()[:200] or None
    title = (title or "").strip()[:160] or None

    ok, reason = _screen(body, name or "")
    published = settings.review_auto_publish and ok
    status = "published" if published else "pending"
    flagged = None if published else (reason or "held_for_review")

    row = db.query_one(
        "INSERT INTO reviews (vertical, listing_id, rating, title, body, author_name, author_email, "
        "status, flagged_reason, ip, source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        [vertical, listing_id, rating, title, body or None, name, email, status, flagged, ip, source])
    if status == "published":
        aggregate(vertical, listing_id)
    return {"ok": True, "id": row["id"] if row else None, "status": status}


def aggregate(vertical: str, listing_id: int) -> dict[str, Any]:
    """Recompute the listing's community_rating / count from its PUBLISHED reviews (separate from
    the web-harvested rating)."""
    if vertical not in verticals.VERTICALS:
        return {"ok": False, "error": "bad_vertical"}
    table = verticals._table(vertical)
    agg = db.query_one(
        "SELECT count(*) AS n, avg(rating)::numeric(3,2) AS avg FROM reviews "
        "WHERE vertical = %s AND listing_id = %s AND status = 'published'", [vertical, listing_id])
    n = int(agg["n"]) if agg else 0
    avg = float(agg["avg"]) if agg and agg["avg"] is not None else None
    db.execute(
        f"UPDATE {table} SET community_rating = %s, community_rating_count = %s, "
        f"community_rating_updated_at = now() WHERE id = %s", [avg, n if n else None, listing_id])
    return {"ok": True, "community_rating": avg, "community_rating_count": n}


def rating_summary(vertical: str, listing_id: int) -> dict[str, Any]:
    """Read-only roll-up of a listing's PUBLISHED reviews (for the API / MCP, no write)."""
    try:
        row = db.query_one(
            "SELECT count(*) AS n, avg(rating)::numeric(3,2) AS avg FROM reviews "
            "WHERE vertical = %s AND listing_id = %s AND status = 'published'",
            [vertical, int(listing_id)])
    except Exception:
        row = None
    n = int(row["n"]) if row else 0
    return {"community_rating": float(row["avg"]) if row and row.get("avg") is not None else None,
            "community_rating_count": n}


def list_for_listing(vertical: str, listing_id: int, limit: int = 20,
                     status: str = "published") -> list[dict]:
    """Reviews for one listing, newest first (published only by default)."""
    try:
        return db.query(
            "SELECT id, rating, title, body, author_name, created_at FROM reviews "
            "WHERE vertical = %s AND listing_id = %s AND status = %s "
            "ORDER BY created_at DESC LIMIT %s", [vertical, int(listing_id), status, limit])
    except Exception:
        return []


def recent_for_ip(ip: str, listing_id: int, hours: int = 24) -> int:
    """How many reviews this IP left on this listing recently — for per-(IP, listing) daily dedupe."""
    if not ip:
        return 0
    try:
        row = db.query_one(
            "SELECT count(*) AS n FROM reviews WHERE ip = %s AND listing_id = %s "
            "AND created_at > now() - (%s || ' hours')::interval", [ip, int(listing_id), hours])
        return int(row["n"]) if row else 0
    except Exception:
        return 0


def ip_count_today(ip: str, hours: int = 24) -> int:
    """How many reviews this IP left across ALL listings recently — global per-IP abuse guard."""
    if not ip:
        return 0
    try:
        row = db.query_one(
            "SELECT count(*) AS n FROM reviews WHERE ip = %s "
            "AND created_at > now() - (%s || ' hours')::interval", [ip, hours])
        return int(row["n"]) if row else 0
    except Exception:
        return 0


def pending(limit: int = 100) -> list[dict]:
    try:
        return db.query("SELECT * FROM reviews WHERE status = 'pending' "
                        "ORDER BY created_at LIMIT %s", [limit])
    except Exception:
        return []


def list_by_status(status: str, limit: int = 100) -> list[dict]:
    try:
        return db.query("SELECT * FROM reviews WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                        [status, limit])
    except Exception:
        return []


def approve(review_id: int, by: str = "admin") -> dict[str, Any]:
    r = db.query_one("SELECT * FROM reviews WHERE id = %s", [review_id])
    if not r:
        return {"ok": False, "error": "not_found"}
    db.execute("UPDATE reviews SET status = 'published', moderated_at = now(), moderated_by = %s, "
               "flagged_reason = NULL WHERE id = %s", [by, review_id])
    aggregate(r["vertical"], r["listing_id"])
    return {"ok": True}


def reject(review_id: int, reason: str | None = None, by: str = "admin") -> dict[str, Any]:
    r = db.query_one("SELECT * FROM reviews WHERE id = %s", [review_id])
    if not r:
        return {"ok": False, "error": "not_found"}
    was_published = r.get("status") == "published"
    db.execute("UPDATE reviews SET status = 'rejected', moderated_at = now(), moderated_by = %s, "
               "flagged_reason = COALESCE(%s, flagged_reason) WHERE id = %s", [by, reason, review_id])
    if was_published:
        aggregate(r["vertical"], r["listing_id"])
    return {"ok": True}


def recent(limit: int = 20) -> list[dict]:
    try:
        return db.query("SELECT * FROM reviews ORDER BY created_at DESC LIMIT %s", [limit])
    except Exception:
        return []


def counts() -> dict[str, int]:
    try:
        rows = db.query("SELECT status, count(*) AS n FROM reviews GROUP BY status")
        return {r["status"]: int(r["n"]) for r in rows}
    except Exception:
        return {}


def moderate_pending(limit: int = 200) -> dict[str, Any]:
    """Agentic queue-shrinker: re-screen held reviews and auto-publish any that are now clean; leave
    genuinely-flagged ones for a human. Returns counts (the supervisor escalates if the backlog grows).
    In manual mode (review_auto_publish off) the agent only reports the backlog."""
    rows = pending(limit)
    if not settings.review_auto_publish:
        return {"auto_published": 0, "left_for_human": len(rows), "mode": "manual"}
    published = left = 0
    for r in rows:
        ok, reason = _screen(r.get("body") or "", r.get("author_name") or "")
        if ok:
            approve(r["id"], by="agent:review_moderation")
            published += 1
        else:
            if reason and reason != r.get("flagged_reason"):
                db.execute("UPDATE reviews SET flagged_reason = %s WHERE id = %s", [reason, r["id"]])
            left += 1
    return {"auto_published": published, "left_for_human": left}


def aggregate_all(limit_per: int = 5000) -> dict[str, Any]:
    """Recompute community ratings for every listing that has published reviews. Cheap + idempotent;
    the ReviewAggregatorAgent runs it so ratings stay correct even if an UPDATE was ever missed."""
    total = 0
    for v in REVIEWABLE:
        try:
            rows = db.query(
                "SELECT DISTINCT listing_id FROM reviews WHERE vertical = %s AND status = 'published' "
                "LIMIT %s", [v, limit_per])
        except Exception:
            continue
        for r in rows:
            aggregate(v, r["listing_id"])
            total += 1
    return {"ok": True, "listings_recomputed": total}
