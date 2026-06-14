"""OpenStreetMap Overpass scraper for Indian apparel & jewelry stores.

Matches clothing/jewelry/fabric/tailor shops whose name signals South-Asian ethnic wear
(saree, lehenga, salwar, sherwani) or Indian jewelers/identity. Public, ODbL, no login.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from .. import osm as _osm
from ..config import settings
from ..pipeline.scrapers.metros import bbox, state_for

_SHOPS = "clothes|jewelry|fashion_accessories|fabric|tailor|boutique"
# Indian-specific signals only — generic "Gold/Jewel/Jeweler" match every pawn shop, so we
# require ethnic-wear words or known Indian jewelers/brands. Precision over recall; admin
# can still add missed Indian-owned stores by hand.
# NB: tokens are matched as unanchored substrings by Overpass, so avoid short fragments like
# "Desi" (matches "Design"/"Desire"). Use whole ethnic-wear words + known Indian brands.
_NAMES = ("Saree|Sari |Saris|Lehenga|Lehnga|Salwar|Kurta|Kurti|Sherwani|Anarkali|Dupatta|"
          "Ethnic Wear|Indian|Bollywood|Punjabi|Patel|Utsav|Kalamandir|Kalaniketan|"
          "Chandni Chowk|Meena Bazaar|Vastra|Pehnava|Rangoli|Cbazaar|Sari Palace|India Sari|"
          "Malabar Gold|Joyalukkas|Tanishq|Mangatrai|Zaveri|Khazana Jewel|Tibarumal|"
          "Lalitha Jewel|Sona Chandi")

_QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  node["shop"~"{shops}"]["name"~"{names}",i]({s},{w},{n},{e});
  way["shop"~"{shops}"]["name"~"{names}",i]({s},{w},{n},{e});
);
out center tags;
"""

_USA_QUERY = """
[out:json][timeout:600];
area["ISO3166-1"="US"][admin_level=2]->.usa;
(
  node["shop"~"clothes|jewelry|fabric|tailor"]["name"~"Saree|Sari|Lehenga|Salwar|Sherwani|Indian|Desi|Bridal Sari",i](area.usa);
  way["shop"~"clothes|jewelry|fabric|tailor"]["name"~"Saree|Sari|Lehenga|Salwar|Sherwani|Indian|Desi|Bridal Sari",i](area.usa);
);
out center tags;
"""


class ApparelOverpassScraper:
    source_name = "osm_overpass"

    def scrape(self, region: str) -> Iterator[dict]:
        if region == "usa":
            query, read_timeout = _USA_QUERY, 660
        else:
            s, w, n, e = bbox(region)
            query = _QUERY_TEMPLATE.format(
                timeout=settings.scraper_timeout_seconds, shops=_SHOPS, names=_NAMES,
                s=s, w=w, n=n, e=e)
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
            "store_type": tags.get("shop"),
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
