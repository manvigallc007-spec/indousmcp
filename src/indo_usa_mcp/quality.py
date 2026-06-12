"""Data-quality scan across verticals: flag records needing attention + find duplicates.

Powers the admin Quality view so the operator can curate the dataset. All table names
come from the vertical registry (never user input), so the f-string SQL is safe.
"""

from __future__ import annotations

from typing import Any

from . import db
from .verticals import VERTICALS

# Issue key -> human label + SQL predicate (columns common to all 3 canonical tables).
ISSUES: dict[str, tuple[str, str]] = {
    "no_region": ("No region tag", "region_tag IS NULL"),
    "no_contact": ("No phone/website/email", "phone IS NULL AND website IS NULL AND email IS NULL"),
    "no_geo": ("Missing coordinates", "lat IS NULL OR lng IS NULL"),
    "no_city": ("No city", "city IS NULL"),
    "no_state": ("No state", "state IS NULL"),
    "low_confidence": ("Low confidence (<0.5)", "confidence_score < 0.5"),
}


def _table(vertical: str) -> str:
    return VERTICALS[vertical]["table"]


def _scalar(sql: str, params=None) -> int:
    row = db.query_one(sql, params)
    return int(list(row.values())[0]) if row else 0


def summary(vertical: str) -> dict[str, Any]:
    table = _table(vertical)
    base = f"FROM {table} WHERE deleted_at IS NULL AND is_active"
    out: dict[str, Any] = {"total": _scalar(f"SELECT count(*) {base}")}
    for key, (_, cond) in ISSUES.items():
        out[key] = _scalar(f"SELECT count(*) {base} AND ({cond})")
    out["duplicate_groups"] = _scalar(
        f"SELECT count(*) FROM (SELECT lower(name), lower(city) {base} "
        f"GROUP BY 1, 2 HAVING count(*) > 1) d")
    return out


def flagged(vertical: str, issue: str, limit: int = 100) -> list[dict]:
    if issue not in ISSUES:
        return []
    cond = ISSUES[issue][1]
    return db.query(
        f"SELECT id, name, city, state, region_tag, confidence_score FROM {_table(vertical)} "
        f"WHERE deleted_at IS NULL AND is_active AND ({cond}) ORDER BY id LIMIT %s", (limit,))


def duplicates(vertical: str, limit: int = 50) -> list[dict]:
    """Groups of active records sharing a normalized name + city (likely duplicates)."""
    return db.query(
        f"SELECT name, city, state, count(*) AS n, array_agg(id ORDER BY id) AS ids "
        f"FROM {_table(vertical)} WHERE deleted_at IS NULL AND is_active "
        f"GROUP BY lower(name), lower(city), name, city, state HAVING count(*) > 1 "
        f"ORDER BY count(*) DESC LIMIT %s", (limit,))


def scan_all() -> dict[str, Any]:
    return {v: summary(v) for v in VERTICALS}
