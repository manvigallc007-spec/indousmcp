"""Vendor flow: US-state dropdown (city stays typed) on the submit form."""

from starlette.testclient import TestClient

from indo_usa_mcp.web import common
from indo_usa_mcp.web.app import app


def test_state_select_marks_selected_and_includes_territories():
    out = common.state_select("state", "tx")
    assert "<select name='state'" in out
    assert "<option value='TX' selected>Texas (TX)</option>" in out
    assert "Puerto Rico (PR)" in out
    assert "Select a state" in out                 # placeholder option


def test_state_select_accepts_full_name():
    out = common.state_select("state", "California")
    assert "<option value='CA' selected>California (CA)</option>" in out


def test_submit_form_uses_state_dropdown():
    r = TestClient(app).get("/submit")
    assert r.status_code == 200
    assert "<select name='state'" in r.text        # dropdown, not a free-text field
    assert "Texas (TX)" in r.text
    assert "name='city'" in r.text                 # city stays a typed input


# --- auto-populate onboarding (A3) + delete (A4) ---
import indo_usa_mcp.onboard as onboard
from indo_usa_mcp.web import portal


def test_parse_place_extracts_public_fields():
    place = {"lat": "33.02", "lon": "-96.7",
             "address": {"house_number": "100", "road": "Main St", "city": "Plano"},
             "extratags": {"website": "https://x.com", "phone": "+1 555",
                           "opening_hours": "Mo-Su 11:00-21:00"}}
    out = onboard._parse_place(place, "Spice Hut", "", "TX")
    assert out["name"] == "Spice Hut" and out["state"] == "TX"
    assert out["lat"] == 33.02 and out["lng"] == -96.7
    assert out["address_full"] == "100 Main St"
    assert out["city"] == "Plano"                  # filled from the result (input city was blank)
    assert out["website"] == "https://x.com" and out["phone"] == "+1 555"
    assert out["hours"] == "Mo-Su 11:00-21:00"


def test_parse_place_falls_back_to_typed_input():
    assert onboard._parse_place(None, "Spice Hut", "Plano", "TX") == {
        "name": "Spice Hut", "city": "Plano", "state": "TX"}


def test_portal_add_requires_login():
    r = TestClient(app).get("/portal/add", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/portal/login" in r.headers["location"]


def test_onboarding_prefills_then_submits(monkeypatch):
    monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
    monkeypatch.setattr(portal.onboard, "lookup",
                        lambda name, city, state, vertical=None: {
                            "name": name, "city": city, "state": state, "address_full": "100 Main St",
                            "phone": "+1 555", "website": "https://x.com", "photo_url": "http://img/p.jpg"})
    c = TestClient(app)
    r = c.post("/portal/add", data={"vertical": "restaurants", "name": "Spice Hut",
                                    "state": "TX", "city": "Plano"})
    assert r.status_code == 200
    assert "Verify Spice Hut" in r.text
    assert "100 Main St" in r.text                 # prefilled from the lookup
    assert "http://img/p.jpg" in r.text            # photo preview

    captured = {}
    monkeypatch.setattr(portal.submissions, "submit",
                        lambda v, payload, contact_email=None, note=None:
                        captured.update(v=v, payload=payload, email=contact_email) or {"ok": True})
    r2 = c.post("/portal/add/confirm",
                data={"vertical": "restaurants", "name": "Spice Hut", "address_full": "100 Main St",
                      "city": "Plano", "state": "TX", "phone": "+1 555", "website": "https://x.com",
                      "hours": "Mon-Sun 11-9", "languages": "Telugu"}, follow_redirects=False)
    assert r2.status_code == 303 and "added=1" in r2.headers["location"]
    assert captured["email"] == "owner@example.com"
    assert captured["payload"]["name"] == "Spice Hut"
    assert captured["payload"]["hours_json"] == {"raw": "Mon-Sun 11-9"}


def test_owner_can_delete_own_submission(monkeypatch):
    monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
    captured = {}
    monkeypatch.setattr(portal.submissions, "delete_for_owner",
                        lambda sid, email: captured.update(sid=sid, email=email) or {"ok": True})
    r = TestClient(app).post("/portal/submission/7/delete", follow_redirects=False)
    assert r.status_code == 303
    assert captured == {"sid": 7, "email": "owner@example.com"}
