"""Importer for the operator's OWN caterbid.co restaurant directory (their data, same VPS).

This is NOT web scraping — caterbid.co runs on the same host, and our containers share its docker
network, so we read caterbid's Postgres directly (fast, legal — it's our data, repeatable). Each row
becomes a restaurant candidate tagged 'catering' (every caterbid business offers catering). All
South-Asian cuisines are kept (Indian, Pakistani, Bangladeshi, Nepali, Sri Lankan) — no exclusion
filter, since this is a curated, owned dataset.

Disabled until CATERBID_DATABASE_URL is set. If caterbid's schema differs from the default, set
CATERBID_QUERY (see config) to alias its columns to our field names.
"""

from __future__ import annotations

from typing import Iterator

from ...config import settings


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _s(v) -> str | None:
    s = str(v).strip() if v not in (None, "") else ""
    return s or None


class CaterbidScraper:
    source_name = "caterbid"

    def scrape(self, region: str) -> Iterator[dict]:  # region unused (DB import, not a metro)
        url = (settings.caterbid_database_url or "").strip()
        if not url:
            return  # disabled until configured — no-op
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(url, row_factory=dict_row, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute(settings.effective_caterbid_query)
                for row in cur:
                    cand = self._row_to_candidate(row)
                    if cand is not None:
                        yield cand

    def _row_to_candidate(self, row: dict) -> dict | None:
        name = _s(row.get("name"))
        if not name:
            return None
        site = (settings.caterbid_site_url or "").rstrip("/")
        return {
            "source_name": self.source_name,
            "source_url": site or None,
            "source_id": _s(row.get("source_id")) or name,
            "name": name,
            "address_full": _s(row.get("address_full")),
            "city": _s(row.get("city")),
            "state": _s(row.get("state")),
            "country": "USA",
            "lat": _f(row.get("lat")),
            "lng": _f(row.get("lng")),
            "phone": _s(row.get("phone")),
            "email": (_s(row.get("email")) or "").lower() or None,
            "website": _s(row.get("website")),
            "menu_url": _s(row.get("menu_url")),
            "hours_json": None,
            # default to "South Asian" so it reads sensibly when caterbid has no cuisine column
            "cuisine_type": _s(row.get("cuisine_type")) or "South Asian",
            "dietary_tags": [],
            # the "smartness": every caterbid business offers catering -> guaranteed catering tag
            "extra_tags": ["catering"],
        }
