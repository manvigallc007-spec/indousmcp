"""Wikidata scraper for Indian restaurants in the USA.

Public, CC0-licensed SPARQL endpoint, no login. Coverage is sparse (mostly notable
chains/landmarks) but it's a fully independent second source that the Discovery and
Scraper agents can cross-reference against OSM.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from ... import osm as _osm
from ...config import settings
from .metros import bbox, state_for

_ENDPOINT = "https://query.wikidata.org/sparql"

# Restaurants (instance of Q11707 or subclass) that serve Indian cuisine (Q1751731),
# located in the USA (Q30), with coordinates. Coordinates let us bucket into metros.
_SPARQL = """
SELECT ?item ?itemLabel ?coord ?website ?phone WHERE {
  ?item wdt:P31/wdt:P279* wd:Q11707 .
  ?item wdt:P361|wdt:P1056 wd:Q1751731 .
  ?item wdt:P17 wd:Q30 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P1329 ?phone. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 500
"""


class WikidataScraper:
    source_name = "wikidata"

    def scrape(self, region: str) -> Iterator[dict]:
        # "usa" = nationwide (no bbox filter); otherwise restrict to the metro bbox.
        bbox_ = None if region == "usa" else bbox(region)
        time.sleep(1)  # politeness
        resp = httpx.get(
            _ENDPOINT,
            params={"query": _SPARQL, "format": "json"},
            headers={
                "User-Agent": settings.scraper_user_agent,
                "Accept": "application/sparql-results+json",
            },
            timeout=settings.scraper_timeout_seconds,
        )
        resp.raise_for_status()
        for binding in resp.json().get("results", {}).get("bindings", []):
            candidate = self._binding_to_candidate(binding, region, bbox_)
            if candidate is not None:
                yield candidate

    def _binding_to_candidate(self, b: dict, region: str, bbox_: tuple | None) -> dict | None:
        name = b.get("itemLabel", {}).get("value")
        coord = b.get("coord", {}).get("value")  # "Point(lng lat)"
        if not name or not coord or _osm.is_excluded_name(name):
            return None
        lat, lng = self._parse_point(coord)
        if lat is None:
            return None
        if bbox_ is not None:
            s, w, n, e = bbox_
            if not (s <= lat <= n and w <= lng <= e):
                return None  # outside the requested metro

        qid = b.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        return {
            "source_name": self.source_name,
            "source_url": b.get("item", {}).get("value"),
            "source_id": qid,
            "name": name,
            "lat": lat,
            "lng": lng,
            "state": state_for(region, lat, lng),
            "country": "USA",
            "website": b.get("website", {}).get("value"),
            "phone": b.get("phone", {}).get("value"),
            "cuisine_type": "Indian",
        }

    @staticmethod
    def _parse_point(point: str) -> tuple[float | None, float | None]:
        # "Point(-122.41 37.77)" -> (37.77, -122.41)
        try:
            inner = point[point.index("(") + 1 : point.index(")")]
            lng_s, lat_s = inner.split()
            return float(lat_s), float(lng_s)
        except (ValueError, IndexError):
            return None, None
