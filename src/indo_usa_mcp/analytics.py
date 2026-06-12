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


def recent_calls(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT tool, client, args, result_count, created_at FROM tool_log "
        "ORDER BY created_at DESC LIMIT %s", (limit,))
