"""Human chat front-end: assistant fallback, cards, page render, API, rate limit. No DB/LLM."""

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp import assistant
from indo_usa_mcp.config import settings
from indo_usa_mcp.web import app, chat as chatmod

_FAKE = {"count": 2, "query": "dosa", "results": [
    {"vertical": "restaurants", "id": 1, "name": "Dosa Hut", "city": "Edison", "state": "NJ",
     "phone": "+1 732 555 0100", "website": "https://dosahut.example", "open_now": True,
     "is_featured": True, "description": "South Indian restaurant in Edison, NJ. Offers dosa."},
    {"vertical": "sweets", "id": 5, "name": "Bikaner Sweets", "city": "Iselin", "state": "NJ",
     "description": "Indian sweets shop (mithai)."},
]}


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(assistant.verticals, "search_all", lambda *a, **k: _FAKE)
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)


def test_search_fallback_reply_and_cards(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    out = assistant.reply([{"role": "user", "content": "dosa near edison"}])
    assert out["provider"] == "search"
    assert "dosa near edison" in out["reply"].lower()   # dynamic reply echoes the query
    assert len(out["cards"]) == 2
    c0 = out["cards"][0]
    assert c0["name"] == "Dosa Hut" and c0["vertical"] == "restaurants" and c0["is_featured"]
    assert c0["phone"] and c0["open_now"] is True


def test_returns_up_to_12_cards_for_show_more(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)
    many = [{"vertical": "restaurants", "id": i, "name": f"Place {i}"} for i in range(20)]
    monkeypatch.setattr(assistant.verticals, "search_all",
                        lambda *a, **k: {"count": 20, "results": many})
    out = assistant.reply([{"role": "user", "content": "biryani in edison nj"}])
    assert len(out["cards"]) == 12          # capped at 12; UI shows 6 + "show more"
    assert "show more" in out["reply"].lower()


def test_chat_has_show_more_button():
    t = TestClient(app).get("/chat").text
    assert "morebtn" in t and "Show '+(cards.length-N)+' more" in t


def test_empty_query_prompts_for_input(no_db):
    out = assistant.reply([{"role": "user", "content": "   "}])
    assert out["cards"] == [] and "looking for" in out["reply"].lower()


def test_llm_inactive_by_default():
    assert assistant.llm_active() is False  # default provider is "search"


def test_llm_error_degrades_to_search(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:1");
    monkeypatch.setattr(settings, "llm_model", "x")
    monkeypatch.setattr(assistant, "_llm_reply", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    out = assistant.reply([{"role": "user", "content": "dosa"}])
    assert out["provider"] == "search" and "unavailable" in out["reply"].lower()
    assert out["llm_error"] == "RuntimeError"


def test_grounded_mode_searches_then_single_call(no_db, monkeypatch):
    # Gemma / small-model path: llm_use_tools=False -> search first, then ONE no-tools LLM call.
    monkeypatch.setattr(settings, "llm_provider", "llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://x")
    monkeypatch.setattr(settings, "llm_model", "gemma2:2b")
    monkeypatch.setattr(settings, "llm_use_tools", False)
    seen = {}

    def fake_chat(convo, use_tools):
        seen["use_tools"] = use_tools
        seen["grounded"] = any("Listings found" in m.get("content", "") for m in convo)
        return {"content": "Try Dosa Hut in Edison!"}
    monkeypatch.setattr(assistant, "_chat", fake_chat)
    out = assistant.reply([{"role": "user", "content": "dosa"}])
    assert out["provider"] == "llm" and out["reply"] == "Try Dosa Hut in Edison!"
    assert len(out["cards"]) == 2                 # cards came from the pre-search
    assert seen["use_tools"] is False and seen["grounded"] is True


def test_grounded_mode_searches_then_single_call(no_db, monkeypatch):
    # Gemma / small-model path: llm_use_tools=False -> search first, then ONE no-tools LLM call.
    monkeypatch.setattr(settings, "llm_provider", "llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://x")
    monkeypatch.setattr(settings, "llm_model", "gemma2:2b")
    monkeypatch.setattr(settings, "llm_use_tools", False)
    seen = {}

    def fake_chat(convo, use_tools):
        seen["use_tools"] = use_tools
        seen["grounded"] = any("Listings found" in m.get("content", "") for m in convo)
        return {"content": "Try Dosa Hut in Edison!"}
    monkeypatch.setattr(assistant, "_chat", fake_chat)
    out = assistant.reply([{"role": "user", "content": "dosa"}])
    assert out["provider"] == "llm" and out["reply"] == "Try Dosa Hut in Edison!"
    assert len(out["cards"]) == 2                 # cards came from the pre-search
    assert seen["use_tools"] is False and seen["grounded"] is True


def test_chat_page_renders():
    r = TestClient(app).get("/chat")
    assert r.status_code == 200 and "chat/api" in r.text


def test_chat_page_is_dost_branded_with_meaning_and_jsonld():
    t = TestClient(app).get("/chat").text
    assert "<title>Dost" in t                 # chatbot brand leads the title
    assert "friend" in t.lower()               # meaning is explained for non-Hindi speakers
    assert "WebApplication" in t and "SearchAction" in t   # chatbot SEO/indexing
    assert "#e8772e" in t and "#0f9b8e" in t   # warm saffron + teal palette
    assert "__" not in t                       # all template placeholders resolved


def test_chat_has_language_selector_and_voice():
    t = TestClient(app).get("/chat").text
    assert 'id="lang"' in t and "हिंदी" in t and "తెలుగు" in t   # EN/HI/TE picker
    assert "startMic" in t and "micbtn" in t                      # mic (SpeechRecognition)
    assert "speechSynthesis" in t                                 # speaker (SpeechSynthesis)
    assert "नमस्ते" in t                                          # Hindi UI string present
    assert "__" not in t                                          # all placeholders resolved


def test_chat_api_accepts_lang(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    r = TestClient(app).post("/chat/api",
                             json={"messages": [{"role": "user", "content": "dosa"}], "lang": "hi"})
    assert r.status_code == 200


def test_og_image_renders():
    r = TestClient(app).get("/og-image.svg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/svg+xml"
    assert "Dost" in r.text and "1200" in r.text


def test_chat_welcome_invites_contribution():
    t = TestClient(app).get("/chat").text
    assert "openContribute" in t and "A restaurant I love" in t   # greeting invites adding favorites


def test_chat_contribute_creates_submission(monkeypatch):
    from indo_usa_mcp import submissions
    seen = {}

    def fake_submit(vertical, payload, **k):
        seen["vertical"], seen["payload"] = vertical, payload
        return {"ok": True, "id": 1}
    monkeypatch.setattr(submissions, "submit", fake_submit)
    r = TestClient(app).post("/chat/contribute",
                             json={"name": "Saravana Bhavan", "city": "Edison, NJ",
                                   "vertical": "restaurants"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert seen["vertical"] == "restaurants"
    assert seen["payload"]["name"] == "Saravana Bhavan"
    assert seen["payload"]["city"] == "Edison" and seen["payload"]["state"] == "NJ"


def test_chat_contribute_requires_name():
    r = TestClient(app).post("/chat/contribute", json={"name": "  "})
    assert r.status_code == 400 and r.json()["ok"] is False


def test_chat_contribute_guesses_vertical(monkeypatch):
    from indo_usa_mcp import submissions
    seen = {}
    monkeypatch.setattr(submissions, "submit",
                        lambda v, p, **k: seen.update(v=v) or {"ok": True, "id": 2})
    TestClient(app).post("/chat/contribute", json={"name": "Apna Bazar grocery", "city": "Iselin"})
    assert seen["v"] == "groceries"   # guessed from the name when no vertical given


def test_chat_api_returns_cards(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    r = TestClient(app).post("/chat/api", json={"messages": [{"role": "user", "content": "dosa"}]})
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "search" and len(data["cards"]) == 2


def test_filter_scopes_to_vertical(monkeypatch):
    from indo_usa_mcp import queries as r_queries
    monkeypatch.setattr(settings, "llm_provider", "search")
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)

    def boom(*a, **k):
        raise AssertionError("search_all must not be called when a vertical filter is set")
    monkeypatch.setattr(assistant.verticals, "search_all", boom)
    monkeypatch.setattr(r_queries, "search_restaurants_by_text",
                        lambda q, **k: {"count": 1, "results": [{"id": 9, "name": "Scoped Diner"}]})
    out = assistant.reply([{"role": "user", "content": "dinner"}],
                          geo={"lat": 40.0, "lng": -74.0},
                          filters={"vertical": "restaurants", "open_now": False})
    assert len(out["cards"]) == 1
    assert out["cards"][0]["name"] == "Scoped Diner" and out["cards"][0]["vertical"] == "restaurants"


def test_open_now_filter(monkeypatch):
    from indo_usa_mcp import hours
    monkeypatch.setattr(settings, "llm_provider", "search")
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)
    monkeypatch.setattr(assistant.verticals, "search_all", lambda *a, **k: {"count": 2, "results": [
        {"vertical": "restaurants", "id": 1, "name": "Open Place", "_o": True},
        {"vertical": "restaurants", "id": 2, "name": "Closed Place", "_o": False}]})
    monkeypatch.setattr(hours, "annotate",
                        lambda rows: [r.__setitem__("open_now", r.get("_o", False)) for r in rows])
    out = assistant.reply([{"role": "user", "content": "food"}],
                          geo={"lat": 40.0, "lng": -74.0}, filters={"vertical": None, "open_now": True})
    assert [c["name"] for c in out["cards"]] == ["Open Place"]


def test_location_clarification(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    # local intent, no geo, no place named -> ask for a city instead of national results
    out = assistant.reply([{"role": "user", "content": "good vegetarian restaurant"}])
    assert out["provider"] == "clarify" and out["cards"] == []
    # but a named place proceeds to search (no clarification)
    out2 = assistant.reply([{"role": "user", "content": "vegetarian restaurant in Edison"}])
    assert out2["provider"] != "clarify"


def test_wants_open_now():
    assert assistant._wants_open_now("indian restaurant open now")
    assert assistant._wants_open_now("what's open near me")
    assert not assistant._wants_open_now("indian restaurant in edison")


@pytest.fixture
def no_results(monkeypatch):
    monkeypatch.setattr(assistant.verticals, "search_all", lambda *a, **k: {"count": 0, "results": []})
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)


def test_extract_location():
    assert assistant._extract_location("dallas restaurants") == ("Dallas", "TX")
    assert assistant._extract_location("biryani in edison, nj") == ("Edison", "NJ")
    assert assistant._extract_location("indian food in texas") == (None, "TX")
    assert assistant._extract_location("temples in the bay area") == (None, "CA")
    assert assistant._extract_location("good dosa near me") == (None, None)
    assert assistant._extract_location("san jose grocery") == ("San Jose", "CA")


def test_chat_scopes_search_to_extracted_city(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)
    seen = {}

    def fake_search_all(q, **k):
        seen["city"], seen["state"] = k.get("city"), k.get("state")
        return {"count": 1, "results": [{"vertical": "restaurants", "name": "Dallas Dhaba",
                                         "city": "Dallas", "state": "TX"}]}
    monkeypatch.setattr(assistant.verticals, "search_all", fake_search_all)
    out = assistant.reply([{"role": "user", "content": "dallas restaurants"}])
    assert seen["city"] == "Dallas" and seen["state"] == "TX"
    assert out["cards"][0]["name"] == "Dallas Dhaba"


def test_chat_widens_to_state_when_city_empty(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)
    calls = []

    def fake_search_all(q, **k):
        calls.append((k.get("city"), k.get("state")))
        if k.get("city"):                      # first try (city) -> empty
            return {"count": 0, "results": []}
        return {"count": 1, "results": [{"vertical": "restaurants", "name": "Plano Tiffins"}]}
    monkeypatch.setattr(assistant.verticals, "search_all", fake_search_all)
    out = assistant.reply([{"role": "user", "content": "dallas tiffin"}])
    assert calls == [("Dallas", "TX"), (None, "TX")]   # narrowed, then widened to the state
    assert out["cards"][0]["name"] == "Plano Tiffins"


def test_typed_category_overrides_conflicting_chip(monkeypatch):
    # Temple chip selected, but the user asks for restaurants -> show restaurants, not temples.
    monkeypatch.setattr(settings, "llm_provider", "search")
    monkeypatch.setattr(assistant.analytics, "log_impressions", lambda *a, **k: None)
    monkeypatch.setattr(assistant.analytics, "log_call", lambda *a, **k: None)
    from indo_usa_mcp import queries as r_queries
    monkeypatch.setattr(assistant.verticals, "search_all",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should scope, not search_all")))

    def boom_temples(*a, **k):
        raise AssertionError("must not search temples when the user typed 'restaurants'")
    monkeypatch.setattr(r_queries, "search_restaurants_by_text",
                        lambda q, **k: {"results": [{"id": 1, "name": "Dallas Dhaba"}]})
    out = assistant.reply([{"role": "user", "content": "restaurants in dallas"}],
                          filters={"vertical": "temples", "open_now": False})
    assert out["cards"][0]["name"] == "Dallas Dhaba"
    assert out["cards"][0]["vertical"] == "restaurants"


def test_is_indian_american_topic():
    assert assistant.is_indian_american_topic("when is diwali this year")
    assert assistant.is_indian_american_topic("best indian restaurant near me")
    assert not assistant.is_indian_american_topic("how do I debug this python error")


def test_offtopic_question_is_declined(no_results, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    out = assistant.reply([{"role": "user", "content": "how do I fix my car engine"}])
    assert out["provider"] == "offtopic" and out["cards"] == []
    assert "indian" in out["reply"].lower()


def test_relevant_miss_uses_web_fallback_and_suggests_add(no_results, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")  # no LLM -> snippet shown directly
    import indo_usa_mcp.websearch as ws
    monkeypatch.setattr(ws, "lookup", lambda q, **k: [
        {"source": "Wikipedia", "title": "Diwali", "text": "Diwali is the festival of lights.",
         "url": "http://x"}])
    out = assistant.reply([{"role": "user", "content": "what is diwali about"}])
    assert out["provider"] == "web"
    assert "festival of lights" in out["reply"]
    assert out["suggest_add"]["url"].endswith("/submit")


def test_local_miss_goes_to_discovery_and_invites_contribution(no_results, monkeypatch):
    # A local business/place we don't have -> engage (ask + invite to add), not a web answer.
    monkeypatch.setattr(settings, "llm_provider", "search")
    out = assistant.reply([{"role": "user", "content": "telugu association in austin"}])
    assert out["provider"] == "discovery" and out["cards"] == []
    assert out["contribute"]["vertical"] == "community"
    assert out["suggest_add"]["url"].endswith("?vertical=community")
    assert "directory" in out["reply"].lower()           # invites adding it


def test_general_question_still_uses_web_not_discovery(no_results, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    import indo_usa_mcp.websearch as ws
    monkeypatch.setattr(ws, "lookup", lambda q, **k: [
        {"source": "Wikipedia", "title": "Diwali", "text": "Festival of lights.", "url": ""}])
    out = assistant.reply([{"role": "user", "content": "what is diwali about"}])
    assert out["provider"] == "web"                       # general knowledge -> web fallback


def test_lang_note():
    assert "Hindi" in (assistant._lang_note({"lang": "hi"}) or "")
    assert "Telugu" in (assistant._lang_note({"lang": "te"}) or "")
    assert assistant._lang_note({"lang": "en"}) is None
    assert assistant._lang_note({}) is None


def test_grounded_reply_carries_language_instruction(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://x")
    monkeypatch.setattr(settings, "llm_model", "gemma2:2b")
    monkeypatch.setattr(settings, "llm_use_tools", False)
    seen = {}

    def fake_chat(convo, use_tools):
        seen["has_hindi"] = any("Hindi" in m.get("content", "") for m in convo)
        return {"content": "नमस्ते! दोसा हट देखिए।"}
    monkeypatch.setattr(assistant, "_chat", fake_chat)
    out = assistant.reply([{"role": "user", "content": "dosa"}],
                          filters={"vertical": None, "open_now": False, "lang": "hi"})
    assert out["provider"] == "llm" and seen["has_hindi"] is True


def test_is_local_request():
    assert assistant._is_local_request("biryani restaurant in dallas")
    assert assistant._is_local_request("krishna temple near me")
    assert not assistant._is_local_request("what is the significance of holi")


def test_web_fallback_serves_from_cache_without_calling_web(no_results, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    import indo_usa_mcp.learning as learning
    import indo_usa_mcp.websearch as ws
    monkeypatch.setattr(learning, "lookup", lambda q: "Cached: Diwali is the festival of lights.")
    monkeypatch.setattr(ws, "lookup",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cache hit must skip web")))
    out = assistant.reply([{"role": "user", "content": "what is diwali"}])
    assert out["provider"] == "web" and out.get("cached") is True
    assert "Cached:" in out["reply"]


def test_web_fallback_stores_fresh_answer(no_results, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    import indo_usa_mcp.learning as learning
    import indo_usa_mcp.websearch as ws
    monkeypatch.setattr(learning, "lookup", lambda q: None)             # cache miss
    monkeypatch.setattr(ws, "lookup", lambda q, **k: [
        {"source": "Wikipedia", "title": "Holi", "text": "Holi is a spring festival.", "url": ""}])
    saved = {}
    monkeypatch.setattr(learning, "store", lambda q, reply, **k: saved.update(q=q, reply=reply))
    out = assistant.reply([{"role": "user", "content": "tell me about holi"}])
    assert out["provider"] == "web" and "spring festival" in out["reply"]
    assert saved.get("q") == "tell me about holi"   # the fresh answer was learned


def test_grounded_empty_composes_web_answer_via_llm(no_results, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://x")
    monkeypatch.setattr(settings, "llm_model", "gemma2:2b")
    monkeypatch.setattr(settings, "llm_use_tools", False)
    import indo_usa_mcp.websearch as ws
    monkeypatch.setattr(ws, "lookup", lambda q, **k: [
        {"source": "Wikipedia", "title": "Holi", "text": "Holi is a spring festival.", "url": ""}])
    # the only _chat call should be the web-compose one (grounded short-circuits on empty search)
    monkeypatch.setattr(assistant, "_chat",
                        lambda convo, use_tools: {"content": "Holi is a Hindu festival of colors."})
    out = assistant.reply([{"role": "user", "content": "tell me about holi"}])
    assert out["provider"] == "web" and "colors" in out["reply"]


def test_no_clarify_loop(no_db, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")
    out1 = assistant.reply([{"role": "user", "content": "restaurants near me"}])
    assert out1["provider"] == "clarify"               # turn 1 asks once
    history = [{"role": "user", "content": "restaurants near me"},
               {"role": "assistant", "content": out1["reply"]},
               {"role": "user", "content": "Edison NJ"}]
    out2 = assistant.reply(history)
    assert out2["provider"] != "clarify"               # turn 2 proceeds (no loop)


def test_search_query_merges_location_followup():
    msgs = [{"role": "user", "content": "vegetarian restaurant"},
            {"role": "assistant", "content": "Which city or area should I look in? ..."},
            {"role": "user", "content": "Edison"}]
    assert assistant._search_query(msgs) == "vegetarian restaurant Edison"


def test_landing_page_renders_with_share_meta():
    r = TestClient(app).get("/")
    assert r.status_code == 200 and "/chat" in r.text and 'property="og:title"' in r.text


def test_chat_api_rate_limit(no_db, monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_min", 1)
    chatmod._HITS.clear()
    c = TestClient(app)
    body = {"messages": [{"role": "user", "content": "dosa"}]}
    assert c.post("/chat/api", json=body).status_code == 200
    assert c.post("/chat/api", json=body).status_code == 429
