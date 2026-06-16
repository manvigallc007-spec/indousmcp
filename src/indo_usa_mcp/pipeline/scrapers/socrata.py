"""Socrata (city open-data, SODA API) importer for South-Asian restaurants.

Free, public-domain city datasets queried over the standard SODA JSON API. The best sources are
*cuisine-tagged* (e.g. NYC restaurant inspections carry cuisine_description='Indian'), so we pull
genuine South-Asian establishments with no name-guessing. Polite by design: server-side filtered
(we only fetch matching rows), paged with delays, modest page size, optional free X-App-Token.

Add a city by dropping a verified dataset into SOCRATA_SOURCES — no code change. v1 routes
restaurant datasets into restaurant_raw; grocery/service datasets can be added the same way later.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx
from psycopg.types.json import Jsonb

from ... import db, osm as _osm
from ...config import settings

# Distinctive Indian / South-Asian tokens for the name-match mode (used where a dataset has no
# cuisine field). Server-side SoQL `like`, so we only fetch matching rows. Kept specific to limit
# noise; the OSM exclusion filter + admin moderation catch the occasional false positive.
_NM_TOKENS = (
    "INDIA", "DESI", "MASALA", "TANDOOR", "BIRYANI", "BIRIYANI", "CURRY", "DOSA", "IDLI", "CHAAT",
    "PANEER", "SAMOSA", "TIKKA", "KARAHI", "KABAB", "PUNJAB", "BOMBAY", "MUMBAI", "DELHI", "CHENNAI",
    "MADRAS", "HYDERABAD", "KERALA", "AMRITSAR", "JAIPUR", "RAJASTHAN", "GUJARAT", "BHARAT",
    "MAHARAJA", "NAMASTE", "ZAIKA", "DHABA", "RASOI", "MIRCHI", "SWAGAT", "SWAAD", "HAVELI", "SITAR",
    "ANNAPURNA", "SARAVANA", "UDUPI", "GANESH", "KRISHNA", "BAWARCHI", "PARADISE BIRYANI", "TIFFIN",
)

# Verified city datasets. Each maps a dataset's columns to our restaurant candidate fields.
# Mode A (cuisine_col): server-filtered by a tagged cuisine (no name guessing). Mode B (name_match):
# server-filtered by Indian/South-Asian name tokens, for datasets without a cuisine field.
SOCRATA_SOURCES: dict[str, dict] = {
    # NYC DOHMH restaurant inspections — cuisine_description is tagged; verified live.
    "nyc_restaurants": {
        "domain": "data.cityofnewyork.us", "dataset": "43nn-pn8j", "vertical": "restaurants",
        "cuisine_col": "cuisine_description",
        "cuisines": ["Indian", "Bangladeshi", "Pakistani"],  # South-Asian per the diaspora scope
        "id_col": "camis", "name_col": "dba",
        "addr_cols": ["building", "street"], "city_col": "boro", "state": "NY",
        "zip_col": "zipcode", "phone_col": "phone", "lat_col": "latitude", "lng_col": "longitude",
    },
    # Chicago food inspections — no cuisine field, so name-match (restaurants only). Verified live.
    "chicago_restaurants": {
        "domain": "data.cityofchicago.org", "dataset": "4ijn-s7e5", "vertical": "restaurants",
        "name_match": True, "facility_filter": "facility_type='Restaurant'",
        "name_col": "dba_name", "addr_cols": ["address"], "city_col": "city", "state": "IL",
        "zip_col": "zip", "lat_col": "latitude", "lng_col": "longitude",
    },
    # San Francisco restaurant scores — no cuisine field, name-match. Verified live.
    "sf_restaurants": {
        "domain": "data.sfgov.org", "dataset": "pyih-qa8i", "vertical": "restaurants",
        "name_match": True,
        "name_col": "business_name", "addr_cols": ["business_address"], "city_col": "business_city",
        "state": "CA", "zip_col": "business_postal_code",
        "lat_col": "business_latitude", "lng_col": "business_longitude",
    },
}


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


class SocrataScraper:
    source_name = "socrata"  # stored provenance is socrata_<city>

    def __init__(self, source_key: str) -> None:
        if source_key not in SOCRATA_SOURCES:
            raise ValueError(f"Unknown Socrata source '{source_key}'")
        self.key = source_key
        self.cfg = SOCRATA_SOURCES[source_key]
        self.last_error: str | None = None

    def scrape(self, region: str = "") -> Iterator[dict]:
        cfg = self.cfg
        base = f"https://{cfg['domain']}/resource/{cfg['dataset']}.json"
        if cfg.get("name_match"):                          # filter by Indian/South-Asian name tokens
            col = cfg["name_col"]
            where = "(" + " OR ".join(f"upper({col}) like '%{t}%'" for t in _NM_TOKENS) + ")"
            if cfg.get("facility_filter"):
                where = f"{where} AND {cfg['facility_filter']}"
        else:                                              # filter by tagged cuisine (no name guessing)
            cuisines = "','".join(c.replace("'", "''") for c in cfg["cuisines"])
            where = f"{cfg['cuisine_col']} in('{cuisines}')"
        order = cfg.get("id_col") or cfg["name_col"]       # name_match datasets lack a stable id col
        headers = {"User-Agent": settings.scraper_user_agent}
        if settings.socrata_app_token.strip():
            headers["X-App-Token"] = settings.socrata_app_token.strip()
        seen: set[str] = set()
        offset, page = 0, 1000
        for _ in range(60):  # safety cap (60k rows); real South-Asian subsets are far smaller
            params = {"$where": where, "$limit": page, "$offset": offset, "$order": order}
            try:
                r = httpx.get(base, params=params, headers=headers, timeout=30.0)
                if r.status_code != 200:
                    if self.last_error is None:
                        self.last_error = f"HTTP {r.status_code} from {base}"
                    return
                rows = r.json()
            except Exception as exc:
                if self.last_error is None:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                return
            if not rows:
                return
            for row in rows:
                cand = self._to_candidate(row)
                if cand and cand["source_id"] not in seen:  # collapse multiple inspections/row
                    seen.add(cand["source_id"])
                    yield cand
            if len(rows) < page:
                return
            offset += page
            time.sleep(0.4)  # polite between pages

    def _to_candidate(self, row: dict) -> dict | None:
        cfg = self.cfg
        name = (str(row.get(cfg["name_col"]) or "")).strip().title()
        if not name or _osm.is_excluded_name(name):
            return None
        street = " ".join(str(row.get(c) or "").strip() for c in cfg["addr_cols"] if row.get(c)).strip()
        city = (str(row.get(cfg["city_col"]) or "")).strip().title() or None
        # name-match datasets lack a stable id -> dedupe by name+street across inspection rows
        rid = (str(row.get(cfg["id_col"]) or "").strip() if cfg.get("id_col") else "") \
            or f"{name}|{street[:40]}"
        zipc = (str(row.get(cfg.get("zip_col")) or "")).strip()
        addr_full = ", ".join(p for p in [street, city, cfg["state"], zipc] if p) or None
        lat, lng = _f(row.get(cfg.get("lat_col"))), _f(row.get(cfg.get("lng_col")))
        if lat == 0 and lng == 0:  # some portals use 0,0 for "unknown"
            lat = lng = None
        cuisine = "South Asian"
        if cfg.get("cuisine_col"):
            cuisine = (str(row.get(cfg["cuisine_col"]) or "")).strip() or "South Asian"
        return {
            "source_name": f"socrata_{self.key.split('_')[0]}",
            "source_url": f"https://{cfg['domain']}/resource/{cfg['dataset']}.json",
            "source_id": rid,
            "name": name,
            "address_full": addr_full,
            "city": city,
            "state": cfg["state"],
            "country": "USA",
            "lat": lat, "lng": lng,
            "phone": (str(row.get(cfg.get("phone_col")) or "")).strip() or None,
            "email": None, "website": None, "menu_url": None, "hours_json": None,
            "cuisine_type": cuisine,
            "dietary_tags": [],
            "extra_tags": [],
        }


def import_source(key: str) -> dict:
    """Pull one Socrata source into restaurant_raw (provenance source_name='socrata_<city>')."""
    cfg = SOCRATA_SOURCES.get(key)
    if cfg is None:
        return {"source": key, "error": "unknown_source"}
    if cfg["vertical"] != "restaurants":
        return {"source": key, "skipped": "only restaurants supported in v1"}
    scraper = SocrataScraper(key)
    count = 0
    for c in scraper.scrape():
        db.execute(
            "INSERT INTO restaurant_raw (source_name, source_url, source_id, payload) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source_name, source_id) "
            "DO UPDATE SET payload = EXCLUDED.payload, scraped_at = now(), "
            "processed = false, processed_at = NULL",
            (c["source_name"], c.get("source_url"), c.get("source_id"), Jsonb(c)),
        )
        count += 1
    return {"source": key, "upserted": count, "error": scraper.last_error}
