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
