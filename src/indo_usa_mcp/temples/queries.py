"""Read queries backing the temple MCP capabilities (agent-facing, JSON-friendly)."""

from __future__ import annotations

from typing import Any

from .. import db, ranking

_PUBLIC_COLS = [
    "id", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "religion", "denomination", "deity",
    "region_tag", "festival_specials", "description", "tags", "is_active", "is_claimed", "confidence_score",
    "version", "source_name", "source_url", "last_seen_at",
]
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"
_COLS_SQL = (", ".join(_PUBLIC_COLS)
             + f", rating, rating_count, community_rating, community_rating_count, {_FEATURED} AS is_featured")


def get_indian_temples(
    *, lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, religion: str | None = None,
    denomination: str | None = None, tag: str | None = None, open_now: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """List active temples, ranked by proximity + freshness + Featured (filters: religion,
    denomination, city, tag, open_now)."""
    extra = []
    if religion:
        extra.append(("LOWER(religion) = LOWER(%s)", [religion]))
    if denomination:
        extra.append(("LOWER(denomination) = LOWER(%s)", [denomination]))
    point = (lat, lng) if lat is not None and lng is not None else None
    return ranking.geo_list("temples", _COLS_SQL, point=point, city=city, state=state,
                            tag=tag, open_now=open_now, limit=limit,
                            radius_miles=radius_miles, extra_where=extra)


def get_temple_details(temple_id: int) -> dict[str, Any] | None:
    record = db.query_one(
        f"SELECT {_COLS_SQL} FROM temples WHERE id = %s AND deleted_at IS NULL", (temple_id,))
    if record is None:
        return None
    record["version_history"] = db.query(
        "SELECT version, change_reason, changed_at FROM temple_versions "
        "WHERE temple_id = %s ORDER BY version DESC", (temple_id,))
    return record


def search_temples_by_text(
    query_text: str, *, city: str | None = None, state: str | None = None, limit: int = 25,
    point: tuple[float, float] | None = None, precomputed_qvec: str | None = None,
) -> dict[str, Any]:
    return ranking.text_search("temples", _COLS_SQL, query_text, city=city, state=state,
                               point=point, limit=limit, precomputed_qvec=precomputed_qvec)


def stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = db.query_one(sql)
        return list(row.values())[0] if row else 0

    return {
        "raw_total": scalar("SELECT count(*) FROM temple_raw"),
        "raw_unprocessed": scalar("SELECT count(*) FROM temple_raw WHERE NOT processed"),
        "temples_active": scalar("SELECT count(*) FROM temples WHERE deleted_at IS NULL AND is_active"),
        "versions_total": scalar("SELECT count(*) FROM temple_versions"),
        "by_religion": db.query(
            "SELECT religion, count(*) AS n FROM temples WHERE deleted_at IS NULL "
            "GROUP BY religion ORDER BY n DESC"),
        "cities": db.query(
            "SELECT city, state, count(*) AS n FROM temples WHERE deleted_at IS NULL "
            "AND city IS NOT NULL GROUP BY city, state ORDER BY n DESC LIMIT 10"),
    }
