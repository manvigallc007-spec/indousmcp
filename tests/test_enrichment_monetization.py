"""Tests for enrichment keywords, channel/email logic, and metro expansion (no DB)."""

from indo_usa_mcp.pipeline import clean, outreach
from indo_usa_mcp.pipeline.scrapers.metros import METROS, state_for


# --- (a) enrichment: expanded cultural inference ---
def test_region_inferred_from_signature_dishes():
    assert clean.infer_region("Saravana Bhavan Tiffin") == "South Indian"
    assert clean.infer_region("Tandoori Nights") == "North Indian"
    assert clean.infer_region("Biryani House") == "Mughlai"
    assert clean.infer_region("Amritsari Dhaba") == "Punjabi"


def test_region_none_when_no_signal():
    assert clean.infer_region("Joe's Place") is None


def test_clean_passes_through_email_lowercased():
    rec = clean.clean({"name": "X", "email": "Owner@Example.COM", "source_name": "t"})
    assert rec["email"] == "owner@example.com"


# --- (d) coverage: secondary metros present with states ---
def test_secondary_metros_added():
    for m in ("los_angeles", "seattle", "atlanta", "boston", "central_nj"):
        assert m in METROS
    assert state_for("seattle") == "WA"
    assert state_for("atlanta") == "GA"
    assert state_for("central_nj") == "NJ"


# --- (c) outreach delivery: channel selection + safe default ---
def test_email_channel_preferred_when_present():
    assert outreach._pick_channel({"email": "a@b.com", "phone": "+1"}) == "email"
    assert outreach._pick_channel({"phone": "+1408"}) == "whatsapp"
    assert outreach._pick_channel({"website": "x"}) == "form"


def test_target_for_maps_channel_to_field():
    r = {"email": "a@b.com", "phone": "+1408", "website": "http://x"}
    assert outreach._target_for(r, "email") == "a@b.com"
    assert outreach._target_for(r, "whatsapp") == "+1408"
    assert outreach._target_for(r, "form") == "http://x"


def test_send_email_is_noop_when_smtp_unconfigured():
    # Default config has no SMTP host -> email disabled -> send is a safe no-op.
    assert outreach.send_email("a@b.com", "hi", "body") is False
