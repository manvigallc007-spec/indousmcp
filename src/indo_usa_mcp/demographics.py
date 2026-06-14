"""US Census ACS demographics — Asian-Indian population by state & metro.

Free, public Census Bureau API (a key is optional for low volume). Aggregated counts only, no PII.
Two uses: (1) the public **/insights** page ("Indian America by the numbers"), and (2) telling us
which metros have the most Indian-Americans so the scrapers can prioritize coverage.

Variable B02015_002E = "Asian Indian" (ACS detailed table "Asian alone by selected groups").
"""

from __future__ import annotations

import httpx

from . import db
from .config import settings

_ACS = "https://api.census.gov/data/{year}/acs/acs5"
_VAR_INDIAN = "B02015_002E"   # Asian Indian (alone)
_VAR_TOTAL = "B01003_001E"    # total population
_GEO = {"state": "state:*",
        "metro": "metropolitan statistical area/micropolitan statistical area:*"}


def _int(v) -> int | None:
    try:
        n = int(v)
        return n if n >= 0 else None   # ACS uses large negative sentinels for "no data"
    except (TypeError, ValueError):
        return None


def _fetch(year: str, geo_clause: str) -> list[dict]:
    params = {"get": f"NAME,{_VAR_INDIAN},{_VAR_TOTAL}", "for": geo_clause}
    if settings.census_api_key:
        params["key"] = settings.census_api_key
    r = httpx.get(_ACS.format(year=year), params=params,
                  headers={"User-Agent": settings.scraper_user_agent}, timeout=30.0)
    r.raise_for_status()
    rows = r.json()
    header, data = rows[0], rows[1:]
    return [dict(zip(header, row)) for row in data]


def refresh(year: str = "2022") -> dict:
    """Pull state + metro Asian-Indian counts into the demographics table. Best-effort per level."""
    upserted, errors = 0, []
    for level, clause in _GEO.items():
        try:
            data = _fetch(year, clause)
        except Exception as exc:
            errors.append(f"{level}: {type(exc).__name__}")
            continue
        for rec in data:
            code = rec.get("state") or rec.get(_GEO[level].split(":")[0]) or rec.get("NAME")
            geoid = f"{level}:{code}"
            db.execute(
                "INSERT INTO demographics (geoid, level, name, indian_population, total_population) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (geoid) DO UPDATE SET "
                "name = EXCLUDED.name, indian_population = EXCLUDED.indian_population, "
                "total_population = EXCLUDED.total_population, updated_at = now()",
                [geoid, level, rec.get("NAME"), _int(rec.get(_VAR_INDIAN)), _int(rec.get(_VAR_TOTAL))])
            upserted += 1
    return {"upserted": upserted, "errors": errors, "year": year}


def top(level: str = "metro", limit: int = 15) -> list[dict]:
    try:
        return db.query(
            "SELECT name, indian_population, total_population FROM demographics "
            "WHERE level = %s AND indian_population IS NOT NULL "
            "ORDER BY indian_population DESC LIMIT %s", [level, limit])
    except Exception:
        return []


def summary() -> dict:
    try:
        row = db.query_one(
            "SELECT count(*) FILTER (WHERE level='metro') AS metros, "
            "COALESCE(sum(indian_population) FILTER (WHERE level='state'), 0) AS total_indian "
            "FROM demographics")
        return dict(row) if row else {}
    except Exception:
        return {}
