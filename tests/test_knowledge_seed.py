"""Curated knowledge articles: well-formed, unique, expanded, with legal/tax disclaimers. No DB."""

import indo_usa_mcp.intelligence as I
import indo_usa_mcp.knowledge_seed as KS


def test_articles_well_formed_and_unique():
    slugs = [a["slug"] for a in KS.ARTICLES]
    assert len(slugs) == len(set(slugs))                 # no duplicate slugs
    assert len(KS.ARTICLES) >= 45                        # 15 + 18 + 12 food/diaspora
    for a in KS.ARTICLES:
        assert a["slug"] and a["title"] and a["text"]
        assert "vertical" in a                           # may be None, but key must exist
        assert len(a["text"]) > 80


def test_key_new_topics_present():
    slugs = {a["slug"] for a in KS.ARTICLES}
    for s in ("h4-ead", "us-citizenship", "visa-stamping-india", "building-credit", "us-banking",
              "health-insurance", "retirement-401k", "fbar-foreign-accounts", "durga-puja",
              "gurpurab", "indian-wedding", "raising-kids-heritage",
              "biryani-guide", "regional-indian-cuisines", "indian-catering", "tiffin-services"):
        assert s in slugs, s


def test_latest_diaspora_topics_present():
    slugs = {a["slug"] for a in KS.ARTICLES}
    for s in ("oci-card", "indian-passport-renewal", "consulate-jurisdiction", "find-h1b-sponsor",
              "find-a-pandit", "cricket-in-usa", "renting-apartment-usa", "bringing-parents-to-visit",
              "shipping-to-india", "buying-a-car-usa"):
        assert s in slugs, s
    by = {a["slug"]: a for a in KS.ARTICLES}
    for s in ("oci-card", "find-h1b-sponsor", "bringing-parents-to-visit"):   # immigration -> disclaimer
        assert "professional" in by[s]["text"].lower(), s


def test_legal_and_tax_articles_carry_disclaimer():
    by = {a["slug"]: a for a in KS.ARTICLES}
    for s in ("h4-ead", "us-citizenship", "visa-stamping-india", "retirement-401k",
              "fbar-foreign-accounts"):
        assert "professional" in by[s]["text"].lower(), s   # _DISCLAIMER appended


def test_new_intelligence_topics_added_and_scoped():
    # TOPICS are search phrases (not themselves gated); the NEW ones I added are US-scoped by design.
    assert len(I.TOPICS) >= 40
    new = ["Indian American naturalization and US citizenship", "OCI card for Indian Americans",
           "H-4 visa spouses working in the United States",
           "FBAR foreign account reporting for Indians in the United States"]
    for t in new:
        assert t in I.TOPICS, t
        assert I._is_usa_relevant(t), t
