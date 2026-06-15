"""OpenStreetMap Overpass scraper for Indian-American real estate.

Matches real-estate offices (office=estate_agent) whose name signals an Indian-from-India agent
or agency (an Indian surname or explicit Indian marker). We require the Indian token (bare
"Realty"/"Homes" matches everything) to keep the India-diaspora guardrail tight. Public, ODbL,
no login. Sparse + noisy — admin curation / submissions expected.
"""

from __future__ import annotations

import time
from typing import Iterator

from .. import osm as _osm
from ..config import settings
from ..pipeline.scrapers.metros import bbox, state_for

# Indian-from-India name signal: common surnames + explicit Indian markers. Combined with
# office=estate_agent this yields Indian-name realtors/agencies.
_NAMES = ("Indian|India |Patel|Shah|Sharma|Gupta|Singh|Reddy|Desai|Mehta|Nair|Iyer|Khanna|"
          "Chopra|Malhotra|Agarwal|Aggarwal|Bhatia|Kapoor|Joshi|Verma|Pillai|Naidu|Bhatt|"
          "Trivedi|Saxena|Sinha|Chauhan|Bansal|Punjabi|Gujarati|Telugu|Tamil|Bharat|Hindustan|Desi Homes")
_KEYS = [("office", "estate_agent")]


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
  node["office"="estate_agent"]["name"~"Indian|India |Patel|Shah|Sharma|Gupta|Singh|Reddy|Desai|Khanna|Malhotra|Punjabi|Gujarati",i](area.usa);
  way["office"="estate_agent"]["name"~"Indian|India |Patel|Shah|Sharma|Gupta|Singh|Reddy|Desai|Khanna|Malhotra|Punjabi|Gujarati",i](area.usa);
);
out center tags;
"""


class RealEstateOverpassScraper:
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
            "realestate_type": tags.get("office") or "agent",
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
