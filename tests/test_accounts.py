"""Business registration: password hashing, purpose tokens, captcha, and form validation (items 6,7).
Pure logic + page renders + pre-DB validation paths — no live DB needed."""

import re

from starlette.testclient import TestClient

import indo_usa_mcp.web.auth as auth
import indo_usa_mcp.web.portal as portal
from indo_usa_mcp.config import settings
from indo_usa_mcp.web.app import app

c = TestClient(app)


def test_password_hash_roundtrip():
    h = auth.hash_password("hunter2pass")
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_password("hunter2pass", h) is True
    assert auth.verify_password("wrongpass", h) is False
    assert auth.verify_password("x", "not-a-valid-hash") is False


def test_action_token_purpose_bound_and_expiring():
    t = auth.make_action_token("a@b.com", "verify", 60)
    assert auth.verify_action_token(t, "verify") == "a@b.com"
    assert auth.verify_action_token(t, "reset") is None          # a verify token != a reset token
    assert auth.verify_action_token(auth.make_action_token("a@b.com", "verify", -1), "verify") is None
    assert auth.verify_action_token("garbage", "verify") is None


def test_math_captcha(monkeypatch):
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", "")
    ch = auth.make_captcha()
    a, b = map(int, re.findall(r"\d+", ch["question"]))
    assert auth.verify_captcha({"captcha_token": ch["token"], "captcha": str(a + b)}) is True
    assert auth.verify_captcha({"captcha_token": ch["token"], "captcha": str(a + b + 1)}) is False
    assert auth.verify_captcha({"captcha_token": "bad", "captcha": "5"}) is False


def test_registration_pages_render():
    assert c.get("/portal/register").status_code == 200
    t = c.get("/portal/register").text
    assert "Create account" in t and "Terms" in t and "What is" in t   # T&C + math captcha shown
    assert c.get("/portal/forgot").status_code == 200
    assert c.get("/portal/reset?t=bad").status_code == 401             # invalid reset token rejected


def test_register_rejects_missing_terms_and_bad_captcha():
    base = {"email": "x@y.com", "password": "12345678", "password2": "12345678"}
    # no T&C acceptance -> 400 (checked before any DB write)
    assert c.post("/portal/register", data={**base, "captcha": "5", "captcha_token": "bad"}).status_code == 400
    # accepted T&C but bad captcha -> 400
    assert c.post("/portal/register",
                  data={**base, "accept": "1", "captcha": "0", "captcha_token": "bad"}).status_code == 400


def test_register_happy_path_sends_verification(monkeypatch):
    created = {}

    def fake_create(e, p):
        created["email"] = e
        return {"ok": True}
    monkeypatch.setattr(portal, "verify_captcha", lambda form: True)
    monkeypatch.setattr(portal, "create_user", fake_create)
    r = c.post("/portal/register", data={"email": "new@user.com", "password": "12345678",
                                         "password2": "12345678", "accept": "1",
                                         "captcha": "5", "captcha_token": "x"})
    assert r.status_code == 200 and "check your email" in r.text.lower()
    assert created["email"] == "new@user.com"
