"""Per-agent usage metering — a DORMANT provision for future monetization (points 12 & 15).

Every MCP tool call and public-API search is already recorded in `tool_log` with a `client` id, so
per-agent usage is countable today (see analytics.py + the admin Traffic view). This module reads
that log to report usage and check quotas.

It is OFF by default (settings.agent_metering_enabled = False): `within_quota()` then always returns
True, so the guard can be wired into the request path now with ZERO behaviour change. When you
decide to charge agents for retrieval, flip the flag — and `within_quota()` starts enforcing
`settings.agent_free_monthly_quota` calls/agent/month at the API/MCP boundary.
"""

from __future__ import annotations

from typing import Any

from . import db
from .config import settings


def enabled() -> bool:
    return settings.agent_metering_enabled


def usage_by_client(days: int = 30, limit: int = 50) -> list[dict]:
    """Per-agent (client) call counts over the window — the billing-ready usage view."""
    return db.query(
        "SELECT COALESCE(client, '(anonymous)') AS client, count(*) AS calls, "
        f"max(created_at) AS last_seen FROM tool_log "
        f"WHERE created_at > now() - interval '{int(days)} days' "
        "GROUP BY client ORDER BY calls DESC LIMIT %s", (limit,))


def monthly_calls(client: str) -> int:
    """Calls by one agent so far this calendar month."""
    row = db.query_one(
        "SELECT count(*) AS n FROM tool_log WHERE client = %s "
        "AND created_at >= date_trunc('month', now())", (client,))
    return int(row["n"]) if row else 0


def within_quota(client: str | None) -> bool:
    """Whether an agent is still within its free monthly quota.

    Always True when metering is OFF (the default) or when the caller is anonymous, so this can be
    wired into the API/MCP path today with no effect until the flag is flipped on."""
    if not enabled() or not client:
        return True
    return monthly_calls(client) < settings.agent_free_monthly_quota


def quota_status(client: str | None) -> dict[str, Any]:
    """Small status object for responses/headers when metering is on (used = this month's calls)."""
    used = monthly_calls(client) if (client and enabled()) else 0
    return {"metering": enabled(), "used": used, "quota": settings.agent_free_monthly_quota,
            "within_quota": within_quota(client)}
