"""Contact form replaces email addresses (item 1) + inbox/draft (item 2). No live DB needed."""

from starlette.testclient import TestClient

import indo_usa_mcp.inbox as inbox
from indo_usa_mcp.web import pages
from indo_usa_mcp.web.app import app

c = TestClient(app)


def test_contact_page_is_a_form_without_email():
    t = c.get("/contact").text
    assert "<form" in t and "Send message" in t
    assert "What is" in t or "cf-turnstile" in t        # captcha present
    assert "mailto:" not in t


def test_no_mailto_anywhere_public():
    for path in ("/contact", "/privacy", "/terms", "/about", "/faq"):
        assert "mailto:" not in c.get(path).text, path


def test_contact_post_rejects_bad_captcha():
    r = c.post("/contact", data={"email": "a@b.com", "body": "hi there",
                                 "captcha": "0", "captcha_token": "bad"})
    assert r.status_code == 400


def test_contact_post_honeypot_silently_accepts(monkeypatch):
    stored = []
    monkeypatch.setattr(pages.inbox, "create_message", lambda *a, **k: stored.append(a) or {"ok": True})
    r = c.post("/contact", data={"email": "a@b.com", "body": "spam", "website": "bot-filled-this"})
    assert r.status_code == 200 and not stored      # honeypot tripped -> not stored


def test_contact_post_stores_valid_message(monkeypatch):
    stored = {}

    def fake_create(name, email, subject, body, ip=None):
        stored.update(email=email, body=body)
        return {"ok": True, "id": 1}
    monkeypatch.setattr(pages, "verify_captcha", lambda form: True)
    monkeypatch.setattr(pages.inbox, "create_message", fake_create)
    r = c.post("/contact", data={"name": "Asha", "email": "asha@example.com", "subject": "Hi",
                                 "body": "Please add my temple", "captcha": "5", "captcha_token": "x"})
    assert r.status_code == 200 and "received" in r.text.lower()
    assert stored["email"] == "asha@example.com"


def test_compose_draft_none_without_llm():
    # default config has no LLM -> drafting returns None (admin writes the reply manually)
    assert inbox.compose_draft({"name": "X", "subject": "Y", "body": "Z"}) is None


def test_admin_messages_requires_login():
    r = c.get("/admin/messages", follow_redirects=False)
    assert r.status_code in (302, 303)
