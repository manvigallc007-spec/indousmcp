"""Parse OSM `opening_hours` into structured per-day intervals + 'open now' logic.

Handles the common subset (day ranges/lists, multiple time ranges, overnight, 24/7).
Anything it can't parse yields None (open-status unknown) rather than guessing.
"""

from __future__ import annotations

import datetime as dt
import re

_WEEK = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]  # index matches datetime.weekday()
_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")


def parse(raw: str | None) -> dict | None:
    """'Mo-Fr 11:00-22:00; Sa 12:00-23:00' -> {'0': [[660,1320]], ..., '5': [[720,1380]]}."""
    if not raw:
        return None
    raw = raw.strip()
    if raw in ("24/7", "Mo-Su 00:00-24:00"):
        return {str(d): [[0, 1440]] for d in range(7)}

    result: dict[str, list] = {}
    for rule in raw.split(";"):
        rule = rule.strip()
        if not rule or any(w in rule.lower() for w in ("closed", "off")):
            continue
        m = re.match(r"^([A-Za-z][A-Za-z,\-\s]*?)\s+([\d:,\-\s]+)$", rule)
        if not m:
            continue
        days = _parse_days(m.group(1))
        intervals = _parse_times(m.group(2))
        if not days or not intervals:
            continue
        for d in days:
            result.setdefault(str(d), []).extend(intervals)
    return result or None


def _parse_days(tok: str) -> set[int]:
    days: set[int] = set()
    for part in tok.replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if a in _WEEK and b in _WEEK:
                i, j = _WEEK.index(a), _WEEK.index(b)
                seq = range(i, j + 1) if i <= j else list(range(i, 7)) + list(range(0, j + 1))
                days.update(seq)
        elif part in _WEEK:
            days.add(_WEEK.index(part))
    return days


def _parse_times(tok: str) -> list[list[int]]:
    out = []
    for mt in _TIME.finditer(tok):
        o = int(mt[1]) * 60 + int(mt[2])
        c = int(mt[3]) * 60 + int(mt[4])
        if c == 0:
            c = 1440
        if c <= o:           # overnight (e.g. 17:00-02:00) -> roll close past midnight
            c += 1440
        out.append([o, c])
    return out


def is_open(structured: dict | None, now: dt.datetime | None = None) -> bool | None:
    """True/False if known, None if hours unknown/unparsed."""
    if not structured:
        return None
    now = now or dt.datetime.now()
    minute = now.hour * 60 + now.minute
    wd = now.weekday()
    for o, c in structured.get(str(wd), []):
        if o <= minute < c:
            return True
    # Intervals from the previous day that roll past midnight.
    for o, c in structured.get(str((wd - 1) % 7), []):
        if c > 1440 and minute < (c - 1440):
            return True
    return False


def structured_of(hours_json) -> dict | None:
    return hours_json.get("structured") if isinstance(hours_json, dict) else None


def annotate(rows: list[dict], now: dt.datetime | None = None) -> None:
    """Add an `open_now` (bool|None) field to each row in place."""
    for r in rows:
        r["open_now"] = is_open(structured_of(r.get("hours_json")), now)


def with_hours(hours_json) -> dict | None:
    """Ensure a hours_json dict carries a parsed `structured` form."""
    if not isinstance(hours_json, dict) or not hours_json.get("raw"):
        return hours_json
    return {"raw": hours_json["raw"], "structured": parse(hours_json["raw"])}
