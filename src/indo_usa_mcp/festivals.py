"""Festival timing for grounded "when is <festival>" answers.

Hindu/Sikh/Jain/Muslim festivals follow lunar or lunisolar calendars, so the exact day shifts every
year. We deliberately publish the MONTH for those (and the exact day only for fixed/solar festivals
like Republic Day or Makar Sankranti) and tell users to confirm the precise date locally — better an
honestly approximate answer than a fabricated precise one. Update YEAR + the list each year.
"""

from __future__ import annotations

from typing import Any

YEAR = 2026

# (festival, when in YEAR, short note). Exact day only where the date is fixed/solar and stable.
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


def kb_article() -> dict[str, Any]:
    """A grounded knowledge-base article on when festivals fall this year."""
    lines = [
        f"Major Indian and South-Asian festivals and roughly when they fall in {YEAR}, for planning "
        f"in the USA. Most Hindu, Sikh, Jain and Muslim festivals follow lunar or lunisolar "
        f"calendars, so the exact day shifts each year — always confirm the precise date with your "
        f"local temple, gurdwara, mosque, or a panchang (Hindu almanac) before making plans. "
        f"Communities in the US often hold the public celebration on the nearest weekend.",
        "",
    ]
    for name, when, note in FESTIVALS:
        lines.append(f"- {name}: {when} {YEAR}" + (f" — {note}" if note else ""))
    return {"slug": f"festival-calendar-{YEAR}", "vertical": None,
            "title": f"Indian festival calendar — when festivals fall in {YEAR}",
            "text": "\n".join(lines)}
