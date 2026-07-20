"""Festival timing for grounded "when is <festival>" answers.

Hindu/Sikh/Jain/Muslim festivals follow lunar or lunisolar calendars, so the exact day shifts every
year. We deliberately publish the MONTH for those (and the exact day only for fixed/solar festivals
like Republic Day or Makar Sankranti) and tell users to confirm the precise date locally — better an
honestly approximate answer than a fabricated precise one. The article year derives from today's date;
extend FESTIVAL_DATES with a new year before the last dated entry runs out (MonitoringAgent alerts you).
"""

from __future__ import annotations

import datetime
from typing import Any

# (festival, when in the current year, short note). Exact day only where the date is fixed/solar.
FESTIVALS: list[tuple[str, str, str]] = [
    ("Makar Sankranti / Pongal", "January 14", "harvest festival (solar; same date most years)"),
    ("Republic Day", "January 26", "national holiday (fixed)"),
    ("Vasant Panchami", "late January / February", "Saraswati puja"),
    ("Maha Shivaratri", "February", "night of Lord Shiva"),
    ("Holi", "March", "festival of colors (Holika Dahan the night before)"),
    ("Ugadi / Gudi Padwa", "March / April", "Telugu, Kannada & Marathi new year"),
    ("Ram Navami", "March / April", "birth of Lord Rama"),
    ("Mahavir Jayanti", "April", "Jain festival"),
    ("Baisakhi / Vaisakhi", "April 13–14", "Sikh new year & harvest (solar)"),
    ("Eid al-Fitr", "March / April", "end of Ramadan — confirm by moon sighting"),
    ("Akshaya Tritiya", "April / May", "auspicious for new beginnings"),
    ("Eid al-Adha (Bakrid)", "May / June", "confirm by moon sighting"),
    ("Rath Yatra", "June / July", "Jagannath chariot festival"),
    ("Guru Purnima", "July", ""),
    ("Raksha Bandhan", "August", "brother–sister bond"),
    ("Independence Day", "August 15", "national holiday (fixed)"),
    ("Janmashtami", "August / September", "birth of Lord Krishna"),
    ("Ganesh Chaturthi", "August / September", "Lord Ganesha"),
    ("Onam", "August / September", "Kerala harvest festival"),
    ("Gandhi Jayanti", "October 2", "national holiday (fixed)"),
    ("Navratri & Durga Puja", "September / October", "nine nights of the goddess; Garba & Dandiya"),
    ("Dussehra (Vijayadashami)", "October", "victory of good over evil"),
    ("Karva Chauth", "October / November", ""),
    ("Dhanteras", "October / November", "start of Diwali season"),
    ("Diwali (Deepavali)", "October / November", "festival of lights; Lakshmi puja"),
    ("Bhai Dooj", "October / November", ""),
    ("Chhath Puja", "October / November", "Sun worship (Bihar/UP/Jharkhand)"),
    ("Guru Nanak Jayanti", "November", "Sikh — Guru Nanak's birthday"),
    ("Christmas", "December 25", "fixed"),
]


# --------------------------------------------------------------------- dated calendar (countdown)
# Curated actual dates for a "days until <festival>" countdown + greetings. Lunar/lunisolar dates
# shift each year and are moon-sighting-dependent (Eid especially), so these are BEST-EFFORT and the
# UI always tells users to confirm locally — same honesty as the month-only FESTIVALS list above.
# UPKEEP: verify + extend this table once a year (a few hours with any published panchang). `emoji`
# and `greeting` power the home banner, /festivals page, chat answers and the shareable greeting card.
_D = datetime.date
FESTIVAL_DATES: dict[int, list[dict[str, Any]]] = {
    2026: [
        {"name": "Makar Sankranti / Pongal", "date": _D(2026, 1, 14), "emoji": "🌾",
         "greeting": "Happy Makar Sankranti & Pongal!"},
        {"name": "Republic Day", "date": _D(2026, 1, 26), "emoji": "🇮🇳",
         "greeting": "Happy Republic Day!"},
        {"name": "Vasant Panchami", "date": _D(2026, 1, 23), "emoji": "📚",
         "greeting": "Happy Vasant Panchami!"},
        {"name": "Maha Shivaratri", "date": _D(2026, 2, 15), "emoji": "🕉️",
         "greeting": "Har Har Mahadev — Happy Maha Shivaratri!"},
        {"name": "Holi", "date": _D(2026, 3, 4), "emoji": "🌈",
         "greeting": "Happy Holi! May your life be as colorful as the festival."},
        {"name": "Ugadi / Gudi Padwa", "date": _D(2026, 3, 19), "emoji": "🌱",
         "greeting": "Happy Ugadi & Gudi Padwa — a joyful new year!"},
        {"name": "Ram Navami", "date": _D(2026, 3, 26), "emoji": "🏹",
         "greeting": "Jai Shri Ram — Happy Ram Navami!"},
        {"name": "Eid al-Fitr", "date": _D(2026, 3, 20), "emoji": "🌙",
         "greeting": "Eid Mubarak!"},
        {"name": "Baisakhi / Vaisakhi", "date": _D(2026, 4, 14), "emoji": "🌾",
         "greeting": "Happy Baisakhi!"},
        {"name": "Akshaya Tritiya", "date": _D(2026, 4, 19), "emoji": "🪙",
         "greeting": "Happy Akshaya Tritiya!"},
        {"name": "Eid al-Adha (Bakrid)", "date": _D(2026, 5, 27), "emoji": "🌙",
         "greeting": "Eid Mubarak!"},
        {"name": "Rath Yatra", "date": _D(2026, 7, 16), "emoji": "🛕",
         "greeting": "Jai Jagannath — Happy Rath Yatra!"},
        {"name": "Guru Purnima", "date": _D(2026, 7, 29), "emoji": "🙏",
         "greeting": "Happy Guru Purnima!"},
        {"name": "Onam", "date": _D(2026, 8, 26), "emoji": "🌸",
         "greeting": "Happy Onam!"},
        {"name": "Raksha Bandhan", "date": _D(2026, 8, 28), "emoji": "🧵",
         "greeting": "Happy Raksha Bandhan!"},
        {"name": "Independence Day", "date": _D(2026, 8, 15), "emoji": "🇮🇳",
         "greeting": "Happy Independence Day!"},
        {"name": "Janmashtami", "date": _D(2026, 9, 4), "emoji": "🦚",
         "greeting": "Happy Krishna Janmashtami!"},
        {"name": "Ganesh Chaturthi", "date": _D(2026, 9, 14), "emoji": "🐘",
         "greeting": "Ganpati Bappa Morya — Happy Ganesh Chaturthi!"},
        {"name": "Navratri & Durga Puja", "date": _D(2026, 10, 11), "emoji": "🪔",
         "greeting": "Happy Navratri! Nine nights of devotion, Garba & Dandiya."},
        {"name": "Dussehra (Vijayadashami)", "date": _D(2026, 10, 20), "emoji": "🏹",
         "greeting": "Happy Dussehra — victory of good over evil!"},
        {"name": "Karva Chauth", "date": _D(2026, 10, 29), "emoji": "🌕",
         "greeting": "Happy Karva Chauth!"},
        {"name": "Dhanteras", "date": _D(2026, 11, 6), "emoji": "🪙",
         "greeting": "Happy Dhanteras!"},
        {"name": "Diwali (Deepavali)", "date": _D(2026, 11, 8), "emoji": "🪔",
         "greeting": "Happy Diwali! ✨ May the festival of lights bring you joy and prosperity."},
        {"name": "Bhai Dooj", "date": _D(2026, 11, 11), "emoji": "🧡",
         "greeting": "Happy Bhai Dooj!"},
        {"name": "Chhath Puja", "date": _D(2026, 11, 15), "emoji": "🌅",
         "greeting": "Happy Chhath Puja!"},
        {"name": "Guru Nanak Jayanti", "date": _D(2026, 11, 24), "emoji": "☬",
         "greeting": "Happy Gurpurab!"},
        {"name": "Christmas", "date": _D(2026, 12, 25), "emoji": "🎄",
         "greeting": "Merry Christmas!"},
    ],
    # 2027 + 2028 are best-effort curated (lunar dates shift & are moon-sighting-dependent) — the UI
    # always labels them "approximate, confirm locally", and MonitoringAgent alerts when they run low.
    2027: [
        {"name": "Makar Sankranti / Pongal", "date": _D(2027, 1, 14), "emoji": "🌾",
         "greeting": "Happy Makar Sankranti & Pongal!"},
        {"name": "Republic Day", "date": _D(2027, 1, 26), "emoji": "🇮🇳",
         "greeting": "Happy Republic Day!"},
        {"name": "Vasant Panchami", "date": _D(2027, 2, 11), "emoji": "📚",
         "greeting": "Happy Vasant Panchami!"},
        {"name": "Maha Shivaratri", "date": _D(2027, 3, 6), "emoji": "🕉️",
         "greeting": "Har Har Mahadev — Happy Maha Shivaratri!"},
        {"name": "Holi", "date": _D(2027, 3, 22), "emoji": "🌈",
         "greeting": "Happy Holi! May your life be as colorful as the festival."},
        {"name": "Eid al-Fitr", "date": _D(2027, 3, 10), "emoji": "🌙", "greeting": "Eid Mubarak!"},
        {"name": "Ugadi / Gudi Padwa", "date": _D(2027, 4, 7), "emoji": "🌱",
         "greeting": "Happy Ugadi & Gudi Padwa — a joyful new year!"},
        {"name": "Baisakhi / Vaisakhi", "date": _D(2027, 4, 14), "emoji": "🌾",
         "greeting": "Happy Baisakhi!"},
        {"name": "Ram Navami", "date": _D(2027, 4, 15), "emoji": "🏹",
         "greeting": "Jai Shri Ram — Happy Ram Navami!"},
        {"name": "Akshaya Tritiya", "date": _D(2027, 5, 8), "emoji": "🪙",
         "greeting": "Happy Akshaya Tritiya!"},
        {"name": "Eid al-Adha (Bakrid)", "date": _D(2027, 5, 17), "emoji": "🌙",
         "greeting": "Eid Mubarak!"},
        {"name": "Rath Yatra", "date": _D(2027, 7, 5), "emoji": "🛕",
         "greeting": "Jai Jagannath — Happy Rath Yatra!"},
        {"name": "Guru Purnima", "date": _D(2027, 7, 18), "emoji": "🙏",
         "greeting": "Happy Guru Purnima!"},
        {"name": "Independence Day", "date": _D(2027, 8, 15), "emoji": "🇮🇳",
         "greeting": "Happy Independence Day!"},
        {"name": "Raksha Bandhan", "date": _D(2027, 8, 17), "emoji": "🧵",
         "greeting": "Happy Raksha Bandhan!"},
        {"name": "Janmashtami", "date": _D(2027, 8, 25), "emoji": "🦚",
         "greeting": "Happy Krishna Janmashtami!"},
        {"name": "Ganesh Chaturthi", "date": _D(2027, 9, 4), "emoji": "🐘",
         "greeting": "Ganpati Bappa Morya — Happy Ganesh Chaturthi!"},
        {"name": "Onam", "date": _D(2027, 9, 12), "emoji": "🌸", "greeting": "Happy Onam!"},
        {"name": "Navratri & Durga Puja", "date": _D(2027, 9, 30), "emoji": "🪔",
         "greeting": "Happy Navratri! Nine nights of devotion, Garba & Dandiya."},
        {"name": "Gandhi Jayanti", "date": _D(2027, 10, 2), "emoji": "🕊️",
         "greeting": "Remembering Mahatma Gandhi on Gandhi Jayanti."},
        {"name": "Dussehra (Vijayadashami)", "date": _D(2027, 10, 9), "emoji": "🏹",
         "greeting": "Happy Dussehra — victory of good over evil!"},
        {"name": "Karva Chauth", "date": _D(2027, 10, 17), "emoji": "🌕",
         "greeting": "Happy Karva Chauth!"},
        {"name": "Dhanteras", "date": _D(2027, 10, 27), "emoji": "🪙", "greeting": "Happy Dhanteras!"},
        {"name": "Diwali (Deepavali)", "date": _D(2027, 10, 29), "emoji": "🪔",
         "greeting": "Happy Diwali! ✨ May the festival of lights bring you joy and prosperity."},
        {"name": "Bhai Dooj", "date": _D(2027, 10, 31), "emoji": "🧡", "greeting": "Happy Bhai Dooj!"},
        {"name": "Chhath Puja", "date": _D(2027, 11, 4), "emoji": "🌅", "greeting": "Happy Chhath Puja!"},
        {"name": "Guru Nanak Jayanti", "date": _D(2027, 11, 14), "emoji": "☬",
         "greeting": "Happy Gurpurab!"},
        {"name": "Christmas", "date": _D(2027, 12, 25), "emoji": "🎄", "greeting": "Merry Christmas!"},
    ],
    2028: [
        {"name": "Makar Sankranti / Pongal", "date": _D(2028, 1, 15), "emoji": "🌾",
         "greeting": "Happy Makar Sankranti & Pongal!"},
        {"name": "Republic Day", "date": _D(2028, 1, 26), "emoji": "🇮🇳",
         "greeting": "Happy Republic Day!"},
        {"name": "Vasant Panchami", "date": _D(2028, 1, 31), "emoji": "📚",
         "greeting": "Happy Vasant Panchami!"},
        {"name": "Eid al-Fitr", "date": _D(2028, 2, 27), "emoji": "🌙", "greeting": "Eid Mubarak!"},
        {"name": "Maha Shivaratri", "date": _D(2028, 2, 23), "emoji": "🕉️",
         "greeting": "Har Har Mahadev — Happy Maha Shivaratri!"},
        {"name": "Holi", "date": _D(2028, 3, 11), "emoji": "🌈",
         "greeting": "Happy Holi! May your life be as colorful as the festival."},
        {"name": "Ugadi / Gudi Padwa", "date": _D(2028, 3, 27), "emoji": "🌱",
         "greeting": "Happy Ugadi & Gudi Padwa — a joyful new year!"},
        {"name": "Ram Navami", "date": _D(2028, 4, 4), "emoji": "🏹",
         "greeting": "Jai Shri Ram — Happy Ram Navami!"},
        {"name": "Baisakhi / Vaisakhi", "date": _D(2028, 4, 13), "emoji": "🌾",
         "greeting": "Happy Baisakhi!"},
        {"name": "Akshaya Tritiya", "date": _D(2028, 4, 26), "emoji": "🪙",
         "greeting": "Happy Akshaya Tritiya!"},
        {"name": "Eid al-Adha (Bakrid)", "date": _D(2028, 5, 5), "emoji": "🌙", "greeting": "Eid Mubarak!"},
        {"name": "Rath Yatra", "date": _D(2028, 6, 24), "emoji": "🛕",
         "greeting": "Jai Jagannath — Happy Rath Yatra!"},
        {"name": "Guru Purnima", "date": _D(2028, 7, 6), "emoji": "🙏", "greeting": "Happy Guru Purnima!"},
        {"name": "Raksha Bandhan", "date": _D(2028, 8, 5), "emoji": "🧵",
         "greeting": "Happy Raksha Bandhan!"},
        {"name": "Janmashtami", "date": _D(2028, 8, 13), "emoji": "🦚",
         "greeting": "Happy Krishna Janmashtami!"},
        {"name": "Independence Day", "date": _D(2028, 8, 15), "emoji": "🇮🇳",
         "greeting": "Happy Independence Day!"},
        {"name": "Ganesh Chaturthi", "date": _D(2028, 8, 23), "emoji": "🐘",
         "greeting": "Ganpati Bappa Morya — Happy Ganesh Chaturthi!"},
        {"name": "Onam", "date": _D(2028, 8, 31), "emoji": "🌸", "greeting": "Happy Onam!"},
        {"name": "Navratri & Durga Puja", "date": _D(2028, 9, 19), "emoji": "🪔",
         "greeting": "Happy Navratri! Nine nights of devotion, Garba & Dandiya."},
        {"name": "Dussehra (Vijayadashami)", "date": _D(2028, 9, 28), "emoji": "🏹",
         "greeting": "Happy Dussehra — victory of good over evil!"},
        {"name": "Gandhi Jayanti", "date": _D(2028, 10, 2), "emoji": "🕊️",
         "greeting": "Remembering Mahatma Gandhi on Gandhi Jayanti."},
        {"name": "Karva Chauth", "date": _D(2028, 10, 6), "emoji": "🌕", "greeting": "Happy Karva Chauth!"},
        {"name": "Dhanteras", "date": _D(2028, 10, 15), "emoji": "🪙", "greeting": "Happy Dhanteras!"},
        {"name": "Diwali (Deepavali)", "date": _D(2028, 10, 17), "emoji": "🪔",
         "greeting": "Happy Diwali! ✨ May the festival of lights bring you joy and prosperity."},
        {"name": "Bhai Dooj", "date": _D(2028, 10, 19), "emoji": "🧡", "greeting": "Happy Bhai Dooj!"},
        {"name": "Chhath Puja", "date": _D(2028, 10, 23), "emoji": "🌅", "greeting": "Happy Chhath Puja!"},
        {"name": "Guru Nanak Jayanti", "date": _D(2028, 11, 2), "emoji": "☬", "greeting": "Happy Gurpurab!"},
        {"name": "Christmas", "date": _D(2028, 12, 25), "emoji": "🎄", "greeting": "Merry Christmas!"},
    ],
}


def _today() -> datetime.date:
    return datetime.date.today()


def _all_dated() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entries in FESTIVAL_DATES.values():
        out.extend(entries)
    out.sort(key=lambda e: e["date"])
    return out


def upcoming(n: int = 6, today: datetime.date | None = None) -> list[dict[str, Any]]:
    """The next `n` dated festivals from `today` (each with a `days_until` added). Sorted soonest-first."""
    t = today or _today()
    out = []
    for e in _all_dated():
        d = (e["date"] - t).days
        if d >= 0:
            out.append({**e, "days_until": d})
        if len(out) >= n:
            break
    return out


def next_festival(today: datetime.date | None = None) -> dict[str, Any] | None:
    up = upcoming(1, today)
    return up[0] if up else None


def days_of_runway(today: datetime.date | None = None) -> int:
    """How many days of dated-festival data remain (last dated entry minus today). Drives the
    MonitoringAgent 'festival calendar running low' alert so the countdown never silently dries up."""
    t = today or _today()
    dated = _all_dated()
    return (dated[-1]["date"] - t).days if dated else 0


def find(query: str, today: datetime.date | None = None) -> dict[str, Any] | None:
    """The soonest upcoming festival whose name loosely matches `query` (for 'when is diwali')."""
    q = (query or "").strip().lower()
    if not q:
        return None
    t = today or _today()
    for e in _all_dated():
        if (e["date"] - t).days < 0:
            continue
        name = e["name"].lower()
        if q in name or any(w in name for w in q.split() if len(w) > 2):
            return {**e, "days_until": (e["date"] - t).days}
    return None


def kb_article() -> dict[str, Any]:
    """A grounded knowledge-base article on when festivals fall this year (year derives from today, so
    the article stays current without a manual YEAR bump)."""
    year = _today().year
    lines = [
        f"Major Indian and South-Asian festivals and roughly when they fall in {year}, for planning "
        f"in the USA. Most Hindu, Sikh, Jain and Muslim festivals follow lunar or lunisolar "
        f"calendars, so the exact day shifts each year — always confirm the precise date with your "
        f"local temple, gurdwara, mosque, or a panchang (Hindu almanac) before making plans. "
        f"Communities in the US often hold the public celebration on the nearest weekend.",
        "",
    ]
    for name, when, note in FESTIVALS:
        lines.append(f"- {name}: {when} {year}" + (f" — {note}" if note else ""))
    return {"slug": f"festival-calendar-{year}", "vertical": None,
            "title": f"Indian festival calendar — when festivals fall in {year}",
            "text": "\n".join(lines)}
