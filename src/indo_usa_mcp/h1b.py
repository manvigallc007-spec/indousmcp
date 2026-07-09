"""Query the H-1B sponsors directory (populated from the DOL LCA file by labor.import_disclosure).

Read-only helpers for the web page, the MCP tool, and the chatbot: search employers by name and/or
worksite state, ranked by certified-LCA volume. Aggregated public figures only.
"""

from __future__ import annotations

from typing import Any

from . import db


def search_sponsors(q: str | None = None, state: str | None = None, limit: int = 40) -> list[dict]:
    where, params = ["certified > 0", "is_active", "deleted_at IS NULL"], []
    if q:
        where.append("employer ILIKE %s")
        params.append(f"%{q.strip().upper()}%")
    if state:
        where.append("%s = ANY(top_states)")
        params.append(state.strip().upper()[:2])
    try:
        return db.query(
            f"SELECT employer, display_name, certified, median_wage, top_titles, top_states, "
            f"top_cities, fiscal_year FROM h1b_sponsors WHERE {' AND '.join(where)} "
            f"ORDER BY certified DESC LIMIT %s", params + [limit])
    except Exception:
        return []


def count() -> int:
    try:
        row = db.query_one(
            "SELECT count(*) AS n FROM h1b_sponsors WHERE is_active AND deleted_at IS NULL")
        return int(row["n"]) if row else 0
    except Exception:
        return 0


# ------------------------------------------------------------------------- admin moderation
_EDIT_FIELDS = ("display_name", "median_wage", "fiscal_year")   # scalars
_LIST_FIELDS = ("top_titles", "top_states", "top_cities")       # frequency-ranked -- not sorted on save
# NOT editable here: employer (upsert key), certified (recomputed every DOL import).


def get_sponsor(sponsor_id: int) -> dict | None:
    return db.query_one("SELECT * FROM h1b_sponsors WHERE id = %s", (sponsor_id,))


def apply_edits(sponsor_id: int, edits: dict) -> dict:
    diff = {k: v for k, v in edits.items() if k in _EDIT_FIELDS or k in _LIST_FIELDS}
    if not diff:
        return {"ok": True, "updated": 0}
    sets = ", ".join(f"{k} = %s" for k in diff)
    db.execute(f"UPDATE h1b_sponsors SET {sets}, updated_at = now() WHERE id = %s",
               [*diff.values(), sponsor_id])
    return {"ok": True, "updated": len(diff), "fields": sorted(diff)}


def set_active(sponsor_id: int, active: bool) -> None:
    db.execute("UPDATE h1b_sponsors SET is_active = %s, updated_at = now() WHERE id = %s",
               (active, sponsor_id))


def set_deleted(sponsor_id: int, deleted: bool) -> None:
    val = "now()" if deleted else "NULL"
    db.execute(f"UPDATE h1b_sponsors SET deleted_at = {val}, updated_at = now() WHERE id = %s",
               (sponsor_id,))


def _admin_filters(q: str | None, flt: str | None) -> tuple[list[str], list]:
    where, params = ["deleted_at IS NULL"], []
    if q:
        where.append("employer ILIKE %s")
        params.append(f"%{q.strip().upper()}%")
    if flt == "inactive":
        where.append("NOT is_active")
    elif flt == "active":
        where.append("is_active")
    return where, params


def list_admin(q: str | None = None, flt: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    where, params = _admin_filters(q, flt)
    return db.query(
        f"SELECT id, employer, display_name, certified, median_wage, is_active, fiscal_year "
        f"FROM h1b_sponsors WHERE {' AND '.join(where)} ORDER BY certified DESC LIMIT %s OFFSET %s",
        params + [limit, offset])


def count_admin(q: str | None = None, flt: str | None = None) -> int:
    where, params = _admin_filters(q, flt)
    row = db.query_one(f"SELECT count(*) AS n FROM h1b_sponsors WHERE {' AND '.join(where)}", params)
    return row["n"] if row else 0
