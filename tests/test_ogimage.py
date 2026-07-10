"""Raster (PNG) social-share cards: render() output, the /og.png route, graceful fallback, and that
every shareable page now points og:image at a PNG (not the old SVG). SVG OG images don't render on
Facebook/LinkedIn/WhatsApp/X, so these are the regression guards for that fix. Real dev DB is used only
by the best-page test (ZZTEST rows, try/finally)."""

import re

from starlette.testclient import TestClient

from indo_usa_mcp import db
from indo_usa_mcp.web import ogimage
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_PNG = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------- render() produces real PNGs
def test_render_each_kind_is_png():
    for kind in ("home", "festival", "city", "movies"):
        b = ogimage.render(kind, name="Diwali", label="Restaurants", city="Plano", state="TX")
        assert b[:8] == _PNG and len(b) > 1000, kind


def test_render_unknown_kind_falls_back_to_home_card():
    assert ogimage.render("nonsense")[:8] == _PNG


def test_ascii_strips_emoji_and_devanagari_but_keeps_separators():
    out = ogimage._ascii("Happy Diwali! ✨ नमस्ते · food — fun")
    assert "✨" not in out and "न" not in out        # emoji + Devanagari dropped
    assert "·" in out and " - " in out               # middot kept; em-dash folded to hyphen
    assert "Happy Diwali!" in out


# --------------------------------------------------------------- /og.png route
def test_og_png_route_returns_png_for_every_kind():
    for path in ("/og.png",
                 "/og.png?kind=festival&name=Diwali",
                 "/og.png?kind=city&label=Restaurants&city=Plano&state=TX",
                 "/og.png?kind=movies"):
        r = _client.get(path)
        assert r.status_code == 200, path
        assert r.headers["content-type"] == "image/png", path
        assert r.content[:8] == _PNG, path


def test_og_png_unknown_kind_still_200_png():
    r = _client.get("/og.png?kind=../etc/passwd")
    assert r.status_code == 200 and r.content[:8] == _PNG


# --------------------------------------------------------------- graceful fallback (never a 500)
def test_render_falls_back_to_real_png_on_error(monkeypatch):
    monkeypatch.setattr(ogimage, "_draw_card",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("render boom")))
    out = ogimage.render("home")
    assert out[:8] == _PNG and out == ogimage._fallback()   # fallback is REAL PNG, never raw JPEG bytes


def test_route_never_500s_when_rendering_breaks(monkeypatch):
    from indo_usa_mcp.web import public
    public._og_png_cached.cache_clear()                # force a cache-miss so the patched failure runs
    monkeypatch.setattr(ogimage, "_draw_card",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("render boom")))
    try:
        r = _client.get("/og.png?kind=festival&name=Holi")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == _PNG                    # real PNG (transcoded fallback), not JPEG, not 500
    finally:
        public._og_png_cached.cache_clear()


def test_long_params_still_render_valid_png():
    # Clamped + hard-wrapped: an oversized no-space param must not overflow or error.
    r = _client.get("/og.png?kind=city&label=" + "A" * 500 + "&city=Plano&state=TX")
    assert r.status_code == 200 and r.content[:8] == _PNG


def test_festival_card_is_day_cached():
    a = _client.get("/og.png?kind=festival&name=Diwali").content
    b = _client.get("/og.png?kind=festival&name=Diwali").content
    assert a == b and a[:8] == _PNG                     # same-day requests return the cached card


# --------------------------------------------------------------- meta wiring across shareable pages
def _og_image(html: str) -> str:
    m = re.search(r'property="og:image" content="([^"]+)"', html)
    return m.group(1) if m else ""


def test_shareable_pages_point_og_image_at_png_not_svg():
    for path in ("/", "/explore", "/faq", "/festivals", "/movies"):
        r = _client.get(path)
        if r.status_code == 503:                       # chat home disabled in a barebones env -> skip
            continue
        html = r.text
        assert "/og.png" in _og_image(html), path      # raster card, not a listing photo or the old SVG
        assert "og-image.svg" not in html, path
        assert 'name="twitter:card" content="summary_large_image"' in html, path
        assert 'property="og:image:width" content="1200"' in html, path


def test_explore_no_longer_uses_small_summary_card():
    html = _client.get("/explore").text
    assert 'content="summary"' not in html             # was twitter:card=summary (tiny) -> now large
    assert _og_image(html).endswith("/og.png")


def test_best_page_uses_tailored_city_card(monkeypatch):
    import indo_usa_mcp.embeddings as emb
    monkeypatch.setattr(emb, "enabled", lambda: False)
    from indo_usa_mcp import verticals
    db.execute("DELETE FROM restaurants WHERE city = 'Zzogtown'")
    try:
        for i in range(3):
            verticals.create_record("restaurants",
                                    {"name": f"ZZOG Card {i}", "city": "Zzogtown", "state": "TX",
                                     "lat": 33.0, "lng": -96.7}, source="test")
        html = _client.get("/best/restaurants/tx/zzogtown").text
        assert "kind=city" in html and "Zzogtown" in _og_image(html)
    finally:
        db.execute("DELETE FROM restaurants WHERE city = 'Zzogtown'")
