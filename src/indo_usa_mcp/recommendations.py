"""Demand-driven recommendations — turn unanswered searches into reviewable build suggestions.

Reads the miss-log (zero-result searches), maps each cluster to a vertical + location with
simple keyword heuristics (no LLM — zero cost), and upserts a recommendation:
  * coverage  — "Grow <vertical> in <city>: N unmet searches" (+ a scrape action when the
    location is a known metro), or
  * new_topic — "<term> doesn't map to any category — consider a new vertical/content."
Admin reviews at /admin/recommendations and approves (optionally triggering the scrape) or
dismisses. Dismissed/approved items are never silently regenerated.
"""

from __future__ import annotations

import re
from typing import Any

from . import analytics, db, verticals
from .pipeline.scrapers.metros import METROS

# query keyword -> vertical
_KW = {
    "restaurant": "restaurants", "food": "restaurants", "eat": "restaurants",
    "thali": "restaurants", "dosa": "restaurants", "biryani": "restaurants",
    "temple": "temples", "mandir": "temples", "gurdwara": "temples", "puja": "temples",
    "grocery": "groceries", "groceries": "groceries", "store": "groceries",
    "doctor": "professionals", "clinic": "professionals", "dentist": "professionals",
    "physician": "professionals", "salon": "salons", "threading": "salons",
    "henna": "salons", "mehndi": "salons", "event": "events", "festival": "events",
    "garba": "events", "concert": "events", "saree": "apparel", "sari": "apparel",
    "lehenga": "apparel", "jewelry": "apparel", "jeweler": "apparel", "clothing": "apparel",
    "sweets": "sweets", "mithai": "sweets", "bakery": "sweets",
    "yoga": "studios", "dance": "studios", "music": "studios", "class": "studios",
    "bharatanatyam": "studios", "money transfer": "services", "remit": "services",
    "remittance": "services", "travel": "services", "visa": "services",
    "immigration": "services", "forex": "services",
    "association": "community", "samaj": "community", "sangam": "community",
    "mandal": "community", "cultural center": "community", "community center": "community",
}
_MIN_MISSES = 3          # min searches before recommending coverage / a topic
_NEW_VERTICAL_MIN = 4    # min TOTAL searches across a cluster before proposing a new vertical

# Candidate NEW verticals (not in today's set) -> signal keywords. Unmapped misses that match
# are clustered into a single "consider this vertical" proposal, so scattered demand
# ("photographer", "decorator", "dj") rolls up into one actionable recommendation.
_CANDIDATE_VERTICALS: dict[str, tuple[str, ...]] = {
    "Priests & pandits": ("priest", "pandit", "purohit", "pujari", "panditji"),
    "Caterers": ("caterer", "catering"),
    "Wedding services": ("photographer", "videographer", "wedding planner", "decorator",
                         "mandap", "dj", "dhol", "makeup artist", "mehndi artist", "bridal"),
    "Tutors & coaching": ("tutor", "tutoring", "coaching", "sat prep", "kumon", "tuition"),
    "Tiffin & meal services": ("tiffin", "home cooked", "home food", "meal service", "dabba"),
    "Realtors": ("realtor", "real estate", "realty"),
    "Finance & legal": ("cpa", "tax preparer", "accountant", "financial advisor",
                        "insurance agent", "immigration attorney", "lawyer", "attorney"),
    "Matrimony": ("matrimony", "matchmaker", "matchmaking", "rishta", "biodata"),
    "Cargo & shipping to India": ("cargo", "shipping to india", "courier to india",
                                  "excess baggage", "ship to india"),
    "Astrology & vastu": ("astrologer", "jyotish", "vastu", "horoscope", "kundli"),
    "Child & elder care": ("babysitter", "nanny", "daycare", "preschool", "child care",
                           "elder care", "assisted living", "senior care"),
}


def _match_vertical(query: str) -> str | None:
    q = (query or "").lower()
    for kw, v in _KW.items():
        if kw in q:
            return v
    return None


def _match_candidate(query: str) -> str | None:
    q = (query or "").lower()
    for label, kws in _CANDIDATE_VERTICALS.items():
        if any(k in q for k in kws):
            return label
    return None


def _metro_for(city: str | None, state: str | None) -> str | None:
    """Map a city/state to a known scrape metro, only on an obvious match. Short aliases must be
    whole tokens (so 'la' doesn't match 'Plano'); multi-word names match as substrings."""
    blob = " ".join(x for x in (city, state) if x).lower()
    tokens = set(re.findall(r"[a-z]+", blob))
    for m in METROS:
        name = m.replace("_", " ")
        if (" " in name and name in blob) or (" " not in name and name in tokens):
            return m
    for phrase, m in {"new york": "nyc_nj", "san francisco": "bay_area",
                      "bay area": "bay_area", "los angeles": "los_angeles"}.items():
        if phrase in blob:
            return m
    for short, m in {"nyc": "nyc_nj", "sf": "bay_area", "dfw": "dallas",
                     "la": "los_angeles"}.items():
        if short in tokens:
            return m
    return None


def generate(days: int = 90) -> dict[str, int]:
    """Build/refresh recommendations from the current miss-log. Returns counts."""
    misses = analytics.top_misses(days=days, limit=200)
    created = updated = 0
    clusters: dict[str, dict[str, Any]] = {}  # candidate vertical -> {n, examples}

    def _upsert(sig, kind, vertical, city, state, query, n, suggestion, action):
        nonlocal created, updated
        row = db.query_one(
            "INSERT INTO recommendations (signature, kind, vertical, city, state, query, "
            "n_misses, suggestion, action) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (signature) DO UPDATE SET n_misses = EXCLUDED.n_misses, "
            "suggestion = EXCLUDED.suggestion WHERE recommendations.status = 'pending' "
            "RETURNING (xmax = 0) AS inserted",
            (sig[:300], kind, vertical, city, state, query, n, suggestion, action))
        if row is not None:
            created += int(row["inserted"])
            updated += int(not row["inserted"])

    for m in misses:
        n = m["n"]
        query = (m.get("query") or "").strip()
        city, state = m.get("city"), m.get("state")
        loc = ", ".join(x for x in (city, state) if x) or "an unspecified location"
        vertical = _match_vertical(query)

        if vertical:
            if n < _MIN_MISSES:
                continue
            label = verticals.VERTICALS.get(vertical, {}).get("label", vertical)
            metro = _metro_for(city, state)
            suggestion = (f"Grow {label} coverage in {loc}: {n} unanswered searches. "
                          + (f"Scrape the '{metro}' metro for {vertical}, "
                             if metro else "Solicit owner submissions / add manually, ")
                          + "or run targeted outreach there.")
            _upsert(f"coverage|{vertical}|{state or ''}|{city or ''}|{query}".lower(),
                    "coverage", vertical, city, state, query, n,
                    suggestion, f"scrape:{metro}:{vertical}" if metro else None)
            continue

        candidate = _match_candidate(query)
        if candidate:  # roll up into a new-vertical proposal (don't emit per-query)
            c = clusters.setdefault(candidate, {"n": 0, "examples": set()})
            c["n"] += n
            c["examples"].add(query)
        elif n >= _MIN_MISSES:  # truly novel phrasing
            _upsert(f"new_topic||{state or ''}|{city or ''}|{query}".lower(), "new_topic",
                    None, city, state, query, n,
                    f"“{query}” ({n} searches) doesn’t map to any category — consider a new "
                    "vertical or a phrasing we should handle.", None)

    # Proposed NEW verticals, aggregated across the cluster.
    for label, c in clusters.items():
        if c["n"] < _NEW_VERTICAL_MIN:
            continue
        eg = ", ".join(sorted(c["examples"])[:3])
        _upsert(f"new_vertical|{label}".lower(), "new_vertical", None, None, None, label, c["n"],
                f"Consider a new “{label}” vertical — {c['n']} unanswered searches across "
                f"e.g. {eg}. Not in OSM; would be submission/outreach-fed.", None)

    return {"scanned": len(misses), "created": created, "updated": updated,
            "proposed_verticals": [k for k, v in clusters.items() if v["n"] >= _NEW_VERTICAL_MIN]}


def list_pending(limit: int = 100) -> list[dict]:
    return db.query("SELECT * FROM recommendations WHERE status = 'pending' "
                    "ORDER BY n_misses DESC, created_at DESC LIMIT %s", (limit,))


def summary() -> dict[str, int]:
    rows = db.query("SELECT status, count(*) AS n FROM recommendations GROUP BY status")
    out = {r["status"]: r["n"] for r in rows}
    return {k: out.get(k, 0) for k in ("pending", "approved", "dismissed", "done")}


def _set_status(rec_id: int, status: str) -> dict | None:
    return db.query_one(
        "UPDATE recommendations SET status = %s, reviewed_at = now() WHERE id = %s RETURNING *",
        (status, rec_id))


def dismiss(rec_id: int) -> dict[str, Any]:
    _set_status(rec_id, "dismissed")
    return {"ok": True}


def approve(rec_id: int, run_scrape: bool = False) -> dict[str, Any]:
    rec = _set_status(rec_id, "approved")
    if rec is None:
        return {"ok": False, "error": "not_found"}
    result: dict[str, Any] = {"ok": True, "vertical": rec.get("vertical")}
    if run_scrape and rec.get("action", "").startswith("scrape:"):
        _, metro, vertical = rec["action"].split(":", 2)
        try:
            import importlib
            pipe = importlib.import_module(f"indo_usa_mcp.{vertical}.pipeline") \
                if vertical not in ("restaurants",) else importlib.import_module("indo_usa_mcp.pipeline.ingest")
            if vertical == "restaurants":
                from .pipeline import ingest
                ingest.scrape_to_raw("osm_overpass", metro)
            else:
                pipe.scrape_to_raw(metro)
            db.execute("UPDATE recommendations SET status = 'done' WHERE id = %s", (rec_id,))
            result["scraped"] = f"{vertical}@{metro}"
        except Exception as exc:
            result["scrape_error"] = str(exc)
    return result
