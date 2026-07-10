"""onboard.ai_fill: LLM structured field-fill for onboarding — grounded, allow-listed, degrade-safe.
Also lookup()'s new website preference. Pure/mocked — no network.

onboard imports assistant/verticals/web_enrich/geocode LAZILY inside functions (`from . import ...`),
so tests patch the REAL modules' attributes, not `onboard.<name>` (which the lazy import shadows)."""

import indo_usa_mcp.onboard as onboard


def _mock_llm(monkeypatch, *, active=True, reply=None, capture=None):
    monkeypatch.setattr("indo_usa_mcp.assistant.llm_active", lambda: active)

    def complete_text(system, user):
        if capture is not None:
            capture["system"], capture["user"] = system, user
        return reply
    monkeypatch.setattr("indo_usa_mcp.assistant.complete_text", complete_text)


def test_ai_fill_noop_when_llm_inactive(monkeypatch):
    _mock_llm(monkeypatch, active=False)
    rec = {"name": "Spice Hut", "city": "Plano", "state": "TX"}
    assert onboard.ai_fill("restaurants", dict(rec)) == rec


def test_ai_fill_only_targets_missing_categorical_fields(monkeypatch):
    cap = {}
    _mock_llm(monkeypatch, reply='{"cuisine_type": "South Indian", "price_range": "$$"}', capture=cap)
    rec = {"name": "Dosa Place", "city": "Plano", "state": "TX", "phone": "", "website": ""}
    out = onboard.ai_fill("restaurants", rec)
    assert out["cuisine_type"] == "South Indian" and out["price_range"] == "$$"
    # SAFETY: the prompt must NEVER ask the model to invent contact/location facts.
    for banned in ("phone", "email", "website", "address_full", "menu_url"):
        assert f"- {banned}:" not in cap["user"], banned
    assert "- cuisine_type:" in cap["user"]


def test_ai_fill_drops_hallucinated_extra_keys(monkeypatch):
    _mock_llm(monkeypatch, reply='{"cuisine_type": "Gujarati", "phone": "555-0000", "website": "http://evil"}')
    out = onboard.ai_fill("restaurants", {"name": "X", "city": "Y", "state": "TX"})
    assert out["cuisine_type"] == "Gujarati"
    assert "phone" not in out and "website" not in out    # unrequested keys never merged


def test_ai_fill_degrades_on_malformed_json(monkeypatch):
    _mock_llm(monkeypatch, reply="sorry, I can't do that")
    rec = {"name": "X", "city": "Y", "state": "TX"}
    assert onboard.ai_fill("restaurants", dict(rec)) == rec   # unchanged, no exception


def test_ai_fill_strips_markdown_fences(monkeypatch):
    _mock_llm(monkeypatch, reply='```json\n{"cuisine_type": "Punjabi"}\n```')
    out = onboard.ai_fill("restaurants", {"name": "X", "city": "Y", "state": "TX"})
    assert out["cuisine_type"] == "Punjabi"


def test_ai_fill_skips_llm_when_nothing_missing(monkeypatch):
    def boom(system, user):
        raise AssertionError("LLM must not be called when nothing is missing")
    monkeypatch.setattr("indo_usa_mcp.assistant.llm_active", lambda: True)
    monkeypatch.setattr("indo_usa_mcp.assistant.complete_text", boom)
    # every categorical field for groceries present, incl. dietary (has_dietary) + languages -> no call
    rec = {"name": "Patel Bros", "city": "Edison", "state": "NJ", "store_type": "grocery",
           "region_tag": "Gujarati", "festival_specials": "Diwali sweets", "languages": "Hindi",
           "dietary_tags": ["vegetarian"]}
    onboard.ai_fill("groceries", rec)   # boom never fires


def test_lookup_prefers_typed_website(monkeypatch):
    monkeypatch.setattr(onboard, "_nominatim_place", lambda n, c, s: None)   # OSM finds nothing
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return {"site_description": "Authentic South Indian tiffin.", "cuisine_tags": ["south indian"]}
    monkeypatch.setattr("indo_usa_mcp.web_enrich._fetch_and_extract", fake_fetch)
    monkeypatch.setattr("indo_usa_mcp.geocode.coords_for", lambda *a, **k: None)

    out = onboard.lookup("Tiffins", "Plano", "TX", "restaurants", website="https://tiffins.example")
    assert captured["url"] == "https://tiffins.example"
    assert out["website"] == "https://tiffins.example"
    assert out["site_description"] == "Authentic South Indian tiffin."
    assert out["cuisine_type"] == "South Indian"          # from cuisine_tags, title-cased
