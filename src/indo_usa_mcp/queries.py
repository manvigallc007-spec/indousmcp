"""Read queries backing the MCP capabilities. Agent-facing, JSON-friendly output."""

from __future__ import annotations

from typing import Any

from . import db, ranking

# Columns exposed to agents (no internal embedding/raw fields).
_PUBLIC_COLS = [
    "id", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "website", "menu_url", "hours_json", "cuisine_type", "region_tag",
    "dietary_tags", "price_range", "delivery_partners", "festival_specials", "description",
    "tags", "is_active", "is_claimed", "confidence_score", "version",
    "source_name", "source_url", "last_seen_at",
]
# A listing is *effectively* featured while flagged AND within its paid window.
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"
# Always return the effective featured flag (not the raw column).
_COLS_SQL = (", ".join(_PUBLIC_COLS)
             + f", rating, rating_count, community_rating, community_rating_count, languages, {_FEATURED} AS is_featured")


def get_indian_restaurants(
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 10.0,
    city: str | None = None,
    state: str | None = None,
    region_tag: str | None = None,
    dietary_tags: list[str] | None = None,
    tag: str | None = None,
    open_now: bool = False,
    featured_only: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """List active restaurants by geo-radius and/or filters, ranked by proximity decay +
    freshness + Featured (no hard featured-first override). `tag` filters a keyword;
    `open_now` keeps only places open now."""
    extra = []
    if region_tag:
        extra.append(("region_tag = %s", [region_tag]))
    if dietary_tags:
        extra.append(("dietary_tags @> %s", [dietary_tags]))
    if featured_only:
        extra.append((_FEATURED, []))
    point = (lat, lng) if lat is not None and lng is not None else None
    return ranking.geo_list("restaurants", _COLS_SQL, point=point, city=city, state=state,
                            tag=tag, open_now=open_now, limit=limit,
                            radius_miles=radius_miles, extra_where=extra)


def get_restaurant_details(restaurant_id: int) -> dict[str, Any] | None:
    """Full canonical record plus its version history."""
    record = db.query_one(
        f"SELECT {_COLS_SQL} FROM restaurants WHERE id = %s AND deleted_at IS NULL",
        (restaurant_id,),
    )
    if record is None:
        return None
    history = db.query(
        "SELECT version, change_reason, changed_at FROM restaurant_versions "
        "WHERE restaurant_id = %s ORDER BY version DESC",
        (restaurant_id,),
    )
    record["version_history"] = history
    return record


def search_restaurants_by_text(
    query_text: str,
    *,
    city: str | None = None,
    state: str | None = None,
    limit: int = 25,
    point: tuple[float, float] | None = None,
    precomputed_qvec: str | None = None,
) -> dict[str, Any]:
    """Hybrid text search over restaurants (exact-name + keyword + vector + proximity +
    freshness). See `ranking.text_search`."""
    return ranking.text_search("restaurants", _COLS_SQL, query_text, city=city, state=state,
                               point=point, limit=limit, precomputed_qvec=precomputed_qvec)


def stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = db.query_one(sql)
        return list(row.values())[0] if row else 0

    return {
        "raw_total": scalar("SELECT count(*) FROM restaurant_raw"),
        "raw_unprocessed": scalar("SELECT count(*) FROM restaurant_raw WHERE NOT processed"),
        "restaurants_active": scalar(
            "SELECT count(*) FROM restaurants WHERE deleted_at IS NULL AND is_active"
        ),
        "restaurants_featured": scalar(
            # effective featured (within the paid window), matching reporting.py — not the raw column,
            # which over-counts listings whose featured_until has already passed.
            f"SELECT count(*) FROM restaurants WHERE deleted_at IS NULL AND {_FEATURED}"
        ),
        "approvals_pending": scalar(
            "SELECT count(*) FROM approval_queue WHERE status = 'pending'"
        ),
        "versions_total": scalar("SELECT count(*) FROM restaurant_versions"),
        "cities": db.query(
            "SELECT city, state, count(*) AS n FROM restaurants "
            "WHERE deleted_at IS NULL AND city IS NOT NULL "
            "GROUP BY city, state ORDER BY n DESC LIMIT 15"
        ),
    }
