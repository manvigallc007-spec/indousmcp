"""Telegram bot front-end: language detection, reply formatting, update dispatch. No network/DB.

assistant.reply and send_message are monkeypatched so nothing leaves the process."""

import indo_usa_mcp.telegram_bot as tb


def test_enabled_reflects_token(monkeypatch):
    monkeypatch.setattr(tb.settings, "telegram_bot_token", "")
    assert tb.enabled() is False
    monkeypatch.setattr(tb.settings, "telegram_bot_token", "123:abc")
    assert tb.enabled() is True


def test_detect_lang_by_script():
    assert tb._detect_lang("నాకు బిర్యానీ కావాలి") == "te"   # Telugu
    assert tb._detect_lang("मुझे मंदिर चाहिए") == "hi"        # Hindi (Devanagari)
    assert tb._detect_lang("biryani near plano") is None     # Latin -> let it default to en


def test_format_reply_lists_cards():
    result = {"reply": "Here are some options:",
              "cards": [{"name": "Spice Hut", "city": "Plano", "state": "TX",
                         "community_rating": 4.6, "vertical": "restaurants", "id": 7}]}
    out = tb._format_reply(result, "https://namasteamerica.us")
    assert "Here are some options:" in out
    assert "1. Spice Hut ⭐4.6" in out
    assert "https://namasteamerica.us/listing/restaurants/7" in out


def test_handle_update_start_sends_welcome(monkeypatch):
    sent = []
    monkeypatch.setattr(tb, "send_message", lambda cid, text: sent.append((cid, text)))
    tb.handle_update({"message": {"chat": {"id": 42}, "text": "/start"}})
    assert sent and sent[0][0] == 42 and "Namaste" in sent[0][1]


def test_handle_update_location_sets_geo(monkeypatch):
    monkeypatch.setattr(tb, "send_message", lambda cid, text: None)
    tb._geo.pop(99, None)
    tb.handle_update({"message": {"chat": {"id": 99},
                                  "location": {"latitude": 33.0, "longitude": -96.7}}})
    assert tb._geo[99] == {"lat": 33.0, "lng": -96.7}


def test_handle_update_question_calls_assistant_with_detected_lang(monkeypatch):
    sent, captured = [], {}
    monkeypatch.setattr(tb, "send_message", lambda cid, text: sent.append(text))

    def fake_reply(messages, geo=None, filters=None):
        captured["lang"] = (filters or {}).get("lang")
        captured["q"] = messages[-1]["content"]
        captured["geo"] = geo
        return {"reply": "ok", "cards": [], "provider": "llm"}

    monkeypatch.setattr(tb.assistant, "reply", fake_reply)
    tb._lang.pop(7, None)
    tb._geo[7] = {"lat": 32.0, "lng": -96.0}
    tb.handle_update({"message": {"chat": {"id": 7}, "text": "నాకు దోసె కావాలి"}})
    assert captured["lang"] == "te"                 # detected Telugu -> reply pipeline in Telugu
    assert captured["geo"] == {"lat": 32.0, "lng": -96.0}   # remembered location threaded through
    assert sent and sent[-1] == "ok"


def test_handle_update_lang_command(monkeypatch):
    monkeypatch.setattr(tb, "send_message", lambda cid, text: None)
    tb._lang.pop(5, None)
    tb.handle_update({"message": {"chat": {"id": 5}, "text": "/hi"}})
    assert tb._lang[5] == "hi"


# --- weekly digest: opt-in subscribers + digest builder (real dev DB, ZZTEST rows) ---
from indo_usa_mcp import db   # noqa: E402

_ZZ_CHAT = -99900001          # disposable test chat_id (negative -> can't collide with real ones)


def test_subscribe_stop_and_city_roundtrip(monkeypatch):
    monkeypatch.setattr(tb, "send_message", lambda cid, text: None)
    db.execute("DELETE FROM telegram_subscribers WHERE chat_id = %s", (_ZZ_CHAT,))
    try:
        tb.handle_update({"message": {"chat": {"id": _ZZ_CHAT}, "text": "/subscribe"}})
        assert any(s["chat_id"] == _ZZ_CHAT for s in tb.active_subscribers())

        tb.handle_update({"message": {"chat": {"id": _ZZ_CHAT}, "text": "/city Edison, NJ"}})
        row = db.query_one("SELECT city, state, active FROM telegram_subscribers WHERE chat_id = %s",
                           (_ZZ_CHAT,))
        assert row["city"] == "Edison" and row["state"] == "NJ" and row["active"] is True

        tb.handle_update({"message": {"chat": {"id": _ZZ_CHAT}, "text": "/stop"}})
        assert not any(s["chat_id"] == _ZZ_CHAT for s in tb.active_subscribers())
    finally:
        db.execute("DELETE FROM telegram_subscribers WHERE chat_id = %s", (_ZZ_CHAT,))


def test_build_weekly_digest_has_festival_and_footer(monkeypatch):
    # No city -> festival countdown + footer at minimum (events/listings sections may be empty).
    msg = tb.build_weekly_digest(city=None, state=None)
    assert "This week" in msg and "/stop to unsubscribe" in msg


def test_recent_listings_only_last_week(monkeypatch):
    # A ZZTEST restaurant created now shows; one created 30 days ago doesn't.
    db.execute("DELETE FROM restaurants WHERE name LIKE 'ZZTEST Digest%'")
    try:
        db.execute("INSERT INTO restaurants (name, natural_key, city, state) "
                   "VALUES ('ZZTEST Digest Fresh', 'zzt-fresh', 'Zzville', 'TX')")
        db.execute("INSERT INTO restaurants (name, natural_key, city, state, created_at) "
                   "VALUES ('ZZTEST Digest Old', 'zzt-old', 'Zzville', 'TX', now() - interval '30 days')")
        names = [r["name"] for r in tb._recent_listings("Zzville", "TX")]
        assert "ZZTEST Digest Fresh" in names and "ZZTEST Digest Old" not in names
    finally:
        db.execute("DELETE FROM restaurants WHERE name LIKE 'ZZTEST Digest%'")


def test_digest_agent_registered_and_scheduled():
    from indo_usa_mcp.agents import AGENTS
    from indo_usa_mcp.agents.scheduler import _RUN_ORDER
    assert "telegram_digest" in AGENTS and "telegram_digest" in _RUN_ORDER


def test_digest_agent_noop_without_token(monkeypatch):
    from indo_usa_mcp.agents import get_agent
    monkeypatch.setattr(tb, "enabled", lambda: False)
    out = get_agent("telegram_digest").run()
    assert out == {"skipped": "telegram_disabled"}
