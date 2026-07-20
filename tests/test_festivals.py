"""Festival countdown: dated helpers, chat intent, /festivals page, greeting card."""

import datetime

from starlette.testclient import TestClient

import indo_usa_mcp.assistant as a
import indo_usa_mcp.festivals as festivals
from indo_usa_mcp.web.app import app

_client = TestClient(app)
_T = datetime.date(2026, 10, 30)   # fixed reference: between Karva Chauth and Dhanteras 2026


def test_upcoming_is_sorted_and_future_only():
    up = festivals.upcoming(3, _T)
    assert [e["name"] for e in up] == ["Dhanteras", "Diwali (Deepavali)", "Bhai Dooj"]
    assert all(e["days_until"] >= 0 for e in up)
    assert up[0]["days_until"] < up[1]["days_until"]      # sorted soonest-first


def test_next_festival():
    assert festivals.next_festival(_T)["name"] == "Dhanteras"


def test_calendar_has_multiyear_runway():
    # 2027 and 2028 are fully populated so the countdown never silently dries up mid-2027.
    years = {e["date"].year for e in festivals._all_dated()}
    assert {2027, 2028} <= years
    assert festivals.days_of_runway(_T) > 365          # well over a year of dated entries remain
    assert festivals.next_festival(datetime.date(2028, 6, 1)) is not None   # still answers deep into 2028


def test_find_matches_and_rolls_to_next_year():
    assert festivals.find("when is diwali", _T)["name"] == "Diwali (Deepavali)"
    holi = festivals.find("holi", _T)                     # 2026 Holi already passed -> next year's
    assert holi["name"] == "Holi" and holi["date"].year == 2027 and holi["days_until"] > 0


def test_find_empty_query_returns_none():
    assert festivals.find("", _T) is None


def test_festival_chat_intent_detection():
    assert a._is_festival_query("when is diwali")
    assert a._is_festival_query("how many days until holi")
    assert a._is_festival_query("upcoming festivals")
    assert not a._is_festival_query("biryani near me")
    assert not a._is_festival_query("when does the restaurant open")   # 'when' but no festival word


def test_festival_reply_gives_date_and_greeting():
    out = a._festival_reply("when is diwali", {})
    assert out["provider"] == "festival"
    assert "Diwali" in out["reply"] and ("day" in out["reply"] or "today" in out["reply"])


def test_reply_routes_festival_query(monkeypatch):
    monkeypatch.setattr(a, "_english", lambda text, filters: text)   # no translate/network
    out = a.reply([{"role": "user", "content": "when is diwali this year"}], filters={"lang": "en"})
    assert out["provider"] == "festival"


def test_festivals_page_renders():
    r = _client.get("/festivals")
    assert r.status_code == 200
    assert "festival" in r.text.lower()
    assert "og.png?kind=festival" in r.text       # PNG greeting-card share links (render on WhatsApp/FB/X)


def test_festival_card_svg_renders():
    r = _client.get("/festival-card.svg?name=Diwali")
    assert r.status_code == 200 and r.headers["content-type"] == "image/svg+xml"
    assert "Diwali" in r.text and "<svg" in r.text


def test_festival_card_defaults_when_unknown_name():
    r = _client.get("/festival-card.svg?name=zznotafestival")
    assert r.status_code == 200 and "<svg" in r.text   # falls back to next festival, never errors
