"""A dependency-free static map: OpenStreetMap raster tiles positioned as plain <img> elements with
listing pins overlaid via absolute CSS. No JavaScript and no external scripts, so it works under our
strict CSP (img-src allows https: tiles) and stays zero-budget. Tiles load lazily and only when the
user expands the map (<details>), keeping tile traffic light and respectful of the OSM tile policy.

Web-Mercator math (standard slippy-map): pick the highest zoom at which every listing fits the fixed
viewport, then lay the covering tiles and place each pin at its screen pixel.
"""

from __future__ import annotations

import html
import math

_W, _H = 640, 360          # tile-math viewport (px); the container is responsive but math uses this
_TILE = 256
_MAXZ = 16


def _lon2x(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * (2 ** z)


def _lat2y(lat: float, z: int) -> float:
    lat = max(min(lat, 85.05), -85.05)
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * (2 ** z)


def _fit_zoom(pts: list[tuple[float, float]]) -> int:
    if len(pts) == 1:
        return 14
    lats = [p[0] for p in pts]
    lngs = [p[1] for p in pts]
    for z in range(_MAXZ, 1, -1):
        xs = [_lon2x(x, z) * _TILE for x in lngs]
        ys = [_lat2y(y, z) * _TILE for y in lats]
        if (max(xs) - min(xs)) <= _W * 0.9 and (max(ys) - min(ys)) <= _H * 0.9:
            return z
    return 3


def render(rows: list[dict], vertical: str, *, title: str = "") -> str:
    """A collapsible static map of the given listings (those with coordinates). Empty string if none
    have coordinates. `rows` are the same dicts the listing cards use (need id, name, lat, lng)."""
    pts = [(float(r["lat"]), float(r["lng"]), r) for r in rows
           if r.get("lat") is not None and r.get("lng") is not None]
    if not pts:
        return ""
    z = _fit_zoom([(p[0], p[1]) for p in pts])
    clat = sum(p[0] for p in pts) / len(pts)
    clng = sum(p[1] for p in pts) / len(pts)
    cx, cy = _lon2x(clng, z) * _TILE, _lat2y(clat, z) * _TILE
    tlx, tly = cx - _W / 2, cy - _H / 2     # viewport top-left in world px

    # Covering tiles
    tiles = ""
    for tx in range(int(tlx // _TILE), int((tlx + _W) // _TILE) + 1):
        for ty in range(int(tly // _TILE), int((tly + _H) // _TILE) + 1):
            n = 2 ** z
            if tx < 0 or ty < 0 or tx >= n or ty >= n:
                continue
            sx, sy = tx * _TILE - tlx, ty * _TILE - tly
            tiles += (f"<img src='https://tile.openstreetmap.org/{z}/{tx}/{ty}.png' "
                      f"alt='' loading='lazy' style='position:absolute;left:{sx:.0f}px;top:{sy:.0f}px;"
                      f"width:{_TILE}px;height:{_TILE}px' width='{_TILE}' height='{_TILE}'>")

    # Pins (numbered to match the list order; cap so a huge city doesn't paint hundreds)
    pins = ""
    for i, (lat, lng, r) in enumerate(pts[:60], 1):
        px = _lon2x(lng, z) * _TILE - tlx
        py = _lat2y(lat, z) * _TILE - tly
        if px < -20 or px > _W + 20 or py < -30 or py > _H + 10:
            continue
        nm = html.escape(r.get("name") or "")
        pv = r.get("vertical") or vertical           # mixed-vertical result sets link each pin correctly
        pins += (f"<a href='/listing/{pv}/{r['id']}' title='{nm}' class='mpin' "
                 f"style='left:{px:.0f}px;top:{py:.0f}px'>{i}</a>")

    cap = html.escape(title or "Map of results")
    return (
        "<details class='mapwrap'><summary>🗺️ Show map</summary>"
        f"<div class='mapview' role='img' aria-label='{cap}'>"
        f"<div class='mapinner' style='width:{_W}px;height:{_H}px'>{tiles}{pins}</div></div>"
        "<div class='mapattr'>© <a href='https://www.openstreetmap.org/copyright' rel='nofollow'>"
        "OpenStreetMap</a> contributors</div></details>")


CSS = """
 .mapwrap{margin:6px 0 16px}
 .mapwrap summary{cursor:pointer;font-weight:600;color:#c1440e;list-style:none;padding:6px 0}
 .mapwrap summary::-webkit-details-marker{display:none}
 .mapview{overflow:auto;border:1px solid #e2e0dd;border-radius:12px;max-width:100%}
 .mapinner{position:relative;background:#e8eef2}
 .mpin{position:absolute;transform:translate(-50%,-100%);background:#c1440e;color:#fff;font-size:11px;
   font-weight:700;min-width:20px;height:20px;line-height:20px;text-align:center;border-radius:11px;
   border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4);padding:0 4px}
 .mpin:hover{background:#9a3409;z-index:5}
 .mapattr{font-size:11px;color:#98a2b3;margin-top:4px}
"""
