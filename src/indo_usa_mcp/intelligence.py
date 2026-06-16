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
    "Indian American naturalization and US citizenship",
    "OCI card for Indian Americans",
    "H-4 visa spouses working in the United States",
    "Durga Puja celebrations in the United States",
    "Janmashtami celebrated in the United States",
    "Vaisakhi and Sikh community in the United States",
    "building credit history as a new immigrant in the USA",
    "health insurance basics for immigrants in the United States",
    "FBAR foreign account reporting for Indians in the United States",
    "raising bicultural Indian American children",
    "Indian American weddings in the United States",
]

_SYSTEM_INTEL = (
    "You build a knowledge base STRICTLY about Indians FROM INDIA living in the USA — immigrants "
    "from India and people of Indian origin who are US citizens or residents — and their life in "
    "AMERICA: their communities, culture and festivals AS OBSERVED IN THE US, food, religion, and "
    "practical topics (US immigration, US taxes, settling in the USA). Using ONLY the reference "
    "material, write a concise, factual, neutral note of 3-6 sentences, FRAMED for the US-based "
    "community (mention the US/America/the diaspora). Do NOT write a general article about India the "
    "country, Indian geography/politics, tourism in India, or people living IN India. If the "
    "references are only about India (not the US-based Indian community), reply with exactly: "
    "NOT_RELEVANT. Never invent businesses, names, prices, or statistics not in the references.")

# A stored note must reference the US-based community (not be a generic India-country article).
_USA_SIGNALS = ("united states", "u.s.", "u.s ", " us ", "usa", "america", "american", "diaspora",
                "immigrant", "nri", "indian-american", "indian american", "in the us")


def _is_usa_relevant(text: str) -> bool:
    t = f" {(text or '').lower()} "
    return any(s in t for s in _USA_SIGNALS)


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
    # The collected DATA must be about the US-based community — reject generic India-country text
    # (about India the country or people living in India) even when the topic was US-scoped.
    if not note or not _is_usa_relevant(note):
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
        if not q or not reply or not _is_usa_relevant(f"{q} {reply}"):
            continue                       # only promote US-diaspora knowledge, not India-country
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
