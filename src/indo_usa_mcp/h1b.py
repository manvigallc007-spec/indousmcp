"""Query the H-1B sponsors directory (populated from the DOL LCA file by labor.import_disclosure).

Read-only helpers for the web page, the MCP tool, and the chatbot: search employers by name and/or
worksite state, ranked by certified-LCA volume. Aggregated public figures only.
"""

from __future__ import annotations

from typing import Any

from . import db


def search_sponsors(q: str | None = None, state: str | None = None, limit: int = 40) -> list[dict]:
    where, params = ["certified > 0"], []
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
        row = db.query_one("SELECT count(*) AS n FROM h1b_sponsors")
        return int(row["n"]) if row else 0
    except Exception:
        return 0
