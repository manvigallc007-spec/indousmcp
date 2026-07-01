"""IRS Exempt-Organizations Business Master File -> Indian temples & community orgs (free).

The IRS publishes every US tax-exempt nonprofit as public-domain CSV files (eo1-eo4). We stream them
and keep ONLY clearly-Indian religious orgs (-> temples) and cultural/community orgs (-> community),
using a tight phrase filter (so "Indiana" / the surname "Jain" don't slip in). This fills coverage
that OSM/Wikidata miss — Hindu temples, gurdwaras, Jain centers, and Telugu/Tamil/Gujarati
associations nationwide. Public org data only, no PII. Records are added via verticals.create_record
(deduped); the admin can moderate any rare false positive.
"""

from __future__ import annotations

import csv
from typing import Any, Iterator

import httpx

from ... import verticals
from ...config import settings

_DEFAULT_URLS = [f"https://www.irs.gov/pub/irs-soi/eo{n}.csv" for n in (1, 2, 3, 4)]

# Tight, low-noise signals (mostly multi-word phrases). Order: religious first -> temples, else
# community. Keep phrases specific so "Indiana" / the surname "Jain" / "Indian" (Native American)
# don't slip in; the admin can still moderate a rare false positive.
_TEMPLE = (
    "hindu temple", "hindu mandir", " mandir", "shiva temple", "venkateswara", "balaji temple",
    "swaminarayan", "iskcon", "hare krishna", "sikh ", "gurdwara", "gurudwara", "khalsa", "nanaksar",
    "jain temple", "jain center", "jain society", "jain sangh", "jain samaj", "ganesh temple",
    "murugan temple", "ayyappa", "sanatan", "hindu society", "vishwa hindu", "hindu swayamsevak",
    "shirdi sai", "sai temple", "sathya sai", "shri swaminarayan", "baps", "datta", "durga temple",
    "hanuman temple", "lakshmi temple", "meenakshi", "radha krishna", "chinmaya", "arya samaj",
    "vedanta society", "ramakrishna", "sringeri", "hindu mandap", "brahma kumaris",
)
_COMMUNITY = (
    "india association", "indian association", "india community", "indian community",
    "telugu association", "telugu samajam", "tana ", "tamil sangam", "tamil association", "gujarati samaj",
    "kerala association", "kerala samajam", "malayalee", "malayali", "marathi mandal", "maharashtra mandal",
    "bengali association", "kannada koota", "kannada sangha", "punjabi cultural", "sindhi association",
    "odia society", "india cultural", "indian cultural", "bharatiya", "indo american", "indo-american",
    "india house", "sewa international", "hindu american", "telugu cultural", "tamil cultural",
    # students, professionals, chambers, heritage schools, seniors — all registered nonprofits.
    "indian students association", "indian student association", "physicians of indian origin",
    "association of physicians of indian", "indian medical association", "asian indian chamber",
    "indo-american chamber", "india chamber of commerce", "us india chamber",
    "hindu heritage", "balvihar", "telugu badi", "hindi vidyalaya", "india foundation",
    "indian foundation", "indian american", "asian indian", "hindu students",
)


def _classify(name: str) -> str | None:
    n = (name or "").lower()
    if any(s in n for s in _TEMPLE):
        return "temples"
    if any(s in n for s in _COMMUNITY):
        return "community"
    return None


def _iter_rows(url: str) -> Iterator[dict]:
    with httpx.stream("GET", url, follow_redirects=True,
                      headers={"User-Agent": settings.scraper_user_agent},
                      timeout=settings.scraper_timeout_seconds) as r:
        r.raise_for_status()
        reader = csv.reader(r.iter_lines())
        header = next(reader, None)
        if not header:
            return
        for vals in reader:
            if len(vals) >= len(header):
                yield dict(zip(header, vals))


def _payload(row: dict) -> dict:
    parts = [(row.get("STREET") or "").strip().title(), (row.get("CITY") or "").strip().title(),
             (row.get("STATE") or "").strip(), (row.get("ZIP") or "")[:5]]
    return {
        "name": (row.get("NAME") or "").strip().title(),
        "address_full": ", ".join(p for p in parts if p),
        "city": (row.get("CITY") or "").strip().title(),
        "state": (row.get("STATE") or "").strip(),
    }


def import_eo(urls: list[str] | None = None, limit: int | None = None) -> dict[str, Any]:
    """Stream the IRS nonprofit files, keep clearly-Indian temples/orgs, and add them (deduped)."""
    if urls is None:
        urls = [u.strip() for u in (settings.irs_eo_urls or "").split(",") if u.strip()] or _DEFAULT_URLS
    scanned = added = dups = 0
    by_vertical: dict[str, int] = {}
    errors: list[str] = []
    for url in urls:
        try:
            for row in _iter_rows(url):
                scanned += 1
                vertical = _classify(row.get("NAME", ""))
                if not vertical:
                    continue
                p = _payload(row)
                if not (p["name"] and p["city"] and p["state"]):
                    continue
                res = verticals.create_record(vertical, p)
                if res.get("ok"):
                    added += 1
                    by_vertical[vertical] = by_vertical.get(vertical, 0) + 1
                elif res.get("error") == "duplicate":
                    dups += 1
                if limit and added >= limit:
                    break
        except Exception as exc:
            errors.append(f"{url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
        if limit and added >= limit:
            break
    return {"scanned": scanned, "added": added, "duplicates": dups,
            "by_vertical": by_vertical, "errors": errors}
