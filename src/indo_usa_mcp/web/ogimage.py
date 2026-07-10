"""Auto-generated raster (PNG) social-share cards.

SVG Open Graph images don't render on Facebook, LinkedIn, WhatsApp, iMessage or X — which is why a
shared namasteamerica.us link showed no preview image. This module renders branded 1200x630 PNG cards
with Pillow so every shared URL gets a compelling, on-brand preview, with a different card per context
(home / festival / city / movies).

Text is drawn with Pillow's built-in scalable font (`ImageFont.load_default(size=...)`, Pillow >=10.1).
That font can't render colour emoji or Devanagari, so all card text is passed through `_ascii()` first
(emoji/non-Latin stripped, smart punctuation folded to ASCII). The site's HTML keeps its emoji — only
the raster text is plain.

`render()` never raises: on any failure it falls back to the static square logo bytes, so the /og.png
route always returns a valid raster image (never a 500).
"""

from __future__ import annotations

import functools
import io
import pathlib

from ..config import settings

_STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

_W, _H = 1200, 630
_MARGIN = 72

# Brand palette — mirrors og_image() in public.py so the raster card matches the site.
_BG = (250, 248, 244)        # #faf8f4
_BAR_TOP = (232, 119, 46)    # #e8772e  brand orange
_BAR_BOT = (15, 155, 142)    # #0f9b8e  teal
_INK = (34, 43, 51)          # #222b33
_TEAL = (15, 155, 142)       # #0f9b8e
_MUTED = (102, 112, 133)     # #667085
_FEST_BG = (255, 243, 220)   # #fff3dc
_FEST_NAME = (180, 83, 15)   # #b4530f
_FEST_TEXT = (90, 50, 16)    # #5a3210

# Smart punctuation the built-in font either lacks or renders oddly -> fold to ASCII.
_PUNCT = {"—": "-", "–": "-", "‒": "-", "…": "...",
          "‘": "'", "’": "'", "“": '"', "”": '"',
          "₹": "Rs ", " ": " "}


def _ascii(s: str) -> str:
    """Drop anything the built-in font can't draw (emoji, Devanagari, ...) and fold smart punctuation.
    Keeps Latin-1 + Latin Extended (incl. the middot '·' used as a separator)."""
    s = "".join(_PUNCT.get(ch, ch) for ch in (s or ""))
    return "".join(ch for ch in s if ch == " " or 33 <= ord(ch) <= 0x2FF).strip()


@functools.lru_cache(maxsize=8)
def _font(size: int):
    from PIL import ImageFont
    return ImageFont.load_default(size=size)   # Pillow >=10.1 -> scalable built-in font (no file to bundle)


@functools.lru_cache(maxsize=1)
def _logo():
    """The square brand mark as an RGBA image, or None if no logo file is present."""
    from PIL import Image
    for ext in ("png", "webp", "jpg", "jpeg"):
        f = _STATIC_DIR / f"logo-square.{ext}"
        if f.exists():
            return Image.open(f).convert("RGBA")
    return None


@functools.lru_cache(maxsize=1)
def _fallback() -> bytes:
    """Last-resort raster, ALWAYS real PNG bytes (the /og.png route hardcodes Content-Type: image/png,
    so returning JPEG/webp here would be a MIME/magic mismatch that OG validators reject). Transcode the
    static logo to PNG; if even that fails, emit a tiny solid-brand PNG so social still gets a valid image."""
    from PIL import Image
    for ext in ("png", "webp", "jpg", "jpeg"):
        f = _STATIC_DIR / f"logo-square.{ext}"
        if f.exists():
            try:
                buf = io.BytesIO()
                Image.open(f).convert("RGB").save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                break
    buf = io.BytesIO()
    Image.new("RGB", (_W, _H), _BAR_TOP).save(buf, format="PNG")
    return buf.getvalue()


def _domain() -> str:
    return (settings.public_web_url or "").split("://", 1)[-1].strip("/") or "namasteamerica.us"


def _fit_prefix(draw, word: str, font, max_w: int) -> int:
    """Largest character count of `word` whose rendered width fits `max_w` (>=1)."""
    lo, hi = 1, len(word)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if draw.textlength(word[:mid], font=font) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _wrap(draw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        # Hard-break a single word too wide to fit a line by itself (defends against a long no-space
        # param even after clamping), so text can never run off the fixed canvas.
        while len(word) > 1 and draw.textlength(word, font=font) > max_w:
            if cur:
                lines.append(cur)
                cur = ""
                if len(lines) == max_lines:
                    return lines
            n = _fit_prefix(draw, word, font, max_w)
            lines.append(word[:n])
            word = word[n:]
            if len(lines) == max_lines:
                return lines
        trial = f"{cur} {word}".strip()
        if not cur or draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            if len(lines) == max_lines:
                return lines
            cur = word
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _draw_card(title: str, subtitle: str, *, bg=_BG, title_color=_INK,
               sub_color=_MUTED, footer_color=_TEAL) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (_W, _H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, _W, 16), fill=_BAR_TOP)
    d.rectangle((0, _H - 16, _W, _H), fill=_BAR_BOT)

    # Brand row: logo + platform name + tagline.
    tx = _MARGIN
    logo = _logo()
    if logo is not None:
        box = 132
        img.paste(logo.resize((box, box)), (_MARGIN, 56), logo.resize((box, box)))
        tx = _MARGIN + box + 28
    d.text((tx, 70), _ascii(settings.platform_name), font=_font(46), fill=_INK)
    d.text((tx + 2, 130), _ascii(settings.platform_tagline), font=_font(26), fill=_TEAL)

    # Title (faux-bold via a 1px stroke), wrapped to <=2 lines.
    tf = _font(76)
    y = 258
    for ln in _wrap(d, _ascii(title), tf, _W - 2 * _MARGIN, 2):
        d.text((_MARGIN, y), ln, font=tf, fill=title_color, stroke_width=1, stroke_fill=title_color)
        y += 92

    # Subtitle, wrapped to <=2 lines.
    sf = _font(32)
    y += 8
    for ln in _wrap(d, _ascii(subtitle), sf, _W - 2 * _MARGIN, 2):
        d.text((_MARGIN, y), ln, font=sf, fill=sub_color)
        y += 44

    d.text((_MARGIN, _H - 66), _domain(), font=_font(28), fill=footer_color)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ per-context cards
def _card_home() -> bytes:
    return _draw_card(
        "Find Indian America",
        f"Restaurants, temples, groceries & events across the USA — "
        f"ask {settings.assistant_name}, your desi friend")


def _card_movies() -> bytes:
    return _draw_card(
        "Indian movies in US theaters",
        "Telugu, Hindi, Tamil & more — find showtimes near you")


def _card_city(label: str, city: str, state: str) -> bytes:
    label = (label or "restaurants").strip()
    loc = ", ".join(x for x in ((city or "").strip(), (state or "").strip()) if x) or "your city"
    return _draw_card(f"Best Indian {label} in {loc}",
                      f"Top-rated picks on {settings.platform_name}")


def _card_festival(name: str) -> bytes:
    from .. import festivals
    hit = (festivals.find(name) if (name or "").strip() else None) or festivals.next_festival() or {}
    fname = hit.get("name") or "Festival season"
    du = hit.get("days_until")
    if du == 0:
        title = f"{fname} is today"
    elif du == 1:
        title = f"{fname} is tomorrow"
    elif isinstance(du, int):
        title = f"{fname} is in {du} days"
    else:
        title = fname
    sub = hit.get("greeting") or f"Warm festival wishes from {settings.platform_name}"
    return _draw_card(title, sub, bg=_FEST_BG, title_color=_FEST_NAME,
                      sub_color=_FEST_TEXT, footer_color=_FEST_NAME)


def render(kind: str = "home", **params) -> bytes:
    """Render the 1200x630 PNG for `kind`; returns PNG bytes, or the static logo bytes on any error."""
    try:
        if kind == "festival":
            return _card_festival(params.get("name", ""))
        if kind == "city":
            return _card_city(params.get("label", ""), params.get("city", ""), params.get("state", ""))
        if kind == "movies":
            return _card_movies()
        return _card_home()
    except Exception:
        return _fallback()
