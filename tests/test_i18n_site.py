"""Site-wide language: the switcher, the per-request contextvar, and honest <html lang>.

Before this, i18n reached 3 of ~25 web modules, the language could only be changed by a JS
<select> on the chat page, and every shell hardcoded `<html lang="en">` — so a Hindi page told
screen readers and search engines it was English.
"""

import re

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp.web import common, i18n
from indo_usa_mcp.web.app import app

# Pages drawn by each of the three shells, plus the chat homepage.
SHELL_PAGES = ["/about", "/faq", "/browse", "/events", "/today", "/insights", "/explore", "/find"]


def _client():
    return TestClient(app)


def _html_lang(text: str) -> str:
    m = re.search(r'<html lang="([^"]+)"', text)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- the switcher
def test_switching_sets_a_cookie_and_returns_to_the_page():
    c = _client()
    r = c.get("/lang/hi?next=/about", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/about"
    assert "lang=hi" in r.headers.get("set-cookie", "")


def test_the_choice_persists_across_requests():
    c = _client()
    c.get("/lang/te?next=/about")
    assert _html_lang(c.get("/browse").text) == "te"      # a different page, same choice
    assert _html_lang(c.get("/faq").text) == "te"


def test_an_unknown_language_is_ignored_rather_than_stored():
    c = _client()
    r = c.get("/lang/xx?next=/about", follow_redirects=False)
    assert r.status_code == 303
    assert "lang=" not in r.headers.get("set-cookie", "")
    assert _html_lang(c.get("/about").text) == "en"


@pytest.mark.parametrize("hostile", ["//evil.example.com", "https://evil.example.com",
                                     "javascript:alert(1)", "http://evil", "\\\\evil.example.com"])
def test_the_switcher_is_not_an_open_redirect(hostile):
    """`next` is attacker-controlled: '//evil.com' looks like a path to a careless check."""
    r = _client().get("/lang/hi", params={"next": hostile}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_a_local_next_is_honoured():
    r = _client().get("/lang/hi", params={"next": "/browse/restaurants/tx/plano"},
                      follow_redirects=False)
    assert r.headers["location"] == "/browse/restaurants/tx/plano"


def test_the_switcher_works_without_javascript():
    """It is plain links + a GET, because the previous JS <select> existed only on the chat page —
    which is exactly why the rest of the site was stuck in English."""
    t = _client().get("/about").text
    assert "/lang/hi?next=" in t and "/lang/te?next=" in t
    start = t.index("class='langsw'")
    sw = t[start:t.index("</div>", start)]          # just the switcher, not the toggle beside it
    assert sw.count("<a href=") == len(i18n.LANGS)
    assert "onclick" not in sw and "<select" not in sw


def test_each_language_is_offered_in_its_own_script():
    """Someone who cannot read the current language still has to find their own."""
    t = _client().get("/about").text
    for name in i18n.LANG_NAMES.values():
        assert name in t


def test_the_current_language_is_marked_for_assistive_tech():
    c = _client()
    c.get("/lang/hi?next=/about")
    sw = c.get("/about").text
    block = sw[sw.index("class='langsw'"):][:800]
    assert "aria-current='true'" in block
    assert "hreflang='hi'" in block


# --------------------------------------------------------------------------- <html lang>
def test_every_shell_declares_the_real_language():
    for lang_code in ("en", "hi", "te"):
        c = _client()
        c.get(f"/lang/{lang_code}?next=/")
        for path in SHELL_PAGES:
            t = c.get(path, follow_redirects=True).text
            assert _html_lang(t) == lang_code, f"{path} claims {_html_lang(t)!r} for {lang_code}"


def test_accept_language_is_used_when_there_is_no_cookie():
    t = _client().get("/about", headers={"Accept-Language": "te-IN,te;q=0.9"}).text
    assert _html_lang(t) == "te"


def test_an_explicit_choice_beats_the_browser_header():
    c = _client()
    c.get("/lang/en?next=/about")
    t = c.get("/about", headers={"Accept-Language": "hi-IN,hi;q=0.9"}).text
    assert _html_lang(t) == "en"


# --------------------------------------------------------------------------- translated chrome
def test_the_main_menu_follows_the_language():
    c = _client()
    c.get("/lang/hi?next=/about")
    t = c.get("/about").text
    assert "होम" in t and "समाचार" in t and "ब्राउज़ करें" in t
    assert ">Browse</a>" not in t                          # not left in English alongside


def test_the_mobile_tab_bar_follows_the_language():
    c = _client()
    c.get("/lang/te?next=/browse")
    t = c.get("/browse").text
    bar = t[t.index("class='tabbar"):]
    assert "హోమ్" in t
    assert "ఈరోజు" in bar and "మరిన్ని" in bar             # Today + More, translated


def test_the_more_sheet_offers_the_language_switcher_on_mobile():
    """The header strip is hidden under 760px, so the sheet has to carry it."""
    html = common.tabbar_html()
    sheet = html[html.index("navsheet-panel"):]
    assert "langsw" in sheet


def test_accessibility_affordances_are_translated():
    c = _client()
    c.get("/lang/hi?next=/about")
    t = c.get("/about").text
    assert "सामग्री पर जाएँ" in t                          # skip link
    assert "लाइट/डार्क बदलें" in t                          # theme toggle label


def test_the_assistant_keeps_its_name_in_every_language():
    """"Dost" is a name, not a string to translate."""
    for lang_code in ("en", "hi", "te"):
        labels = dict(common.nav_items(lang_code))
        assert "Dost" in labels["/chat"]


# --------------------------------------------------------------------------- the data layer
def test_every_key_exists_in_every_language():
    """A key missing a translation silently falls back to English, which looks like a bug the
    visitor cannot report. Catch it here instead."""
    missing = {k: sorted(set(i18n.LANGS) - set(v)) for k, v in i18n._T.items()
               if set(i18n.LANGS) - set(v)}
    assert not missing, f"untranslated: {missing}"


def test_no_translation_is_accidentally_still_english():
    """A copy-pasted entry whose hi/te value is the English string is a silent omission."""
    same = [k for k, v in i18n._T.items()
            if v.get("hi") == v["en"] or v.get("te") == v["en"]]
    assert not same, f"hi/te identical to en: {same}"


def test_tr_falls_back_rather_than_raising():
    assert i18n.tr("nav_home", lang_code="en") == "Home"
    assert i18n.tr("definitely_not_a_key") == "definitely_not_a_key"


def test_the_language_is_en_outside_a_request():
    """CLI, agents and the MCP server render without a request; they must not crash or leak a
    language from a previous web request."""
    assert i18n.lang() == "en"
    assert i18n.tr("nav_home") == "Home"


def test_the_english_nav_list_still_matches_the_translated_one():
    """NAV_ITEMS is still used by sitemaps and the chat page's own top nav."""
    assert [h for h, _ in common.NAV_ITEMS] == [h for h, _ in common.nav_items("en")]
