"""The mobile touch layer: bottom tab bar, the "More" sheet, thumb-reach rules, skeletons.

Why it exists: 70%+ of local search happens on a phone, and the top nav is an eleven-item horizontal
scroll strip whose later items are effectively invisible there. These tests pin the contract that
every nav destination stays reachable on a phone and that nothing floats over the chat composer.
"""

import re

from starlette.testclient import TestClient

from indo_usa_mcp.web import theme
from indo_usa_mcp.web.common import NAV_ITEMS, TAB_ITEMS, tabbar_html
from indo_usa_mcp.web.app import app

_client = TestClient(app)

# Public shells that should carry the bar. Admin and the API docs are deliberately excluded:
# they are desktop tools, not visitor pages.
_PAGES = ["/", "/explore", "/browse", "/about", "/find", "/events", "/today", "/questions",
          "/insights", "/news", "/movies", "/for-business", "/faq", "/contact"]


def test_tab_bar_is_on_every_public_shell():
    for path in _PAGES:
        t = _client.get(path, follow_redirects=True).text
        assert "class='tabbar" in t or 'class="tabbar' in t, f"{path} has no bottom tab bar"


def test_error_pages_keep_the_tab_bar():
    assert "tabbar" in _client.get("/definitely-not-a-page").text


def test_every_nav_destination_is_reachable_on_a_phone():
    """The top strip is hidden under 760px, so a destination that is in neither the bar nor the
    sheet becomes unreachable on a phone. This is the regression that matters most."""
    html = tabbar_html()
    tab_hrefs = {href for _, _, href in TAB_ITEMS}
    for href, label in NAV_ITEMS:
        if href in tab_hrefs or href == "/chat":      # /chat redirects to "/", which is a tab
            continue
        assert f"href='{href}'" in html, f"{label} ({href}) is unreachable on mobile"


def test_tab_bar_marks_the_current_destination():
    html = tabbar_html("/browse")
    assert "class=on" in html and "aria-current='page'" in html
    # "/" must not match every path, or every page would look like Home
    assert "aria-current='page'" not in tabbar_html("/browse").split("href='/browse'")[0]


def test_home_tab_is_only_active_on_home():
    assert "aria-current='page'" in tabbar_html("/")
    home_anchor = tabbar_html("/events").split("href='/browse'")[0]
    assert "aria-current" not in home_anchor


def test_more_sheet_is_accessible():
    html = tabbar_html()
    assert "aria-expanded='false'" in html          # the trigger reports its state
    assert "aria-controls='na-sheet'" in html
    assert "aria-modal='true'" in html
    assert "Escape" in html                         # dismissable from the keyboard
    assert "<div class='navsheet' id='na-sheet' hidden" in html   # starts closed


def test_chat_bar_does_not_float_over_the_composer():
    """On the chat page the composer owns the bottom edge of a full-height flex column, so the bar
    must join the flow rather than be fixed on top of it."""
    t = _client.get("/").text
    assert "tabbar is-static" in t
    # and it comes after the composer in document order
    assert t.index("class=\"composer\"") < t.index("tabbar is-static")


def test_other_pages_use_the_fixed_bar():
    t = _client.get("/browse").text
    assert "tabbar is-static" not in t


def test_touch_layer_is_mobile_only_and_leaves_desktop_alone():
    css = _client.get("/theme.css").text
    assert ".tabbar{display:none}" in css                      # hidden by default
    mobile = css.split("@media (max-width:760px)")[1]
    assert ".site-nav{display:none}" in mobile                 # strip hidden only on mobile
    assert ".tabbar{display:flex" in mobile


def test_fixed_bar_does_not_cover_page_content():
    mobile = _client.get("/theme.css").text.split("@media (max-width:760px)")[1]
    assert "padding-bottom:calc(58px + env(safe-area-inset-bottom))" in mobile


def test_tap_targets_meet_the_44px_guideline():
    css = _client.get("/theme.css").text
    mobile = css.split("@media (max-width:760px)")[1]
    for rule in ("min-height:52px", "min-height:48px", "min-height:44px", "min-height:46px"):
        assert rule in mobile, f"missing {rule}"
    # nothing in the touch layer should set a target below 40px
    smalls = [int(m) for m in re.findall(r'min-height:(\d+)px', mobile)]
    assert smalls and min(smalls) >= 40, f"a tap target is only {min(smalls)}px"


def test_safe_area_is_respected():
    """An iPhone's home indicator overlaps a bar pinned to bottom:0 without this."""
    css = _client.get("/theme.css").text
    assert css.count("env(safe-area-inset-bottom)") >= 3


def test_skeletons_are_defined_and_used_while_loading():
    css = _client.get("/theme.css").text
    assert ".sk{" in css and "sk-shimmer" in css
    t = _client.get("/").text
    assert "function skeletons(" in t
    assert "content.appendChild(skeletons(2))" in t
    assert "aria-hidden" in t          # placeholders are not announced


def test_chat_thread_is_a_live_region():
    """A streamed answer must be announced; without aria-live a screen reader misses it."""
    assert 'aria-live="polite"' in _client.get("/").text


def test_shimmer_stops_for_reduced_motion():
    assert "prefers-reduced-motion" in theme.BASE_CSS


def test_chat_page_cancels_the_fixed_bar_spacing():
    """The design system reserves bottom room for the FIXED bar. The chat page's bar is static
    inside a 100dvh flex column, so keeping that reservation would leave dead space under the
    composer. The page-local override must survive future edits to its <style> block."""
    t = _client.get("/").text
    assert "@media(max-width:760px){body{padding-bottom:0}}" in t
    # and the override must come after the stylesheet link, or it loses the tie
    assert t.index('href="/theme.css"') < t.index("@media(max-width:760px){body{padding-bottom:0}}")
