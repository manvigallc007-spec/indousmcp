"""OpenStreetMap Overpass scraper for Indian-American healthcare professionals.

Queries healthcare amenities (doctors/dentist/clinic/pharmacy) whose name carries a strong
Indian signal (common Indian surnames or India/Ayurveda). Public, ODbL, no login.
Heuristic name-matching => some noise; confidence scoring + admin curation handle it.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from .. import osm as _osm
from ..config import settings
from ..pipeline.scrapers.metros import bbox, state_for

_AMENITY = "doctors|dentist|clinic|pharmacy"
# Strong Indian-name signals (surnames + India/Ayurveda). Ambiguous ones omitted to cut noise.
_NAMES = ("Patel|Shah|Sharma|Gupta|Reddy|Rao|Desai|Mehta|Naidu|Iyer|Nair|Menon|Pillai|"
          "Krishnan|Subramani|Bhatt|Joshi|Agarwal|Agrawal|Verma|Kapoor|Malhotra|Chopra|"
          "Trivedi|Pandya|Parikh|Vyas|Amin|Gandhi|Chaudhar|Sethi|Goyal|Bansal|Jain|Singh|"
          "Sandhu|Dhillon|Ayurved|Indian|India ")

_QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  node["amenity"~"{amenity}"]["name"~"{names}",i]({s},{w},{n},{e});
  way["amenity"~"{amenity}"]["name"~"{names}",i]({s},{w},{n},{e});
  node["healthcare"]["name"~"{names}",i]({s},{w},{n},{e});
);
out center tags;
"""

_USA_QUERY = """
[out:json][timeout:600];
area["ISO3166-1"="US"][admin_level=2]->.usa;
(
  node["amenity"~"doctors|dentist|clinic"]["name"~"Patel|Shah|Reddy|Rao|Desai|Mehta|Iyer|Nair|Gupta|Sharma|Ayurved|Indian",i](area.usa);
  way["amenity"~"doctors|dentist|clinic"]["name"~"Patel|Shah|Reddy|Rao|Desai|Mehta|Iyer|Nair|Gupta|Sharma|Ayurved|Indian",i](area.usa);
);
out center tags;
"""


class ProfessionalOverpassScraper:
    source_name = "osm_overpass"

    def scrape(self, region: str) -> Iterator[dict]:
        if region == "usa":
            query, read_timeout = _USA_QUERY, 660
        else:
            s, w, n, e = bbox(region)
            query = _QUERY_TEMPLATE.format(
                timeout=settings.scraper_timeout_seconds, amenity=_AMENITY, names=_NAMES,
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
        ptype = (tags.get("amenity") or tags.get("healthcare") or "").lower() or None
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
            "profession_type": ptype,
            "speciality": tags.get("healthcare:speciality") or tags.get("speciality"),
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
