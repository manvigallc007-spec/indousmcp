"""Curated seed: Indian consular missions in the USA (embassy + consulates general).

Government offices that handle passports, visas, OCI cards, and document attestation for Indian
nationals and the diaspora — a small, stable, high-utility dataset. Seeded into the `services`
vertical (service_type='consulate'). Jurisdictions are described at the REGION level (accurate and
stable) rather than exact state lists, which have shifted (e.g. when the Seattle consulate opened);
passport/visa/OCI applications are processed through VFS Global — always confirm on the official site.
"""

from __future__ import annotations

from typing import Any

# name, city, state, official website, short regional jurisdiction.
CONSULATES: list[dict] = [
    {"name": "Embassy of India, Washington DC", "city": "Washington", "state": "DC",
     "website": "https://www.indianembassyusa.gov.in",
     "region": "the Washington DC area (DC, Maryland, Virginia) plus national embassy functions"},
    {"name": "Consulate General of India, New York", "city": "New York", "state": "NY",
     "website": "https://www.indiainnewyork.gov.in",
     "region": "the Northeastern US (New York, New Jersey, Pennsylvania, Ohio and New England)"},
    {"name": "Consulate General of India, San Francisco", "city": "San Francisco", "state": "CA",
     "website": "https://www.cgisf.gov.in",
     "region": "Northern California and the Western US"},
    {"name": "Consulate General of India, Chicago", "city": "Chicago", "state": "IL",
     "website": "https://www.cgichicago.gov.in",
     "region": "the Midwestern US"},
    {"name": "Consulate General of India, Houston", "city": "Houston", "state": "TX",
     "website": "https://www.cgihouston.gov.in",
     "region": "Texas and the south-central US"},
    {"name": "Consulate General of India, Atlanta", "city": "Atlanta", "state": "GA",
     "website": "https://www.indianconsulateatlanta.gov.in",
     "region": "the Southeastern US"},
    {"name": "Consulate General of India, Seattle", "city": "Seattle", "state": "WA",
     "website": "https://www.cgiseattle.gov.in",
     "region": "the Pacific Northwest"},
]


def _payload(c: dict) -> dict[str, Any]:
    return {
        "name": c["name"], "city": c["city"], "state": c["state"], "country": "USA",
        "website": c.get("website"), "service_type": "consulate", "region_tag": "Government",
        "description": (
            f"Indian government consular mission serving {c['region']}. Services: passport, visa, "
            "OCI card, and document attestation — passport/visa/OCI applications are processed "
            "through VFS Global. Confirm current hours, jurisdiction and appointments on the "
            "official website."),
    }


def seed() -> dict[str, Any]:
    """Upsert the consular missions into the services vertical (deduped)."""
    from . import verticals
    added = dups = 0
    for c in CONSULATES:
        res = verticals.create_record("services", _payload(c))
        if res.get("ok"):
            added += 1
        elif res.get("error") == "duplicate":
            dups += 1
    return {"consulates": len(CONSULATES), "added": added, "duplicates": dups}
