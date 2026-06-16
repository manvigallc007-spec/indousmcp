"""Restaurant tags include biryani / catering / tiffin (broadened detection)."""

import indo_usa_mcp.tags as tags


def test_biryani_catering_tiffin_tags():
    t = tags.extract("restaurants", {"name": "Paradise Hyderabadi Biryani & Catering",
                                     "description": "", "cuisine_type": "Indian"})
    assert "biryani" in t and "catering" in t
    assert "tiffin" in tags.extract("restaurants", {"name": "Annapurna Tiffin Service"})
    assert "biryani" in tags.extract("restaurants", {"name": "Dum Pukht",
                                                     "description": "famous for dum biryani"})


def test_catering_matches_cater_word_forms():
    assert "catering" in tags.extract("restaurants", {"name": "Spice Caterers"})
    assert "catering" in tags.extract("restaurants", {"name": "We cater parties", "description": ""})
