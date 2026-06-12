"""Vertical registry + generic admin data helpers.

Maps each vertical (restaurants / temples / groceries) to its table, stats, editable
fields and a versioned update function, so admin/data code stays generic instead of being
duplicated per vertical. Table names come only from this registry (never user input), so
the f-string SQL below is safe.
"""

from __future__ import annotations

from typing import Any, Callable

from . import db, queries as r_queries
from .groceries import pipeline as g_pipeline, queries as g_queries
from .pipeline import clean, ingest
from .professionals import pipeline as p_pipeline, queries as p_queries
from .salons import pipeline as s_pipeline, queries as s_queries
from .temples import pipeline as t_pipeline, queries as t_queries


def _update_restaurant(existing: dict, diff: dict) -> None:
    ingest._update_canonical(existing, {**existing, **diff}, diff, change_reason="admin edit")


def _update_temple(existing: dict, diff: dict) -> None:
    t_pipeline._update(existing, {**existing, **diff}, diff)


def _update_grocery(existing: dict, diff: dict) -> None:
    g_pipeline._update(existing, {**existing, **diff}, diff)


def _update_professional(existing: dict, diff: dict) -> None:
    p_pipeline._update(existing, {**existing, **diff}, diff)


def _update_salon(existing: dict, diff: dict) -> None:
    s_pipeline._update(existing, {**existing, **diff}, diff)


# label, queries module, stats fn, scalar edit fields, has_hours, has_dietary, update fn
VERTICALS: dict[str, dict[str, Any]] = {
    "restaurants": {
        "label": "Restaurants", "table": "restaurants", "queries": r_queries,
        "edit_fields": ["phone", "email", "website", "menu_url", "address_full", "city",
                        "state", "cuisine_type", "region_tag", "price_range", "festival_specials"],
        "has_hours": True, "has_dietary": True, "update": _update_restaurant,
        "supports_claims": True,
    },
    "temples": {
        "label": "Temples", "table": "temples", "queries": t_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "religion", "denomination", "deity", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_temple,
        "supports_claims": False,
    },
    "groceries": {
        "label": "Groceries", "table": "groceries", "queries": g_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "store_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": True, "update": _update_grocery,
        "supports_claims": False,
    },
    "professionals": {
        "label": "Professionals", "table": "professionals", "queries": p_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "profession_type", "speciality", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_professional,
        "supports_claims": False,
    },
    "salons": {
        "label": "Salons", "table": "salons", "queries": s_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "salon_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_salon,
        "supports_claims": False,
    },
}


def get(vertical: str) -> dict[str, Any]:
    if vertical not in VERTICALS:
        raise ValueError(f"Unknown vertical '{vertical}'")
    return VERTICALS[vertical]


def _table(vertical: str) -> str:
    return get(vertical)["table"]


# ------------------------------------------------------------------ generic queries
_FLT_MAP = {"featured": "is_featured", "claimed": "is_claimed",
            "inactive": "NOT is_active", "active": "is_active"}


def _filters(q, flt, state, city):
    where, params = ["deleted_at IS NULL"], []
    if q:
        where.append("(name ILIKE %s OR city ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if flt in _FLT_MAP:
        where.append(_FLT_MAP[flt])
    if state:
        where.append("LOWER(state) = LOWER(%s)")
        params.append(state)
    if city:
        where.append("LOWER(city) = LOWER(%s)")
        params.append(city)
    return where, params


def list_records(vertical: str, q: str | None = None, flt: str | None = None,
                 state: str | None = None, city: str | None = None,
                 limit: int = 50, offset: int = 0) -> list[dict]:
    where, params = _filters(q, flt, state, city)
    sql = (f"SELECT id, name, city, state, is_active, is_featured, is_claimed, "
           f"confidence_score, region_tag FROM {_table(vertical)} WHERE {' AND '.join(where)} "
           f"ORDER BY id DESC LIMIT %s OFFSET %s")
    return db.query(sql, params + [limit, offset])


def count_records(vertical: str, q: str | None = None, flt: str | None = None,
                  state: str | None = None, city: str | None = None) -> int:
    where, params = _filters(q, flt, state, city)
    row = db.query_one(f"SELECT count(*) AS n FROM {_table(vertical)} WHERE {' AND '.join(where)}", params)
    return row["n"] if row else 0


def geo_summary(vertical: str, state: str | None = None) -> list[dict]:
    """Country/state/city rollup. Without `state`: counts per state. With it: per city."""
    table = _table(vertical)
    if state is None:
        return db.query(
            f"SELECT COALESCE(state, '(unknown)') AS state, count(*) AS n FROM {table} "
            f"WHERE deleted_at IS NULL AND is_active GROUP BY state ORDER BY n DESC")
    return db.query(
        f"SELECT COALESCE(city, '(unknown)') AS city, count(*) AS n FROM {table} "
        f"WHERE deleted_at IS NULL AND is_active AND LOWER(state) = LOWER(%s) "
        f"GROUP BY city ORDER BY n DESC", (state,))


def normalize_geography(vertical: str) -> dict:
    """Backfill: normalize existing city/state (e.g. 'California' -> 'CA') in place."""
    table = _table(vertical)
    updated = 0
    for r in db.query(f"SELECT id, city, state FROM {table} WHERE deleted_at IS NULL"):
        ns, nc = clean.normalize_state(r["state"]), clean.normalize_city(r["city"])
        if ns != r["state"] or nc != r["city"]:
            db.execute(f"UPDATE {table} SET state = %s, city = %s, updated_at = now() WHERE id = %s",
                       (ns, nc, r["id"]))
            updated += 1
    return {"vertical": vertical, "updated": updated}


def get_record(vertical: str, rec_id: int) -> dict | None:
    return db.query_one(f"SELECT * FROM {_table(vertical)} WHERE id = %s", (rec_id,))


# ----------------------------------------------------------------- generic mutations
def set_featured(vertical: str, rec_id: int, days: int | None = 30) -> None:
    table = _table(vertical)
    if days is None:
        db.execute(f"UPDATE {table} SET is_featured = true, featured_until = NULL, "
                   f"updated_at = now() WHERE id = %s", (rec_id,))
    else:
        db.execute(f"UPDATE {table} SET is_featured = true, "
                   f"featured_until = now() + (%s || ' days')::interval, updated_at = now() "
                   f"WHERE id = %s", (days, rec_id))


def unset_featured(vertical: str, rec_id: int) -> None:
    db.execute(f"UPDATE {_table(vertical)} SET is_featured = false, featured_until = NULL, "
               f"updated_at = now() WHERE id = %s", (rec_id,))


def set_active(vertical: str, rec_id: int, active: bool) -> None:
    db.execute(f"UPDATE {_table(vertical)} SET is_active = %s, updated_at = now() WHERE id = %s",
               (active, rec_id))


def set_deleted(vertical: str, rec_id: int, deleted: bool) -> None:
    val = "now()" if deleted else "NULL"
    db.execute(f"UPDATE {_table(vertical)} SET deleted_at = {val}, updated_at = now() WHERE id = %s",
               (rec_id,))


def apply_edits(vertical: str, rec_id: int, edits: dict) -> dict:
    """Versioned admin edit of a record's allowed fields."""
    cfg = get(vertical)
    existing = get_record(vertical, rec_id)
    if existing is None:
        return {"ok": False, "error": "not_found"}
    allowed = set(cfg["edit_fields"]) | ({"hours_json"} if cfg["has_hours"] else set()) \
        | ({"dietary_tags"} if cfg["has_dietary"] else set())
    from .pipeline.ingest import _normalize
    diff = {k: v for k, v in edits.items()
            if k in allowed and _normalize(existing.get(k)) != _normalize(v)}
    if not diff:
        return {"ok": True, "updated": 0}
    cfg["update"](existing, diff)
    return {"ok": True, "updated": len(diff), "fields": sorted(diff)}


def enhance_existing(vertical: str) -> dict[str, Any]:
    """Backfill search quality on existing rows: geocode-fill city/state, (re)generate the
    description + tags + structured hours, and (re)compute the embedding. Idempotent."""
    from . import describe, embeddings, hours as hmod, tags as tagmod
    from .pipeline import clean as rclean
    from .pipeline.ingest import _adapt
    table = _table(vertical)
    changed = embedded = 0
    for r in db.query(f"SELECT * FROM {table} WHERE deleted_at IS NULL"):
        city, state = rclean.fill_location(r.get("city"), r.get("state"), r.get("lat"), r.get("lng"))
        rec = {**r, "city": city, "state": state}
        rec["description"] = describe.describe(vertical, rec)
        rec["tags"] = tagmod.extract(vertical, rec)
        new_hours = hmod.with_hours(r.get("hours_json"))

        updates = {"city": city, "state": state, "description": rec["description"],
                   "tags": rec["tags"], "hours_json": new_hours}
        sets, params = [], []
        for f, v in updates.items():
            if v != r.get(f):
                sets.append(f"{f} = %s"); params.append(_adapt(v))
        if sets:
            db.execute(f"UPDATE {table} SET {', '.join(sets)}, updated_at = now() WHERE id = %s",
                       params + [r["id"]])
            changed += 1
        if embeddings.enabled():
            db.execute(f"UPDATE {table} SET embedding = %s::vector WHERE id = %s",
                       (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(rec))), r["id"]))
            embedded += 1
    return {"vertical": vertical, "changed": changed, "embedded": embedded}


_MERGE_FILL = ["phone", "email", "website", "address_full", "region_tag",
               "hours_json", "description"]


def merge_duplicates(vertical: str, keep_id: int, drop_ids: list[int]) -> dict[str, Any]:
    """Merge duplicates into the keeper: fill the keeper's empty fields from the dropped
    records, then soft-delete the dropped ones (reversible)."""
    keeper = get_record(vertical, keep_id)
    if keeper is None:
        return {"ok": False, "error": "keeper_not_found"}
    diff: dict[str, Any] = {}
    for did in drop_ids:
        d = get_record(vertical, did)
        if d is None:
            continue
        for f in _MERGE_FILL:
            if keeper.get(f) in (None, "", {}) and d.get(f) not in (None, "", {}) and f not in diff:
                diff[f] = d.get(f)
    if diff:
        get(vertical)["update"](keeper, diff)
    for did in drop_ids:
        set_deleted(vertical, did, True)
    return {"ok": True, "kept": keep_id, "dropped": list(drop_ids), "filled": sorted(diff)}


def featured_summary() -> dict[str, Any]:
    """Active (effective) featured counts per vertical — the live paid placements."""
    out, total = {}, 0
    for key in VERTICALS:
        row = db.query_one(
            f"SELECT count(*) AS n FROM {_table(key)} WHERE deleted_at IS NULL "
            f"AND is_featured AND (featured_until IS NULL OR featured_until > now())")
        out[key] = row["n"] if row else 0
        total += out[key]
    return {"by_vertical": out, "total": total}
