"""OpenStreetMap Overpass scraper for Indian beauty salons.

Matches hairdresser/beauty shops whose name signals South-Asian beauty services
(threading, brow, henna/mehndi) or Indian identity/surnames. Public, ODbL, no login.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from ..config import settings
from ..pipeline.scrapers.metros import bbox, state_for

_SHOPS = "hairdresser|beauty"
# "threading" and "henna/mehndi" are near-exclusive South-Asian signals; plus Indian names.
_NAMES = ("Threading|Thread|Brow|Eyebrow|Henna|Mehndi|Mehendi|Indian|Desi|Bombay|Punjab|"
          "Patel|Shah|Sharma|Reddy|Iyer|Nair|Kaur|Sundari|Bollywood|Saheli|Sahara|Ziba|"
          "Tip ?and ?Toe|Glam India")

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
  node["shop"~"hairdresser|beauty"]["name"~"Threading|Brow|Eyebrow|Henna|Mehndi|Indian|Desi",i](area.usa);
  way["shop"~"hairdresser|beauty"]["name"~"Threading|Brow|Eyebrow|Henna|Mehndi|Indian|Desi",i](area.usa);
);
out center tags;
"""


class SalonOverpassScraper:
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
        resp = httpx.post(
            settings.overpass_url, data={"data": query},
            headers={"User-Agent": settings.scraper_user_agent}, timeout=read_timeout)
        resp.raise_for_status()
        for element in resp.json().get("elements", []):
            candidate = self._to_candidate(element, region)
            if candidate is not None:
                yield candidate

    def _to_candidate(self, element: dict, region: str) -> dict | None:
        tags = element.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name:
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
            "salon_type": tags.get("shop"),
        }

    @staticmethod
    def _address(tags: dict) -> str | None:
        parts = [
            " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
            tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode"),
        ]
        joined = ", ".join(p for p in parts if p)
        return joined or None
