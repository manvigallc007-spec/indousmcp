"""Read queries for events. Only APPROVED events are agent-visible; UPCOMING by default
(past events are kept and date-filtered, retrievable with include_past)."""

from __future__ import annotations

import math
from typing import Any

from .. import db, embeddings

_PUBLIC_COLS = [
    "id", "name", "description", "tags", "category", "organizer", "venue_name",
    "start_at", "end_at", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "region_tag", "festival_specials", "status",
    "is_active", "is_claimed", "confidence_score", "version", "source_name", "source_url",
    "last_seen_at",
]
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"
_COLS_SQL = ", ".join(_PUBLIC_COLS) + f", {_FEATURED} AS is_featured"
_UPCOMING = "COALESCE(end_at, start_at) >= now()"
_BASE = "deleted_at IS NULL AND is_active = true AND status = 'approved'"


def _haversine_miles(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def get_indian_events(
    *, lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, category: str | None = None,
    tag: str | None = None, include_past: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """List approved Indian-American events. Upcoming by default; set include_past=true for history."""
    where = [_BASE]
    params: list[Any] = []
    if not include_past:
        where.append(_UPCOMING)
    if category:
        where.append("LOWER(category) = LOWER(%s)")
        params.append(category)
    if tag:
        where.append("tags @> %s")
        params.append([tag.lower()])
    if city:
        where.append("LOWER(city) = LOWER(%s)")
        params.append(city)
    if state:
        where.append("LOWER(state) = LOWER(%s)")
        params.append(state)
    if lat is not None and lng is not None:
        deg = radius_miles / 69.0
        where.append("lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s")
        params += [lat - deg, lat + deg, lng - deg * 1.5, lng + deg * 1.5]

    order = "start_at DESC" if include_past else "start_at ASC"
    sql = (f"SELECT {_COLS_SQL} FROM events WHERE {' AND '.join(where)} "
           f"ORDER BY {_FEATURED} DESC, {order} LIMIT %s")
    params.append(max(limit * 4, limit))
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
        rows = kept
    return {"count": len(rows[:limit]), "results": rows[:limit]}


def get_event_details(event_id: int) -> dict[str, Any] | None:
    record = db.query_one(
        f"SELECT {_COLS_SQL} FROM events WHERE id = %s AND deleted_at IS NULL", (event_id,))
    if record is None:
        return None
    record["version_history"] = db.query(
        "SELECT version, change_reason, changed_at FROM event_versions "
        "WHERE event_id = %s ORDER BY version DESC", (event_id,))
    return record


def search_events_by_text(
    query_text: str, *, city: str | None = None, state: str | None = None, limit: int = 25,
    precomputed_qvec: str | None = None,
) -> dict[str, Any]:
    filters = [_BASE]
    geo: list[Any] = []
    if city:
        filters.append("LOWER(city) = LOWER(%s)")
        geo.append(city)
    if state:
        filters.append("LOWER(state) = LOWER(%s)")
        geo.append(state)

    if embeddings.enabled():
        qvec = precomputed_qvec or embeddings.to_vector_literal(embeddings.embed(query_text))
        where = " AND ".join([*filters, "embedding IS NOT NULL"])
        sql = (f"SELECT {_COLS_SQL}, 1 - (embedding <=> %s::vector) AS match_score "
               f"FROM events WHERE {where} ORDER BY {_FEATURED} DESC, embedding <=> %s::vector LIMIT %s")
        rows = db.query(sql, [qvec, *geo, qvec, limit])
        if rows:
            return {"count": len(rows), "query": query_text, "ranking": "semantic", "results": rows}

    where = " AND ".join(filters)
    sql = (f"SELECT {_COLS_SQL}, similarity(name, %s) AS match_score FROM events "
           f"WHERE {where} ORDER BY {_FEATURED} DESC, match_score DESC LIMIT %s")
    rows = db.query(sql, [query_text, *geo, limit])
    return {"count": len(rows), "query": query_text, "ranking": "trigram", "results": rows}


def stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = db.query_one(sql)
        return list(row.values())[0] if row else 0

    return {
        "raw_total": scalar("SELECT count(*) FROM event_raw"),
        "raw_unprocessed": scalar("SELECT count(*) FROM event_raw WHERE NOT processed"),
        "events_total": scalar("SELECT count(*) FROM events WHERE deleted_at IS NULL"),
        "approved": scalar("SELECT count(*) FROM events WHERE deleted_at IS NULL AND status='approved'"),
        "pending": scalar("SELECT count(*) FROM events WHERE deleted_at IS NULL AND status='pending'"),
        "upcoming": scalar(f"SELECT count(*) FROM events WHERE {_BASE} AND {_UPCOMING}"),
        "past": scalar(f"SELECT count(*) FROM events WHERE {_BASE} AND NOT ({_UPCOMING})"),
        "versions_total": scalar("SELECT count(*) FROM event_versions"),
    }
