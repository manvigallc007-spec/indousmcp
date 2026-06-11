"""Tests for the password-safe DB URL and feedback validation (no DB)."""

from indo_usa_mcp.config import Settings
from indo_usa_mcp.pipeline import feedback


def test_password_special_chars_are_url_encoded():
    s = Settings(database_url="", postgres_password="p@ss#/:rd",
                 postgres_host="db", postgres_port=5432, _env_file=None)
    url = s.effective_database_url
    # @ # / : in the password must be percent-encoded, not break the URL structure.
    assert "p%40ss%23%2F%3Ard" in url
    assert url.startswith("postgresql://diaspora:")
    assert url.endswith("@db:5432/diaspora")


def test_explicit_database_url_takes_precedence():
    s = Settings(database_url="postgresql://x:y@h:1/d", _env_file=None)
    assert s.effective_database_url == "postgresql://x:y@h:1/d"


def test_feedback_rejects_non_correctable_field():
    # Identity fields aren't correctable; this returns before touching the DB.
    res = feedback.submit_correction(1, "name", "Hacked Name")
    assert res["ok"] is False
    assert res["error"] == "field_not_correctable"
    assert "name" not in res["allowed"]


def test_feedback_correctable_fields_are_scalar_safe():
    assert "phone" in feedback.CORRECTABLE_FIELDS
    assert "region_tag" in feedback.CORRECTABLE_FIELDS
    # Identity / structured fields must never be auto-correctable.
    for forbidden in ("name", "lat", "lng", "natural_key", "dietary_tags", "hours_json"):
        assert forbidden not in feedback.CORRECTABLE_FIELDS
