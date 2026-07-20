"""Ask-the-community Q&A: members ask questions, Dost posts an instant AI answer, the community adds
and upvotes answers. Each published question is a public, indexable page. Content is screened with the
SAME moderation as reviews (clean auto-publishes; flagged waits as 'pending'). Never raises to callers
on the answer/vote paths; question creation returns a structured result.
"""

from __future__ import annotations

import re
from typing import Any

from . import db, reviews, verticals
from .config import settings

_MIN_TITLE = 12
_MAX_TITLE = 200
_MAX_BODY = 2000


def enabled() -> bool:
    return settings.qa_enabled


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:70] or "question"


# --------------------------------------------------------------------------- ask
def create_question(title: str, *, body: str = "", asker_email: str | None = None,
                    city: str | None = None, state: str | None = None,
                    vertical: str | None = None, ip: str | None = None) -> dict[str, Any]:
    """Create a question. Clean ones publish immediately + get an instant Dost answer; flagged ones wait
    for moderation. Returns {'ok', 'id', 'slug', 'status'} or {'ok': False, 'error'}."""
    if not enabled():
        return {"ok": False, "error": "qa_disabled"}
    title = (title or "").strip()
    body = (body or "").strip()
    if len(title) < _MIN_TITLE:
        return {"ok": False, "error": "too_short"}
    if len(title) > _MAX_TITLE or len(body) > _MAX_BODY:
        return {"ok": False, "error": "too_long"}
    if vertical and vertical not in verticals.VERTICALS:
        vertical = None
    ok, reason = reviews._screen(f"{title}\n{body}")           # reuse the review spam/abuse screen
    status = "published" if ok else "pending"
    row = db.query_one(
        "INSERT INTO questions (title, body, asker_email, city, state, vertical, status, flagged_reason) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (title, body or None, (asker_email or "").strip().lower() or None,
         (city or "").strip() or None, (state or "").strip().upper() or None, vertical, status, reason))
    qid = row["id"]
    slug = f"{_slugify(title)}-{qid}"
    db.execute("UPDATE questions SET slug = %s WHERE id = %s", (slug, qid))
    if status == "published":
        _dost_answer(qid, title, body, city=city, state=state)
    return {"ok": True, "id": qid, "slug": slug, "status": status}


def _dost_answer(question_id: int, title: str, body: str, *, city=None, state=None) -> None:
    """Post an instant grounded AI answer as the first answer. No-op if the LLM is inactive or fails."""
    try:
        from . import assistant
        if not assistant.llm_active():
            return
        q = title + (f"\n\n{body}" if body else "")
        filters = {"city": city, "state": state} if city else None
        res = assistant.reply([{"role": "user", "content": q}], filters=filters)
        text = (res.get("reply") or "").strip()
        if text:
            db.execute("INSERT INTO answers (question_id, body, is_ai, status) "
                       "VALUES (%s,%s,TRUE,'published')", (question_id, text))
            _bump_answer_count(question_id)
    except Exception:
        pass


# --------------------------------------------------------------------------- answers + votes
def add_answer(question_id: int, body: str, author_email: str, ip: str | None = None) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "qa_disabled"}
    q = db.query_one("SELECT id FROM questions WHERE id=%s AND status='published'", (question_id,))
    if not q:
        return {"ok": False, "error": "not_found"}
    body = (body or "").strip()
    if len(body) < 2:
        return {"ok": False, "error": "too_short"}
    if len(body) > _MAX_BODY:
        return {"ok": False, "error": "too_long"}
    ok, reason = reviews._screen(body)
    status = "published" if ok else "pending"
    row = db.query_one(
        "INSERT INTO answers (question_id, body, author_email, status) VALUES (%s,%s,%s,%s) RETURNING id",
        (question_id, body, (author_email or "").strip().lower() or None, status))
    if status == "published":
        _bump_answer_count(question_id)
    return {"ok": True, "id": row["id"], "status": status}


def vote_answer(answer_id: int, email: str) -> dict[str, Any]:
    """Toggle an upvote (one per member per answer). Returns {'ok', 'voted', 'upvotes'}."""
    email = (email or "").strip().lower()
    a = db.query_one("SELECT id FROM answers WHERE id=%s", (answer_id,))
    if not a or not email:
        return {"ok": False, "error": "not_found"}
    existing = db.query_one("SELECT id FROM answer_votes WHERE answer_id=%s AND email=%s", (answer_id, email))
    if existing:
        db.execute("DELETE FROM answer_votes WHERE id=%s", (existing["id"],))
        db.execute("UPDATE answers SET upvotes = GREATEST(upvotes-1,0) WHERE id=%s", (answer_id,))
        voted = False
    else:
        db.execute("INSERT INTO answer_votes (answer_id, email) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                   (answer_id, email))
        db.execute("UPDATE answers SET upvotes = upvotes+1 WHERE id=%s", (answer_id,))
        voted = True
    row = db.query_one("SELECT upvotes FROM answers WHERE id=%s", (answer_id,))
    return {"ok": True, "voted": voted, "upvotes": int(row["upvotes"]) if row else 0}


def _bump_answer_count(question_id: int) -> None:
    db.execute("UPDATE questions SET answer_count = ("
               "SELECT count(*) FROM answers WHERE question_id=%s AND status='published'), "
               "updated_at=now() WHERE id=%s", (question_id, question_id))


# --------------------------------------------------------------------------- read
def get_question(slug: str) -> dict | None:
    q = db.query_one("SELECT * FROM questions WHERE slug=%s AND status='published'", (slug,))
    if not q:
        return None
    q["answers"] = db.query(
        "SELECT id, body, author_email, is_ai, upvotes, created_at FROM answers "
        "WHERE question_id=%s AND status='published' ORDER BY is_ai DESC, upvotes DESC, created_at ASC",
        (q["id"],))
    return q


def bump_views(question_id: int) -> None:
    try:
        db.execute("UPDATE questions SET view_count = view_count+1 WHERE id=%s", (question_id,))
    except Exception:
        pass


def list_questions(limit: int = 50, city: str | None = None) -> list[dict]:
    sql = "SELECT id, slug, title, city, state, vertical, answer_count, view_count, created_at " \
          "FROM questions WHERE status='published'"
    params: list[Any] = []
    if city:
        sql += " AND LOWER(city)=LOWER(%s)"
        params.append(city)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    return db.query(sql, params)


def search_questions(query: str, limit: int = 8) -> list[dict]:
    """Published questions matching a free-text query (title/body), most-answered first. For agents +
    the answer-engine surface."""
    q = (query or "").strip()
    if not q:
        return []
    return db.query(
        "SELECT slug, title, city, state, vertical, answer_count FROM questions "
        "WHERE status='published' AND (title ILIKE %s OR body ILIKE %s) "
        "ORDER BY answer_count DESC, created_at DESC LIMIT %s", (f"%{q}%", f"%{q}%", limit))


def trending(limit: int = 5) -> list[dict]:
    """Recent published questions with the most engagement — for the Today feed."""
    return db.query(
        "SELECT slug, title, answer_count FROM questions WHERE status='published' "
        "AND created_at > now() - interval '30 days' "
        "ORDER BY (answer_count*3 + view_count) DESC, created_at DESC LIMIT %s", (limit,))


# --------------------------------------------------------------------------- moderation (admin)
def list_pending_questions(limit: int = 200) -> list[dict]:
    return db.query("SELECT id, slug, title, body, city, state, vertical, flagged_reason, created_at "
                    "FROM questions WHERE status = 'pending' ORDER BY created_at LIMIT %s", (limit,))


def list_pending_answers(limit: int = 200) -> list[dict]:
    return db.query(
        "SELECT a.id, a.body, a.author_email, a.created_at, q.title AS question_title, q.slug "
        "FROM answers a JOIN questions q ON q.id = a.question_id "
        "WHERE a.status = 'pending' ORDER BY a.created_at LIMIT %s", (limit,))


def pending_count() -> int:
    r = db.query_one("SELECT (SELECT count(*) FROM questions WHERE status='pending') "
                     "+ (SELECT count(*) FROM answers WHERE status='pending') AS n")
    return int(r["n"]) if r else 0


def moderate_question(question_id: int, approve: bool) -> None:
    """Publish (and let Dost answer) or reject a held question."""
    if not approve:
        db.execute("UPDATE questions SET status='rejected', updated_at=now() WHERE id=%s", (question_id,))
        return
    q = db.query_one("SELECT id, title, body, city, state, status FROM questions WHERE id=%s", (question_id,))
    if not q or q["status"] != "pending":
        return
    db.execute("UPDATE questions SET status='published', flagged_reason=NULL, updated_at=now() WHERE id=%s",
               (question_id,))
    _dost_answer(question_id, q["title"], q.get("body") or "", city=q.get("city"), state=q.get("state"))


def moderate_answer(answer_id: int, approve: bool) -> None:
    row = db.query_one("SELECT question_id, status FROM answers WHERE id=%s", (answer_id,))
    if not row or row["status"] != "pending":
        return
    db.execute("UPDATE answers SET status=%s WHERE id=%s",
               ("published" if approve else "rejected", answer_id))
    if approve:
        _bump_answer_count(row["question_id"])


def unanswered(limit: int = 50) -> list[dict]:
    """Published questions with no community (non-AI) answer — a demand signal for outreach."""
    return db.query(
        "SELECT q.id, q.slug, q.title, q.city, q.state, q.vertical FROM questions q "
        "WHERE q.status='published' AND NOT EXISTS ("
        "  SELECT 1 FROM answers a WHERE a.question_id=q.id AND a.status='published' AND NOT a.is_ai) "
        "ORDER BY q.created_at DESC LIMIT %s", (limit,))
