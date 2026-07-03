"""Hindi/Telugu requests are normalized to English for search + topic routing (replies stay
in-language via the LLM). Telugu/Hindi strings are built from codepoints so the test source is
pure ASCII and immune to console/encoding mangling. No live DB or network."""

import re

import indo_usa_mcp.assistant as a

# Telugu "నాకు బిర్యానీ" (~"I want biryani") and Hindi "मुझे मंदिर" (~"I want a temple").
TEL = "".join(chr(c) for c in (0x0C28, 0x0C3E, 0x0C15, 0x0C41, 0x20, 0x0C2C, 0x0C3F))
HIN = "".join(chr(c) for c in (0x092E, 0x0941, 0x091D, 0x0947))
# Telugu "దోసె" (dosa) and the real query "నాకు దోసె కావాలి" (~"I want dosa") that was observed, in
# production, mistranslated to "I need a dosage" by BOTH the LLM and the key-less MyMemory fallback
# -- a total zero-result miss (38 occurrences in analytics.top_misses). See _KNOWN_CORRECTIONS.
DOSA_TE = "".join(chr(c) for c in (0x0C26, 0x0C4B, 0x0C38, 0x0C46))
DOSA_QUERY_TE = "".join(chr(c) for c in (
    0x0C28, 0x0C3E, 0x0C15, 0x0C41, 0x20, 0x0C26, 0x0C4B, 0x0C38, 0x0C46, 0x20,
    0x0C15, 0x0C3E, 0x0C35, 0x0C3E, 0x0C32, 0x0C3F))


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


def test_reply_feeds_english_to_engine(monkeypatch):
    # THE FIX: a Telugu request -> the LLM engine receives the ENGLISH translation (so its tool
    # search is reliable), not the raw Telugu. Reply language is handled separately by _lang_note.
    monkeypatch.setattr(a, "_needs_location", lambda *args, **k: False)
    monkeypatch.setattr(a, "llm_active", lambda: True)
    monkeypatch.setattr(a, "_english", lambda text, filters: "biryani in plano")
    monkeypatch.setattr(a, "_is_knowledge_question", lambda q, f: False)
    monkeypatch.setattr(a, "_thin_contribute", lambda *args, **k: None)
    monkeypatch.setattr(a, "_localize", lambda t, lang: t)   # reply-language handled separately below
    captured = {}

    def fake_engine(messages, geo, filters):
        captured["text"] = messages[-1]["content"]
        return {"reply": "ok", "cards": [{"name": "X"}], "provider": "llm"}
    monkeypatch.setattr(a, "_llm_reply", fake_engine)
    monkeypatch.setattr(a, "_grounded_reply", fake_engine)
    a.reply([{"role": "user", "content": TEL}], filters={"lang": "te"})
    assert captured["text"] == "biryani in plano"            # engine got English, not Telugu


# --- reply LANGUAGE: every branch is localized back to the user's choice (the reported bug) ---
def test_localize_passthrough(monkeypatch):
    # English target, empty text, or text already in native script -> unchanged (no translate call).
    monkeypatch.setattr(a, "complete_text",
                        lambda *x: (_ for _ in ()).throw(AssertionError("must not translate")))
    assert a._localize("Here are 5 places.", "en") == "Here are 5 places."
    assert a._localize("", "te") == ""
    assert a._localize(TEL, "te") == TEL                     # already Telugu script -> left as-is


def test_localize_translates_english_via_llm(monkeypatch):
    monkeypatch.setattr(a, "complete_text", lambda system, user: chr(0x0C28) + user)  # -> Telugu script
    a._XLATE_CACHE.clear()
    out = a._localize("Top H-1B sponsors in TX.", "te")
    assert a._has_indic(out)                                 # reply came back in Telugu script


def test_localize_falls_back_to_mymemory_without_llm(monkeypatch):
    monkeypatch.setattr(a, "complete_text", lambda *x: None)             # LLM inactive
    monkeypatch.setattr(a, "_mymemory_from_en", lambda text, tgt: f"[{tgt}]{text}")
    a._XLATE_CACHE.clear()
    assert a._localize("No results found.", "hi") == "[hi]No results found."


def test_reply_localizes_every_branch(monkeypatch):
    # THE FIX: whatever branch built the (English) reply, reply() localizes the visible text.
    monkeypatch.setattr(a, "_reply_impl",
                        lambda m, g, f: {"reply": "Top H-1B sponsors in TX.", "cards": []})
    monkeypatch.setattr(a, "_localize", lambda text, lang: f"<{lang}>{text}")
    out = a.reply([{"role": "user", "content": "x"}], filters={"lang": "te"})
    assert out["reply"] == "<te>Top H-1B sponsors in TX."


def test_reply_does_not_localize_english(monkeypatch):
    monkeypatch.setattr(a, "_reply_impl", lambda m, g, f: {"reply": "Hello", "cards": []})
    called = []
    monkeypatch.setattr(a, "_localize", lambda text, lang: called.append(1) or text)
    out = a.reply([{"role": "user", "content": "x"}], filters={"lang": "en"})
    assert out["reply"] == "Hello" and not called            # English selected -> never localized


# --- known-translation-error correction (a real observed miss: దోసె "dosa" -> "dosage") ---
def test_apply_known_corrections_fixes_the_observed_mistranslation():
    out = a._apply_known_corrections(DOSA_QUERY_TE, "I need a dosage")
    assert re.search(r"\bdosa\b", out)                       # "dosa" now present as its own word


def test_apply_known_corrections_word_boundary_not_fooled_by_dosage():
    # "dosa" is literally a SUBSTRING of "dosage" -- a naive `in` check would wrongly conclude the
    # correction was already applied and skip it. This is the exact bug caught during verification.
    out = a._apply_known_corrections(DOSA_QUERY_TE, "I need a dosage")
    assert out.lower().count("dosa") >= 1 and out != "I need a dosage"   # correction WAS applied


def test_apply_known_corrections_noop_when_already_correct():
    out = a._apply_known_corrections(DOSA_QUERY_TE, "I want a dosa restaurant")
    assert out == "I want a dosa restaurant"                 # already right -> untouched


def test_apply_known_corrections_noop_when_term_absent():
    out = a._apply_known_corrections(TEL, "I need a dosage")  # unrelated Telugu text (biryani)
    assert out == "I need a dosage"                          # no dosa token in the original -> no-op


def test_translate_to_english_applies_correction_llm_path(monkeypatch):
    monkeypatch.setattr(a, "llm_active", lambda: True)
    monkeypatch.setattr(a, "complete_text", lambda system, user: "I need a dosage")
    a._XLATE_CACHE.clear()
    out = a._translate_to_english(DOSA_QUERY_TE, "te")
    assert re.search(r"\bdosa\b", out)


def test_translate_to_english_applies_correction_mymemory_path(monkeypatch):
    monkeypatch.setattr(a, "llm_active", lambda: False)
    monkeypatch.setattr(a, "_mymemory_en", lambda text, src: "I need a dosage")
    a._XLATE_CACHE.clear()
    out = a._translate_to_english(DOSA_QUERY_TE, "te")
    assert re.search(r"\bdosa\b", out)


def test_interpret_to_english_applies_correction(monkeypatch):
    monkeypatch.setattr(a, "complete_text", lambda system, user: "I need a dosage")
    a._XLATE_CACHE.clear()
    out = a._interpret_to_english(DOSA_QUERY_TE, "te")
    assert re.search(r"\bdosa\b", out)


def test_translate_prompt_is_domain_grounded():
    # The bare "You are a translator" prompt had no domain context -- the actual bug. Assert the
    # LLM system prompt now grounds ambiguous short words in the directory's own domain.
    assert "directory" in a._XLATE_DOMAIN_HINT.lower()
    assert "dosa" in a._XLATE_DOMAIN_HINT.lower()
