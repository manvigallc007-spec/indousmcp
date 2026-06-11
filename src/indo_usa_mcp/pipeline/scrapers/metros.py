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


# Dominant US state per metro, used to backfill `state` when a source omits it.
_METRO_STATE: dict[str, str] = {
    "bay_area": "CA",
    "dallas": "TX",
    "houston": "TX",
    "chicago": "IL",
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
