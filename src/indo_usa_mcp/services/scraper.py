"""OpenStreetMap Overpass scraper for Indian community services.

Matches money-transfer/bank/travel/immigration/tax offices whose name signals an
India-focused service or Indian identity. Public, ODbL, no login. Noisy — admin curation
expected.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from .. import osm as _osm
from ..config import settings
from ..pipeline.scrapers.metros import bbox, state_for

# Core use case is remittance (heavily India/South-Asia corridor), so we keep the money-
# transfer category broad but require an Indian token for travel/legal (where bare "Travel/
# Visa" match everything). Avoid short fragments like "Desi" (matches "Design"). Admin curates.
_NAMES = ("Indian|India |Punjabi|Patel|Sharma|Gupta|Bharat|Hindustan|Apna|Khanna|"
          "Money Transfer|Money2India|Xpress Money|Ria Money|Remit|Remit2India|Swift Remit|"
          "Placid|Forex|Currency Exchange|Yatra|Akbar Travel|Riya Travel|Indo American|"
          "Indo-American")

# OSM keys hosting these services. Built per-bbox by _block().
_KEYS = [("amenity", "bank|bureau_de_change"),
         ("office", "financial|travel_agent|lawyer|tax_advisor|estate_agent|insurance|accountant"),
         ("shop", "travel_agency|money_lender")]


def _block(s, w, n, e) -> str:
    lines = []
    for key, vals in _KEYS:
        lines.append(f'  node["{key}"~"{vals}"]["name"~"{{names}}",i]({s},{w},{n},{e});')
        lines.append(f'  way["{key}"~"{vals}"]["name"~"{{names}}",i]({s},{w},{n},{e});')
    return "\n".join(lines)


_USA_QUERY = """
[out:json][timeout:600];
area["ISO3166-1"="US"][admin_level=2]->.usa;
(
  node["office"~"travel_agent|financial"]["name"~"Indian|Desi|India Travel|Yatra|Akbar|Money2India|Xpress Money",i](area.usa);
  node["amenity"="bureau_de_change"]["name"~"Indian|India|Remit|Money Transfer|Xpress Money|Ria Money",i](area.usa);
);
out center tags;
"""


class ServiceOverpassScraper:
    source_name = "osm_overpass"

    def scrape(self, region: str) -> Iterator[dict]:
        if region == "usa":
            query, read_timeout = _USA_QUERY, 660
        else:
            s, w, n, e = bbox(region)
            query = (f"[out:json][timeout:{settings.scraper_timeout_seconds}];\n(\n"
                     f"{_block(s, w, n, e).format(names=_NAMES)}\n);\nout center tags;\n")
            read_timeout = settings.scraper_timeout_seconds + 30
        time.sleep(1)  # politeness
        for element in _osm.overpass_post(query, read_timeout).get("elements", []):
            candidate = self._to_candidate(element, region)
            if candidate is not None:
                yield candidate

    def _to_candidate(self, element: dict, region: str) -> dict | None:
        tags = element.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name or _osm.is_excluded_name(name):
            return None
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lng = element.get("lon") or element.get("center", {}).get("lon")
        osm_id = f"{element.get('type')}/{element.get('id')}"
        return {
            "source_name": self.source_name,
            "source_url": f"https://www.openstreetmap.org/{osm_id}",
            "source_id": osm_id,
            "name": name,
            "address_full": self._address(tags),
            "city": tags.get("addr:city"),
            "state": tags.get("addr:state") or state_for(region, lat, lng),
            "country": "USA",
            "lat": lat,
            "lng": lng,
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "email": tags.get("email") or tags.get("contact:email"),
            "website": tags.get("website") or tags.get("contact:website"),
            "hours_json": {"raw": tags["opening_hours"]} if tags.get("opening_hours") else None,
            "service_type": tags.get("office") or tags.get("amenity") or tags.get("shop"),
            "extra_tags": _osm.attribute_tags(tags),
        }

    @staticmethod
    def _address(tags: dict) -> str | None:
        parts = [
            " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
            tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode"),
        ]
        joined = ", ".join(p for p in parts if p)
        return joined or None
