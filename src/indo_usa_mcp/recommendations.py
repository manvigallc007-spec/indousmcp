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
}
_MIN_MISSES = 3  # only recommend something searched at least this many times


def _match_vertical(query: str) -> str | None:
    q = (query or "").lower()
    for kw, v in _KW.items():
        if kw in q:
            return v
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
    for m in misses:
        n = m["n"]
        if n < _MIN_MISSES:
            continue
        query = (m.get("query") or "").strip()
        city, state = m.get("city"), m.get("state")
        loc = ", ".join(x for x in (city, state) if x) or "an unspecified location"
        vertical = _match_vertical(query)

        if vertical:
            kind, action = "coverage", None
            label = verticals.VERTICALS.get(vertical, {}).get("label", vertical)
            metro = _metro_for(city, state)
            suggestion = (f"Grow {label} coverage in {loc}: {n} unanswered searches. "
                          + (f"Scrape the '{metro}' metro for {vertical}, "
                             if metro else "Solicit owner submissions / add manually, ")
                          + "or run targeted outreach there.")
            if metro:
                action = f"scrape:{metro}:{vertical}"
        else:
            kind, action = "new_topic", None
            suggestion = (f"“{query}” ({n} searches) doesn’t map to any current category — "
                          "consider a new vertical, or whether it's a phrasing we should handle.")

        sig = f"{kind}|{vertical or ''}|{state or ''}|{city or ''}|{query}".lower()[:300]
        row = db.query_one(
            "INSERT INTO recommendations (signature, kind, vertical, city, state, query, "
            "n_misses, suggestion, action) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (signature) DO UPDATE SET n_misses = EXCLUDED.n_misses, "
            "suggestion = EXCLUDED.suggestion WHERE recommendations.status = 'pending' "
            "RETURNING (xmax = 0) AS inserted",
            (sig, kind, vertical, city, state, query, n, suggestion, action))
        if row is not None:
            created += int(row["inserted"])
            updated += int(not row["inserted"])
    return {"scanned": len(misses), "created": created, "updated": updated}


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
