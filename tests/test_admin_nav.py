"""Admin nav is grouped into sections and renders (badges degrade gracefully without a DB)."""

from indo_usa_mcp.web import common


def test_admin_nav_is_grouped():
    assert all(isinstance(sec, str) and isinstance(items, list) for sec, items in common._ADMIN_NAV)
    labels = [lbl for _sec, items in common._ADMIN_NAV for lbl, _href in items]
    for must in ("Overview", "Operations", "Messages", "Approvals", "Moderation", "Agents",
                "Search all", "Movies", "Employers", "Knowledge"):
        assert must in labels, must


def test_admin_page_renders_grouped_nav():
    html = common.admin_page("Test", "<p>hi</p>", active="Messages").body.decode()
    assert "navgrp" in html and "navsec" in html          # grouped structure
    assert ">Messages<" in html or "Messages<span" in html  # the item is present
    assert "Listings" in html and "Inbox" in html          # section labels
