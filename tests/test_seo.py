"""schema.org JSON-LD helpers + FAQ page rich results. No live DB needed."""

import json

from starlette.testclient import TestClient

from indo_usa_mcp.web import seo
from indo_usa_mcp.web.app import app


def test_faq_jsonld_strips_html_and_is_valid():
    out = seo.faq_jsonld([("What is it?", "A <b>free</b> directory.\n  Really.")])
    assert out.startswith('<script type="application/ld+json">')
    body = out[len('<script type="application/ld+json">'):-len("</script>")]
    data = json.loads(body)
    assert data["@type"] == "FAQPage"
    q = data["mainEntity"][0]
    assert q["@type"] == "Question" and q["name"] == "What is it?"
    assert q["acceptedAnswer"]["text"] == "A free directory. Really."   # tags stripped, ws collapsed


def test_jsonld_script_escapes_angle_brackets():
    # The '<' that could break out of the <script> must be escaped.
    out = seo.jsonld_script({"x": "</script><script>alert(1)"})
    assert "</script><script>" not in out[:-len("</script>")]
    assert "\\u003c" in out


def test_breadcrumb_jsonld_positions():
    out = seo.breadcrumb_jsonld([("Home", "https://x/"), ("Browse", "https://x/browse")])
    data = json.loads(out[len('<script type="application/ld+json">'):-len("</script>")])
    assert data["@type"] == "BreadcrumbList"
    assert [i["position"] for i in data["itemListElement"]] == [1, 2]
    assert data["itemListElement"][1]["name"] == "Browse"


def test_faq_page_renders_faqpage_schema():
    r = TestClient(app).get("/faq")
    assert r.status_code == 200
    assert '"@type": "FAQPage"' in r.text
    assert "Can I search in Hindi or Telugu" in r.text          # the expanded Q&A is present
