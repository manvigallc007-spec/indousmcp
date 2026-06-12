"""Read queries backing the temple MCP capabilities (agent-facing, JSON-friendly)."""

from __future__ import annotations

import math
from typing import Any

from .. import db, embeddings

_PUBLIC_COLS = [
    "id", "name", "address_full", "city", "state", "country", "lat", "lng",
    "phone", "email", "website", "hours_json", "religion", "denomination", "deity",
    "region_tag", "festival_specials", "is_active", "is_claimed", "confidence_score",
    "version", "source_name", "source_url", "last_seen_at",
]
_FEATURED = "(is_featured AND (featured_until IS NULL OR featured_until > now()))"
_COLS_SQL = ", ".join(_PUBLIC_COLS) + f", {_FEATURED} AS is_featured"


def _haversine_miles(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def get_indian_temples(
    *, lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, religion: str | None = None,
    denomination: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """List active temples by geo-radius and/or filters (religion, denomination, city)."""
    where = ["deleted_at IS NULL", "is_active = true"]
    params: list[Any] = []
    if city:
        where.append("LOWER(city) = LOWER(%s)")
        params.append(city)
    if state:
        where.append("LOWER(state) = LOWER(%s)")
        params.append(state)
    if religion:
        where.append("LOWER(religion) = LOWER(%s)")
        params.append(religion)
    if denomination:
        where.append("LOWER(denomination) = LOWER(%s)")
        params.append(denomination)
    if lat is not None and lng is not None:
        deg = radius_miles / 69.0
        where.append("lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s")
        params += [lat - deg, lat + deg, lng - deg * 1.5, lng + deg * 1.5]

    sql = (f"SELECT {_COLS_SQL} FROM temples WHERE {' AND '.join(where)} "
           f"ORDER BY {_FEATURED} DESC, confidence_score DESC LIMIT %s")
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
        kept.sort(key=lambda r: (not r["is_featured"], r["distance_miles"]))
        rows = kept
    rows = rows[:limit]
    return {"count": len(rows), "results": rows}


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
) -> dict[str, Any]:
    filters = ["deleted_at IS NULL", "is_active = true"]
    geo: list[Any] = []
    if city:
        filters.append("LOWER(city) = LOWER(%s)")
        geo.append(city)
    if state:
        filters.append("LOWER(state) = LOWER(%s)")
        geo.append(state)

    if embeddings.enabled():
        qvec = embeddings.to_vector_literal(embeddings.embed(query_text))
        where = " AND ".join([*filters, "embedding IS NOT NULL"])
        sql = (f"SELECT {_COLS_SQL}, 1 - (embedding <=> %s::vector) AS match_score "
               f"FROM temples WHERE {where} "
               f"ORDER BY {_FEATURED} DESC, embedding <=> %s::vector LIMIT %s")
        rows = db.query(sql, [qvec, *geo, qvec, limit])
        if rows:
            return {"count": len(rows), "query": query_text, "ranking": "semantic", "results": rows}

    where = " AND ".join(filters)
    sql = (f"SELECT {_COLS_SQL}, similarity(name, %s) AS match_score FROM temples "
           f"WHERE {where} ORDER BY {_FEATURED} DESC, match_score DESC, confidence_score DESC LIMIT %s")
    rows = db.query(sql, [query_text, *geo, limit])
    return {"count": len(rows), "query": query_text, "ranking": "trigram", "results": rows}


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
