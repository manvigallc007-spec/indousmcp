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


def test_llm_search_provider_is_disabled_by_default():
    s = Settings(_env_file=None)
    assert s.llm_provider == "search" and s.llm_enabled is False


def test_groq_preset_fills_base_url_model_and_tools():
    s = Settings(llm_provider="groq", _env_file=None)
    assert s.llm_enabled is True
    assert s.effective_llm_base_url == "https://api.groq.com/openai/v1"
    assert s.effective_llm_model == "llama-3.3-70b-versatile"
    assert s.effective_llm_use_tools is True


def test_ollama_preset_uses_grounded_mode():
    s = Settings(llm_provider="ollama", _env_file=None)
    assert s.effective_llm_base_url.endswith(":11434/v1")
    assert s.effective_llm_use_tools is False


def test_explicit_env_overrides_preset():
    # An explicitly-set model must win over the preset's default.
    s = Settings(llm_provider="groq", llm_model="llama-3.1-8b-instant", _env_file=None)
    assert s.effective_llm_model == "llama-3.1-8b-instant"
    assert s.effective_llm_base_url == "https://api.groq.com/openai/v1"  # still from preset


def test_blank_env_values_fall_back_to_preset():
    # Compose injects empty LLM_BASE_URL/LLM_MODEL defaults; blank must mean "use the preset".
    s = Settings(llm_provider="groq", llm_base_url="", llm_model="", _env_file=None)
    assert s.effective_llm_base_url == "https://api.groq.com/openai/v1"
    assert s.effective_llm_model == "llama-3.3-70b-versatile"


def test_custom_llm_provider_uses_explicit_fields():
    s = Settings(llm_provider="llm", llm_base_url="http://my-host/v1", llm_model="x", _env_file=None)
    assert s.llm_enabled is True
    assert s.effective_llm_base_url == "http://my-host/v1" and s.effective_llm_model == "x"


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
