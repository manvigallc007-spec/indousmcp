"""Bounding boxes for Phase-1 high-density metros (south, west, north, east).

Coordinates are approximate metro-area envelopes, kept deliberately generous.
"""

from __future__ import annotations

# (south_lat, west_lng, north_lat, east_lng)
METROS: dict[str, tuple[float, float, float, float]] = {
    "bay_area": (37.20, -122.55, 38.10, -121.75),
    "nyc_nj": (40.49, -74.30, 40.92, -73.70),
    "dallas": (32.55, -97.05, 33.05, -96.55),
    "houston": (29.50, -95.70, 30.10, -95.10),
    "chicago": (41.65, -87.95, 42.10, -87.50),
}


def bbox(metro: str) -> tuple[float, float, float, float]:
    try:
        return METROS[metro]
    except KeyError:
        raise ValueError(
            f"Unknown metro '{metro}'. Known: {', '.join(sorted(METROS))}"
        ) from None
