"""Vertical registry + generic admin data helpers.

Maps each vertical (restaurants / temples / groceries) to its table, stats, editable
fields and a versioned update function, so admin/data code stays generic instead of being
duplicated per vertical. Table names come only from this registry (never user input), so
the f-string SQL below is safe.
"""

from __future__ import annotations

import functools
import uuid
from typing import Any, Callable
from urllib.parse import urlparse

from . import db, queries as r_queries
from .apparel import pipeline as ap_pipeline, queries as ap_queries
from .community import pipeline as co_pipeline, queries as co_queries
from .events import pipeline as e_pipeline, queries as e_queries
from .groceries import pipeline as g_pipeline, queries as g_queries
from .pipeline import clean, ingest
from .professionals import pipeline as p_pipeline, queries as p_queries
from .salons import pipeline as s_pipeline, queries as s_queries
from .services import pipeline as sv_pipeline, queries as sv_queries
from .studios import pipeline as st_pipeline, queries as st_queries
from .sweets import pipeline as sw_pipeline, queries as sw_queries
from .temples import pipeline as t_pipeline, queries as t_queries
# Phase-2 verticals (legal / education / real estate / finance).
from .education import pipeline as ed_pipeline, queries as ed_queries
from .finance import pipeline as fi_pipeline, queries as fi_queries
from .legal import pipeline as lg_pipeline, queries as lg_queries
from .realestate import pipeline as re_pipeline, queries as re_queries


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


def _update_event(existing: dict, diff: dict) -> None:
    e_pipeline._update(existing, {**existing, **diff}, diff)


def _update_apparel(existing: dict, diff: dict) -> None:
    ap_pipeline._update(existing, {**existing, **diff}, diff)


def _update_sweets(existing: dict, diff: dict) -> None:
    sw_pipeline._update(existing, {**existing, **diff}, diff)


def _update_studio(existing: dict, diff: dict) -> None:
    st_pipeline._update(existing, {**existing, **diff}, diff)


def _update_service(existing: dict, diff: dict) -> None:
    sv_pipeline._update(existing, {**existing, **diff}, diff)


def _update_community(existing: dict, diff: dict) -> None:
    co_pipeline._update(existing, {**existing, **diff}, diff)


def _update_legal(existing: dict, diff: dict) -> None:
    lg_pipeline._update(existing, {**existing, **diff}, diff)


def _update_education(existing: dict, diff: dict) -> None:
    ed_pipeline._update(existing, {**existing, **diff}, diff)


def _update_realestate(existing: dict, diff: dict) -> None:
    re_pipeline._update(existing, {**existing, **diff}, diff)


def _update_finance(existing: dict, diff: dict) -> None:
    fi_pipeline._update(existing, {**existing, **diff}, diff)


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
    "events": {
        "label": "Events", "table": "events", "queries": e_queries,
        "edit_fields": ["category", "organizer", "venue_name", "address_full", "city", "state",
                        "website", "phone", "email", "region_tag", "festival_specials"],
        "has_hours": False, "has_dietary": False, "update": _update_event,
        "supports_claims": False,
    },
    "apparel": {
        "label": "Apparel & Jewelry", "table": "apparel", "queries": ap_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "store_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_apparel,
        "supports_claims": False,
    },
    "sweets": {
        "label": "Sweets & Bakeries", "table": "sweets", "queries": sw_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "store_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": True, "update": _update_sweets,
        "supports_claims": False,
    },
    "studios": {
        "label": "Yoga & Dance Studios", "table": "studios", "queries": st_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "studio_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_studio,
        "supports_claims": False,
    },
    "services": {
        "label": "Community Services", "table": "services", "queries": sv_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "service_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_service,
        "supports_claims": False,
    },
    "community": {
        "label": "Community & Associations", "table": "community", "queries": co_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "org_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_community,
        "supports_claims": False,
    },
    "legal": {
        "label": "Immigration & Legal", "table": "legal", "queries": lg_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "legal_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_legal,
        "supports_claims": False,
    },
    "education": {
        "label": "Education & Tutoring", "table": "education", "queries": ed_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "edu_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_education,
        "supports_claims": False,
    },
    "realestate": {
        "label": "Real Estate", "table": "realestate", "queries": re_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "realestate_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_realestate,
        "supports_claims": False,
    },
    "finance": {
        "label": "Finance & Tax", "table": "finance", "queries": fi_queries,
        "edit_fields": ["phone", "email", "website", "address_full", "city", "state",
                        "finance_type", "region_tag", "festival_specials"],
        "has_hours": True, "has_dietary": False, "update": _update_finance,
        "supports_claims": False,
    },
}


def get(vertical: str) -> dict[str, Any]:
    if vertical not in VERTICALS:
        raise ValueError(f"Unknown vertical '{vertical}'")
    return VERTICALS[vertical]


def _table(vertical: str) -> str:
    return get(vertical)["table"]


def backfill_coords(limit: int = 200) -> dict[str, Any]:
    """Forward-geocode existing active listings that have an address/city but no lat/lng, so they
    become sortable by distance ("near me"). Polite to Nominatim (1 req/s). Returns per-vertical
    counts. `limit` caps rows per vertical per run."""
    import time

    from . import geocode
    out: dict[str, Any] = {"total_filled": 0, "by_vertical": {}}
    for v in VERTICALS:
        try:
            rows = db.query(
                f"SELECT id, address_full, city, state FROM {_table(v)} "
                f"WHERE deleted_at IS NULL AND (lat IS NULL OR lng IS NULL) "
                f"AND (address_full IS NOT NULL OR city IS NOT NULL) LIMIT %s", [limit])
        except Exception:
            continue
        filled = 0
        for r in rows:
            pt = geocode.coords_for(r.get("address_full"), r.get("city"), r.get("state"))
            if pt:
                db.execute(f"UPDATE {_table(v)} SET lat = %s, lng = %s WHERE id = %s",
                           [pt[0], pt[1], r["id"]])
                filled += 1
            time.sleep(1.0)  # Nominatim usage policy: <= 1 request/second
        if rows:
            out["by_vertical"][v] = {"checked": len(rows), "filled": filled}
            out["total_filled"] += filled
    return out


def flagged_non_india(limit_per: int = 40) -> list[dict]:
    """Active listings whose NAME signals a NON-India-from-India 'Indian' — Native American / West
    Indian / brand homonyms (osm.is_excluded_name) — surfaced for one-click admin moderation."""
    from . import osm
    out: list[dict] = []
    for v in VERTICALS:
        try:
            rows = db.query(f"SELECT id, name, city, state FROM {_table(v)} "
                            f"WHERE deleted_at IS NULL AND is_active ORDER BY id DESC LIMIT 3000")
        except Exception:
            continue
        n = 0
        for r in rows:
            if osm.is_excluded_name(r["name"]):
                out.append({"vertical": v, "id": r["id"], "name": r["name"],
                            "city": r.get("city"), "state": r.get("state")})
                n += 1
                if n >= limit_per:
                    break
    return out


def purge_excluded(dry_run: bool = True) -> dict[str, Any]:
    """Find (and, unless dry_run, soft-delete) already-stored listings whose name signals a
    NON-India-diaspora 'Indian' — Native American / West Indian / brand homonyms (see
    osm.is_excluded_name). Soft-delete + deactivate is reversible (sets deleted_at + is_active)."""
    from . import osm
    out: dict[str, Any] = {"dry_run": dry_run, "by_vertical": {}, "total": 0}
    for v in VERTICALS:
        try:
            rows = db.query(f"SELECT id, name FROM {_table(v)} WHERE deleted_at IS NULL")
        except Exception:
            continue
        bad = [(r["id"], r["name"]) for r in rows if osm.is_excluded_name(r["name"])]
        if bad and not dry_run:
            db.execute(f"UPDATE {_table(v)} SET deleted_at = now(), is_active = false "
                       f"WHERE id = ANY(%s)", [[i for i, _ in bad]])
        if bad:
            out["by_vertical"][v] = {"matched": len(bad), "samples": [n for _, n in bad[:8]]}
            out["total"] += len(bad)
    return out


# ----------------------------------------- geographic guardrail: listings OUTSIDE the USA
# This directory is for India-from-India life *in the USA*; some scrapers (OSM/Wikidata/IRS)
# can bleed in records that are physically abroad. Detect them by location, not by name.
_US_REGION_CODES = clean._STATE_CODES | {"PR", "VI", "GU", "AS", "MP"}  # 50 states + DC + territories
_US_COUNTRY_NAMES = {"usa", "us", "u.s.", "u.s.a.", "united states",
                     "united states of america", "america"}
# Generous US lat/lng boxes (incl. AK, HI, territories). Rectangular, so it can't separate a
# border city from its neighbour — it only flags CLEARLY foreign coordinates. Country/state catch
# the rest. (lat_min, lat_max, lng_min, lng_max)
_US_BOXES = (
    (24.0, 49.6, -125.1, -66.7),     # contiguous US
    (51.0, 71.6, -180.0, -129.0),    # Alaska
    (51.0, 71.6, 172.0, 180.0),      # Aleutians (across the antimeridian)
    (18.5, 22.4, -160.6, -154.6),    # Hawaii
    (17.6, 18.6, -67.4, -64.5),      # Puerto Rico + US Virgin Islands
    (13.2, 20.6, 144.5, 146.2),      # Guam + Northern Mariana Islands
    (-14.6, -14.0, -171.2, -169.3),  # American Samoa
)


def _in_us_bbox(lat: float, lng: float) -> bool:
    return any(a <= lat <= b and c <= lng <= d for a, b, c, d in _US_BOXES)


# Major Indian cities (incl. Telugu-belt towns + common spelling variants), stored as
# clean.normalize_name() output (lowercase, ascii, single spaces). Used only when a listing has NO
# usable coordinates to confirm — a city literally named e.g. "Hyderabad" is almost certainly India
# even when the scraper defaulted country='USA'. Deliberately EXCLUDES names with notable US
# namesakes (Delhi CA/NY, Salem OR/MA, Madras OR, Aurora, Columbus...) to avoid false hits.
_INDIAN_CITIES = frozenset({
    "mumbai", "bombay", "navi mumbai", "new delhi", "hyderabad", "secunderabad", "bengaluru",
    "bangalore", "chennai", "kolkata", "calcutta", "pune", "poona", "ahmedabad", "surat", "jaipur",
    "lucknow", "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam", "vizag", "patna",
    "vadodara", "baroda", "ghaziabad", "ludhiana", "agra", "nashik", "faridabad", "meerut", "rajkot",
    "varanasi", "srinagar", "aurangabad", "dhanbad", "amritsar", "allahabad", "prayagraj", "ranchi",
    "howrah", "jabalpur", "gwalior", "coimbatore", "vijayawada", "jodhpur", "madurai", "raipur",
    "kota", "guwahati", "chandigarh", "mysuru", "mysore", "gurgaon", "gurugram", "noida",
    "tiruchirappalli", "trichy", "bhubaneswar", "kochi", "cochin", "thiruvananthapuram", "trivandrum",
    "warangal", "guntur", "nellore", "tirupati", "kakinada", "rajahmundry", "kurnool", "anantapur",
    "kadapa", "eluru", "ongole", "nizamabad", "karimnagar", "khammam", "mahbubnagar", "tenali",
    "chittoor", "bhimavaram", "machilipatnam", "srikakulam", "vizianagaram", "mangalore", "mangaluru",
    "hubli", "belgaum", "kalaburagi", "gulbarga", "kolhapur", "solapur", "udaipur", "ajmer", "bikaner",
    "bareilly", "moradabad", "aligarh", "gorakhpur", "saharanpur", "jhansi", "ujjain", "jammu",
    "dehradun", "siliguri", "asansol", "durgapur", "tirunelveli", "vellore", "erode", "tiruppur",
    "jamshedpur", "bhilai", "cuttack", "kozhikode", "calicut", "thrissur", "kollam", "kannur",
    "jalandhar", "kakinada", "proddatur", "adoni", "hindupur",
})


def _is_indian_city(city) -> bool:
    return bool(city) and clean.normalize_name(city) in _INDIAN_CITIES


def _non_usa_reason(country, state, lat, lng, city=None) -> tuple[str, str] | None:
    """If a listing looks physically outside the USA return ``(reason, confidence)`` where
    confidence is ``'high'`` (safe to auto-remove) or ``'review'`` (surface for a human), else
    ``None``. Order of trust: an explicit non-US *country* is the most deliberate signal (scrapers
    default to ``'USA'``, so a real foreign value came from the source) and wins even over a
    rectangular box that happens to contain a border city; then coordinates (authoritative when
    usable); then, with no coords to confirm, a *city in India* or a non-US *state* are softer
    'review' hints a human should eyeball."""
    c = (country or "").strip().lower()
    if c and c not in _US_COUNTRY_NAMES:
        return (f"country = '{country}'", "high")
    la = lo = None
    if lat is not None and lng is not None:
        try:
            la, lo = float(lat), float(lng)
        except (TypeError, ValueError):
            la = lo = None
    if la is not None and not (la == 0 and lo == 0):          # 0,0 = junk coords -> fall through
        return None if _in_us_bbox(la, lo) else (f"coords outside US ({la:.3f}, {lo:.3f})", "high")
    if _is_indian_city(city):
        return (f"city = '{city}' (city in India)", "review")
    st = clean.normalize_state(state)
    if st and st.strip().upper() not in _US_REGION_CODES:
        return (f"state = '{state}' (not a US state)", "review")
    return None


def _scan_non_usa(vertical: str, scan_limit: int | None = None) -> list[dict]:
    lim = f" LIMIT {int(scan_limit)}" if scan_limit else ""
    try:
        rows = db.query(
            f"SELECT id, name, city, state, country, lat, lng FROM {_table(vertical)} "
            f"WHERE deleted_at IS NULL AND is_active ORDER BY id DESC{lim}")
    except Exception:
        return []
    out: list[dict] = []
    for r in rows:
        hit = _non_usa_reason(r.get("country"), r.get("state"), r.get("lat"), r.get("lng"),
                              r.get("city"))
        if hit:
            reason, conf = hit
            out.append({"vertical": vertical, "id": r["id"], "name": r["name"],
                        "city": r.get("city"), "state": r.get("state"), "country": r.get("country"),
                        "reason": reason, "confidence": conf})
    return out


def flagged_non_usa(limit_per: int = 80) -> list[dict]:
    """Active listings that look physically OUTSIDE the USA (foreign scrape bleed) — surfaced for
    admin review. High-confidence first (foreign coords / explicit foreign country), then 'review'
    hints (a city in India, or a non-US state, with no coordinates to confirm)."""
    out: list[dict] = []
    for v in VERTICALS:
        hits = _scan_non_usa(v, scan_limit=3000)
        hits.sort(key=lambda x: 0 if x["confidence"] == "high" else 1)
        out.extend(hits[:limit_per])
    return out


def purge_non_usa(dry_run: bool = True) -> dict[str, Any]:
    """Find (and, unless dry_run, soft-delete) listings physically outside the USA. Only
    HIGH-confidence matches (coords outside the US, or an explicit non-US country) are removed;
    'review' hints (non-US state, no coords) are reported but never auto-deleted. Soft-delete sets
    deleted_at + is_active=false, so it is fully reversible."""
    out: dict[str, Any] = {"dry_run": dry_run, "by_vertical": {}, "total": 0, "needs_review": 0}
    for v in VERTICALS:
        hits = _scan_non_usa(v)
        high = [h for h in hits if h["confidence"] == "high"]
        review = [h for h in hits if h["confidence"] == "review"]
        if high and not dry_run:
            db.execute(f"UPDATE {_table(v)} SET deleted_at = now(), is_active = false "
                       f"WHERE id = ANY(%s)", [[h["id"] for h in high]])
        if high or review:
            out["by_vertical"][v] = {
                ("removed" if not dry_run else "matched"): len(high),
                "needs_review": len(review),
                "samples": [f"{h['name']} [{h['reason']}]" for h in high[:6]],
                "review_samples": [f"{h['name']} ({h.get('city')}) [{h['reason']}]"
                                   for h in review[:8]],
            }
            out["total"] += len(high)
            out["needs_review"] += len(review)
    return out


# --------------------------------------------- duplicate auto-merge (safe: physical-identity gated)
# Gap-fill these scalar columns on the survivor from its duplicates (only when the survivor's value
# is empty), and union these list columns across the whole cluster.
_MERGE_FILL = ("phone", "email", "website", "address_full", "lat", "lng", "photo_url",
               "menu_url", "price_range", "region_tag", "description")
_MERGE_UNION = ("tags", "languages", "dietary_tags")


def _host(url) -> str:
    try:
        h = urlparse(url or "").netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _near(a: dict, b: dict, tol: float = 0.0015) -> bool:   # ~150m
    try:
        return (abs(float(a["lat"]) - float(b["lat"])) <= tol
                and abs(float(a["lng"]) - float(b["lng"])) <= tol)
    except (TypeError, ValueError, KeyError):
        return False


def _same_place(a: dict, b: dict) -> bool:
    """Two same-name+city rows are the SAME physical place only if a strong identity matches (phone /
    website host / address / ~150m coords). This is what stops a chain's two branches from merging.
    If NEITHER row has any locating signal at all, same name+city is taken as a duplicate."""
    pa, pb = clean.normalize_phone(a.get("phone")), clean.normalize_phone(b.get("phone"))
    if pa and pa == pb:
        return True
    wa, wb = _host(a.get("website")), _host(b.get("website"))
    if wa and wa == wb:
        return True
    aa, ab = clean.normalize_name(a.get("address_full") or ""), clean.normalize_name(b.get("address_full") or "")
    if aa and aa == ab:
        return True
    if a.get("lat") is not None and b.get("lat") is not None and _near(a, b):
        return True
    a_has = bool(pa or wa or aa or a.get("lat") is not None)
    b_has = bool(pb or wb or ab or b.get("lat") is not None)
    return not a_has and not b_has


def _cluster(rows: list[dict]) -> list[list[dict]]:
    """Greedy single-link clustering of same-name+city rows into same-physical-place groups."""
    clusters: list[list[dict]] = []
    for r in rows:
        for cl in clusters:
            if any(_same_place(r, m) for m in cl):
                cl.append(r)
                break
        else:
            clusters.append([r])
    return [cl for cl in clusters if len(cl) > 1]


def _completeness(r: dict) -> int:
    return sum(1 for c in ("phone", "email", "website", "address_full", "lat", "photo_url",
                           "description") if r.get(c) not in (None, ""))


def _pick_survivor(cluster: list[dict]) -> dict:
    """Keep the best record: owner-claimed first, then highest confidence, most complete, lowest id."""
    return sorted(cluster, key=lambda r: (
        0 if r.get("is_claimed") else 1,
        -float(r.get("confidence_score") or 0),
        -_completeness(r),
        r["id"]))[0]


@functools.lru_cache(maxsize=None)
def _table_columns_cached(table: str) -> frozenset[str]:
    return frozenset(row["column_name"] for row in db.query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)))


def _table_columns(table: str) -> set[str]:
    """Cached forever per process: schema is static for the life of a running process (migrations
    apply before startup, not against a live server), and now that this is called on every page view
    (web/landing.py _listings, web/reviews.py _fetch — not just batch/agent code) an uncached
    information_schema hit per request would be wasteful. A transient DB error is NOT cached (lru_cache
    doesn't memoize a raised exception), so a retry can still succeed once the DB is back."""
    try:
        return set(_table_columns_cached(table))
    except Exception:
        return set()


def dedupe_listings(dry_run: bool = True) -> dict[str, Any]:
    """Merge duplicate listings (same name+city AND same physical place) into one: keep the best
    record, gap-fill its empty fields + union tags/languages from the rest, and soft-delete the
    others (reversible). dry_run=True only reports what would merge. Events are skipped."""
    from .pipeline.ingest import _adapt
    out: dict[str, Any] = {"dry_run": dry_run, "by_vertical": {}, "merged_groups": 0, "removed": 0}
    for v in VERTICALS:
        if v == "events":
            continue
        table = _table(v)
        try:
            groups = db.query(
                f"SELECT array_agg(id) AS ids FROM {table} "
                f"WHERE deleted_at IS NULL AND is_active AND name IS NOT NULL AND city IS NOT NULL "
                f"GROUP BY lower(name), lower(city) HAVING count(*) > 1")
        except Exception:
            continue
        cols = _table_columns(table)
        fill = [c for c in _MERGE_FILL if c in cols]
        union = [c for c in _MERGE_UNION if c in cols]
        vgroups = vremoved = 0
        samples: list[str] = []
        for g in groups:
            try:
                rows = db.query(f"SELECT * FROM {table} WHERE id = ANY(%s)", (g["ids"],))
            except Exception:
                continue
            for cluster in _cluster(rows):
                survivor = _pick_survivor(cluster)
                losers = [r for r in cluster if r["id"] != survivor["id"]]
                if not losers:
                    continue
                vgroups += 1
                vremoved += len(losers)
                if len(samples) < 6:
                    samples.append(f"{survivor['name']} ({survivor.get('city')}) ×{len(cluster)}")
                if dry_run:
                    continue
                sets, params = [], []
                for c in fill:
                    if survivor.get(c) in (None, ""):
                        val = next((r.get(c) for r in losers if r.get(c) not in (None, "")), None)
                        if val is not None:
                            sets.append(f"{c} = %s")
                            params.append(_adapt(val))  # defensive: _MERGE_FILL is scalar-only by
                            # design, but this guards against a JSONB column ever sneaking in (as
                            # happened once via a name collision) crashing the whole agent run.
                for c in union:
                    merged: list = []
                    for r in cluster:
                        for x in (r.get(c) or []):
                            if x not in merged:
                                merged.append(x)
                    if merged and merged != (survivor.get(c) or []):
                        sets.append(f"{c} = %s")
                        params.append(_adapt(merged))
                if sets:
                    sets.append("updated_at = now()")
                    db.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = %s",
                               params + [survivor["id"]])
                db.execute(f"UPDATE {table} SET deleted_at = now(), is_active = false, "
                           f"updated_at = now() WHERE id = ANY(%s)", ([r["id"] for r in losers],))
        if vgroups:
            out["by_vertical"][v] = {"merged_groups": vgroups, "removed": vremoved, "samples": samples}
            out["merged_groups"] += vgroups
            out["removed"] += vremoved
    return out


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
    allowed = set(cfg["edit_fields"]) | {"languages"} | ({"hours_json"} if cfg["has_hours"] else set()) \
        | ({"dietary_tags"} if cfg["has_dietary"] else set())
    from .pipeline.ingest import _normalize
    diff = {k: v for k, v in edits.items()
            if k in allowed and _normalize(existing.get(k)) != _normalize(v)}
    if not diff:
        return {"ok": True, "updated": 0}
    # A languages edit feeds the description (embedded for search) + the searchable language tags —
    # refresh both so search/display stay consistent and the row re-embeds. Tag refresh is surgical
    # (only the '*-speaking' tags) so OSM amenity/dish tags are preserved.
    if "languages" in diff:
        from . import describe, tags as tagmod
        merged = {**existing, **diff}
        new_desc = describe.describe(vertical, merged)
        if _normalize(existing.get("description")) != _normalize(new_desc):
            diff["description"] = new_desc
        kept = [t for t in (existing.get("tags") or []) if not str(t).endswith("-speaking")]
        new_tags = sorted(set(kept) | set(tagmod.language_tags(merged.get("languages"))))
        if _normalize(existing.get("tags")) != _normalize(new_tags):
            diff["tags"] = new_tags
    cfg["update"](existing, diff)
    return {"ok": True, "updated": len(diff), "fields": sorted(diff)}


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def create_record(vertical: str, data: dict, *, source: str = "admin",
                  confidence: float = 0.7) -> dict[str, Any]:
    """Create a canonical listing — the zero-noise way to add what OSM misses.

    Builds the same canonical shape scrapers produce (natural_key, description, tags, embedding),
    active immediately, tagged with its provenance (`source` -> source_name, e.g. 'admin',
    'submission', 'irs', 'consulate') and `confidence`. Events are excluded (they're agent-managed:
    admin only approves). Returns {ok, id} or {ok: False, error}.
    """
    cfg = get(vertical)
    if vertical == "events":
        return {"ok": False, "error": "events_are_agent_managed"}
    from . import describe, embeddings, tags as tagmod
    from .pipeline.ingest import _adapt
    table = cfg["table"]
    name = (data.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name_required"}
    from . import osm
    if osm.is_excluded_name(name):  # Native American / West Indian / brand homonyms — not us
        return {"ok": False, "error": "not_india_diaspora"}
    lat, lng = _to_float(data.get("lat")), _to_float(data.get("lng"))
    city, state = clean.fill_location((data.get("city") or "").strip() or None,
                                      (data.get("state") or "").strip() or None, lat, lng)
    # No coordinates given (typical for admin-adds / owner submissions)? Forward-geocode the
    # address so the listing is sortable by distance / appears in "near me".
    if lat is None or lng is None:
        from . import geocode
        pt = geocode.coords_for((data.get("address_full") or "").strip() or None, city, state)
        if pt:
            lat, lng = pt
    rec: dict[str, Any] = {
        "natural_key": clean.natural_key(name, lat, lng),
        "name": name,
        "address_full": (data.get("address_full") or "").strip() or None,
        "city": city, "state": state,
        "country": (data.get("country") or "USA").strip() or "USA",
        "lat": lat, "lng": lng,
        "phone": clean.normalize_phone(data.get("phone")),
        "email": (data.get("email") or "").strip().lower() or None,
        "website": (data.get("website") or "").strip() or None,
        "region_tag": (data.get("region_tag") or "").strip() or None,
        "festival_specials": (data.get("festival_specials") or "").strip() or None,
        "source_name": source, "source_id": f"{source}/{uuid.uuid4().hex[:12]}",
        "confidence_score": confidence, "is_active": True,
    }
    if cfg["has_hours"]:
        raw = (data.get("hours") or "").strip()
        rec["hours_json"] = clean._with_hours({"raw": raw}) if raw else None
    if cfg["has_dietary"]:
        rec["dietary_tags"] = data.get("dietary_tags") or []
    rec["languages"] = tagmod.parse_languages(data.get("languages"))
    for f in cfg["edit_fields"]:  # vertical-specific scalars (type column, speciality, ...)
        if f not in rec:
            v = data.get(f)
            rec[f] = (v.strip() or None) if isinstance(v, str) else v
    rec["description"] = describe.describe(vertical, rec)
    rec["tags"] = sorted(set(tagmod.extract(vertical, rec)) | set(tagmod.language_tags(rec["languages"])))

    if db.query_one(f"SELECT 1 AS x FROM {table} WHERE natural_key = %s", (rec["natural_key"],)):
        return {"ok": False, "error": "duplicate"}
    cols = {r["column_name"] for r in db.query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))}
    use = [k for k in rec if k in cols]
    row = db.query_one(
        f"INSERT INTO {table} ({', '.join(use)}, last_seen_at) "
        f"VALUES ({', '.join(['%s'] * len(use))}, now()) RETURNING id",
        [_adapt(rec[k]) for k in use])
    new_id = row["id"]
    if embeddings.enabled():
        db.execute(f"UPDATE {table} SET embedding = %s::vector WHERE id = %s",
                   (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(rec))), new_id))
    return {"ok": True, "id": new_id, "vertical": vertical}


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


# Admin's manual "merge these two into one" (below) — distinct from the auto-dedupe _MERGE_FILL
# above (line 428). Kept separate on purpose: this one goes through the vertical's `update` fn
# (which knows how to adapt JSONB columns like hours_json), while auto-dedupe writes raw SQL and
# must stick to plain scalar columns. A same-named constant here previously SHADOWED the one above,
# silently making auto-dedupe try (and fail) to gap-fill the JSONB hours_json column.
_ADMIN_MERGE_FILL = ["phone", "email", "website", "address_full", "region_tag",
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
        for f in _ADMIN_MERGE_FILL:
            if keeper.get(f) in (None, "", {}) and d.get(f) not in (None, "", {}) and f not in diff:
                diff[f] = d.get(f)
    if diff:
        get(vertical)["update"](keeper, diff)
    for did in drop_ids:
        set_deleted(vertical, did, True)
    return {"ok": True, "kept": keep_id, "dropped": list(drop_ids), "filled": sorted(diff)}


def search_all(query: str, city: str | None = None, state: str | None = None,
               limit: int = 20, lat: float | None = None, lng: float | None = None) -> dict[str, Any]:
    """Search every vertical at once and merge by the hybrid score (exact-match first, then
    relevance/proximity/freshness — see ranking.py).

    Each result is tagged with its `vertical`. Optional `lat`/`lng` enable proximity ranking.
    """
    from . import embeddings
    qvec = embeddings.to_vector_literal(embeddings.embed(query)) if embeddings.enabled() else None
    point = (lat, lng) if lat is not None and lng is not None else None

    merged: list[dict] = []
    ranking_mode = "trigram"
    for key, cfg in VERTICALS.items():
        fn = getattr(cfg["queries"], f"search_{key}_by_text", None)
        if fn is None:
            continue
        res = fn(query, city=city, state=state, limit=limit, point=point, precomputed_qvec=qvec)
        ranking_mode = res.get("ranking", ranking_mode)
        for r in res["results"]:
            r.setdefault("vertical", key)
            merged.append(r)
    # Hybrid-ranked verticals carry `score`; events (date-first) carry only `match_score`.
    merged.sort(key=lambda r: r.get("score", r.get("match_score") or 0.0), reverse=True)
    merged = merged[:limit]
    return {"count": len(merged), "query": query, "ranking": ranking_mode, "results": merged}


def featured_summary() -> dict[str, Any]:
    """Active (effective) featured counts per vertical — the live paid placements.

    Resilient to a not-yet-migrated table (counts it as 0) so the admin never 500s.
    """
    out, total = {}, 0
    for key in VERTICALS:
        try:
            row = db.query_one(
                f"SELECT count(*) AS n FROM {_table(key)} WHERE deleted_at IS NULL "
                f"AND is_featured AND (featured_until IS NULL OR featured_until > now())")
            out[key] = row["n"] if row else 0
        except Exception:
            out[key] = 0
        total += out[key]
    return {"by_vertical": out, "total": total}
