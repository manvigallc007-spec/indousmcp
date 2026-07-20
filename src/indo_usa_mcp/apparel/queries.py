"""Read queries backing the apparel MCP capabilities."""

from __future__ import annotations

from typing import Any

from .. import db, ranking

_PUBLIC_COLS = [
    "id", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "store_type", "region_tag",
    "festival_specials", "description", "tags", "is_active", "is_claimed", "confidence_score",
    "version", "source_name", "source_url", "last_seen_at",
]
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"
_COLS_SQL = (", ".join(_PUBLIC_COLS)
             + f", rating, rating_count, community_rating, community_rating_count, languages, {_FEATURED} AS is_featured")


def get_indian_apparel(
    *, lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25, offset: int = 0,
) -> dict[str, Any]:
    """List active Indian apparel/jewelry stores, ranked by proximity + freshness + Featured."""
    point = (lat, lng) if lat is not None and lng is not None else None
    return ranking.geo_list("apparel", _COLS_SQL, point=point, city=city, state=state,
                            tag=tag, open_now=open_now, limit=limit, offset=offset, radius_miles=radius_miles)


def get_apparel_details(apparel_id: int) -> dict[str, Any] | None:
    record = db.query_one(
        f"SELECT {_COLS_SQL} FROM apparel WHERE id = %s AND deleted_at IS NULL", (apparel_id,))
    if record is None:
        return None
    record["version_history"] = db.query(
        "SELECT version, change_reason, changed_at FROM apparel_versions "
        "WHERE apparel_id = %s ORDER BY version DESC", (apparel_id,))
    return record


def search_apparel_by_text(
    query_text: str, *, city: str | None = None, state: str | None = None, limit: int = 25, offset: int = 0,
    point: tuple[float, float] | None = None, precomputed_qvec: str | None = None,
) -> dict[str, Any]:
    return ranking.text_search("apparel", _COLS_SQL, query_text, city=city, state=state,
                               point=point, limit=limit, offset=offset, precomputed_qvec=precomputed_qvec)


def stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = db.query_one(sql)
        return list(row.values())[0] if row else 0

    return {
        "raw_total": scalar("SELECT count(*) FROM apparel_raw"),
        "raw_unprocessed": scalar("SELECT count(*) FROM apparel_raw WHERE NOT processed"),
        "apparel_active": scalar("SELECT count(*) FROM apparel WHERE deleted_at IS NULL AND is_active"),
        "versions_total": scalar("SELECT count(*) FROM apparel_versions"),
        "cities": db.query(
            "SELECT city, state, count(*) AS n FROM apparel WHERE deleted_at IS NULL "
            "AND city IS NOT NULL GROUP BY city, state ORDER BY n DESC LIMIT 10"),
    }
