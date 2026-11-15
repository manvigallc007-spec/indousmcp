"""The design system (web/theme.py): one stylesheet, one palette, light + dark.

These tests are the guard rails that stop the old pattern from creeping back — a page shell
re-declaring its own hex palette, or a new page shipping without the shared stylesheet.
"""

import re

from starlette.testclient import TestClient

from indo_usa_mcp.web import theme
from indo_usa_mcp.web.app import app

_client = TestClient(app)

# Every full-document shell in the app. A new shell must be added here *and* link /theme.css.
_SHELL_PAGES = ["/", "/explore", "/browse", "/about", "/faq", "/privacy", "/terms", "/contact",
                "/find", "/events", "/today", "/questions", "/insights", "/for-business",
                "/for-agents", "/news", "/articles", "/movies", "/employers", "/api",
                "/portal/login", "/portal/register", "/me", "/leaderboard", "/submit"]


def test_theme_css_is_served_and_cacheable():
    r = _client.get("/theme.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert "max-age" in r.headers.get("cache-control", "")


def test_palette_is_defined_once_for_light_and_dark():
    css = _client.get("/theme.css").text
    # light is the base, on bare :root
    assert ":root{" in css.replace(" ", "")
    # the warm saffron/terracotta + teal identity. --brand is #e77429 rather than the original
    # #e8772e so it clears 3:1 on white as non-text UI; --brand-fill is the deeper terracotta
    # that white text can sit on (see tests/test_contrast.py).
    assert "--brand:#e77429" in css and "--accent:#0f9b8e" in css
    assert "--brand-fill:#c1440e" in css and "--on-brand:#fff" in css
    # dark exists in both forms: OS preference (guarded) and explicit choice
    assert '@media (prefers-color-scheme: dark)' in css
    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css
    # colour-scheme is declared so form controls/scrollbars follow the theme
    assert "color-scheme:light" in css and "color-scheme:dark" in css


def test_no_token_is_defined_only_in_the_dark_block():
    """Light must be complete on its own — a token that exists only under the dark media query
    renders as an invalid value in light mode."""
    css = theme.TOKENS_CSS
    light = css.split("@media")[0]
    names = set(re.findall(r'(--[a-z0-9-]+):', css))
    light_names = set(re.findall(r'(--[a-z0-9-]+):', light))
    assert names - light_names == set(), f"defined only in dark: {sorted(names - light_names)}"


def test_tokens_are_not_self_referential():
    """`--brand:var(--brand)` is a cycle: the declaration is dropped and the page loses the colour.
    This is the exact bug a mechanical hex->token migration introduces."""
    for css in (theme.THEME_CSS, *(_client.get(p).text for p in ("/", "/explore", "/about"))):
        assert not re.search(r'(--[a-z0-9-]+)\s*:\s*var\(\1\)', css)


def test_every_shell_links_the_design_system():
    for path in _SHELL_PAGES:
        t = _client.get(path, follow_redirects=True).text
        assert '<link rel="stylesheet" href="/theme.css">' in t, f"{path} is not on the design system"


def test_error_pages_are_themed_too():
    t = _client.get("/definitely-not-a-page").text
    assert '<link rel="stylesheet" href="/theme.css">' in t


def test_pages_carry_no_hardcoded_surface_colours():
    """Surfaces/text/borders must come from tokens, or dark mode shows light patches. Decorative
    per-category hues and map pins are the documented exceptions."""
    svg = re.compile(r'<svg.*?</svg>', re.S)
    meta = re.compile(r'<meta name="theme-color"[^>]*>')
    jsmap = re.compile(r'COLOR=\{.*?\}', re.S)
    # Map pins sit on top of OSM tile imagery, which is light in both themes (tinting someone
    # else's map data makes it harder to read), so the pins stay white. Both the static and the
    # interactive pin are exempt; the rest of the map chrome is tokenized like anything else.
    pin = re.compile(r'\.mpin\{.*?\.mapattr|\.imap-pin\{.*?\.imap-ctl', re.S)
    banned = ("#fff;", "#faf8f4", "#ece6dd", "#222b33", "#667085", "#c1440e;")
    for path in ("/", "/explore", "/browse", "/about", "/today"):
        t = _client.get(path, follow_redirects=True).text
        # the theme toggle's own script legitimately names the two theme-color values
        t = t.replace("'#14110e':'#e8772e'", "")
        t = pin.sub("", jsmap.sub("", meta.sub("", svg.sub("", t))))
        for lit in banned:
            assert lit not in t, f"{path} still hardcodes {lit}"


def test_theme_toggle_and_skip_link_are_present():
    t = _client.get("/").text
    assert "naToggleTheme()" in t                     # the control
    assert "na_theme" in t                            # the remembered choice
    assert 'class="skip-link"' in t or "class='skip-link'" in t
    # the pre-paint resolver must run in <head>, before any body markup, or the theme flashes
    assert t.index("naToggleTheme") < t.index("<body")


def test_reduced_motion_is_respected():
    """The chat UI ships pulsing mic/typing animations; they must stop for visitors who ask."""
    assert "prefers-reduced-motion" in _client.get("/theme.css").text


def test_service_worker_caches_the_stylesheet():
    sw = _client.get("/sw.js").text
    assert "/theme.css" in sw


def test_theme_toggle_cannot_be_pushed_off_the_header():
    """The nav strip is a flex sibling of the toggle. Without min-width:0 it refuses to shrink
    below its content width at mid widths and shoves the toggle out of view."""
    from indo_usa_mcp.web.common import NAV_CSS
    rule = [r for r in NAV_CSS.split("}") if ".site-nav{" in r][0]
    assert "min-width:0" in rule
    assert "flex:0 0 auto" in _client.get("/theme.css").text.split(".theme-toggle{")[1][:200]

