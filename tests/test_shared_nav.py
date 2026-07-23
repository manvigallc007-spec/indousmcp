"""The shared site header menu must appear on EVERY page shell (homepage, landing content pages, the
narrow owner/auth card, the /explore marketing page, the about/legal pages, and error pages) so
navigation is consistent everywhere — and it must be mobile-visible (not display:none)."""

from starlette.testclient import TestClient

from indo_usa_mcp.web.app import app
from indo_usa_mcp.web.common import NAV_ITEMS, nav_html

_client = TestClient(app)

# Items that should be reachable from every page (excludes self-referential Home/Ask-Dost).
_MUST_LINK = [h for h, _ in NAV_ITEMS if h not in ("/", "/chat")]

# One representative URL per distinct full-document shell.
_SHELL_URLS = [
    "/",                       # chat.py _CHAT_HTML (homepage)
    "/browse",                 # landing._page
    "/articles",               # landing._page (news roundups)
    "/portal/login",           # common._page (narrow card)
    "/about",                  # pages._doc
    "/explore",                # public._LANDING_HTML
    "/zzz-definitely-not-real",  # errors._ERR_TMPL (404)
]


def _has_link(html: str, href: str) -> bool:
    return f'href="{href}"' in html or f"href='{href}'" in html


def test_every_shell_shows_full_menu():
    for url in _SHELL_URLS:
        html = _client.get(url).text
        missing = [h for h in _MUST_LINK if not _has_link(html, h)]
        assert not missing, f"{url} is missing nav links: {missing}"


def test_homepage_menu_not_hidden_on_mobile():
    html = _client.get("/").text
    # the old rule hid the menu on phones; it must be gone
    assert ".topnav{display:none}" not in html
    assert "overflow-x:auto" in html            # menu scrolls instead of hiding


def test_nav_html_marks_active_item():
    out = nav_html(active="/browse")
    assert "aria-current='page'" in out and "class='on'" in out
    # the CTA is styled distinctly
    assert "nav-cta" in nav_html()
