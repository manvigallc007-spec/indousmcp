"""The interactive map (web/mapview.py): rendering, pin data, and the tile-politeness contract.

OSM's tile usage policy is a courtesy, not a contract — abusing it gets the whole site blocked. The
tests here pin the three things that keep us inside it: tiles are only fetched once the visitor
opens the map, the zoom is capped, and attribution always renders. Real dev DB, ZZTEST rows.
"""

import json
import re

from starlette.testclient import TestClient

from indo_usa_mcp import db, verticals
from indo_usa_mcp.web import mapview
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_CITY = "Zzmapville"


def _mk(name, **over):
    rec = {"name": name, "city": _CITY, "state": "TX", "lat": 33.0, "lng": -96.7}
    rec.update(over)
    return verticals.create_record("restaurants", rec, source="test")["id"]


# ------------------------------------------------------------------ pure rendering (no DB)
def test_no_coordinates_renders_nothing():
    assert mapview.render([{"id": 1, "name": "A"}], "restaurants") == ""
    assert mapview.render([], "restaurants") == ""


def test_pins_carry_what_the_popup_needs():
    rows = [{"id": 7, "name": "Dosa Hut", "lat": 40.5, "lng": -74.4, "city": "Edison",
             "state": "NJ", "open_now": True, "community_rating": 4.3}]
    html = mapview.render(rows, "restaurants")
    cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*\})\)", html).group(1))
    pin = cfg["pins"][0]
    assert pin["id"] == 7 and pin["name"] == "Dosa Hut" and pin["v"] == "restaurants"
    assert pin["lat"] == 40.5 and pin["lng"] == -74.4
    assert pin["city"] == "Edison" and pin["open"] is True and pin["rating"] == 4.3
    assert pin["n"] == 1                                  # numbering matches the result list


def test_mixed_vertical_rows_keep_their_own_vertical():
    """search_all returns several verticals at once; each pin must deep-link to the right one."""
    rows = [{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0, "vertical": "temples"},
            {"id": 2, "name": "B", "lat": 1.1, "lng": 2.1}]
    cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*\})\)",
                               mapview.render(rows, "restaurants")).group(1))
    assert [p["v"] for p in cfg["pins"]] == ["temples", "restaurants"]


def test_pin_count_is_capped():
    rows = [{"id": i, "name": f"P{i}", "lat": 30 + i * 0.01, "lng": -96} for i in range(400)]
    cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*\})\)",
                               mapview.render(rows, "restaurants")).group(1))
    assert len(cfg["pins"]) == 200                        # _PIN_CAP, not 400 DOM nodes


def test_rows_without_coordinates_are_skipped_not_dropped_from_numbering():
    rows = [{"id": 1, "name": "no coords"},
            {"id": 2, "name": "has coords", "lat": 1.0, "lng": 2.0}]
    cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*\})\)",
                               mapview.render(rows, "restaurants")).group(1))
    assert len(cfg["pins"]) == 1 and cfg["pins"][0]["n"] == 2   # pin 2 == list item 2


def test_bounds_cover_every_pin():
    rows = [{"id": 1, "name": "A", "lat": 10.0, "lng": -20.0},
            {"id": 2, "name": "B", "lat": 12.0, "lng": -18.0}]
    cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*\})\)",
                               mapview.render(rows, "restaurants")).group(1))
    assert cfg["bounds"] == [10.0, -20.0, 12.0, -18.0]      # [minLat, minLng, maxLat, maxLng]


def test_script_cannot_be_broken_out_of():
    """A listing called '</script><script>…' must not escape the JSON blob."""
    rows = [{"id": 1, "name": "</script><script>alert(1)</script>", "lat": 1.0, "lng": 2.0}]
    html = mapview.render(rows, "restaurants")
    assert "</script><script>alert" not in html
    assert "<\\/script>" in html


def test_zoom_is_capped():
    assert mapview._MAX_Z <= 18        # deeper zooms multiply tile requests for no added value
    cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*\})\)",
                               mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}],
                                              "restaurants")).group(1))
    assert cfg["maxZ"] == mapview._MAX_Z


# ------------------------------------------------------------------ politeness + fallback
def test_map_starts_collapsed_so_no_tiles_are_fetched_unasked():
    html = mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}], "restaurants")
    assert "<details class='imap' >" in html or "<details class='imap'>" in html
    assert " open" not in html.split(">")[0]
    # and the client only initialises on the toggle
    assert "det.addEventListener('toggle'" in mapview.JS


def test_listing_page_map_is_open_because_where_is_it_is_the_question():
    html = mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}], "restaurants",
                          collapsed=False)
    assert "<details class='imap' open>" in html


def test_attribution_is_always_present():
    html = mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}], "restaurants")
    assert "openstreetmap.org/copyright" in html and "OpenStreetMap" in html


def test_noscript_falls_back_to_the_static_map():
    html = mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}], "restaurants")
    assert "<noscript>" in html and "tile.openstreetmap.org" in html.split("<noscript>")[1]


def test_no_third_party_script_is_loaded():
    """The whole point of hand-rolling this: it stays inside script-src 'self'."""
    html = mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}], "restaurants")
    assert "<script src=" not in html
    assert "unpkg" not in html and "cdn" not in html.lower()


# ------------------------------------------------------------------ wired into real pages
def test_browse_city_page_has_an_interactive_map():
    rid = _mk("ZZTEST Map Cafe")
    try:
        r = _client.get(f"/browse/restaurants/tx/{_CITY.lower()}")
        assert r.status_code == 200
        assert "class='imap'" in r.text and "naMap(" in r.text
        assert "imap-btn" in r.text                     # zoom / fit / locate controls
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_find_results_have_an_interactive_map():
    rid = _mk("ZZTEST Findable Cafe")
    try:
        r = _client.get("/find", params={"q": "ZZTEST Findable", "city": _CITY})
        assert r.status_code == 200 and "naMap(" in r.text
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_listing_page_has_a_single_pin_map():
    rid = _mk("ZZTEST Pinned Cafe")
    try:
        r = _client.get(f"/listing/restaurants/{rid}")
        assert r.status_code == 200 and "naMap(" in r.text
        cfg = json.loads(re.search(r"naMap\('m\d+',(\{.*?\})\)\</script\>", r.text).group(1))
        assert cfg["single"] is True and len(cfg["pins"]) == 1
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_client_script_is_shipped_once_per_page():
    rid = _mk("ZZTEST Once Cafe")
    try:
        t = _client.get(f"/browse/restaurants/tx/{_CITY.lower()}").text
        assert t.count("window.naMap=window.naMap||function") == 1
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# ------------------------------------------------------------------ interaction + a11y
def test_every_gesture_is_wired():
    for handler in ("pointerdown", "pointermove", "wheel", "dblclick", "touchstart", "touchmove"):
        assert handler in mapview.JS, f"{handler} is not handled"


def test_map_is_usable_without_a_pointer():
    assert "keydown" in mapview.JS and "ArrowLeft" in mapview.JS
    assert "box.tabIndex=0" in mapview.JS
    html = mapview.render([{"id": 1, "name": "A", "lat": 1.0, "lng": 2.0}], "restaurants")
    assert "aria-label='Zoom in'" in html and "aria-label='Fit all pins'" in html
    assert "role='application'" in html


def test_pins_are_buttons_with_accessible_names():
    assert "createElement('button')" in mapview.JS
    assert "setAttribute('aria-label',p.name" in mapview.JS


def test_popup_escapes_listing_text():
    """Pin data goes through textContent, not innerHTML, so a crafted name cannot inject."""
    assert "d.textContent=s" in mapview.JS and "function esc(s)" in mapview.JS
    assert "esc(p.name)" in mapview.JS


def test_offscreen_tiles_are_released():
    assert "live[k2].remove()" in mapview.JS      # not an unbounded cache


def test_tile_cache_is_keyed_by_unwrapped_column():
    """At low zoom a wide viewport can show the same world tile in two columns. Keying the cache by
    the wrapped x made both columns share one <img>, leaving one of them blank."""
    assert "k=z+'/'+tx+'/'+ty" in mapview.JS            # unwrapped key
    assert ".replace('{x}',wx)" in mapview.JS           # wrapped only in the request URL


def test_in_view_tiles_are_not_lazy_loaded():
    """Only in-view tiles are ever created, and lazy-loading a transformed element inside an
    overflow-hidden box can mean it never loads at all."""
    assert "loading='lazy'" not in mapview.JS
    assert "decoding='async'" in mapview.JS


def test_client_is_defined_before_any_map_calls_it():
    """Each map ships an inline naMap(...) call beside its own markup, so the definition must come
    earlier in the document. It was originally emitted at the end of <body>, which meant every map
    threw ReferenceError and rendered blank."""
    rid = _mk("ZZTEST Order Cafe")
    try:
        for path in (f"/browse/restaurants/tx/{_CITY.lower()}", f"/listing/restaurants/{rid}"):
            t = _client.get(path).text
            defn = t.find("window.naMap=window.naMap||function")
            call = t.find("naMap('m")
            assert defn != -1 and call != -1, f"{path} has no map"
            assert defn < call, f"{path} calls naMap before defining it"
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))

