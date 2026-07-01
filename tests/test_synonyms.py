"""Query synonym/alias expansion: aliases (mandir, kirana, OBGYN, biriyani…) gain their canonical
term so they route + embed well; clean queries are untouched."""

from indo_usa_mcp import synonyms


def test_expand_adds_canonical_for_alias():
    assert "temple" in synonyms.expand("mandir near me")
    assert "grocery" in synonyms.expand("kirana store in plano")
    assert "gynecologist" in synonyms.expand("obgyn in irving")
    assert "biryani" in synonyms.expand("biriyani place")          # fixes a spelling variant
    assert "accountant" in synonyms.expand("need a cpa for taxes")
    assert "gurdwara" in synonyms.expand("gurudwara near me")


def test_expand_no_change_when_canonical_present_or_no_alias():
    assert synonyms.expand("best biryani") == "best biryani"        # canonical already present
    assert synonyms.expand("saravana bhavan") == "saravana bhavan"  # no alias
    assert synonyms.expand("indian restaurant in dallas") == "indian restaurant in dallas"
    assert synonyms.expand("") == "" and synonyms.expand(None) is None


def test_expand_new_diaspora_aliases():
    assert "chaat" in synonyms.expand("pani puri near me")
    assert "cardiologist" in synonyms.expand("heart doctor in dallas")
    assert "optometrist" in synonyms.expand("eye doctor")
    assert "mehndi" in synonyms.expand("henna artist for wedding")
    assert "lehenga" in synonyms.expand("ghagra shop")
    assert "kurta" in synonyms.expand("kurti store")
    assert "salwar kameez" in synonyms.expand("punjabi suit tailor")


def test_expand_whole_word_only_and_capped():
    assert "accountant" not in synonyms.expand("cpasomething")      # not a whole word
    # never adds more than a handful of terms
    out = synonyms.expand("mandir kirana obgyn cpa dosai dabba masjid")
    assert len(out.split()) <= 7 + 4
