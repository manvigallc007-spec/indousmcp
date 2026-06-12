"""Offline reverse geocoding: fill city/state from coordinates.

Uses the `reverse_geocoder` package (bundled GeoNames data, no network, free). Returns
the raw GeoNames city + admin1 (state name); callers normalize the state. Degrades to
(None, None) if the package isn't installed.
"""

from __future__ import annotations

_rg = None
_unavailable = False


def _geocoder():
    global _rg, _unavailable
    if _rg is None and not _unavailable:
        try:
            import reverse_geocoder  # noqa: lazy + heavy (loads a k-d tree on first use)
            _rg = reverse_geocoder
        except Exception:
            _unavailable = True
    return _rg


def city_state(lat, lng) -> tuple[str | None, str | None]:
    """Return (city, state_name) for a US coordinate, or (None, None) if unavailable."""
    if lat is None or lng is None:
        return (None, None)
    rg = _geocoder()
    if rg is None:
        return (None, None)
    try:
        r = rg.search([(float(lat), float(lng))], mode=1)[0]
        return (r.get("name") or None, r.get("admin1") or None)
    except Exception:
        return (None, None)
