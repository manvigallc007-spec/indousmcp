"""WCAG 2.1 contrast of the design-system palette — enforced, in both themes.

The audience skews older and multilingual, so readable text is a feature, not a compliance chore.
These tests do the real relative-luminance maths on the tokens in web/theme.py, which means a future
palette tweak that looks fine on one monitor still cannot silently fall below AA.

Targets: 4.5:1 for body text, 3.0:1 for large text and for non-text UI (borders, icons, meters).
"""

import re

import pytest

from indo_usa_mcp.web import theme


# --------------------------------------------------------------------------- colour maths
def _rgb(value: str) -> tuple[int, int, int]:
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    h = h[:6]                                     # ignore any alpha suffix (#rrggbbaa)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(value: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(x) for x in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", block))


_CSS = theme.TOKENS_CSS
LIGHT = _tokens(_CSS.split("@media")[0])
DARK = _tokens(_CSS.split(':root[data-theme="dark"]')[1])

# (foreground, background, minimum, what it is)
PAIRS = [
    ("--ink", "--bg", 4.5, "body text on the page"),
    ("--ink", "--panel", 4.5, "body text on a card"),
    ("--ink-2", "--panel", 4.5, "secondary text on a card"),
    ("--ink-3", "--panel", 4.5, "form labels on a card"),
    ("--muted", "--panel", 4.5, "muted text on a card"),
    ("--muted", "--bg", 4.5, "muted text on the page"),
    ("--faint", "--panel", 3.0, "faint/meta text on a card"),
    ("--brand-strong", "--panel", 4.5, "a link on a card"),
    ("--brand-strong", "--bg", 4.5, "a link on the page"),
    ("--brand-ink", "--warm-tint", 4.5, "partner-bar link"),
    ("--accent-ink", "--panel", 4.5, "accent text on a card"),
    ("--warm-ink", "--warm-tint", 4.5, "text on the warm strip"),
    ("--on-brand", "--brand-fill", 4.5, "text on a filled brand button"),
    ("--on-accent", "--accent-fill", 4.5, "text on a filled accent button"),
    ("--on-status", "--err", 4.5, "text on a red badge"),
    ("--ok", "--ok-tint", 4.5, "success text on its tint"),
    ("--warn", "--warn-tint", 4.5, "warning text on its tint"),
    ("--err", "--err-tint", 4.5, "error text on its tint"),
    ("--info", "--info-tint", 4.5, "info text on its tint"),
    ("--ok", "--panel", 4.5, "success text on a card"),
    ("--warn", "--panel", 4.5, "warning text on a card"),
    ("--err", "--panel", 4.5, "error text on a card"),
    ("--star", "--panel", 4.5, "the rating line on a card"),
    ("--brand", "--panel", 3.0, "brand as non-text UI on a card"),
    ("--accent", "--panel", 3.0, "accent as non-text UI on a card"),
]

CATEGORIES = ("restaurants", "temples", "groceries", "professionals", "salons", "events", "apparel",
              "sweets", "studios", "services", "community", "legal", "education", "realestate",
              "finance", "movies", "employers")


@pytest.mark.parametrize("theme_name,palette", [("light", LIGHT), ("dark", DARK)])
@pytest.mark.parametrize("fg,bg,need,label", PAIRS, ids=[p[3].replace(" ", "-") for p in PAIRS])
def test_token_pair_meets_wcag_aa(theme_name, palette, fg, bg, need, label):
    assert fg in palette, f"{fg} is not defined in the {theme_name} palette"
    assert bg in palette, f"{bg} is not defined in the {theme_name} palette"
    got = contrast(palette[fg], palette[bg])
    assert got >= need, (
        f"{theme_name}: {label} ({fg} {palette[fg]} on {bg} {palette[bg]}) "
        f"is {got:.2f}:1, needs {need}:1")


@pytest.mark.parametrize("theme_name,palette,surface", [("light", LIGHT, "--panel"),
                                                        ("dark", DARK, "--panel")])
@pytest.mark.parametrize("category", CATEGORIES)
def test_category_hue_is_readable_on_its_own_surface(theme_name, palette, surface, category):
    """Each category hue is also used as text (the count line on a category card), so 4.5:1."""
    token = f"--cat-{category}"
    assert token in palette, f"{token} missing from the {theme_name} palette"
    got = contrast(palette[token], palette[surface])
    assert got >= 4.5, (f"{theme_name}: {token} ({palette[token]}) on {surface} "
                        f"({palette[surface]}) is {got:.2f}:1, needs 4.5:1")


def test_both_themes_define_the_same_token_set():
    """A token present in one theme and missing in the other is a hole that only shows up for the
    visitors using that theme."""
    assert set(DARK) - set(LIGHT) == set(), f"dark-only tokens: {sorted(set(DARK) - set(LIGHT))}"
    assert set(LIGHT) - set(DARK) == set(), f"light-only tokens: {sorted(set(LIGHT) - set(DARK))}"


def test_the_two_dark_blocks_are_identical():
    """Dark is declared twice — once for the OS preference, once for the explicit choice. If they
    drift, the toggle and the system setting render differently."""
    media_dark = _tokens(_CSS.split('@media')[1].split(':root[data-theme="dark"]')[0])
    assert media_dark == DARK, "the two dark declarations have drifted apart"
