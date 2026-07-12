"""Cross-promotion bar for sibling apps (biryanihub.co, caterbid.co), shown below the header on
every public-facing page template. TestClient only -- no DB writes."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import common
from indo_usa_mcp.web.app import app

_client = TestClient(app)


def test_partner_bar_links_both_apps():
    out = common.partner_bar()
    assert "https://biryanihub.co" in out and "BiryaniHub.co" in out
    assert "https://caterbid.co" in out and "CaterBid.co" in out
    assert "target='_blank'" in out and "rel='noopener'" in out   # opens in a new tab, no opener leak


def test_partner_bar_shows_on_every_public_page_template():
    # One page per distinct header/template: chat.py (/), public.py (/explore), pages.py (/faq),
    # landing.py (/browse) -- each wires partner_bar() into its own head/body shell independently.
    for path in ("/", "/explore", "/faq", "/browse"):
        html = _client.get(path).text
        assert "biryanihub.co" in html and "caterbid.co" in html, path


def test_partner_bar_not_shown_on_admin_pages():
    # admin_page() (the /admin/* shell) deliberately does not include the partner bar.
    r = _client.get("/admin/login")
    assert "biryanihub.co" not in r.text
