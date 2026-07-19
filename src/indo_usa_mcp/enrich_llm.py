"""LLM-polished, grounded editorial content (descriptions + review summaries) -> ai_content table.

Gated on the LLM (Groq) being active. Strictly grounded: the model only rewrites facts we already
hold (describe.describe) and summarizes real review text — it must not invent anything. Output lives
in the side `ai_content` table so it never fights the templated `description` column, and the
listing's embedding is refreshed to include the richer text so semantic search improves too.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from . import assistant, db

# Bump when the enrichment OUTPUT shape changes (e.g. adding aspects) so already-enriched rows are
# re-generated once to gain the new fields, not just newly-added listings.
_ENRICH_VERSION = "2"

_ASPECTS_SYS = (
    "From the review text below, extract what customers actually say. Use ONLY the reviews; never "
    "invent. Return STRICT JSON only (no markdown, no prose): {\"aspects\": [up to 6 SHORT lowercase "
    "customer-language tags, 1-4 words each, e.g. \"great biryani\", \"long wait\", \"family friendly\", "
    "\"authentic dosa\", \"good value\"], \"sentiment\": one of \"positive\", \"mixed\", \"negative\"}. "
    "If the reviews are too thin to tell, return {\"aspects\": [], \"sentiment\": \"mixed\"}."
)

_DESC_SYS = (
    "You are an editor for an Indian-American business directory. Rewrite the FACTS into one "
    "natural, helpful description of 1-2 sentences. Strict rules: use ONLY the facts given; never "
    "invent cuisine, dishes, ratings, awards, prices, or claims; no hype or superlatives that are "
    "not in the facts; keep it under 320 characters; plain text, no surrounding quotes."
)
_REV_SYS = (
    "Summarize what reviewers say about this place in ONE neutral sentence under 200 characters. "
    "Use ONLY the review text provided; do not invent. Note recurring themes (food, service, "
    "value, atmosphere). If opinions conflict, say so briefly. Plain text, no surrounding quotes."
)


def get(vertical: str, listing_id: int) -> dict | None:
    try:
        return db.query_one(
            "SELECT description, review_summary, aspects, sentiment FROM ai_content "
            "WHERE vertical = %s AND listing_id = %s", (vertical, listing_id))
    except Exception:
        return None


def _extract_aspects(rblock: str) -> tuple[list[str], str | None]:
    """Grounded aspect tags + overall sentiment from review text. ([], None) when unavailable."""
    from .onboard import _strip_json
    raw = assistant.complete_text(_ASPECTS_SYS, f"REVIEWS:\n{rblock}")
    if not raw:
        return [], None
    try:
        data = json.loads(_strip_json(raw))
        aspects = [str(a).strip().lower()[:40] for a in (data.get("aspects") or [])
                   if isinstance(a, str) and a.strip()][:6]
        sentiment = data.get("sentiment") if data.get("sentiment") in ("positive", "mixed", "negative") else None
        return aspects, sentiment
    except Exception:
        return [], None


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x01".join(p or "" for p in parts).encode("utf-8")).hexdigest()


def _review_block(items: list[dict]) -> str:
    bodies = [(r.get("body") or "").strip() for r in items if (r.get("body") or "").strip()]
    return "\n".join(f"- {b[:300]}" for b in bodies[:8])


def enrich_listing(vertical: str, row: dict, reviews: list[dict]) -> dict | None:
    """Generate + upsert ai_content for one listing. Returns the new content, or None if skipped
    (LLM inactive, or inputs unchanged since last run)."""
    if not assistant.llm_active():
        return None
    from . import describe, embeddings, verticals

    facts = describe.describe(vertical, row)
    rblock = _review_block(reviews)
    src = _hash(facts, rblock, _ENRICH_VERSION)
    existing = db.query_one(
        "SELECT source_hash, aspects FROM ai_content WHERE vertical = %s AND listing_id = %s",
        (vertical, row["id"]))
    if existing and existing.get("source_hash") == src and existing.get("aspects") is not None:
        return None                                   # inputs unchanged AND already has aspects -> skip

    desc = assistant.complete_text(_DESC_SYS, f"FACTS: {facts}")
    desc = desc.strip().strip('"')[:400] if desc else None
    rsum, aspects, sentiment = None, [], None
    if rblock.count("\n") >= 1:                        # >= 2 review bodies -> worth summarizing
        rsum = assistant.complete_text(_REV_SYS, f"REVIEWS:\n{rblock}")
        rsum = rsum.strip().strip('"')[:300] if rsum else None
        aspects, sentiment = _extract_aspects(rblock)   # structured, grounded, customer-language tags

    db.execute(
        "INSERT INTO ai_content (vertical, listing_id, description, review_summary, aspects, sentiment, "
        "source_hash, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, now()) "
        "ON CONFLICT (vertical, listing_id) DO UPDATE SET description = EXCLUDED.description, "
        "review_summary = EXCLUDED.review_summary, aspects = EXCLUDED.aspects, "
        "sentiment = EXCLUDED.sentiment, source_hash = EXCLUDED.source_hash, updated_at = now()",
        (vertical, row["id"], desc, rsum, aspects or [], sentiment, src))

    if (desc or rsum or aspects) and embeddings.enabled():   # richer text -> better semantic recall
        try:
            # Fold the polished description, the review summary AND the structured aspect tags into the
            # vector. The aspects are genuine customer language ("great biryani", "family friendly")
            # that neither the templated description nor even the summary reliably carries — strong
            # signal for phrase-style queries ("kid friendly temple", "authentic dosa place").
            text = " ".join(t for t in (embeddings.text_for(row), desc, rsum, " ".join(aspects)) if t)
            db.execute(f"UPDATE {verticals._table(vertical)} SET embedding = %s::vector WHERE id = %s",
                       (embeddings.to_vector_literal(embeddings.embed(text)), row["id"]))
        except Exception:
            pass
    return {"description": desc, "review_summary": rsum, "aspects": aspects, "sentiment": sentiment}


def run(vertical: str, limit: int = 30) -> dict[str, Any]:
    """Enrich a batch of this vertical's listings that don't yet have ai_content (coverage-first)."""
    if not assistant.llm_active():
        return {"vertical": vertical, "skipped": "llm_inactive"}
    from . import reviews as reviews_mod, verticals
    table = verticals._table(vertical)
    try:
        rows = db.query(
            f"SELECT t.* FROM {table} t "
            f"LEFT JOIN ai_content a ON a.vertical = %s AND a.listing_id = t.id "
            f"WHERE t.deleted_at IS NULL AND t.is_active AND (a.listing_id IS NULL OR a.aspects IS NULL) "
            f"ORDER BY t.id LIMIT %s", (vertical, limit))
    except Exception as exc:
        return {"vertical": vertical, "error": str(exc)}
    done = 0
    for row in rows:
        try:
            revs = reviews_mod.list_for_listing(vertical, row["id"], limit=8)
        except Exception:
            revs = []
        try:
            if enrich_listing(vertical, row, revs):
                done += 1
        except Exception:
            pass
        time.sleep(0.2)                               # gentle on the free Groq rate limit
    return {"vertical": vertical, "scanned": len(rows), "generated": done}


def run_all(limit_per: int = 30) -> dict[str, Any]:
    from . import verticals
    out: dict[str, Any] = {}
    for v in verticals.VERTICALS:
        if v == "events":
            continue
        out[v] = run(v, limit=limit_per)
    return out
