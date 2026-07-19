"""Phase 6 — distribution/virality: the share widget (native share + WhatsApp + copy) on shareable
pages, and the referral loop (stable code, first-touch attribution, count) + /me invite surface.
Real dev DB, ZZTEST rows, try/finally; login mocked."""

from starlette.testclient import TestClient

from indo_usa_mcp import accounts, db, qa, verticals
from indo_usa_mcp.web import common, me as me_mod, portal, qa_web
from indo_usa_mcp.web.app import app

_client = TestClient(app)


# --------------------------------------------------------------- share widget
def test_share_html_absolutizes_and_has_channels():
    out = common.share_html("/listing/restaurants/5", "Spice Hut")
    assert "://" in out and "/listing/restaurants/5" in out          # relative path -> absolute
    assert "navigator.share" in out and "wa.me" in out               # native + WhatsApp
    assert "naShare" in out


def test_share_widget_on_listing_and_qa_pages(monkeypatch):
    rid = verticals.create_record("restaurants", {"name": "ZZTEST Share P6", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7}, source="test")["id"]
    monkeypatch.setattr(qa_web, "portal_email", lambda r: "asker@example.com")
    qres = qa.create_question("ZZTEST where is good pani puri in Edison?", asker_email="asker@example.com")
    try:
        assert "↗ Share" in _client.get(f"/listing/restaurants/{rid}").text
        assert "↗ Share" in _client.get(f"/q/{qres['slug']}").text
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
        db.execute("DELETE FROM questions WHERE asker_email=%s", ("asker@example.com",))


# --------------------------------------------------------------- referral loop
def test_referral_code_stable_and_resolves():
    e = "zztest_ref_a@example.com"
    try:
        code = accounts.ensure_referral_code(e)
        assert len(code) == 8 and accounts.ensure_referral_code(e) == code   # stable
        assert accounts.referrer_for_code(code) == e
        assert accounts.referrer_for_code("nope") is None
    finally:
        db.execute("DELETE FROM user_profiles WHERE email=%s", (e,))


def test_referral_attribution_first_touch_and_no_self():
    ref, new = "zztest_ref_r@example.com", "zztest_ref_n@example.com"
    try:
        code = accounts.ensure_referral_code(ref)
        assert accounts.attribute_referral(ref, code) is False           # no self-referral
        assert accounts.attribute_referral(new, code) is True
        assert accounts.referral_count(ref) == 1
        # a later, different referrer can't overwrite first-touch attribution
        other = accounts.ensure_referral_code("zztest_ref_o@example.com")
        assert accounts.attribute_referral(new, other) is False
        assert accounts.referral_count(ref) == 1
    finally:
        db.execute("DELETE FROM user_profiles WHERE email IN (%s,%s,%s)",
                   (ref, new, "zztest_ref_o@example.com"))


# --------------------------------------------------------------- /me + registration wiring
def test_me_shows_invite_link_and_count(monkeypatch):
    e = "zztest_ref_me@example.com"
    monkeypatch.setattr(me_mod, "portal_email", lambda req: e)
    try:
        accounts.attribute_referral("zztest_joiner@example.com", accounts.ensure_referral_code(e))
        html = _client.get("/me").text
        code = accounts.ensure_referral_code(e)
        assert "Invite friends" in html and f"ref={code}" in html
        assert "1</b> joined via you" in html
    finally:
        db.execute("DELETE FROM user_profiles WHERE email IN (%s,%s)", (e, "zztest_joiner@example.com"))


def test_register_form_carries_ref():
    html = _client.get("/portal/register?ref=abc12345").text
    assert "name='ref' value='abc12345'" in html
