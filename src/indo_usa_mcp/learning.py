"""Learning layer: a semantic answer cache that builds in-app intelligence over time.

When the chatbot answers a *general* question from free web sources (the LLM-using fallback), we
store the answer keyed by a fastembed vector. The next time someone asks the same thing — even
worded differently — we serve it locally (cosine match) instead of calling the external LLM again.
So the app gets smarter from the questions asked and fewer queries leave to the generic LLM.

Only general-knowledge answers are cached (no per-listing results, which must stay live/nearest),
so there's no staleness risk. Everything is best-effort: any DB/embedding failure → no caching,
the chat just answers normally.
"""

from __future__ import annotations

import re

from . import db, embeddings

# Cosine similarity at/above which two questions count as "the same". High, to avoid wrong reuse.
_SIM_THRESHOLD = 0.88


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())[:400]


def lookup(query: str) -> str | None:
    """A cached reply for a semantically-equivalent earlier question, or None. Bumps hit stats."""
    qn = _norm(query)
    if not qn:
        return None
    try:
        if embeddings.enabled():
            qvec = embeddings.to_vector_literal(embeddings.embed(query))
            row = db.query_one(
                "SELECT id, reply, 1 - (embedding <=> %s::vector) AS sim FROM answer_cache "
                "WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT 1",
                [qvec, qvec])
            hit = row if (row and row.get("sim") is not None
                          and float(row["sim"]) >= _SIM_THRESHOLD) else None
        else:
            hit = db.query_one("SELECT id, reply FROM answer_cache WHERE query_norm = %s", [qn])
        if hit:
            db.execute("UPDATE answer_cache SET hits = hits + 1, last_used_at = now() "
                       "WHERE id = %s", [hit["id"]])
            return hit["reply"]
    except Exception:
        return None
    return None


def store(query: str, reply: str, provider: str = "web") -> None:
    """Remember a general-knowledge answer for next time (best-effort, dedup by normalized query)."""
    qn = _norm(query)
    if not qn or not (reply or "").strip():
        return
    try:
        qvec = embeddings.to_vector_literal(embeddings.embed(query)) if embeddings.enabled() else None
        db.execute(
            "INSERT INTO answer_cache (query_norm, query, embedding, reply, provider) "
            "VALUES (%s, %s, %s::vector, %s, %s) "
            "ON CONFLICT (query_norm) DO UPDATE SET reply = EXCLUDED.reply, "
            "embedding = EXCLUDED.embedding, hits = answer_cache.hits + 1, last_used_at = now()",
            [qn, query[:500], qvec, reply, provider])
    except Exception:
        pass


def prune(max_age_days: int = 120, max_rows: int = 5000) -> dict:
    """Keep the cache small and fresh: drop entries unused for a while, then cap total size."""
    try:
        db.execute("DELETE FROM answer_cache WHERE last_used_at < now() - "
                   "make_interval(days => %s)", [max_age_days])
        db.execute("DELETE FROM answer_cache WHERE id IN "
                   "(SELECT id FROM answer_cache ORDER BY last_used_at DESC OFFSET %s)", [max_rows])
        row = db.query_one("SELECT count(*) AS n, COALESCE(sum(hits), 0) AS hits FROM answer_cache")
        return {"cached_entries": row["n"], "total_hits": row["hits"]} if row else {}
    except Exception as exc:
        return {"error": type(exc).__name__}


def stats() -> dict:
    try:
        row = db.query_one("SELECT count(*) AS n, COALESCE(sum(hits), 0) AS hits FROM answer_cache")
        return {"cached_entries": row["n"], "total_hits": row["hits"]} if row else {}
    except Exception:
        return {}
