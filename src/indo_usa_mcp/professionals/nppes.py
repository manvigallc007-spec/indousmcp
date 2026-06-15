"""NPPES NPI Registry scraper for Indian-American healthcare professionals.

The CMS National Provider Identifier registry is a FREE, public US-government API (no key) listing
every provider's name, specialty (taxonomy), and practice address. We query it by common Indian
surnames within a state and map each provider into a professionals candidate — far more complete
and authoritative than OSM for doctors/dentists/clinics. Public professional/business info only.

NPPES doesn't return coordinates, so these land with city/state but no lat/lng; run `backfill-geo`
afterward to geocode them for distance ranking.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

from ..config import settings

# Common Indian surnames used to find diaspora providers (NPPES has no ethnicity field). Curated
# for signal; admin curation handles the occasional non-Indian namesake.
_SURNAMES = [
    "Patel", "Shah", "Sharma", "Gupta", "Reddy", "Rao", "Desai", "Mehta", "Naidu", "Iyer", "Nair",
    "Menon", "Pillai", "Krishnan", "Bhatt", "Joshi", "Agarwal", "Verma", "Kapoor", "Malhotra",
    "Chopra", "Trivedi", "Parikh", "Amin", "Gandhi", "Goyal", "Bansal", "Jain", "Singh", "Sandhu",
    "Dhillon", "Chaudhary", "Subramanian", "Venkatesan", "Banerjee", "Mukherjee", "Chatterjee",
    "Pandey", "Mishra", "Tiwari", "Yadav", "Shetty", "Hegde", "Kaur", "Gill", "Prasad",
]


def _profession_type(desc: str | None) -> str:
    d = (desc or "").lower()
    if "dent" in d or "orthodont" in d:
        return "dentist"
    if "pharmac" in d:
        return "pharmacy"
    if "chiropract" in d:
        return "chiropractor"
    if "psych" in d or "counsel" in d or "therap" in d:
        return "counseling"
    return "doctor"


class NppesScraper:
    source_name = "nppes"

    def __init__(self) -> None:
        # First request failure reason (HTTP status / exception), surfaced by the pipeline so a
        # systemic problem — wrong host, blocked egress — is never again hidden as a silent "0".
        self.last_error: str | None = None

    def scrape(self, state: str, surnames: list[str] | None = None,
               limit_per: int = 200) -> Iterator[dict]:
        st = (state or "").strip().upper()[:2]
        if not st:
            return
        for sn in (surnames or _SURNAMES):
            try:
                r = httpx.get(settings.nppes_api_url,
                              params={"version": "2.1", "last_name": sn, "state": st,
                                      "enumeration_type": "NPI-1", "country_code": "US",
                                      "limit": limit_per},
                              headers={"User-Agent": settings.scraper_user_agent}, timeout=20.0)
                if r.status_code != 200:
                    if self.last_error is None:
                        self.last_error = f"HTTP {r.status_code} from {settings.nppes_api_url}"
                    results = []
                else:
                    results = r.json().get("results", []) or []
            except Exception as exc:
                if self.last_error is None:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                results = []
            for res in results:
                cand = self._to_candidate(res)
                if cand:
                    yield cand
            time.sleep(0.2)  # be polite to the public API

    def _to_candidate(self, res: dict) -> dict | None:
        npi = res.get("number")
        basic = res.get("basic", {}) or {}
        first = (basic.get("first_name") or "").strip().title()
        last = (basic.get("last_name") or "").strip().title()
        if not npi or not last:
            return None
        cred = (basic.get("credential") or "").strip().strip(".")
        name = f"{first} {last}".strip() + (f", {cred}" if cred else "")
        taxes = res.get("taxonomies", []) or []
        primary = next((t for t in taxes if t.get("primary")), taxes[0] if taxes else {})
        desc = primary.get("desc")
        addrs = res.get("addresses", []) or []
        loc = next((a for a in addrs if a.get("address_purpose") == "LOCATION"),
                   addrs[0] if addrs else {})
        city = (loc.get("city") or "").title() or None
        state = (loc.get("state") or "").strip() or None
        addr_full = ", ".join(p for p in [
            " ".join(x for x in (loc.get("address_1"), loc.get("address_2")) if x),
            city, state, (loc.get("postal_code") or "")[:5]] if p) or None
        return {
            "source_name": self.source_name,
            "source_url": f"https://npiregistry.cms.gov/provider-view/{npi}",
            "source_id": str(npi),
            "name": name,
            "address_full": addr_full,
            "city": city, "state": state, "country": "USA",
            "lat": None, "lng": None,
            "phone": loc.get("telephone_number"),
            "email": None, "website": None, "hours_json": None,
            "profession_type": _profession_type(desc),
            "speciality": desc,
            "extra_tags": [],
        }
