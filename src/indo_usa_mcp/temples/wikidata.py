"""Wikidata importer for notable US Hindu temples, Sikh gurdwaras and Jain temples (CC0, no key).

Hindu temples are found by class (Q842402). Gurdwaras and Jain temples aren't reliably classed in
Wikidata, so they're matched by name (their labels always carry "Gurdwara"/"Jain temple"...).
Coordinates are required (filters out people / abstract items). City/state are filled from the
coordinates by the temple cleaner. Free/open, polite (one request per query, dedup across queries).
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from .. import osm as _osm
from ..config import settings

_ENDPOINT = "https://query.wikidata.org/sparql"

# Hindu temples (Q842402 + subclasses) in the USA (Q30) with coordinates.
_HINDU_SPARQL = """
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

# Gurdwaras + Jain temples by name (not consistently classed). Coords required keeps it to places.
_SIKH_JAIN_SPARQL = """
SELECT ?item ?itemLabel ?coord ?website ?phone WHERE {
  ?item wdt:P17 wd:Q30 ; wdt:P625 ?coord ; rdfs:label ?itemLabel .
  FILTER(LANG(?itemLabel) = "en")
  FILTER(CONTAINS(LCASE(?itemLabel), "gurdwara") || CONTAINS(LCASE(?itemLabel), "sikh temple")
         || CONTAINS(LCASE(?itemLabel), "jain temple") || CONTAINS(LCASE(?itemLabel), "jain center")
         || CONTAINS(LCASE(?itemLabel), "jain mandir") || CONTAINS(LCASE(?itemLabel), "jain society"))
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P1329 ?phone. }
}
LIMIT 500
"""


def _parse_point(point: str) -> tuple[float | None, float | None]:
    # "Point(-122.41 37.77)" -> (37.77, -122.41)
    try:
        inner = point[point.index("(") + 1 : point.index(")")]
        lng_s, lat_s = inner.split()
        return float(lat_s), float(lng_s)
    except (ValueError, IndexError):
        return None, None


def _religion_for(name: str) -> str:
    n = name.lower()
    if "gurdwara" in n or "sikh" in n:
        return "sikh"
    if "jain" in n:
        return "jain"
    return "hindu"


class WikidataTempleScraper:
    source_name = "wikidata"

    def __init__(self) -> None:
        self.last_error: str | None = None

    def scrape(self) -> Iterator[dict]:
        seen: set[str] = set()
        for sparql in (_HINDU_SPARQL, _SIKH_JAIN_SPARQL):
            for cand in self._run(sparql):
                if cand["source_id"] not in seen:
                    seen.add(cand["source_id"])
                    yield cand

    def _run(self, sparql: str) -> Iterator[dict]:
        time.sleep(1)  # politeness between queries
        try:
            r = httpx.get(_ENDPOINT, params={"query": sparql, "format": "json"},
                          headers={"User-Agent": settings.scraper_user_agent,
                                   "Accept": "application/sparql-results+json"},
                          timeout=settings.scraper_timeout_seconds)
            r.raise_for_status()
            bindings = r.json().get("results", {}).get("bindings", [])
        except Exception as exc:
            if self.last_error is None:
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
            "religion": _religion_for(name),
            "website": b.get("website", {}).get("value"),
            "phone": b.get("phone", {}).get("value"),
            "extra_tags": [],
        }
