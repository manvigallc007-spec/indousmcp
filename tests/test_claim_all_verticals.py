"""All-vertical claim funnel: the claim mechanism (create/status/verify/owner_listing) generalized to
any vertical with restaurant back-compat, the self-serve /claim/start flow, and portal ownership.
Real dev DB, ZZTEST rows, try/finally."""

from starlette.testclient import TestClient

from indo_usa_mcp import db, verticals
from indo_usa_mcp.pipeline import outreach
from indo_usa_mcp.web import portal
from indo_usa_mcp.web.app import app

_client = TestClient(app)


def _mk(vertical, name, **extra):
    payload = {"name": name, "city": "Plano", "state": "TX", "lat": 33.0, "lng": -96.7}
    payload.update(extra)
    return verticals.create_record(vertical, payload, source="test")["id"]


def _cleanup(vertical, rid):
    db.execute("DELETE FROM claims WHERE vertical=%s AND record_id=%s", (vertical, rid))
    db.execute(f"DELETE FROM {verticals._table(vertical)} WHERE id=%s", (rid,))


# --------------------------------------------------------------- claim mechanism (non-restaurant)
def test_claim_mechanism_for_temple():
    tid = _mk("temples", "ZZTEST Claim Temple")
    try:
        claim = outreach.create_claim(tid, "form", "pujari@t.org", vertical="temples")
        assert claim["vertical"] == "temples" and claim["record_id"] == tid and "token=" in claim["claim_link"]
        st = outreach.claim_status(claim["token"])
        assert st["vertical"] == "temples" and st["listing_name"] == "ZZTEST Claim Temple"
        assert st["restaurant_id"] == tid                       # back-compat alias
        res = outreach.verify_claim(claim["token"], owner_email="OWNER@T.org")
        assert res["ok"] and res["vertical"] == "temples" and res["record_id"] == tid
        assert db.query_one("SELECT is_claimed FROM temples WHERE id=%s", (tid,))["is_claimed"] is True
        assert outreach.owner_listing(claim["token"])["name"] == "ZZTEST Claim Temple"
        # email normalized + re-claim blocked
        assert db.query_one("SELECT owner_email FROM claims WHERE token=%s", (claim["token"],))["owner_email"] == "owner@t.org"
        assert outreach.verify_claim(claim["token"])["error"] == "claim_claimed"
    finally:
        _cleanup("temples", tid)


def test_restaurant_claim_back_compat():
    rid = _mk("restaurants", "ZZTEST Claim Resto")
    try:
        claim = outreach.create_claim(rid, "email", "a@b.com")     # default vertical = restaurants
        row = db.query_one("SELECT restaurant_id, vertical, record_id FROM claims WHERE token=%s", (claim["token"],))
        assert row["restaurant_id"] == rid and row["vertical"] == "restaurants" and row["record_id"] == rid
        assert outreach.verify_claim(claim["token"], owner_email="a@b.com")["ok"]
        assert db.query_one("SELECT is_claimed FROM restaurants WHERE id=%s", (rid,))["is_claimed"] is True
    finally:
        _cleanup("restaurants", rid)


def test_owned_includes_claims_across_verticals():
    email = "zztest_multi_owner@example.com"
    tid = _mk("temples", "ZZTEST Owned Temple")
    sid = _mk("salons", "ZZTEST Owned Salon")
    try:
        for v, rid in (("temples", tid), ("salons", sid)):
            outreach.verify_claim(outreach.create_claim(rid, "form", vertical=v)["token"], owner_email=email)
        owned = {(o["vertical"], o["id"]) for o in portal._owned(email)}
        assert ("temples", tid) in owned and ("salons", sid) in owned
    finally:
        db.execute("DELETE FROM claims WHERE owner_email=%s", (email,))
        _cleanup("temples", tid)
        _cleanup("salons", sid)


# --------------------------------------------------------------- self-serve /claim/start
def test_claim_start_with_on_file_email_creates_claim():
    gid = _mk("groceries", "ZZTEST Start Grocery", email="owner@g.com")
    try:
        html = _client.get(f"/claim/start/groceries/{gid}").text
        assert "/claim?token=" in html                          # dev inline verify link (no SMTP)
        assert db.query_one("SELECT count(*) AS n FROM claims WHERE vertical='groceries' AND record_id=%s",
                            (gid,))["n"] == 1
    finally:
        _cleanup("groceries", gid)


def test_claim_start_without_email_routes_to_contact():
    gid = _mk("groceries", "ZZTEST No Email Grocery")             # no email on file
    try:
        html = _client.get(f"/claim/start/groceries/{gid}").text
        assert "contact us" in html.lower() and "/contact" in html
        assert db.query_one("SELECT count(*) AS n FROM claims WHERE vertical='groceries' AND record_id=%s",
                            (gid,))["n"] == 0                     # no claim created without a verify path
    finally:
        _cleanup("groceries", gid)


def test_claim_start_already_claimed():
    gid = _mk("groceries", "ZZTEST Claimed Grocery", email="o@g.com")
    verticals.set_claimed("groceries", gid, True)
    try:
        assert "already claimed" in _client.get(f"/claim/start/groceries/{gid}").text.lower()
    finally:
        _cleanup("groceries", gid)


# --------------------------------------------------------------- web verify -> portal
def test_claim_post_signs_in_and_redirects_to_manage():
    sid = _mk("sweets", "ZZTEST Claim Sweets", email="o@s.com")
    try:
        tok = outreach.create_claim(sid, "form", "o@s.com", vertical="sweets")["token"]
        r = _client.post("/claim", data={"token": tok, "email": "o@s.com"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/portal/listing/sweets/{sid}"
        assert db.query_one("SELECT is_claimed FROM sweets WHERE id=%s", (sid,))["is_claimed"] is True
    finally:
        _cleanup("sweets", sid)


def test_listing_shows_claim_cta_only_when_unclaimed():
    aid = _mk("apparel", "ZZTEST Claim Apparel")
    try:
        assert "Own this business? Claim it" in _client.get(f"/listing/apparel/{aid}").text
        verticals.set_claimed("apparel", aid, True)
        assert "Own this business? Claim it" not in _client.get(f"/listing/apparel/{aid}").text
    finally:
        _cleanup("apparel", aid)
