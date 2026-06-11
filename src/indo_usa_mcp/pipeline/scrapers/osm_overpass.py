"""OpenStreetMap Overpass scraper for Indian restaurants.

Public, ODbL-licensed, no login, ToS-safe. Queries nodes/ways tagged
``amenity=restaurant`` + ``cuisine~indian`` within a metro bounding box.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from ...config import settings
from .metros import bbox, state_for

# Overpass QL: restaurants whose cuisine tag contains "indian" (case-insensitive),
# as nodes, ways and relations, within the bbox. `out center` gives ways a point.
_QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  node["amenity"="restaurant"]["cuisine"~"indian",i]({s},{w},{n},{e});
  way["amenity"="restaurant"]["cuisine"~"indian",i]({s},{w},{n},{e});
  relation["amenity"="restaurant"]["cuisine"~"indian",i]({s},{w},{n},{e});
);
out center tags;
"""

# Nationwide: every Indian restaurant in the USA (admin area), no bbox. Larger + slower;
# meant for an occasional manual run, not the daily agent loop.
_USA_QUERY = """
[out:json][timeout:600];
area["ISO3166-1"="US"][admin_level=2]->.usa;
(
  node["amenity"="restaurant"]["cuisine"~"indian",i](area.usa);
  way["amenity"="restaurant"]["cuisine"~"indian",i](area.usa);
);
out center tags;
"""


class OverpassScraper:
    source_name = "osm_overpass"

    def scrape(self, region: str) -> Iterator[dict]:
        if region == "usa":
            query = _USA_QUERY
            read_timeout = 660
        else:
            s, w, n, e = bbox(region)
            query = _QUERY_TEMPLATE.format(
                timeout=settings.scraper_timeout_seconds, s=s, w=w, n=n, e=e
            )
            read_timeout = settings.scraper_timeout_seconds + 30
        # Politeness: single rate-limited request; Overpass throttles heavy use.
        time.sleep(1)
        resp = httpx.post(
            settings.overpass_url,
            data={"data": query},
            headers={"User-Agent": settings.scraper_user_agent},
            timeout=read_timeout,
        )
        resp.raise_for_status()
        for element in resp.json().get("elements", []):
            candidate = self._element_to_candidate(element, region)
            if candidate is not None:
                yield candidate

    def _element_to_candidate(self, element: dict, region: str) -> dict | None:
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            return None

        # Nodes carry lat/lon directly; ways/relations carry a computed "center".
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lng = element.get("lon") or element.get("center", {}).get("lon")

        address_full = self._build_address(tags)
        osm_id = f"{element.get('type')}/{element.get('id')}"

        return {
            "source_name": self.source_name,
            "source_url": f"https://www.openstreetmap.org/{osm_id}",
            "source_id": osm_id,
            "name": name,
            "address_full": address_full,
            "city": tags.get("addr:city"),
            # Fall back to the metro's state when OSM omits addr:state.
            "state": tags.get("addr:state") or state_for(region, lat, lng),
            "country": "USA",
            "lat": lat,
            "lng": lng,
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "email": tags.get("email") or tags.get("contact:email"),
            "website": tags.get("website") or tags.get("contact:website"),
            "menu_url": tags.get("menu") or tags.get("website:menu"),
            "hours_json": {"raw": tags["opening_hours"]} if tags.get("opening_hours") else None,
            "cuisine_type": tags.get("cuisine", "indian").replace(";", ", "),
            "dietary_tags": self._dietary_from_tags(tags),
        }

    @staticmethod
    def _build_address(tags: dict) -> str | None:
        parts = [
            " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
            tags.get("addr:city"),
            tags.get("addr:state"),
            tags.get("addr:postcode"),
        ]
        joined = ", ".join(p for p in parts if p)
        return joined or None

    @staticmethod
    def _dietary_from_tags(tags: dict) -> list[str]:
        out: list[str] = []
        if tags.get("diet:vegetarian") in ("yes", "only"):
            out.append("vegetarian")
        if tags.get("diet:vegan") in ("yes", "only"):
            out.append("vegan")
        if tags.get("diet:halal") in ("yes", "only"):
            out.append("halal")
        return out
