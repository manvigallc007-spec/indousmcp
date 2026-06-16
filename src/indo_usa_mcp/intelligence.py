"""Diaspora-intelligence engine — continuously grows Dost's knowledge about Indians FROM INDIA in
the USA (immigrants from India + people of Indian origin who are now US citizens).

Everything here is free (no paid APIs) and lands in the per-vertical knowledge base (pgvector), so
the intelligence is vectorized, searched first by Dost, and owned by us. Four loops, run by the
DiasporaIntelligenceAgent on a daily cadence:

  1. PROACTIVE  — rotate through a curated list of diaspora topics, fetch the best free web sources
                  (Wikipedia/DuckDuckGo), (LLM-)compose a concise factual note, store it in the KB.
  2. DEMAND     — look at what people ask Dost that came up empty (the miss-log); if it's an
                  on-topic knowledge question we don't already cover, learn it from the web and store.
  3. PROMOTE    — take questions we already answered from the open web (the answer cache) and promote
                  them into the KB as permanent, vectorized documents (so next time it's internal).
  4. CURATE     — suppress listings that clearly don't represent Indians-from-India (the
                  Native-American / West-Indian / brand-homonym guardrail), reversibly.

Relevance gate: only India-diaspora material is stored — the LLM is told to reply 'NOT_RELEVANT'
(and we also keyword-check) so we never pollute the KB with off-topic web text.
"""

from __future__ import annotations

import re
import time
from typing import Any

from . import db, websearch
from .config import settings

# Curated diaspora-intelligence topics (search phrases). Rotated a few per run; add freely.
TOPICS: list[str] = [
    "Indian Americans population in the United States",
    "Indian immigration to the United States history",
    "Asian Indian community in the United States by state",
    "H-1B visa Indian workers United States",
    "Green card backlog for Indians EB-2 EB-3",
    "OPT and STEM OPT for Indian students",
    "Telugu people in the United States",
    "Tamil Americans community",
    "Gujarati Americans community",
    "Punjabi Americans community",
    "Bengali Americans community",
    "Malayali Americans community",
    "Marathi Americans community",
    "Kannada community in the United States",
    "Hindu Americans",
    "Sikh Americans",
    "Jain community in the United States",
    "Indian festivals celebrated in the United States",
    "Diwali in the United States",
    "Navratri Garba in the United States",
    "Indian cuisine in the United States",
    "Little India neighborhoods in the United States",
    "Edison New Jersey Indian American community",
    "Bay Area Indian American community",
    "Indian American entrepreneurs and professionals",
    "Indian classical dance Bharatanatyam in America",
    "Indian American organizations and associations",
    "NRI taxes United States and India",
    "Sending remittances from USA to India",
    "Indian grocery stores and brands in America",
]

_SYSTEM_INTEL = (
    "You build a knowledge base about Indians FROM INDIA living in the USA — immigrants from India "
    "and people of Indian origin who are US citizens. Topics: their history, communities, culture, "
    "festivals, food, religion, and practical life (immigration, taxes, settling in). Using ONLY the "
    "reference material, write a concise, factual, neutral note of 3-6 sentences on the given topic. "
    "Do NOT invent businesses, names, prices, or statistics not in the references. If the references "
    "are NOT about this audience/topic, reply with exactly: NOT_RELEVANT")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:90] or "x"


def _covered(query: str, max_dist: float = 0.28) -> bool:
    """True if the KB already has a close answer (so we don't relearn it)."""
    from . import knowledge
    try:
        hits = knowledge.search(query, limit=1)
    except Exception:
        return False
    if not hits:
        return False
    d = hits[0].get("dist")
    return True if d is None else (d <= max_dist)   # ILIKE hit (no dist) or a close vector hit


def learn(topic: str, *, source_ref: str, title: str,
          require_relevance: bool = False, vertical: str | None = None) -> bool:
    """Fetch free web sources for `topic`, compose a factual note, and store it in the KB. Returns
    True if something was learned. Honest about relevance — skips off-topic material."""
    if not settings.web_fallback_enabled:
        return False
    snips = websearch.lookup(topic, max_snippets=3)
    if not snips:
        return False
    refs = "\n\n".join(f"[{s['source']}] {s.get('title', '')}: {s.get('text', '')}" for s in snips)
    from . import assistant, knowledge
    note: str | None = None
    if assistant.llm_active():
        note = assistant.complete_text(_SYSTEM_INTEL, f"Topic: {topic}\n\nReferences:\n{refs[:4000]}")
        if note and "NOT_RELEVANT" in note.upper():
            return False
    if not note:  # no LLM -> use the top snippet, gated on relevance for user-driven topics
        top = snips[0]
        if require_relevance and not assistant.is_indian_american_topic(f"{topic} {top.get('text','')}"):
            return False
        note = (top.get("text") or "").strip()
    if not note:
        return False
    res = knowledge.upsert_document(source_type="learned", source_ref=source_ref, title=title,
                                    content=note, vertical=vertical)
    return bool(res.get("ok"))


def learn_proactive(limit: int = 4) -> int:
    """Rotate through TOPICS (by day of year, so daily runs cover new ground) and learn a few."""
    import datetime
    if not TOPICS:
        return 0
    n = len(TOPICS)
    start = (datetime.date.today().timetuple().tm_yday * limit) % n
    done = 0
    for i in range(min(limit, n)):
        t = TOPICS[(start + i) % n]
        if learn(t, source_ref=f"intel:{_slug(t)}", title=t):
            done += 1
        time.sleep(1)  # polite to the free endpoints
    return done


def learn_from_misses(limit: int = 4) -> int:
    """Learn on-topic knowledge questions people asked that the directory couldn't answer."""
    from . import analytics, assistant
    try:
        misses = analytics.top_misses(days=30, limit=40)
    except Exception:
        return 0
    done = 0
    for m in misses:
        q = (m.get("query") or "").strip()
        if (not q or not assistant._is_knowledge_question(q, None)
                or not assistant.is_indian_american_topic(q) or _covered(q)):
            continue
        if learn(q, source_ref=f"learned:{_slug(q)}", title=q, require_relevance=True):
            done += 1
        if done >= limit:
            break
        time.sleep(1)
    return done


def promote_learned_answers(limit: int = 10) -> int:
    """Promote questions already answered from the open web (the answer cache) into the KB, so they
    become permanent, vectorized, internal knowledge."""
    from . import knowledge
    try:
        rows = db.query("SELECT query, reply FROM answer_cache WHERE hits >= 1 "
                        "ORDER BY hits DESC, last_used_at DESC LIMIT %s", [limit])
    except Exception:
        return 0
    done = 0
    for r in rows:
        q, reply = (r.get("query") or "").strip(), (r.get("reply") or "").strip()
        if not q or not reply:
            continue
        res = knowledge.upsert_document(source_type="learned", source_ref=f"cache:{_slug(q)}",
                                        title=q, content=reply)
        if res.get("ok") and not res.get("unchanged"):
            done += 1
    return done


def curate_non_india() -> int:
    """Suppress active listings that clearly don't represent Indians-from-India (reversible)."""
    try:
        from . import verticals
        return int(verticals.purge_excluded(dry_run=False).get("total", 0))
    except Exception:
        return 0


def run(**params: Any) -> dict[str, Any]:
    """One full intelligence cycle. Each step is isolated so a failure never aborts the rest."""
    out: dict[str, Any] = {}
    for key, fn, arg in (
        ("proactive", learn_proactive, params.get("proactive_limit", 4)),
        ("from_misses", learn_from_misses, params.get("miss_limit", 4)),
        ("promoted", promote_learned_answers, params.get("promote_limit", 10)),
    ):
        try:
            out[key] = fn(arg)
        except Exception as exc:
            out[key] = f"error: {type(exc).__name__}"
    out["suppressed_non_india"] = curate_non_india()
    return out
