"""Owner engagement: offers/announcements a claimed-listing owner posts, and owner replies to reviews.

Ownership is enforced by the WEB layer (web/portal.py `_require_owner`) before these are called; the
functions here still scope every write by (vertical, listing_id) + owner_email so a stray call can't
touch another listing. Content is screened with the same review moderation. Never invents anything.
"""

from __future__ import annotations

from typing import Any

from . import db, reviews

_KINDS = {"offer", "announcement"}
_MAX_TITLE = 120
_MAX_BODY = 600


# --------------------------------------------------------------------------- offers / announcements
def create_post(vertical: str, listing_id: int, owner_email: str, *, kind: str = "offer",
                title: str = "", body: str = "", expires_at: str | None = None) -> dict[str, Any]:
    title = (title or "").strip()
    kind = kind if kind in _KINDS else "offer"
    if len(title) < 3:
        return {"ok": False, "error": "too_short"}
    if len(title) > _MAX_TITLE or len(body or "") > _MAX_BODY:
        return {"ok": False, "error": "too_long"}
    ok, reason = reviews._screen(f"{title}\n{body}")           # reuse the spam/abuse screen
    if not ok:
        return {"ok": False, "error": "flagged", "reason": reason}
    row = db.query_one(
        "INSERT INTO owner_posts (vertical, listing_id, owner_email, kind, title, body, expires_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (vertical, listing_id, (owner_email or "").strip().lower(), kind, title,
         (body or "").strip() or None, (expires_at or "").strip() or None))
    return {"ok": True, "id": row["id"]}


def remove_post(post_id: int, owner_email: str) -> None:
    db.execute("UPDATE owner_posts SET status='removed' WHERE id=%s AND lower(owner_email)=lower(%s)",
               (post_id, (owner_email or "").strip()))


def active_posts(vertical: str, listing_id: int) -> list[dict]:
    """Live, non-expired posts for a listing (for the public listing page)."""
    return db.query(
        "SELECT id, kind, title, body, expires_at, created_at FROM owner_posts "
        "WHERE vertical=%s AND listing_id=%s AND status='active' "
        "AND (expires_at IS NULL OR expires_at > now()) ORDER BY created_at DESC",
        (vertical, listing_id))


def owner_posts(vertical: str, listing_id: int, owner_email: str) -> list[dict]:
    """All of an owner's posts for a listing (for the manage view — includes expired)."""
    return db.query(
        "SELECT id, kind, title, body, expires_at, status, created_at FROM owner_posts "
        "WHERE vertical=%s AND listing_id=%s AND lower(owner_email)=lower(%s) AND status='active' "
        "ORDER BY created_at DESC", (vertical, listing_id, (owner_email or "").strip()))


# --------------------------------------------------------------------------- reply to a review
def reply_to_review(review_id: int, vertical: str, listing_id: int, text: str) -> dict[str, Any]:
    """Post/replace the owner's public reply on one of THEIR listing's reviews (scoped by v+id)."""
    text = (text or "").strip()
    if len(text) < 2:
        return {"ok": False, "error": "too_short"}
    if len(text) > _MAX_BODY:
        return {"ok": False, "error": "too_long"}
    ok, reason = reviews._screen(text)
    if not ok:
        return {"ok": False, "error": "flagged", "reason": reason}
    row = db.query_one(
        "UPDATE reviews SET owner_reply=%s, owner_reply_at=now() "
        "WHERE id=%s AND vertical=%s AND listing_id=%s AND status='published' RETURNING id",
        (text, review_id, vertical, listing_id))
    return {"ok": True} if row else {"ok": False, "error": "not_found"}


def clear_reply(review_id: int, vertical: str, listing_id: int) -> None:
    db.execute("UPDATE reviews SET owner_reply=NULL, owner_reply_at=NULL "
               "WHERE id=%s AND vertical=%s AND listing_id=%s", (review_id, vertical, listing_id))


def ai_reply_draft(listing_name: str, review: dict) -> str | None:
    """A grounded, professional draft reply to a review, for the owner to edit. None if LLM inactive."""
    from . import assistant
    if not assistant.llm_active():
        return None
    stars = int(review.get("rating") or 0)
    body = (review.get("body") or "").strip()
    sys = ("You are helping a small business owner write a SHORT, warm, professional public reply to a "
           "customer review. 2-3 sentences max. Thank them; if the review is critical, acknowledge it "
           "graciously and invite them back — never argue, never make promises about refunds/discounts, "
           "never invent facts. Plain text, first person as the business. No signature.")
    user = f"Business: {listing_name}\nReview ({stars}/5): {body or '(rating only, no text)'}"
    draft = assistant.complete_text(sys, user)
    return draft.strip().strip('"')[:_MAX_BODY] if draft else None
