"""Anti-spam / CAN-SPAM hardening: opt-out tokens, message shape, gate, /optout route. No DB."""

from starlette.testclient import TestClient

from indo_usa_mcp.config import settings
from indo_usa_mcp.pipeline import compliance, outreach
from indo_usa_mcp.web import app


def test_normalize_contact():
    assert compliance.normalize_contact("  Owner@Example.COM ") == "owner@example.com"
    assert compliance.normalize_contact("+1 (732) 555-0100") == "17325550100"


def test_opt_out_token_roundtrip_and_tamper():
    c = "owner@example.com"
    tok = compliance.opt_out_token(c)
    assert compliance.verify_opt_out(c, tok)
    assert not compliance.verify_opt_out(c, tok[:-1] + "x")     # tampered
    assert not compliance.verify_opt_out("other@example.com", tok)  # wrong contact
    assert not compliance.verify_opt_out(c, "")
    # case-insensitive: same token for differently-cased email
    assert compliance.verify_opt_out("Owner@Example.com", tok)


def test_opt_out_link_has_contact_and_signature():
    link = compliance.opt_out_link("owner@example.com")
    assert "/optout?" in link and "c=owner%40example.com" in link and "t=" in link


def test_draft_message_includes_unsubscribe_and_postal(monkeypatch):
    monkeypatch.setattr(settings, "outreach_postal_address", "123 Main St, Edison, NJ 08820")
    msg = outreach.draft_message(
        {"name": "Spice Hub", "city": "Edison"},
        "https://x/claim?token=abc", "email", opt_out_url="https://x/optout?c=a&t=b")
    assert "Unsubscribe instantly: https://x/optout?c=a&t=b" in msg
    assert "123 Main St, Edison, NJ 08820" in msg           # CAN-SPAM postal address
    assert "Spice Hub" in msg


def test_draft_message_falls_back_to_reply_optout_without_link():
    msg = outreach.draft_message({"name": "X"}, "https://x/claim", "email")
    assert "reply and we'll remove you" in msg


def test_compliance_gate_blocks_until_smtp_and_postal(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", ""); monkeypatch.setattr(settings, "outreach_postal_address", "")
    assert settings.outreach_compliant is False
    # SMTP alone is not enough — postal address is still required.
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "u"); monkeypatch.setattr(settings, "smtp_password", "p")
    assert settings.email_enabled is True and settings.outreach_compliant is False
    monkeypatch.setattr(settings, "outreach_postal_address", "1 A St, NJ")
    assert settings.outreach_compliant is True


def test_optout_route_rejects_bad_signature():
    r = TestClient(app).get("/optout?c=owner@example.com&t=forged")
    assert r.status_code == 400 and "Invalid unsubscribe" in r.text
