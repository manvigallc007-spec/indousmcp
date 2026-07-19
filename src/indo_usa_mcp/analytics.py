"""Agent traffic analytics: record every MCP tool call and summarize usage.

Answers "how much agent traffic, which tools, which clients, over time". Logging is
best-effort and never raises into a tool response (the caller wraps it in try/except).
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from . import db


def log_call(tool: str, args: dict | None, result_count: int | None, client: str | None) -> None:
    # keep args small + JSON-serialisable
    safe = {k: v for k, v in (args or {}).items()
            if isinstance(v, (str, int, float, bool, list)) and v not in (None, "")}
    db.execute(
        "INSERT INTO tool_log (tool, client, args, result_count) VALUES (%s, %s, %s, %s)",
        (tool, client, Jsonb(safe) if safe else None, result_count),
    )


# tool name -> the vertical it serves (for impression attribution).
_TOOL_VERTICAL = {
    "get_indian_restaurants": "restaurants", "get_restaurant_details": "restaurants",
    "search_restaurants_by_text": "restaurants",
    "get_indian_temples": "temples", "get_temple_details": "temples",
    "search_temples_by_text": "temples",
    "get_indian_groceries": "groceries", "get_grocery_details": "groceries",
    "search_groceries_by_text": "groceries",
    "get_indian_professionals": "professionals", "get_professional_details": "professionals",
    "search_professionals_by_text": "professionals",
    "get_indian_salons": "salons", "get_salon_details": "salons",
    "search_salons_by_text": "salons",
    "get_indian_events": "events", "get_event_details": "events",
    "search_events_by_text": "events",
    "get_indian_apparel": "apparel", "get_apparel_details": "apparel",
    "search_apparel_by_text": "apparel",
    "get_indian_sweets": "sweets", "get_sweets_details": "sweets",
    "search_sweets_by_text": "sweets",
    "get_indian_studios": "studios", "get_studio_details": "studios",
    "search_studios_by_text": "studios",
    "get_indian_services": "services", "get_service_details": "services",
    "search_services_by_text": "services",
    "get_indian_community": "community", "get_community_details": "community",
    "search_community_by_text": "community",
    "get_indian_legal": "legal", "get_legal_details": "legal",
    "search_legal_by_text": "legal",
    "get_indian_education": "education", "get_education_details": "education",
    "search_education_by_text": "education",
    "get_indian_realestate": "realestate", "get_realestate_details": "realestate",
    "search_realestate_by_text": "realestate",
    "get_indian_finance": "finance", "get_finance_details": "finance",
    "search_finance_by_text": "finance",
}


def _impression_rows(tool: str, result) -> list[tuple[str, int]]:
    if not isinstance(result, dict):
        return []
    if tool == "search_all":
        return [(r["vertical"], r["id"]) for r in result.get("results", [])
                if r.get("vertical") and r.get("id")]
    vertical = _TOOL_VERTICAL.get(tool)
    if not vertical:
        return []
    if "results" in result:  # list/search tools
        return [(vertical, r["id"]) for r in result["results"] if r.get("id")]
    if result.get("id"):     # *_details tools
        return [(vertical, result["id"])]
    return []


def log_impressions(tool: str, result) -> None:
    """Increment per-listing impression counts for the records a tool surfaced."""
    for vertical, rid in _impression_rows(tool, result):
        db.execute(
            "INSERT INTO impressions (vertical, record_id, day, count) "
            "VALUES (%s, %s, current_date, 1) "
            "ON CONFLICT (vertical, record_id, day) DO UPDATE SET count = impressions.count + 1",
            (vertical, rid),
        )


_LISTING_EVENT_KINDS = {"view", "call", "website", "directions"}


def log_listing_event(vertical: str, record_id: int, kind: str) -> bool:
    """Record one human listing event (view/call/website/directions). Returns False on bad input."""
    if kind not in _LISTING_EVENT_KINDS:
        return False
    try:
        db.execute(
            "INSERT INTO listing_events (vertical, record_id, kind, day, count) "
            "VALUES (%s, %s, %s, current_date, 1) "
            "ON CONFLICT (vertical, record_id, kind, day) DO UPDATE SET count = listing_events.count + 1",
            (vertical, int(record_id), kind))
        return True
    except Exception:
        return False


def listing_metrics(vertical: str, record_id: int, days: int = 30) -> dict[str, int]:
    """Per-kind event totals for one listing over the window (0-filled)."""
    out = {k: 0 for k in _LISTING_EVENT_KINDS}
    try:
        for r in db.query(
            "SELECT kind, sum(count) AS n FROM listing_events "
            f"WHERE vertical = %s AND record_id = %s AND day > current_date - {int(days)} GROUP BY kind",
            (vertical, record_id)):
            out[r["kind"]] = int(r["n"])
    except Exception:
        pass
    return out


def top_listings(days: int = 30, limit: int = 15) -> list[dict]:
    return db.query(
        "SELECT vertical, record_id, sum(count) AS impressions FROM impressions "
        f"WHERE day > current_date - {int(days)} "
        "GROUP BY vertical, record_id ORDER BY impressions DESC LIMIT %s", (limit,))


def reach_for(vertical: str, record_id: int, days: int = 30) -> int:
    row = db.query_one(
        "SELECT COALESCE(sum(count), 0) AS n FROM impressions "
        f"WHERE vertical = %s AND record_id = %s AND day > current_date - {int(days)}",
        (vertical, record_id))
    return int(row["n"]) if row else 0


def _scalar(sql: str, params=None) -> int:
    row = db.query_one(sql, params)
    return int(list(row.values())[0]) if row and list(row.values())[0] is not None else 0


def traffic_summary(days: int = 30) -> dict[str, Any]:
    win = f"created_at > now() - interval '{int(days)} days'"
    return {
        "days": days,
        "total_calls": _scalar(f"SELECT count(*) FROM tool_log WHERE {win}"),
        "calls_today": _scalar("SELECT count(*) FROM tool_log WHERE created_at::date = current_date"),
        "distinct_clients": _scalar(f"SELECT count(DISTINCT client) FROM tool_log WHERE {win}"),
        "by_tool": db.query(
            f"SELECT tool, count(*) AS n, max(created_at) AS last FROM tool_log WHERE {win} "
            f"GROUP BY tool ORDER BY n DESC"),
        "by_client": db.query(
            f"SELECT COALESCE(client, '(unknown)') AS client, count(*) AS n FROM tool_log "
            f"WHERE {win} GROUP BY client ORDER BY n DESC LIMIT 20"),
        "by_day": db.query(
            f"SELECT created_at::date AS day, count(*) AS n FROM tool_log WHERE {win} "
            f"GROUP BY day ORDER BY day DESC LIMIT 14"),
    }


def top_misses(days: int = 30, limit: int = 25) -> list[dict]:
    """Demand signal: searches that returned ZERO results, ranked by frequency. Reuses
    tool_log (every search — MCP tools + chatbot — logs its query/filters + result_count),
    so this is the ranked 'what to add next' list, by query and location."""
    win = f"created_at > now() - interval '{int(days)} days'"
    return db.query(
        "SELECT COALESCE(NULLIF(args->>'query',''), NULLIF(args->>'tag',''), '(geo/filter)') AS query, "
        "args->>'city' AS city, args->>'state' AS state, "
        "count(*) AS n, max(created_at) AS last_seen, "
        "count(DISTINCT client) AS sources "
        "FROM tool_log "
        f"WHERE result_count = 0 AND {win} "
        "AND (tool LIKE 'search\\_%%' OR tool LIKE 'get\\_indian\\_%%' OR tool IN ('search_all', 'api_search') "
        "     OR (tool = 'chat' AND args->>'provider' IN ('search','llm','discovery'))) "
        "GROUP BY 1, 2, 3 ORDER BY n DESC, last_seen DESC LIMIT %s", (limit,))


# ------------------------------------------------------------- first-party pageviews (human traffic)
def log_pageview(path: str) -> None:
    """Count a public HTML pageview (server-side -> not blocked by ad-blockers). Daily aggregate."""
    db.execute(
        "INSERT INTO pageviews (path, day, count) VALUES (%s, current_date, 1) "
        "ON CONFLICT (path, day) DO UPDATE SET count = pageviews.count + 1", ((path or "/")[:200],))


def pageview_summary(days: int = 30) -> dict[str, Any]:
    win = f"day > current_date - {int(days)}"
    return {
        "total": _scalar(f"SELECT COALESCE(sum(count), 0) FROM pageviews WHERE {win}"),
        "today": _scalar("SELECT COALESCE(sum(count), 0) FROM pageviews WHERE day = current_date"),
        "by_day": db.query(f"SELECT day, sum(count) AS n FROM pageviews WHERE {win} "
                           f"GROUP BY day ORDER BY day DESC LIMIT 14"),
        "top_paths": db.query(f"SELECT path, sum(count) AS n FROM pageviews WHERE {win} "
                              f"GROUP BY path ORDER BY n DESC LIMIT 15"),
    }


def recent_calls(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT tool, client, args, result_count, created_at FROM tool_log "
        "ORDER BY created_at DESC LIMIT %s", (limit,))
