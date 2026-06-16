"""Bounding boxes for Phase-1 high-density metros (south, west, north, east).

Coordinates are approximate metro-area envelopes, kept deliberately generous.
"""

from __future__ import annotations

# (south_lat, west_lng, north_lat, east_lng)
METROS: dict[str, tuple[float, float, float, float]] = {
    # Phase-1 high-density metros
    "bay_area": (37.20, -122.55, 38.10, -121.75),
    "nyc_nj": (40.49, -74.30, 40.92, -73.70),
    "dallas": (32.55, -97.05, 33.05, -96.55),
    "houston": (29.50, -95.70, 30.10, -95.10),
    "chicago": (41.65, -87.95, 42.10, -87.50),
    # Secondary metros (diaspora hubs)
    "los_angeles": (33.70, -118.55, 34.30, -117.85),
    "seattle": (47.40, -122.45, 47.78, -122.10),
    "atlanta": (33.55, -84.55, 34.05, -84.10),
    "phoenix": (33.25, -112.35, 33.75, -111.65),
    "austin": (30.10, -97.95, 30.50, -97.55),
    "boston": (42.25, -71.20, 42.45, -70.95),
    "philadelphia": (39.85, -75.30, 40.15, -74.95),
    "raleigh": (35.70, -78.80, 35.95, -78.50),
    "detroit": (42.20, -83.35, 42.55, -82.90),
    "central_nj": (40.40, -74.55, 40.70, -74.20),
    # Additional diaspora hubs (broaden coverage). DC-area is split into NoVA + suburban MD so the
    # state backfill stays single-state (the actual Indian hubs are Fairfax/Loudoun + Montgomery Co.).
    "northern_virginia": (38.60, -77.70, 39.12, -77.00),
    "suburban_maryland": (38.85, -77.35, 39.25, -76.80),
    "sacramento": (38.35, -121.65, 38.85, -121.05),
    "minneapolis": (44.70, -93.55, 45.15, -92.90),
    "san_diego": (32.53, -117.40, 33.18, -116.90),
    "denver": (39.55, -105.20, 39.95, -104.70),
    "tampa": (27.70, -82.75, 28.20, -82.25),
    "orlando": (28.25, -81.65, 28.85, -81.15),
    "charlotte": (35.05, -81.05, 35.45, -80.60),
    "columbus": (39.85, -83.20, 40.20, -82.80),
    "portland": (45.35, -123.00, 45.65, -122.45),
    "las_vegas": (35.95, -115.35, 36.35, -114.95),
    "hartford": (41.55, -72.90, 41.90, -72.45),
    # Batch 3 — more diaspora hubs (single-state envelopes)
    "san_antonio": (29.20, -98.75, 29.65, -98.25),
    "miami": (25.55, -80.45, 26.40, -80.05),       # Miami-Dade + Broward (Davie/Pembroke Pines)
    "nashville": (35.95, -87.05, 36.40, -86.55),
    "indianapolis": (39.55, -86.40, 39.95, -85.90),
    "cleveland": (41.35, -81.95, 41.65, -81.45),
    "cincinnati": (39.00, -84.75, 39.30, -84.30),
    "pittsburgh": (40.30, -80.20, 40.60, -79.75),
    "overland_park": (38.85, -94.85, 39.10, -94.55),   # KC's Indian hub is on the KS side
    "st_louis": (38.50, -90.45, 38.80, -90.10),
    "milwaukee": (42.90, -88.10, 43.20, -87.85),
    "salt_lake_city": (40.50, -112.10, 40.90, -111.75),
    "richmond": (37.40, -77.65, 37.70, -77.25),
    "long_island": (40.60, -73.75, 40.95, -72.85),     # Nassau + Suffolk, NY
    "orange_county": (33.55, -118.10, 33.95, -117.60),  # Irvine/Anaheim, CA
    "inland_empire": (33.75, -117.65, 34.20, -117.10),  # Riverside/San Bernardino, CA
}


# Valid scrape regions: each metro, plus "usa" for an occasional nationwide sweep.
SCRAPE_REGIONS: list[str] = sorted(METROS) + ["usa"]

# The densest diaspora metros — always scraped each run so they stay fresh; the rest rotate.
_PRIORITY = ("nyc_nj", "bay_area", "central_nj", "chicago", "dallas", "houston", "atlanta",
             "los_angeles", "northern_virginia", "seattle")


def scrape_set(per_run: int = 22) -> list[str]:
    """A rotating batch of metros so a single run never hammers the free APIs with all 40+ at once.
    Priority metros are always included; the rest cycle (full coverage over a couple of runs)."""
    import datetime
    keys = list(METROS)
    if len(keys) <= per_run:
        return keys
    now = datetime.datetime.utcnow()
    idx = now.timetuple().tm_yday * 24 + now.hour          # advances each hour -> new ground per run
    start = (idx * per_run) % len(keys)
    batch = {keys[(start + i) % len(keys)] for i in range(per_run)}
    batch.update(m for m in _PRIORITY if m in METROS)
    return [m for m in keys if m in batch]                 # keep METROS order (deterministic)


def bbox(metro: str) -> tuple[float, float, float, float]:
    try:
        return METROS[metro]
    except KeyError:
        raise ValueError(
            f"Unknown metro '{metro}'. Known: {', '.join(sorted(METROS))}"
        ) from None


# Dominant US state per metro, used to backfill `state` when a source omits it.
_METRO_STATE: dict[str, str] = {
    "bay_area": "CA",
    "dallas": "TX",
    "houston": "TX",
    "chicago": "IL",
    "los_angeles": "CA",
    "seattle": "WA",
    "atlanta": "GA",
    "phoenix": "AZ",
    "austin": "TX",
    "boston": "MA",
    "philadelphia": "PA",
    "raleigh": "NC",
    "detroit": "MI",
    "central_nj": "NJ",
    "northern_virginia": "VA",
    "suburban_maryland": "MD",
    "sacramento": "CA",
    "minneapolis": "MN",
    "san_diego": "CA",
    "denver": "CO",
    "tampa": "FL",
    "orlando": "FL",
    "charlotte": "NC",
    "columbus": "OH",
    "portland": "OR",
    "las_vegas": "NV",
    "hartford": "CT",
    "san_antonio": "TX",
    "miami": "FL",
    "nashville": "TN",
    "indianapolis": "IN",
    "cleveland": "OH",
    "cincinnati": "OH",
    "pittsburgh": "PA",
    "overland_park": "KS",
    "st_louis": "MO",
    "milwaukee": "WI",
    "salt_lake_city": "UT",
    "richmond": "VA",
    "long_island": "NY",
    "orange_county": "CA",
    "inland_empire": "CA",
}


def state_for(metro: str, lat: float | None = None, lng: float | None = None) -> str | None:
    """Best-effort state for a point within a metro (used only when the source lacks it).

    The NYC/NJ metro straddles two states, so it's split at the Hudson River
    (longitude ~ -74.02): west of it is NJ, east is NY.
    """
    if metro == "nyc_nj":
        if lng is None:
            return None
        return "NJ" if lng < -74.02 else "NY"
    return _METRO_STATE.get(metro)
