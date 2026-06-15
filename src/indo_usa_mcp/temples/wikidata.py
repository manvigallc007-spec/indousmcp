"""Wikidata importer for notable US Hindu temples (CC0, free SPARQL — no key).

Complements OSM with notable, named temples (e.g. Malibu Hindu Temple, Hindu Temple of Greater
Chicago). Coverage is modest (~dozens) but high-quality and fully free/open. City/state are filled
from coordinates by the temple cleaner. Verified live: ~65 US Hindu temples with coordinates.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from .. import osm as _osm
from ..config import settings

_ENDPOINT = "https://query.wikidata.org/sparql"

# Hindu temples (Q842402 + subclasses) located in the USA (Q30) that carry coordinates.
_SPARQL = """
SELECT ?item ?itemLabel ?coord ?website ?phone WHERE {
  ?item wdt:P31/wdt:P279* wd:Q842402 .
  ?item wdt:P17 wd:Q30 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P1329 ?phone. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 1500
"""


def _parse_point(point: str) -> tuple[float | None, float | None]:
    # "Point(-122.41 37.77)" -> (37.77, -122.41)
    try:
        inner = point[point.index("(") + 1 : point.index(")")]
        lng_s, lat_s = inner.split()
        return float(lat_s), float(lng_s)
    except (ValueError, IndexError):
        return None, None


class WikidataTempleScraper:
    source_name = "wikidata"

    def __init__(self) -> None:
        self.last_error: str | None = None

    def scrape(self) -> Iterator[dict]:
        time.sleep(1)  # politeness
        try:
            r = httpx.get(_ENDPOINT, params={"query": _SPARQL, "format": "json"},
                          headers={"User-Agent": settings.scraper_user_agent,
                                   "Accept": "application/sparql-results+json"},
                          timeout=settings.scraper_timeout_seconds)
            r.raise_for_status()
            bindings = r.json().get("results", {}).get("bindings", [])
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return
        for b in bindings:
            cand = self._to_candidate(b)
            if cand is not None:
                yield cand

    def _to_candidate(self, b: dict) -> dict | None:
        name = b.get("itemLabel", {}).get("value")
        coord = b.get("coord", {}).get("value")
        if not name or not coord or _osm.is_excluded_name(name):
            return None
        lat, lng = _parse_point(coord)
        if lat is None:
            return None
        qid = b.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        return {
            "source_name": self.source_name,
            "source_url": b.get("item", {}).get("value"),
            "source_id": qid,
            "name": name,
            "lat": lat, "lng": lng,
            "country": "USA",
            "religion": "hindu",
            "website": b.get("website", {}).get("value"),
            "phone": b.get("phone", {}).get("value"),
            "extra_tags": [],
        }
