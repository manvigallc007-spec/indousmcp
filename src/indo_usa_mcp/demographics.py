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


def _num(v) -> float | None:
    """Float parse with the ACS 'jam'/suppression guard (medians use big negative sentinels)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None   # income / age / percent are all non-negative


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


# --------------------------------------------------------------------------- richer facts
# Languages spoken at home (ACS detailed table B16001) — works WITHOUT a key. Codes verified against
# the live API. Urdu/Bengali/Punjabi/Nepali are shared with the wider South-Asian diaspora, so we
# present these honestly as "Indian & South-Asian languages." (slug, display label) per estimate var.
_LANG_VARS: dict[str, tuple[str, str]] = {
    "B16001_048E": ("hindi", "Hindi"),
    "B16001_066E": ("telugu", "Telugu"),
    "B16001_069E": ("tamil", "Tamil"),
    "B16001_045E": ("gujarati", "Gujarati"),
    "B16001_054E": ("punjabi", "Punjabi"),
    "B16001_057E": ("bengali", "Bengali"),
    "B16001_051E": ("urdu", "Urdu"),
    "B16001_060E": ("indic_other", "Nepali, Marathi & other Indic"),
    "B16001_072E": ("dravidian_other", "Malayalam, Kannada & other Dravidian"),
}

# Selected Population Profile (S0201) for "Asian Indian alone" (POPGROUP 013): income/education/work
# for the diaspora specifically. The SPP endpoint REQUIRES a free Census API key (the B-tables don't),
# so this step is skipped (not failed) when census_api_key is unset. metric -> (code, unit, label).
_SPP = "https://api.census.gov/data/{year}/acs/acs1/spp"
_SPP_POPGROUP = "013"
_SPP_VARS: dict[str, tuple[str, str, str]] = {
    "median_household_income": ("S0201_214E", "usd", "Median household income"),
    "per_capita_income": ("S0201_235E", "usd", "Per-capita income"),
    "median_age": ("S0201_018E", "years", "Median age"),
    "unemployment_rate": ("S0201_159E", "percent", "Unemployment rate"),
}
# Percentages computed from a (numerator, denominator) pair. metric -> (num, denom, label).
_SPP_PCT: dict[str, tuple[str, str, str]] = {
    "pct_bachelors_plus": ("S0201_099E", "S0201_090E", "Bachelor's degree or higher (25+)"),
    "pct_prof_occupations": ("S0201_177E", "S0201_176E", "In management/science/arts jobs"),
}


def _upsert_fact(geoid: str, level: str, name: str | None, metric: str,
                 value: float | None, unit: str, label: str) -> None:
    db.execute(
        "INSERT INTO demographics_facts (geoid, level, name, metric, value, unit, label) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (geoid, metric) DO UPDATE SET "
        "level = EXCLUDED.level, name = EXCLUDED.name, value = EXCLUDED.value, "
        "unit = EXCLUDED.unit, label = EXCLUDED.label, updated_at = now()",
        [geoid, level, name, metric, value, unit, label])


def refresh_languages(year: str = "2022") -> dict:
    """Indian & South-Asian languages spoken at home, by state + a national roll-up. Free B16001."""
    codes = ",".join(_LANG_VARS)
    params = {"get": f"NAME,{codes}", "for": "state:*"}
    if settings.census_api_key:
        params["key"] = settings.census_api_key
    try:
        r = httpx.get(_ACS.format(year=year), params=params,
                      headers={"User-Agent": settings.scraper_user_agent}, timeout=40.0)
        r.raise_for_status()
        rows = r.json()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}"}
    header, data = rows[0], rows[1:]
    national: dict[str, int] = {code: 0 for code in _LANG_VARS}
    upserted = 0
    for row in data:
        rec = dict(zip(header, row))
        st = rec.get("state")
        for code, (slug, label) in _LANG_VARS.items():
            v = _int(rec.get(code))
            if v is None:
                continue
            national[code] += v
            _upsert_fact(f"state:{st}", "state", rec.get("NAME"), f"lang:{slug}", v, "speakers", label)
            upserted += 1
    for code, (slug, label) in _LANG_VARS.items():
        _upsert_fact("us", "us", "United States", f"lang:{slug}", national[code], "speakers", label)
    return {"ok": True, "upserted": upserted, "year": year}


def refresh_profile(year: str = "2022") -> dict:
    """Income/education/occupation for Asian-Indians (S0201, POPGROUP 013), US + states. Needs a free
    Census API key; returns {'skipped': ...} (not an error) when one isn't configured."""
    if not settings.census_api_key:
        return {"ok": False, "skipped": "no_census_api_key"}
    codes = ["S0201_001E"] + [v[0] for v in _SPP_VARS.values()]
    for ncode, dcode, _ in _SPP_PCT.values():
        codes += [ncode, dcode]
    getvars = "NAME," + ",".join(dict.fromkeys(codes))      # de-dup, preserve order
    out: dict = {"states": 0, "us": False, "errors": []}
    for clause, level in (("us:1", "us"), ("state:*", "state")):
        params = {"get": getvars, "for": clause, "POPGROUP": _SPP_POPGROUP,
                  "key": settings.census_api_key}
        try:
            r = httpx.get(_SPP.format(year=year), params=params,
                          headers={"User-Agent": settings.scraper_user_agent}, timeout=40.0)
            r.raise_for_status()
            rows = r.json()
        except Exception as exc:
            out["errors"].append(f"{level}: {type(exc).__name__}")
            continue
        header, data = rows[0], rows[1:]
        for row in data:
            rec = dict(zip(header, row))
            geoid = "us" if level == "us" else f"state:{rec.get('state')}"
            name = rec.get("NAME")
            for metric, (code, unit, label) in _SPP_VARS.items():
                v = _num(rec.get(code))
                if v is not None:
                    _upsert_fact(geoid, level, name, metric, v, unit, label)
            for metric, (ncode, dcode, label) in _SPP_PCT.items():
                num, den = _num(rec.get(ncode)), _num(rec.get(dcode))
                if num is not None and den and den > 0:
                    _upsert_fact(geoid, level, name, metric, round(100.0 * num / den, 1), "percent", label)
            if level == "us":
                out["us"] = True
            else:
                out["states"] += 1
    return {"ok": True, **out, "year": year}


def facts(geoid: str = "us") -> dict[str, dict]:
    """All profile metrics for a place, keyed by metric (value/unit/label)."""
    try:
        rows = db.query("SELECT metric, value, unit, label FROM demographics_facts "
                        "WHERE geoid = %s AND metric NOT LIKE 'lang:%%'", [geoid])
        return {r["metric"]: dict(r) for r in rows}
    except Exception:
        return {}


def languages(geoid: str = "us", limit: int = 9) -> list[dict]:
    """Top languages spoken at home for a place, most speakers first."""
    try:
        return db.query(
            "SELECT label, value FROM demographics_facts WHERE geoid = %s AND metric LIKE 'lang:%%' "
            "AND value > 0 ORDER BY value DESC LIMIT %s", [geoid, limit])
    except Exception:
        return []


def refresh_all(year: str = "2022") -> dict:
    """One call for the agent/CLI: population + languages + profile, then feed it to the KB."""
    return {"population": refresh(year), "languages": refresh_languages(year),
            "profile": refresh_profile(year), "knowledge": to_knowledge()}


def to_knowledge() -> dict:
    """Compose the population, income/education and language stats into knowledge-base documents so
    Dost answers them in prose. vertical=None (general knowledge); idempotent via content hashing."""
    from . import knowledge
    docs = 0
    total = summary().get("total_indian") or 0
    states, metros = top("state", 10), top("metro", 10)
    if total or states:
        lines = ["Indians from India in the USA — population and where they live (U.S. Census ACS)."]
        if total:
            lines.append(f"About {total:,} people of Asian-Indian origin live in the United States.")
        if states:
            lines.append("States with the most Indian-Americans: " + "; ".join(
                f"{r['name']} ({(r['indian_population'] or 0):,})" for r in states) + ".")
        if metros:
            lines.append("Metro areas with the most Indian-Americans: " + "; ".join(
                f"{r['name']} ({(r['indian_population'] or 0):,})" for r in metros) + ".")
        if knowledge.upsert_document(
                source_type="census", source_ref="census:population", vertical=None,
                title="Indian-American population across the USA",
                content="\n".join(lines)).get("ok"):
            docs += 1

    f = facts("us")
    g = lambda m: (f.get(m) or {}).get("value")    # noqa: E731
    parts = ["Indians from India in the USA — income, education and work (U.S. Census ACS Selected "
             "Population Profile for Asian-Indian alone)."]
    if g("median_household_income"):
        parts.append(f"Median household income is about ${g('median_household_income'):,.0f}.")
    if g("per_capita_income"):
        parts.append(f"Per-capita income is about ${g('per_capita_income'):,.0f}.")
    if g("pct_bachelors_plus"):
        parts.append(f"About {g('pct_bachelors_plus'):.0f}% of adults 25+ hold a bachelor's degree "
                     "or higher — among the highest of any group in the country.")
    if g("pct_prof_occupations"):
        parts.append(f"About {g('pct_prof_occupations'):.0f}% work in management, business, science "
                     "and arts occupations.")
    if g("median_age"):
        parts.append(f"The median age is about {g('median_age'):.0f} years.")
    if g("unemployment_rate") is not None:
        parts.append(f"The unemployment rate is about {g('unemployment_rate'):.1f}%.")
    if len(parts) > 1 and knowledge.upsert_document(
            source_type="census", source_ref="census:profile", vertical=None,
            title="Indian-Americans: income, education and work", content=" ".join(parts)).get("ok"):
        docs += 1

    langs = languages("us")
    if langs:
        listed = "; ".join(f"{r['label']} ({int(r['value']):,} speakers)" for r in langs if r["value"])
        if knowledge.upsert_document(
                source_type="census", source_ref="census:languages", vertical=None,
                title="Indian languages spoken in the USA",
                content=("Indian and South-Asian languages spoken at home in the United States "
                         f"(U.S. Census ACS), most-spoken first: {listed}. Most Indian-Americans "
                         "also speak English fluently.")).get("ok"):
            docs += 1
    return {"ok": True, "kb_documents": docs}
