"""Consumer account layer: profile, saved places, followed cities/categories.

Shares the SAME login/session as business owners (session 'owner_email', web/auth.py) -- a profile or
saved rows simply mark someone as a consumer; there is one account type. Powers the personalized Today
feed, saved lists, follows, and digest notifications. All emails are lower-cased on write/read.
"""

from __future__ import annotations

from typing import Any

from . import db, verticals

_DIGEST_FREQS = {"off", "daily", "weekly"}
_FOLLOW_KINDS = {"city", "vertical"}


def _norm(email: str) -> str:
    return (email or "").strip().lower()


# --------------------------------------------------------------------------- profile
def get_profile(email: str) -> dict | None:
    return db.query_one("SELECT * FROM user_profiles WHERE email = %s", (_norm(email),))


def upsert_profile(email: str, *, display_name: str | None = None, home_city: str | None = None,
                   home_state: str | None = None, languages: list[str] | None = None,
                   followed_verticals: list[str] | None = None, notify_web: bool = False,
                   notify_email: bool = True, digest_freq: str = "weekly") -> dict:
    """Create/replace the caller's profile. Unknown verticals are dropped; digest_freq is clamped."""
    email = _norm(email)
    langs = [s.strip() for s in (languages or []) if s and s.strip()]
    fvs = [v for v in (followed_verticals or []) if v in verticals.VERTICALS]
    freq = digest_freq if digest_freq in _DIGEST_FREQS else "weekly"
    db.execute(
        "INSERT INTO user_profiles (email, display_name, home_city, home_state, languages, "
        "followed_verticals, notify_web, notify_email, digest_freq) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (email) DO UPDATE SET display_name=EXCLUDED.display_name, "
        "home_city=EXCLUDED.home_city, home_state=EXCLUDED.home_state, languages=EXCLUDED.languages, "
        "followed_verticals=EXCLUDED.followed_verticals, notify_web=EXCLUDED.notify_web, "
        "notify_email=EXCLUDED.notify_email, digest_freq=EXCLUDED.digest_freq, updated_at=now()",
        (email, (display_name or "").strip() or None, (home_city or "").strip() or None,
         (home_state or "").strip().upper() or None, langs, fvs,
         bool(notify_web), bool(notify_email), freq))
    return get_profile(email)


# --------------------------------------------------------------------------- saved places
def save_place(email: str, vertical: str, listing_id: int) -> dict[str, Any]:
    """Save a listing to the caller's list. Verifies the listing exists + is live first."""
    if vertical not in verticals.VERTICALS:
        return {"ok": False, "error": "bad_vertical"}
    row = db.query_one(
        f"SELECT id, name FROM {verticals._table(vertical)} "
        f"WHERE id = %s AND deleted_at IS NULL AND is_active", (listing_id,))
    if not row:
        return {"ok": False, "error": "not_found"}
    db.execute("INSERT INTO saved_places (email, vertical, listing_id) VALUES (%s,%s,%s) "
               "ON CONFLICT (email, vertical, listing_id) DO NOTHING", (_norm(email), vertical, listing_id))
    return {"ok": True, "name": row["name"]}


def unsave_place(email: str, vertical: str, listing_id: int) -> None:
    db.execute("DELETE FROM saved_places WHERE email=%s AND vertical=%s AND listing_id=%s",
               (_norm(email), vertical, listing_id))


def is_saved(email: str, vertical: str, listing_id: int) -> bool:
    return bool(db.query_one(
        "SELECT 1 FROM saved_places WHERE email=%s AND vertical=%s AND listing_id=%s",
        (_norm(email), vertical, listing_id)))


def list_saved(email: str, limit: int = 100) -> list[dict]:
    """Saved places joined to their live listing (name/city/state), newest-saved first. Silently drops
    any that were since removed."""
    rows = db.query("SELECT vertical, listing_id, created_at FROM saved_places WHERE email=%s "
                    "ORDER BY created_at DESC LIMIT %s", (_norm(email), limit))
    out: list[dict] = []
    for s in rows:
        v = s["vertical"]
        if v not in verticals.VERTICALS:
            continue
        r = db.query_one(f"SELECT id, name, city, state FROM {verticals._table(v)} "
                         f"WHERE id=%s AND deleted_at IS NULL", (s["listing_id"],))
        if r:
            out.append({"vertical": v, "saved_at": s["created_at"], **r})
    return out


# --------------------------------------------------------------------------- follows
def follow(email: str, kind: str, value: str) -> dict[str, Any]:
    value = (value or "").strip()
    if kind not in _FOLLOW_KINDS or not value:
        return {"ok": False, "error": "bad_follow"}
    if kind == "vertical" and value not in verticals.VERTICALS:
        return {"ok": False, "error": "bad_vertical"}
    db.execute("INSERT INTO follows (email, kind, value) VALUES (%s,%s,%s) "
               "ON CONFLICT (email, kind, value) DO NOTHING", (_norm(email), kind, value))
    return {"ok": True}


def unfollow(email: str, kind: str, value: str) -> None:
    db.execute("DELETE FROM follows WHERE email=%s AND kind=%s AND value=%s",
               (_norm(email), kind, (value or "").strip()))


def list_follows(email: str, kind: str | None = None) -> list[dict]:
    if kind:
        return db.query("SELECT kind, value, created_at FROM follows WHERE email=%s AND kind=%s "
                        "ORDER BY created_at DESC", (_norm(email), kind))
    return db.query("SELECT kind, value, created_at FROM follows WHERE email=%s "
                    "ORDER BY created_at DESC", (_norm(email),))
