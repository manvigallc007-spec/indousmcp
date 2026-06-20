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
