"""Tests for website enrichment parsing (schema.org / Open Graph / socials). No network, no DB."""

from indo_usa_mcp import describe, web_enrich

# A representative business page: JSON-LD Restaurant in an @graph, OG meta, social + mailto links.
PAGE = """
<html><head>
<meta property="og:image" content="/img/hero.jpg">
<meta property="og:description" content="Authentic   Hyderabadi biryani &amp; dosa in Edison.">
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Spice Hub"},
  {"@type":"Restaurant","name":"Spice Hub",
   "telephone":"+1-732-555-0100","email":"mailto:hello@spicehub.com",
   "priceRange":"$$","servesCuisine":["South Indian","Hyderabadi"],
   "image":"https://cdn.spicehub.com/photo.jpg",
   "hasMenu":"https://spicehub.com/menu",
   "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.6","reviewCount":"212"},
   "sameAs":["https://www.instagram.com/spicehub","https://facebook.com/spicehub"]}
]}
</script>
</head><body>
<a href="mailto:catering@spicehub.com">Catering</a>
<a href="https://twitter.com/spicehub?ref=foot">Twitter</a>
</body></html>
"""


def test_extract_full_signals():
    sig = web_enrich.extract(PAGE, base_url="https://spicehub.com/")
    assert sig["rating"] == 4.6 and sig["rating_count"] == 212
    assert sig["price_range"] == "$$"
    assert sig["phone"] == "+1-732-555-0100"
    assert sig["email"] == "hello@spicehub.com"          # JSON-LD email wins over mailto link
    assert sig["menu_url"] == "https://spicehub.com/menu"
    assert sig["photo_url"] == "https://cdn.spicehub.com/photo.jpg"  # JSON-LD beats og:image
    assert set(sig["cuisine_tags"]) == {"south indian", "hyderabadi"}
    assert sig["socials"] == {"instagram": "https://www.instagram.com/spicehub",
                              "facebook": "https://facebook.com/spicehub",
                              "twitter": "https://twitter.com/spicehub"}
    assert "biryani" in sig["site_description"].lower()


def test_og_image_resolved_relative_when_no_jsonld_image():
    html = '<meta property="og:image" content="/logo.png">'
    assert web_enrich.extract(html, "https://x.com/a/b") == {"photo_url": "https://x.com/logo.png"}


def test_jsonld_handles_bare_array_and_missing_rating():
    html = ('<script type="application/ld+json">'
            '[{"@type":"LocalBusiness","name":"X","priceRange":"$"}]</script>')
    sig = web_enrich.extract(html)
    assert sig["price_range"] == "$" and "rating" not in sig


def test_rating_out_of_range_ignored():
    html = ('<script type="application/ld+json">{"@type":"Restaurant",'
            '"aggregateRating":{"ratingValue":"99"}}</script>')
    assert "rating" not in web_enrich.extract(html)


def test_malformed_jsonld_does_not_raise():
    assert web_enrich.extract("<script type='application/ld+json'>{not json,,}</script>") == {}
    assert web_enrich.extract("") == {}


def test_description_includes_rating():
    d = describe.describe("restaurants",
                          {"name": "Spice Hub", "city": "Edison", "state": "NJ",
                           "rating": 4.6, "rating_count": 212})
    assert "Rated 4.6/5 from 212 reviews." in d
