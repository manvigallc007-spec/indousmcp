"""Telegram bot front-end for Dost — wraps assistant.reply().

The Indian diaspora lives in WhatsApp/Telegram groups, so a free bot people can forward to each
other is the highest-virality human channel. This reuses the exact same assistant pipeline as the
web chat (multilingual search + KB), so there's one brain behind every surface.

Enable: create a bot with @BotFather, set TELEGRAM_BOT_TOKEN in .env, then run the long-poll loop:
    python -m indo_usa_mcp.telegram_bot
(or the `telegram` service in docker-compose.prod.yml). It uses getUpdates long-polling, so NO
public webhook / extra port is needed. Blank token = disabled (idles).
"""

from __future__ import annotations

import time

import httpx

from . import assistant
from .config import settings

_API = "https://api.telegram.org/bot{token}/{method}"

# Per-chat preferred language (/en /hi /te) + last shared location. In-memory is fine: a single bot
# process owns the long-poll, and these are soft preferences (re-detected from text otherwise).
_lang: dict[int, str] = {}
_geo: dict[int, dict] = {}

WELCOME = (
    "\U0001f64f Namaste! I'm Dost — your guide to Indian America.\n\n"
    "Ask me for Indian restaurants, temples, groceries, events, doctors and more across the USA — "
    "in English, हिंदी or తెలుగు.\n\n"
    "\U0001f4cd Share your location for nearest-first results.\n"
    "Try: “biryani near me” or “Hindu temple in Dallas”.\n\n"
    "Commands: /en /hi /te to set language.\n"
    "\U0001f514 /subscribe for a weekly digest of festivals, events & new places near you."
)

# Telugu and Devanagari (Hindi) Unicode blocks — to auto-reply in the user's script.
_TELUGU = range(0x0C00, 0x0C80)
_DEVANAGARI = range(0x0900, 0x0980)


def enabled() -> bool:
    return bool((settings.telegram_bot_token or "").strip())


def _call(method: str, **params) -> dict:
    if not enabled():
        return {}
    url = _API.format(token=settings.telegram_bot_token.strip(), method=method)
    try:
        return httpx.post(url, json=params, timeout=65.0).json()
    except Exception:
        return {}


def send_message(chat_id, text: str) -> None:
    _call("sendMessage", chat_id=chat_id, text=(text or "")[:4000], disable_web_page_preview=True)


# ------------------------------------------------------------------- weekly-digest subscriptions
def subscribe(chat_id, city=None, state=None, lang="en") -> None:
    from . import db
    db.execute(
        "INSERT INTO telegram_subscribers (chat_id, city, state, lang, active) "
        "VALUES (%s,%s,%s,%s,true) ON CONFLICT (chat_id) DO UPDATE SET active = true, "
        "city = COALESCE(EXCLUDED.city, telegram_subscribers.city), "
        "state = COALESCE(EXCLUDED.state, telegram_subscribers.state), lang = EXCLUDED.lang",
        (chat_id, city, state, lang))


def unsubscribe(chat_id) -> None:
    from . import db
    db.execute("UPDATE telegram_subscribers SET active = false WHERE chat_id = %s", (chat_id,))


def set_subscriber_city(chat_id, city, state, lang="en") -> None:
    """Set the digest city; also (re)subscribes, so '/city Edison, NJ' is a one-step opt-in."""
    from . import db
    db.execute(
        "INSERT INTO telegram_subscribers (chat_id, city, state, lang, active) "
        "VALUES (%s,%s,%s,%s,true) ON CONFLICT (chat_id) DO UPDATE SET active = true, "
        "city = EXCLUDED.city, state = EXCLUDED.state", (chat_id, city, state, lang))


def active_subscribers() -> list[dict]:
    from . import db
    try:
        return db.query("SELECT chat_id, city, state, lang FROM telegram_subscribers WHERE active")
    except Exception:
        return []


def _recent_listings(city: str, state: str | None, days: int = 7, limit: int = 6) -> list[dict]:
    """Listings added in the last `days` for a city, newest-first across verticals."""
    from . import db, verticals
    out: list[dict] = []
    for v in verticals.VERTICALS:
        if v == "events":
            continue
        t = verticals._table(v)
        sql = (f"SELECT name, created_at FROM {t} WHERE deleted_at IS NULL AND is_active "
               f"AND created_at > now() - (%s || ' days')::interval AND LOWER(city) = LOWER(%s)")
        params = [days, city]
        if state:
            sql += " AND LOWER(state) = LOWER(%s)"
            params.append(state)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        try:
            for r in db.query(sql, params):
                out.append({"name": r["name"], "vertical": v, "created_at": r["created_at"]})
        except Exception:
            pass
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out[:limit]


def _event_when(dt) -> str:
    return dt.strftime("%a %b %d") if hasattr(dt, "strftime") else ""


def build_weekly_digest(city: str | None = None, state: str | None = None) -> str:
    """Assemble a subscriber's weekly digest: festival countdown + this week's events + new listings.
    Sections with no content are skipped; the festival line is near-always present."""
    from . import festivals
    base = settings.public_web_url.rstrip("/")
    parts = ["\U0001f5de This week with Namaste America"]

    nf = festivals.next_festival()
    if nf:
        d = nf["days_until"]
        when = "today!" if d == 0 else ("tomorrow" if d == 1 else f"in {d} days")
        parts.append(f"{nf['emoji']} {nf['name']} is {when} — {nf['greeting']}")

    try:
        from .events import queries as eq
        events = eq.get_indian_events(city=city, state=state, limit=5).get("results", [])
    except Exception:
        events = []
    if events:
        lines = ["\U0001f4c5 Upcoming events" + (f" near {city}" if city else "") + ":"]
        for e in events:
            when = _event_when(e.get("start_at"))
            loc = ", ".join(x for x in (e.get("venue_name"), e.get("city")) if x)
            lines.append(f"• {e.get('name')}" + (f" — {when}" if when else "")
                         + (f" ({loc})" if loc else ""))
        parts.append("\n".join(lines))

    if city:
        recent = _recent_listings(city, state)
        if recent:
            lines = [f"\U0001f195 New in {city}:"]
            lines += [f"• {r['name']} ({r['vertical']})" for r in recent]
            parts.append("\n".join(lines))

    parts.append(f"Explore more → {base}/   ·   /stop to unsubscribe")
    return "\n\n".join(parts)


def _detect_lang(text: str) -> str | None:
    for ch in text or "":
        o = ord(ch)
        if o in _TELUGU:
            return "te"
        if o in _DEVANAGARI:
            return "hi"
    return None


def _format_reply(result: dict, base: str) -> str:
    """assistant.reply() result -> a plain-text Telegram message: the answer + up to 6 listings."""
    lines = [(result.get("reply") or "").strip()]
    for i, c in enumerate((result.get("cards") or [])[:6], 1):
        name = c.get("name") or "?"
        where = ", ".join(x for x in (c.get("city"), c.get("state")) if x)
        addr = c.get("address_full") or where
        rating = c.get("community_rating") or c.get("rating")
        star = f" ⭐{rating}" if rating else ""
        link = (f"{base}/listing/{c.get('vertical')}/{c.get('id')}"
                if c.get("vertical") and c.get("id") else "")
        detail = "\n   ".join(x for x in (addr, link) if x)
        lines.append(f"{i}. {name}{star}" + (f"\n   {detail}" if detail else ""))
    return "\n\n".join(p for p in lines if p).strip() or "Sorry, I didn't catch that. Try again?"


def handle_update(update: dict) -> None:
    """Process one Telegram update: commands, a shared location, or a question for Dost."""
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if not chat_id:
        return

    if msg.get("location"):                       # location share -> nearest-first from now on
        loc = msg["location"]
        _geo[chat_id] = {"lat": loc.get("latitude"), "lng": loc.get("longitude")}
        send_message(chat_id, "\U0001f4cd Got your location — I'll show the nearest matches.")
        return

    text = (msg.get("text") or "").strip()
    if not text:
        return
    low = text.lower()
    if low in ("/start", "/help"):
        send_message(chat_id, WELCOME)
        return
    if low in ("/en", "/hi", "/te"):
        _lang[chat_id] = low[1:]
        send_message(chat_id, "✅ Language set. Ask me anything!")
        return
    if low == "/subscribe":
        g = _geo.get(chat_id)
        subscribe(chat_id, lang=_lang.get(chat_id, "en"))
        send_message(chat_id, "\U0001f514 Subscribed to the weekly digest — festivals, events and new "
                     "places. Use /city <your city>, e.g. “/city Edison, NJ”, to localize it. /stop "
                     "to unsubscribe.")
        return
    if low == "/stop":
        unsubscribe(chat_id)
        send_message(chat_id, "You've unsubscribed from the weekly digest. Send /subscribe anytime to "
                     "turn it back on.")
        return
    if low.startswith("/city"):
        rest = text[5:].strip()
        if not rest:
            send_message(chat_id, "Tell me your city, e.g. “/city Edison, NJ”.")
            return
        city, st = (rest.rsplit(",", 1) if "," in rest else (rest, ""))
        set_subscriber_city(chat_id, city.strip(), (st.strip()[:2].upper() or None),
                            lang=_lang.get(chat_id, "en"))
        send_message(chat_id, f"\U0001f4cd Got it — your weekly digest is set for {city.strip()}. "
                     "/stop to unsubscribe.")
        return

    lang = _lang.get(chat_id) or _detect_lang(text) or "en"
    filters = {"vertical": None, "open_now": False, "lang": lang}
    try:
        result = assistant.reply([{"role": "user", "content": text[:1000]}],
                                 geo=_geo.get(chat_id), filters=filters)
    except Exception:
        send_message(chat_id, "Sorry, something went wrong on my side. Please try again.")
        return
    base = settings.public_web_url.rstrip("/")
    send_message(chat_id, _format_reply(result, base))
    try:                                          # best-effort usage logging (Admin -> Traffic)
        from . import analytics
        analytics.log_call("chat", {"query": text[:200], "provider": result.get("provider")},
                           len(result.get("cards") or []), "telegram")
    except Exception:
        pass


def poll_loop() -> None:
    """Long-poll getUpdates forever, dispatching each message. Idles quietly if no token is set."""
    if not enabled():
        print("Telegram bot disabled (TELEGRAM_BOT_TOKEN not set); idling.")
        while True:
            time.sleep(3600)
    print("Telegram bot polling (getUpdates)…")
    offset: int | None = None
    while True:
        params = {"timeout": 50, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        data = _call("getUpdates", **params)
        if not data or not data.get("ok"):
            time.sleep(3)                         # API hiccup -> short backoff, then retry
            continue
        for upd in data.get("result") or []:
            offset = upd["update_id"] + 1
            try:
                handle_update(upd)
            except Exception:
                pass


if __name__ == "__main__":
    poll_loop()
