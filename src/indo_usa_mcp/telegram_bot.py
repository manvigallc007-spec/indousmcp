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
    "Commands: /en /hi /te to set language."
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
