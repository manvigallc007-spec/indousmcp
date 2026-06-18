"""Hindi/Telugu requests are normalized to English for search + topic routing (replies stay
in-language via the LLM). Telugu/Hindi strings are built from codepoints so the test source is
pure ASCII and immune to console/encoding mangling. No live DB or network."""

import indo_usa_mcp.assistant as a

# Telugu "నాకు బిర్యానీ" (~"I want biryani") and Hindi "मुझे मंदिर" (~"I want a temple").
TEL = "".join(chr(c) for c in (0x0C28, 0x0C3E, 0x0C15, 0x0C41, 0x20, 0x0C2C, 0x0C3F))
HIN = "".join(chr(c) for c in (0x092E, 0x0941, 0x091D, 0x0947))


def test_has_indic_detects_script():
    assert a._has_indic(TEL) is True
    assert a._has_indic(HIN) is True
    assert a._has_indic("biryani near plano") is False
    assert a._has_indic("") is False


def test_english_passthrough_for_ascii_and_english_lang():
    # English text stays untouched even when language is Telugu (don't double-translate).
    assert a._english("biryani near plano", {"lang": "te"}) == "biryani near plano"
    # If the user selected English we never translate, even if the text were non-English.
    assert a._english(TEL, {"lang": "en"}) == TEL
    assert a._english("dosa", {}) == "dosa"


def test_english_translates_native_script(monkeypatch):
    # default config has no LLM -> uses the key-less fallback (stubbed here, no network)
    monkeypatch.setattr(a, "_mymemory_en", lambda text, src: "biryani restaurant")
    a._XLATE_CACHE.clear()
    assert a._english(TEL, {"lang": "te"}) == "biryani restaurant"


def test_run_search_searches_in_english(monkeypatch):
    captured = {}
    monkeypatch.setattr(a, "_mymemory_en", lambda text, src: "biryani restaurant")
    monkeypatch.setattr(a, "_guess_vertical", lambda q: None)          # force the search_all path
    monkeypatch.setattr(a.verticals, "search_all",
                        lambda q, **k: captured.update(q=q) or {"results": [], "count": 0})
    a._XLATE_CACHE.clear()
    a._run_search({"query": TEL}, {"lang": "te"})
    assert captured["q"] == "biryani restaurant"                       # Telugu -> English before search


def test_translate_prefers_llm_when_active(monkeypatch):
    monkeypatch.setattr(a, "llm_active", lambda: True)
    monkeypatch.setattr(a, "complete_text", lambda system, user: "temple near me")
    a._XLATE_CACHE.clear()
    assert a._translate_to_english(HIN, "hi") == "temple near me"


def test_romanized_telugu_interpreted_via_llm(monkeypatch):
    # STT often returns ROMANIZED Telugu (Latin letters), not native script -> the LLM interprets it.
    monkeypatch.setattr(a, "llm_active", lambda: True)
    monkeypatch.setattr(a, "complete_text", lambda system, user: "biryani in plano")
    a._XLATE_CACHE.clear()
    assert a._english("naaku plano lo biryani kavali", {"lang": "te"}) == "biryani in plano"


def test_romanized_passthrough_without_llm(monkeypatch):
    # No LLM -> can't interpret romanized input; leave it untouched (no MyMemory on Latin text).
    monkeypatch.setattr(a, "llm_active", lambda: False)
    a._XLATE_CACHE.clear()
    assert a._english("naaku biryani", {"lang": "te"}) == "naaku biryani"
