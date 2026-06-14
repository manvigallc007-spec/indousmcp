"""Hybrid search ranking shared by every vertical, search_all, and the chatbot.

Combines exact-name match + keyword/tag overlap + vector similarity + proximity decay +
freshness into one score, so:
  * an exact listing name ranks #1 — even above a paid Featured listing (W_EXACT >> W_FEATURED),
  * nearby and recently-verified listings rank higher,
  * Featured is only a tiebreak among similarly-relevant results.

No PostGIS: distance is Python haversine, freshness uses `last_seen_at` (when the scraper last
re-confirmed the listing). The per-vertical query modules are thin wrappers over `text_search`
and `geo_list` here — adapt nothing else.
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Any

from . import db, embeddings, hours

# ---- tunable weights (exact dominates; featured is a modest nudge) ----
W_EXACT = 5.0
W_KEYWORD = 1.5
W_VECTOR = 2.0
W_PROXIMITY = 1.5
W_FRESHNESS = 1.0
W_FEATURED = 1.0
STALE_HALFLIFE_DAYS = 45.0
PROX_HALFLIFE_MI = 5.0
_CANDIDATES = 100  # how many relevance candidates to rerank

# category-ish columns to treat as an exact/keyword match target, across verticals
_CAT_FIELDS = ("cuisine_type", "store_type", "salon_type", "studio_type", "service_type",
               "profession_type", "speciality", "religion", "denomination", "deity",
               "region_tag", "category", "store_type")


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def freshness_score(last_seen_at) -> float:
    if last_seen_at is None:
        return 0.0
    now = _dt.datetime.now(_dt.timezone.utc)
    ref = last_seen_at if last_seen_at.tzinfo else last_seen_at.replace(tzinfo=_dt.timezone.utc)
    age_days = max((now - ref).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / STALE_HALFLIFE_DAYS)


def proximity_score(distance_mi: float | None) -> float:
    if distance_mi is None:
        return 0.0
    return 0.5 ** (distance_mi / PROX_HALFLIFE_MI)


def verified_label(last_seen_at) -> str | None:
    """Human-readable freshness for cards/MCP output."""
    if last_seen_at is None:
        return None
    now = _dt.datetime.now(_dt.timezone.utc)
    ref = last_seen_at if last_seen_at.tzinfo else last_seen_at.replace(tzinfo=_dt.timezone.utc)
    days = (now - ref).days
    if days <= 0:
        return "verified today"
    if days == 1:
        return "verified yesterday"
    if days < 30:
        return f"verified {days} days ago"
    months = days // 30
    return f"verified {months} month{'s' if months > 1 else ''} ago"


def _name_exact(q_norm: str, q_terms: set[str], name: str) -> float:
    """1.0 when the query clearly names this listing (full equality, or the multi-word name
    appears in the query, or a multi-word query is a substring of the name). Single common
    words ('dosa') are NOT exact — they only contribute keyword overlap."""
    if not q_norm or not name:
        return 0.0
    if q_norm == name:
        return 1.0
    name_tokens = name.split()
    if len(name_tokens) >= 2 and name in q_norm:      # "...mughlai express edison"
        return 1.0
    if len(q_terms) >= 2 and q_norm in name:          # "mughlai express" in "mughlai express llc"
        return 1.0
    return 0.0


def score_row(row: dict, q_norm: str, q_terms: set[str],
              vector_sim: float, distance_mi: float | None) -> float:
    name = _norm(row.get("name"))
    cats = {_norm(row.get(k)) for k in _CAT_FIELDS if row.get(k)}
    tags = {str(t).lower() for t in (row.get("tags") or [])}

    exact = _name_exact(q_norm, q_terms, name)
    if not exact and q_norm and q_norm in cats:       # whole query == a category value
        exact = 1.0
    cat_tokens = {tok for c in cats for tok in c.split()}
    overlap = len(q_terms & (set(name.split()) | tags | cat_tokens))
    keyword = min(overlap / max(len(q_terms), 1), 1.0) if q_terms else 0.0
    featured = 1.0 if row.get("is_featured") else 0.0

    return (
        W_EXACT * exact
        + W_KEYWORD * keyword
        + W_VECTOR * max(0.0, min(vector_sim, 1.0))
        + W_PROXIMITY * proximity_score(distance_mi)
        + W_FRESHNESS * freshness_score(row.get("last_seen_at"))
        + W_FEATURED * featured
    )


def rerank(rows: list[dict], query: str, point: tuple[float, float] | None = None,
           nearest_first: bool = False) -> list[dict]:
    """Score + sort rows; annotates each with score/distance/verified_ago.

    Default: by hybrid relevance score (exact-name first, then keyword/vector/proximity/fresh).
    `nearest_first` (we know where the user is): the relevance candidates are ordered by **distance
    ascending** — "show me the nearest ones, distance doesn't matter" — with the relevance score as
    a tie-break, and an exact-name match still allowed to lead. Rows without coordinates sort last.
    """
    q_norm = _norm(query)
    q_terms = set(q_norm.split())
    for r in rows:
        dist = None
        if point and r.get("lat") is not None and r.get("lng") is not None:
            dist = _haversine_miles(point[0], point[1], r["lat"], r["lng"])
            r["distance_miles"] = round(dist, 2)
        vs = r.get("match_score")
        vs = float(vs) if vs is not None else 0.0
        r["score"] = round(score_row(r, q_norm, q_terms, vs, dist), 4)
        r["verified_ago"] = verified_label(r.get("last_seen_at"))
    if nearest_first and point:
        # exact-name hits first; then nearest; score breaks ties; no-coord rows last.
        rows.sort(key=lambda r: (
            0 if r["score"] >= W_EXACT else 1,
            r.get("distance_miles") if r.get("distance_miles") is not None else float("inf"),
            -r["score"]))
    else:
        rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


# ----------------------------------------------------- shared candidate fetch + rerank
def _filters(city, state, extra_where):
    where = ["deleted_at IS NULL", "is_active = true"]
    params: list[Any] = []
    if city:
        where.append("LOWER(city) = LOWER(%s)")
        params.append(city)
    if state:
        where.append("LOWER(state) = LOWER(%s)")
        params.append(state)
    for clause, p in (extra_where or []):
        where.append(clause)
        params += list(p)
    return where, params


def text_search(table: str, cols_sql: str, query: str, *, city: str | None = None,
                state: str | None = None, point: tuple[float, float] | None = None,
                limit: int = 25, extra_where: list | None = None,
                precomputed_qvec: str | None = None,
                nearest_first: bool | None = None) -> dict[str, Any]:
    """Hybrid text search: relevance candidates (vector or trigram) UNION an exact/keyword
    pull (so exact names are never missed by vector recall), reranked by the hybrid score.
    `precomputed_qvec` lets a caller (e.g. search_all) embed the query once and reuse it.
    `nearest_first` defaults to ON whenever a `point` is known (we know where the user is →
    "show the nearest, distance doesn't matter"): relevance picks the candidates, distance orders
    them, so a wider pool is gathered to avoid missing the genuinely-closest matches. Pass
    `nearest_first=False` to force pure hybrid-relevance ordering."""
    near = (point is not None) if nearest_first is None else nearest_first
    where, params = _filters(city, state, extra_where)
    where_sql = " AND ".join(where)
    cand: dict[Any, dict] = {}
    n_cand = 300 if (near and point) else _CANDIDATES  # wider net when ordering by distance

    if embeddings.enabled():
        qvec = precomputed_qvec or embeddings.to_vector_literal(embeddings.embed(query))
        sql = (f"SELECT {cols_sql}, 1 - (embedding <=> %s::vector) AS match_score FROM {table} "
               f"WHERE {where_sql} AND embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT %s")
        rows = db.query(sql, [qvec, *params, qvec, n_cand])
        ranking = "semantic"
    else:
        sql = (f"SELECT {cols_sql}, similarity(name, %s) AS match_score FROM {table} "
               f"WHERE {where_sql} ORDER BY match_score DESC LIMIT %s")
        rows = db.query(sql, [query, *params, n_cand])
        ranking = "trigram"
    for r in rows:
        cand[r["id"]] = r

    # Guarantee exact/keyword candidates regardless of vector recall.
    kw = (f"SELECT {cols_sql}, similarity(name, %s) AS match_score FROM {table} "
          f"WHERE {where_sql} AND (name ILIKE %s OR tags @> %s) LIMIT 50")
    for r in db.query(kw, [query, *params, f"%{query}%", [query.lower()]]):
        cand.setdefault(r["id"], r)  # keep vector match_score if already present

    results = rerank(list(cand.values()), query, point, nearest_first=near)[:limit]
    return {"count": len(results), "query": query, "ranking": ranking, "results": results}


def geo_list(table: str, cols_sql: str, *, point: tuple[float, float] | None = None,
             city: str | None = None, state: str | None = None, tag: str | None = None,
             open_now: bool = False, limit: int = 25, radius_miles: float = 150.0,
             extra_where: list | None = None) -> dict[str, Any]:
    """Geo/filter listing ordered NEAREST-FIRST when a point is given (distance doesn't matter —
    show the closest). `radius_miles` is a generous prefilter (default 150) so we don't pull the
    whole table, not a hard 'too far' cutoff; pass a smaller value to bound it tightly."""
    ew = list(extra_where or [])
    if tag:
        ew.append(("tags @> %s", [[tag.lower()]]))
    where, params = _filters(city, state, ew)
    if point:
        deg = radius_miles / 69.0
        where.append("lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s")
        params += [point[0] - deg, point[0] + deg, point[1] - deg * 1.5, point[1] + deg * 1.5]
    sql = f"SELECT {cols_sql} FROM {table} WHERE {' AND '.join(where)} LIMIT %s"
    rows = db.query(sql, params + [max(limit * 12, 400)])

    if point:
        rows = [r for r in rows if r.get("lat") is not None and r.get("lng") is not None]
    hours.annotate(rows)
    if open_now:
        rows = [r for r in rows if r.get("open_now")]
    results = rerank(rows, "", point, nearest_first=bool(point))[:limit]
    return {"count": len(results), "results": results}
