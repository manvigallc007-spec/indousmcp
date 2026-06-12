"""Read queries backing the MCP capabilities. Agent-facing, JSON-friendly output."""

from __future__ import annotations

import math
from typing import Any

from . import db, embeddings, hours

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
_COLS_SQL = ", ".join(_PUBLIC_COLS) + f", {_FEATURED} AS is_featured"


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


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
    """List active restaurants by geo-radius and/or filters.

    Featured listings are surfaced first (explicit `is_featured` flag), then by
    confidence, then by proximity. `tag` filters on a keyword (e.g. "biryani"); `open_now`
    keeps only places open at the current time (records carry an `open_now` flag).
    """
    where = ["deleted_at IS NULL", "is_active = true"]
    params: list[Any] = []

    if city:
        where.append("LOWER(city) = LOWER(%s)")
        params.append(city)
    if state:
        where.append("LOWER(state) = LOWER(%s)")
        params.append(state)
    if region_tag:
        where.append("region_tag = %s")
        params.append(region_tag)
    if dietary_tags:
        where.append("dietary_tags @> %s")
        params.append(dietary_tags)
    if tag:
        where.append("tags @> %s")
        params.append([tag.lower()])
    if featured_only:
        where.append(_FEATURED)

    # Coarse bbox prefilter when a point is given (radius later refined exactly).
    if lat is not None and lng is not None:
        deg = radius_miles / 69.0
        where.append("lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s")
        params += [lat - deg, lat + deg, lng - deg * 1.5, lng + deg * 1.5]

    sql = (
        f"SELECT {_COLS_SQL} FROM restaurants WHERE {' AND '.join(where)} "
        f"ORDER BY {_FEATURED} DESC, confidence_score DESC LIMIT %s"
    )
    params.append(max(limit * 4, limit))  # over-fetch; radius filter trims below
    rows = db.query(sql, params)

    if lat is not None and lng is not None:
        kept = []
        for row in rows:
            if row["lat"] is None or row["lng"] is None:
                continue
            d = _haversine_miles(lat, lng, row["lat"], row["lng"])
            if d <= radius_miles:
                row["distance_miles"] = round(d, 2)
                kept.append(row)
        kept.sort(key=lambda r: (not r["is_featured"], r["distance_miles"]))
        rows = kept

    hours.annotate(rows)
    if open_now:
        rows = [r for r in rows if r.get("open_now")]
    rows = rows[:limit]
    return {"count": len(rows), "results": rows}


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
) -> dict[str, Any]:
    """Text search over restaurants.

    Uses embedding-ranked vector search (pgvector cosine) when an embedding provider
    is configured and rows have embeddings; otherwise falls back to trigram (pg_trgm).
    """
    filters = ["deleted_at IS NULL", "is_active = true"]
    geo: list[Any] = []
    if city:
        filters.append("LOWER(city) = LOWER(%s)")
        geo.append(city)
    if state:
        filters.append("LOWER(state) = LOWER(%s)")
        geo.append(state)

    if embeddings.enabled():
        return _search_semantic(query_text, filters, geo, limit)
    return _search_trigram(query_text, filters, geo, limit)


def _search_semantic(query_text, filters, geo, limit) -> dict[str, Any]:
    qvec = embeddings.to_vector_literal(embeddings.embed(query_text))
    where = " AND ".join([*filters, "embedding IS NOT NULL"])
    # cosine distance (<=>); match_score = 1 - distance for a 0..1 similarity.
    sql = (
        f"SELECT {_COLS_SQL}, 1 - (embedding <=> %s::vector) AS match_score "
        f"FROM restaurants WHERE {where} "
        f"ORDER BY {_FEATURED} DESC, embedding <=> %s::vector LIMIT %s"
    )
    rows = db.query(sql, [qvec, *geo, qvec, limit])
    # Fall back to trigram if no embedded rows matched the filters yet.
    if not rows:
        return _search_trigram(query_text, filters, geo, limit)
    return {"count": len(rows), "query": query_text, "ranking": "semantic", "results": rows}


def _search_trigram(query_text, filters, geo, limit) -> dict[str, Any]:
    where = " AND ".join(filters)
    sql = (
        f"SELECT {_COLS_SQL}, similarity(name, %s) AS match_score "
        f"FROM restaurants WHERE {where} "
        f"ORDER BY {_FEATURED} DESC, match_score DESC, confidence_score DESC LIMIT %s"
    )
    rows = db.query(sql, [query_text, *geo, limit])
    return {"count": len(rows), "query": query_text, "ranking": "trigram", "results": rows}


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
            "SELECT count(*) FROM restaurants WHERE deleted_at IS NULL AND is_featured"
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
