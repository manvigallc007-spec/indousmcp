"""Phase 1 consumer accounts: profile, saved places, follows, the /me hub, and the ♡ Save toggle on
listing pages. Real dev DB, ZZTEST rows, try/finally; login simulated by monkeypatching portal_email."""

import indo_usa_mcp.embeddings as emb
from indo_usa_mcp import accounts, db, verticals
from indo_usa_mcp.web import me as me_mod
from indo_usa_mcp.web import reviews as reviews_mod
from indo_usa_mcp.web.app import app
from starlette.testclient import TestClient

_client = TestClient(app)
_E = "zztest_p1@example.com"


def _mk_listing(name="ZZTEST P1 Place"):
    db.execute("DELETE FROM restaurants WHERE name=%s", (name,))
    return verticals.create_record("restaurants", {"name": name, "city": "Plano", "state": "TX",
                                                   "lat": 33.0, "lng": -96.7}, source="test")["id"]


def _cleanup(rid=None):
    for t in ("user_profiles", "saved_places", "follows"):
        db.execute(f"DELETE FROM {t} WHERE email=%s", (_E,))
    if rid:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- accounts.py helpers
def test_profile_upsert_normalizes_and_clamps():
    try:
        p = accounts.upsert_profile(_E, home_city="Plano", home_state="tx",
                                    languages=["Telugu", " ", "English"],
                                    followed_verticals=["restaurants", "bogus"], digest_freq="hourly")
        assert p["home_state"] == "TX"
        assert p["languages"] == ["Telugu", "English"]        # blanks dropped
        assert p["followed_verticals"] == ["restaurants"]     # unknown vertical dropped
        assert p["digest_freq"] == "weekly"                   # invalid freq clamped
        # upsert is idempotent-replace
        p2 = accounts.upsert_profile(_E, home_city="Edison", home_state="NJ")
        assert p2["home_city"] == "Edison" and p2["home_state"] == "NJ"
    finally:
        _cleanup()


def test_save_place_verifies_listing_and_is_idempotent():
    rid = _mk_listing()
    try:
        assert accounts.save_place(_E, "restaurants", rid)["ok"]
        assert accounts.save_place(_E, "restaurants", rid)["ok"]     # dup -> no error
        assert accounts.is_saved(_E, "restaurants", rid)
        assert accounts.save_place(_E, "nope", rid)["error"] == "bad_vertical"
        assert accounts.save_place(_E, "restaurants", 999_999_999)["error"] == "not_found"
        saved = accounts.list_saved(_E)
        assert len(saved) == 1 and saved[0]["name"] == "ZZTEST P1 Place"
        accounts.unsave_place(_E, "restaurants", rid)
        assert not accounts.is_saved(_E, "restaurants", rid)
    finally:
        _cleanup(rid)


def test_follow_validates_kind_and_vertical():
    try:
        assert accounts.follow(_E, "city", "Plano, TX")["ok"]
        assert accounts.follow(_E, "vertical", "temples")["ok"]
        assert accounts.follow(_E, "vertical", "bogus")["error"] == "bad_vertical"
        assert accounts.follow(_E, "planet", "mars")["error"] == "bad_follow"
        vals = {(f["kind"], f["value"]) for f in accounts.list_follows(_E)}
        assert ("city", "Plano, TX") in vals and ("vertical", "temples") in vals
        accounts.unfollow(_E, "city", "Plano, TX")
        assert ("city", "Plano, TX") not in {(f["kind"], f["value"]) for f in accounts.list_follows(_E)}
    finally:
        _cleanup()


# --------------------------------------------------------------- /me routes
def test_me_requires_login():
    r = _client.get("/me", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me/login"


def test_me_home_and_prefs_roundtrip(monkeypatch):
    monkeypatch.setattr(me_mod, "portal_email", lambda req: _E)
    try:
        r = _client.post("/me/prefs", data={"display_name": "Manvi", "home_city": "Plano",
                                            "home_state": "TX", "languages": "Telugu, English",
                                            "followed_verticals": ["restaurants", "temples"],
                                            "notify_email": "1", "digest_freq": "daily"},
                         follow_redirects=False)
        assert r.status_code == 303 and "/me?ok=1" in r.headers["location"]
        prof = accounts.get_profile(_E)
        assert prof["display_name"] == "Manvi" and prof["digest_freq"] == "daily"
        assert set(prof["followed_verticals"]) == {"restaurants", "temples"}
        html = _client.get("/me").text
        assert "Manvi" in html and "Telugu, English" in html
    finally:
        _cleanup()


def test_me_save_and_unsave_via_routes(monkeypatch):
    monkeypatch.setattr(me_mod, "portal_email", lambda req: _E)
    rid = _mk_listing()
    try:
        r = _client.post("/me/save", data={"vertical": "restaurants", "id": str(rid),
                                           "next": f"/listing/restaurants/{rid}"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/listing/restaurants/{rid}"
        assert accounts.is_saved(_E, "restaurants", rid)
        _client.post("/me/unsave", data={"vertical": "restaurants", "id": str(rid)}, follow_redirects=False)
        assert not accounts.is_saved(_E, "restaurants", rid)
    finally:
        _cleanup(rid)


def test_me_save_rejects_open_redirect(monkeypatch):
    monkeypatch.setattr(me_mod, "portal_email", lambda req: _E)
    rid = _mk_listing()
    try:
        r = _client.post("/me/save", data={"vertical": "restaurants", "id": str(rid),
                                           "next": "https://evil.example.com"}, follow_redirects=False)
        assert r.headers["location"] == "/me"          # external next rejected -> safe fallback
    finally:
        _cleanup(rid)


# --------------------------------------------------------------- ♡ Save toggle on the listing page
def test_listing_save_button_toggles_for_signed_in_user(monkeypatch):
    monkeypatch.setattr(reviews_mod, "portal_email", lambda req: _E)
    rid = _mk_listing()
    try:
        html = _client.get(f"/listing/restaurants/{rid}").text
        assert "♡ Save" in html and "/me/save" in html          # not saved yet
        accounts.save_place(_E, "restaurants", rid)
        html2 = _client.get(f"/listing/restaurants/{rid}").text
        assert "♥ Saved" in html2 and "/me/unsave" in html2     # now shows saved state
    finally:
        _cleanup(rid)
