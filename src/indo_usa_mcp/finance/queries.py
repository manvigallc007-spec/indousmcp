"""Read queries backing the finance & tax MCP capabilities."""

from __future__ import annotations

from typing import Any

from .. import db, ranking

_PUBLIC_COLS = [
    "id", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "finance_type", "region_tag",
    "festival_specials", "description", "tags", "is_active", "is_claimed", "confidence_score",
    "version", "source_name", "source_url", "last_seen_at",
]
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"
_COLS_SQL = ", ".join(_PUBLIC_COLS) + f", rating, rating_count, {_FEATURED} AS is_featured"


def get_indian_finance(
    *, lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """List active Indian-American CPAs, tax preparers & financial advisors, ranked by proximity +
    freshness + Featured (filter by `tag`, e.g. 'cpa', 'tax' or 'financial_advisor')."""
    point = (lat, lng) if lat is not None and lng is not None else None
    return ranking.geo_list("finance", _COLS_SQL, point=point, city=city, state=state,
                            tag=tag, open_now=open_now, limit=limit, radius_miles=radius_miles)


def get_finance_details(finance_id: int) -> dict[str, Any] | None:
    record = db.query_one(
        f"SELECT {_COLS_SQL} FROM finance WHERE id = %s AND deleted_at IS NULL", (finance_id,))
    if record is None:
        return None
    record["version_history"] = db.query(
        "SELECT version, change_reason, changed_at FROM finance_versions "
        "WHERE finance_id = %s ORDER BY version DESC", (finance_id,))
    return record


def search_finance_by_text(
    query_text: str, *, city: str | None = None, state: str | None = None, limit: int = 25,
    point: tuple[float, float] | None = None, precomputed_qvec: str | None = None,
) -> dict[str, Any]:
    return ranking.text_search("finance", _COLS_SQL, query_text, city=city, state=state,
                               point=point, limit=limit, precomputed_qvec=precomputed_qvec)


def stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = db.query_one(sql)
        return list(row.values())[0] if row else 0

    return {
        "raw_total": scalar("SELECT count(*) FROM finance_raw"),
        "raw_unprocessed": scalar("SELECT count(*) FROM finance_raw WHERE NOT processed"),
        "finance_active": scalar("SELECT count(*) FROM finance WHERE deleted_at IS NULL AND is_active"),
        "versions_total": scalar("SELECT count(*) FROM finance_versions"),
        "cities": db.query(
            "SELECT city, state, count(*) AS n FROM finance WHERE deleted_at IS NULL "
            "AND city IS NOT NULL GROUP BY city, state ORDER BY n DESC LIMIT 10"),
    }
