"""Bounding boxes for Phase-1 high-density metros (south, west, north, east).

Coordinates are approximate metro-area envelopes, kept deliberately generous.
"""

from __future__ import annotations

# (south_lat, west_lng, north_lat, east_lng)
METROS: dict[str, tuple[float, float, float, float]] = {
    # Phase-1 high-density metros
    "bay_area": (37.15, -122.55, 38.15, -121.55),   # + Tracy/Mountain House (east)
    "nyc_nj": (40.49, -74.30, 40.92, -73.70),
    # Full DFW metroplex: Fort Worth/Arlington (west) + the dense northern Indian suburbs —
    # Irving, Plano, Richardson, Carrollton AND Frisco/McKinney/Allen/Prosper (north) + Rockwall (east).
    "dallas": (32.45, -97.50, 33.35, -96.40),
    "houston": (29.45, -95.90, 30.20, -95.05),     # + Katy (west) + The Woodlands/Spring (north)
    # Chicagoland incl. the western Indian belt — Naperville/Aurora (SW) + Schaumburg/Hoffman/Palatine (NW).
    "chicago": (41.55, -88.45, 42.25, -87.50),
    # Secondary metros (diaspora hubs)
    "los_angeles": (33.70, -118.55, 34.30, -117.85),
    "seattle": (47.30, -122.50, 47.85, -121.95),    # + Redmond/Sammamish/Issaquah (east) + Bothell (north)
    "atlanta": (33.45, -84.65, 34.25, -83.90),      # + Alpharetta/Cumming (north) + Johns Creek/Lawrenceville (east)
    "phoenix": (33.20, -112.35, 33.75, -111.60),    # + Chandler/Gilbert (southeast)
    "austin": (30.05, -98.05, 30.65, -97.50),       # + Round Rock/Cedar Park/Leander (north)
    "boston": (42.10, -71.70, 42.65, -70.80),       # + MetroWest (Framingham/Westborough/Shrewsbury) + Burlington/Lowell
    "philadelphia": (39.80, -75.65, 40.25, -74.90),  # + King of Prussia/Exton (west PA)
    "raleigh": (35.60, -79.05, 36.15, -78.45),      # + Morrisville/Cary/Apex + Durham/Chapel Hill
    "detroit": (42.10, -83.60, 42.70, -82.85),      # + Novi/Canton/Farmington/Northville (west) + Troy/Rochester (north)
    "central_nj": (40.25, -74.75, 40.92, -74.05),   # + Princeton (south) + Parsippany/Bridgewater/Somerset (north)
    # Additional diaspora hubs (broaden coverage). DC-area is split into NoVA + suburban MD so the
    # state backfill stays single-state (the actual Indian hubs are Fairfax/Loudoun + Montgomery Co.).
    "northern_virginia": (38.60, -77.70, 39.12, -77.00),
    "suburban_maryland": (38.80, -77.40, 39.35, -76.65),  # + Howard Co (Columbia/Ellicott City)
    "sacramento": (38.35, -121.65, 38.85, -121.05),
    "minneapolis": (44.65, -93.60, 45.25, -92.80),   # Eden Prairie/Maple Grove/Eagan/Woodbury edges
    "san_diego": (32.53, -117.40, 33.18, -116.90),
    "denver": (39.45, -105.30, 40.05, -104.60),    # + Boulder/Broomfield (N) + Parker/Castle Rock (S)
    "tampa": (27.65, -82.80, 28.45, -82.20),       # + Wesley Chapel/Land O'Lakes (north)
    "orlando": (28.25, -81.65, 28.85, -81.15),
    "charlotte": (35.00, -81.10, 35.60, -80.50),   # + Huntersville/Cornelius (Lake Norman) + Concord
    "columbus": (39.80, -83.35, 40.30, -82.70),    # + Dublin/Powell/Westerville/New Albany (north)
    "portland": (45.30, -123.10, 45.70, -122.40),  # + Hillsboro/Beaverton (west)
    "las_vegas": (35.95, -115.35, 36.35, -114.95),
    "hartford": (41.55, -72.90, 41.90, -72.45),
    # Batch 3 — more diaspora hubs (single-state envelopes)
    "san_antonio": (29.20, -98.75, 29.65, -98.25),
    "miami": (25.55, -80.45, 26.40, -80.05),       # Miami-Dade + Broward (Davie/Pembroke Pines)
    "nashville": (35.80, -87.10, 36.45, -86.35),   # + Franklin (S) + Murfreesboro/Smyrna (SE)
    "indianapolis": (39.55, -86.45, 40.10, -85.80),   # + Carmel/Westfield/Noblesville/Fishers (north hubs)
    "cleveland": (41.25, -82.05, 41.70, -81.35),   # + Solon/Twinsburg/Hudson (SE) + Westlake/Avon (W)
    "cincinnati": (39.00, -84.80, 39.45, -84.25),  # + Mason/West Chester/Liberty Twp (north hubs)
    "pittsburgh": (40.25, -80.25, 40.75, -79.65),  # + Cranberry/Wexford (N) + Monroeville/Murrysville (E)
    "overland_park": (38.85, -94.85, 39.10, -94.55),   # KC's Indian hub is on the KS side
    "st_louis": (38.45, -90.75, 38.90, -90.05),    # + Chesterfield/Ballwin/Wildwood (west hubs)
    "milwaukee": (42.85, -88.35, 43.25, -87.85),   # + Brookfield/Waukesha/New Berlin (W) + Mequon (N)
    "salt_lake_city": (40.30, -112.20, 40.95, -111.65),  # + Lehi/American Fork (Silicon Slopes, south)
    "richmond": (37.40, -77.65, 37.70, -77.25),
    "long_island": (40.60, -73.75, 40.95, -72.85),     # Nassau + Suffolk, NY
    "orange_county": (33.55, -118.10, 33.95, -117.60),  # Irvine/Anaheim, CA
    "inland_empire": (33.70, -117.85, 34.20, -117.05),  # + Chino Hills/Chino/Eastvale (W); Riverside/San Bernardino, CA
    # Batch 4 — Central Valley (big Punjabi/Sikh community), university towns (large Indian grad
    # populations), and additional mid-size diaspora/professional hubs.
    "fresno": (36.65, -119.92, 36.92, -119.62),         # + Clovis, CA
    "stockton": (37.85, -121.45, 38.05, -121.15),       # + Lodi/Manteca, CA (Sikh belt)
    "modesto": (37.55, -121.10, 37.75, -120.85),        # CA
    "bakersfield": (35.27, -119.18, 35.47, -118.85),    # CA
    "ann_arbor": (42.20, -83.83, 42.34, -83.66),        # MI (U-Michigan)
    "champaign": (40.05, -88.32, 40.17, -88.15),        # IL (UIUC)
    "west_lafayette": (40.38, -86.96, 40.49, -86.83),   # IN (Purdue)
    "college_station": (30.55, -96.40, 30.68, -96.23),  # TX (Texas A&M)
    "gainesville": (29.58, -82.42, 29.72, -82.25),      # FL (UF)
    "madison": (42.95, -89.56, 43.18, -89.24),          # WI (UW-Madison)
    "louisville": (38.15, -85.92, 38.35, -85.55),       # KY
    "memphis": (35.00, -90.20, 35.30, -89.75),          # TN
    "knoxville": (35.85, -84.10, 36.10, -83.75),        # TN
    "huntsville": (34.58, -86.75, 34.85, -86.45),       # AL (aerospace/engineering)
    "birmingham": (33.35, -86.95, 33.65, -86.60),       # AL
    "oklahoma_city": (35.30, -97.70, 35.65, -97.30),    # OK
    "tulsa": (36.00, -96.15, 36.30, -95.75),            # OK
    "albuquerque": (34.95, -106.80, 35.25, -106.45),    # NM
    "tucson": (32.10, -111.10, 32.40, -110.75),         # AZ
    "omaha": (41.15, -96.15, 41.40, -95.85),            # NE
    "des_moines": (41.50, -93.80, 41.70, -93.50),       # IA
    "new_orleans": (29.85, -90.25, 30.10, -89.90),      # LA
    "greenville_sc": (34.75, -82.55, 34.95, -82.25),    # SC
    "greensboro": (35.95, -80.40, 36.18, -79.70),       # NC (Triad: Greensboro/Winston-Salem)
    "hampton_roads": (36.68, -76.42, 37.05, -75.95),    # VA (Norfolk/Virginia Beach)
    "dayton": (39.65, -84.35, 39.90, -84.05),           # OH
    "grand_rapids": (42.85, -85.82, 43.10, -85.50),     # MI
    "buffalo": (42.80, -79.00, 43.05, -78.65),          # NY
    "rochester_ny": (43.05, -77.80, 43.25, -77.45),     # NY
    "fort_myers": (26.40, -82.02, 26.70, -81.65),       # FL (+ Cape Coral)
    "wilmington_de": (39.65, -75.72, 39.85, -75.45),    # DE
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
    # Batch 4
    "fresno": "CA", "stockton": "CA", "modesto": "CA", "bakersfield": "CA",
    "ann_arbor": "MI", "champaign": "IL", "west_lafayette": "IN", "college_station": "TX",
    "gainesville": "FL", "madison": "WI", "louisville": "KY", "memphis": "TN", "knoxville": "TN",
    "huntsville": "AL", "birmingham": "AL", "oklahoma_city": "OK", "tulsa": "OK",
    "albuquerque": "NM", "tucson": "AZ", "omaha": "NE", "des_moines": "IA", "new_orleans": "LA",
    "greenville_sc": "SC", "greensboro": "NC", "hampton_roads": "VA", "dayton": "OH",
    "grand_rapids": "MI", "buffalo": "NY", "rochester_ny": "NY", "fort_myers": "FL",
    "wilmington_de": "DE",
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
