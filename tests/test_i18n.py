"""Server-side UI i18n: the submit + review forms render in the visitor's cookie language (en/hi/te).
Expected strings come from i18n.t() so the test source stays ASCII (no Indic literals to mangle)."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import i18n
from indo_usa_mcp.web.app import app


class _R:
    def __init__(self, lang=None, accept=""):
        self.cookies = {"lang": lang} if lang else {}
        self.headers = {"accept-language": accept}


def test_page_lang_cookie_then_accept_then_default():
    assert i18n.page_lang(_R("te")) == "te"
    assert i18n.page_lang(_R("hi")) == "hi"
    assert i18n.page_lang(_R("xx")) == "en"                         # unknown cookie -> en
    assert i18n.page_lang(_R(accept="te-IN,te;q=0.9")) == "te"      # Accept-Language fallback
    assert i18n.page_lang(_R()) == "en"


def test_submit_form_renders_in_telugu_and_hindi():
    te = i18n.t(_R("te"))
    body = TestClient(app, cookies={"lang": "te"}).get("/submit").text
    assert te["add_business"] in body and te["submit_for_review"] in body
    assert "Add your business" not in body                          # actually translated, not English
    hi = i18n.t(_R("hi"))
    assert hi["add_business"] in TestClient(app, cookies={"lang": "hi"}).get("/submit").text


def test_submit_form_defaults_to_english():
    assert "Add your business" in TestClient(app).get("/submit").text
