"""OpenStreetMap Overpass scraper for Indian sweets & bakeries.

Matches confectionery/pastry/bakery shops whose name signals Indian sweets (mithai) or
South-Asian bakeries. Public, ODbL, no login.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from .. import osm as _osm
from ..config import settings
from ..pipeline.scrapers.metros import bbox, state_for

_SHOPS = "confectionery|pastry|bakery"
# Indian-specific only — bare "Sweet/Sweets" matches every candy shop (Sockerbit Swedish,
# Sweets & Such), and "Desi" substring-matches "Design"/"Desire". So we require mithai/dish
# words, known Indian sweet brands, or an "Indian/Desi Sweets" phrase. Precision over recall;
# admin can add Indian-owned shops with non-obvious names by hand.
_NAMES = ("Mithai|Mishtan|Misthan|Mishthan|Halwai|Indian Sweets|Desi Sweets|India Sweets|"
          "Bombay Sweets|Maharaja|Rajbhog|Aggarwal|Brijwasi|Nathu|Kailash|Janta|Chandni|"
          "Patel|Bikaner|Bikanervala|Haldiram|Royal Sweets|Nirala|Ambala|Sukhadia|Surati|"
          "Saravana|Grand Sweets|Annapurna|Anand Bhavan|Adyar|Mysore|Gulab Jamun|Jalebi|"
          "Rasmalai|Rasgulla|Rasagulla|Laddu|Ladoo|Barfi|Burfi|Kaju|Soan Papdi|Peda|"
          "Gujarat|Punjab")

# Indian sweets in OSM are mapped two ways, so we use two arms:
#   1) a confectionery/bakery shop with an Indian-specific NAME (above), and
#   2) an Indian-CUISINE eatery/shop named like a sweet/mithai shop (catches the many mithai
#      counters tagged as restaurants/cafes — where the name+cuisine together are safe).
_CUISINE = "indian|bangladeshi|pakistani|sri_lankan|south_asian|nepalese"
_SWEET_WORDS = "Sweet|Sweets|Mithai|Mishtan|Halwa|Halwai|Lassi|Namkeen|Chaat|Bakery|Kachori"


def _arms(s, w, n, e) -> str:
    lines = []
    for el in ("node", "way"):  # arm 1: sweet/bakery shop, Indian name
        lines.append(f'  {el}["shop"~"confectionery|pastry|bakery"]["name"~"{{names}}",i]({s},{w},{n},{e});')
    for el in ("node", "way"):  # arm 2: Indian-cuisine place named like a sweet shop
        lines.append(f'  {el}["cuisine"~"{_CUISINE}"]["name"~"{{sweets}}",i]({s},{w},{n},{e});')
    return "\n".join(lines)


_USA_QUERY = f"""
[out:json][timeout:600];
area["ISO3166-1"="US"][admin_level=2]->.usa;
(
  node["shop"~"confectionery|pastry|bakery"]["name"~"Mithai|Indian Sweets|Bombay Sweets|Bikaner|Haldiram|Royal Sweets|Maharaja",i](area.usa);
  node["cuisine"~"{_CUISINE}"]["name"~"Sweets|Mithai|Halwa",i](area.usa);
);
out center tags;
"""


class SweetsOverpassScraper:
    source_name = "osm_overpass"

    def scrape(self, region: str) -> Iterator[dict]:
        if region == "usa":
            query, read_timeout = _USA_QUERY, 660
        else:
            s, w, n, e = bbox(region)
            query = (f"[out:json][timeout:{settings.scraper_timeout_seconds}];\n(\n"
                     f"{_arms(s, w, n, e).format(names=_NAMES, sweets=_SWEET_WORDS)}\n);\n"
                     f"out center tags;\n")
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
            "store_type": tags.get("shop") or "sweets",
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
