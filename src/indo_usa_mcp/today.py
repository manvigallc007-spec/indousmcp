"""'Today in Indian America' — the personalized daily feed that makes the site a daily habit.

Assembles, for a viewer's city + languages: the festival countdown (+ an APPROXIMATE panchang/tithi
line, honestly labeled), the soonest events near them, new Indian movies in their language, places newly
added in their city, and a rotating culture/immigration 'did you know' nugget. Pure read-only assembly
over existing data — every section degrades gracefully (omitted when empty), nothing here can raise.

The digest agent reuses `assemble()` to build email/Telegram/push digests from the same data.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

# ------------------------------------------------------------------ approximate panchang (tithi)
# A lunar day (tithi) = the moon gaining 12° on the sun. We approximate it from the mean synodic phase
# off a known new moon — good to ~a day, NEVER exact (true tithi needs real lunar/solar longitude).
# Clearly labeled "approx" everywhere it surfaces, same honesty rule the festival dates already follow.
_NEW_MOON_REF = _dt.datetime(2000, 1, 6, 18, 14, tzinfo=_dt.timezone.utc)  # a known new moon (UTC)
_SYNODIC = 29.530588853  # mean synodic month, days
_TITHI_NAMES = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami",
                "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi"]


def approx_tithi(now: _dt.datetime | None = None) -> str:
    """A best-effort 'Shukla/Krishna <tithi> (approx)' string for today. Never raises."""
    try:
        n = now or _dt.datetime.now(_dt.timezone.utc)
        if n.tzinfo is None:
            n = n.replace(tzinfo=_dt.timezone.utc)
        age = ((n - _NEW_MOON_REF).total_seconds() / 86400.0) % _SYNODIC
        t = int(age / _SYNODIC * 30)                 # 0..29
        paksha = "Shukla" if t < 15 else "Krishna"   # waxing / waning
        i = t % 15
        name = ("Purnima" if t == 14 else "Amavasya" if t == 29 else _TITHI_NAMES[i])
        return f"{paksha} {name} (approx.)"
    except Exception:
        return ""


# ------------------------------------------------------------------ daily nugget (rotates by day)
def daily_nugget(today: _dt.date | None = None) -> dict | None:
    """One knowledge-base article, chosen deterministically by day so it rotates daily."""
    try:
        from . import knowledge_seed
        arts = knowledge_seed.ARTICLES
        if not arts:
            return None
        d = today or _dt.date.today()
        a = arts[d.toordinal() % len(arts)]
        text = (a.get("text") or "").strip()
        return {"slug": a.get("slug"), "title": a.get("title"),
                "snippet": (text[:220] + "…") if len(text) > 220 else text}
    except Exception:
        return None


# ------------------------------------------------------------------ popular-near-you fallback
def popular_near(city: str | None, state: str | None = None, limit: int = 6) -> list[dict]:
    """Top community-rated listings in a city, across reviewable verticals — the fallback for the
    'new places' section so Today is never empty in a thin/quiet city. Never raises."""
    if not city:
        return []
    try:
        from . import reviews, verticals
        from . import db
        out: list[dict] = []
        for v in reviews.REVIEWABLE:
            try:
                rows = db.query(
                    f"SELECT id, name, community_rating, community_rating_count FROM {verticals._table(v)} "
                    f"WHERE deleted_at IS NULL AND is_active AND lower(city) = lower(%s) "
                    f"AND community_rating_count > 0 "
                    f"ORDER BY community_rating DESC NULLS LAST, community_rating_count DESC LIMIT %s",
                    (city, limit))
            except Exception:
                continue
            for r in rows:
                out.append({"vertical": v, "id": r["id"], "name": r["name"],
                            "rating": float(r["community_rating"]) if r.get("community_rating") else None,
                            "rating_count": int(r.get("community_rating_count") or 0)})
        out.sort(key=lambda x: (x["rating"] or 0, x["rating_count"]), reverse=True)
        return out[:limit]
    except Exception:
        return []


# ------------------------------------------------------------------ the feed
def assemble(*, city: str | None = None, state: str | None = None, languages: list[str] | None = None,
             lat: float | None = None, lng: float | None = None,
             today: _dt.date | None = None) -> dict[str, Any]:
    """Build the Today feed for a location + languages. All sections optional; never raises."""
    today = today or _dt.date.today()
    out: dict[str, Any] = {"city": city, "state": state, "date": today.isoformat()}

    # Festival countdown + approximate tithi
    try:
        from . import festivals
        nf = festivals.next_festival()
        if nf:
            d = nf["days_until"]
            out["festival"] = {"name": nf["name"], "emoji": nf.get("emoji"),
                               "greeting": nf.get("greeting"), "days_until": d,
                               "when": "today!" if d == 0 else ("tomorrow" if d == 1 else f"in {d} days")}
    except Exception:
        pass
    out["tithi"] = approx_tithi()

    # Soonest events near the viewer
    try:
        from .events import queries as eq
        ev = eq.get_indian_events(lat=lat, lng=lng, city=city, state=state, limit=5).get("results", [])
        out["events"] = [{"id": e.get("id"), "name": e.get("name"), "start_at": e.get("start_at"),
                          "venue_name": e.get("venue_name"), "city": e.get("city")} for e in ev]
    except Exception:
        out["events"] = []

    # New Indian movies in the viewer's language(s)
    try:
        from . import movies
        langs = [l for l in (languages or []) if l]
        seen, mv = set(), []
        for row in (sum((movies.list_in_theaters(language=l, limit=8) for l in langs), [])
                    if langs else movies.list_in_theaters(limit=8)):
            if row["id"] not in seen:
                seen.add(row["id"])
                mv.append({"id": row["id"], "title": row["title"], "language": row.get("language"),
                           "poster_url": row.get("poster_url"), "ticket_url": row.get("ticket_url")})
        out["movies"] = mv[:6]
    except Exception:
        out["movies"] = []

    # Places newly added in the viewer's city; fall back to top-rated nearby so it's never empty.
    try:
        if city:
            from .telegram_bot import _recent_listings
            out["new_places"] = _recent_listings(city, state, days=14, limit=6)
        else:
            out["new_places"] = []
    except Exception:
        out["new_places"] = []
    out["popular"] = popular_near(city, state, limit=6) if not out["new_places"] else []

    out["nugget"] = daily_nugget(today)

    # Trending community questions (Ask-the-community, Phase 3)
    try:
        from . import qa
        if qa.enabled():
            out["questions"] = qa.trending(limit=4)
            # "Help answer this": one unanswered question the viewer could answer today. Deterministic
            # by day so it's stable across a day's page loads. Never just the festival line.
            un = qa.unanswered(limit=20)
            out["help_answer"] = un[today.toordinal() % len(un)] if un else None
        else:
            out["questions"], out["help_answer"] = [], None
    except Exception:
        out["questions"], out["help_answer"] = [], None
    return out


def render_digest_text(feed: dict, base_url: str) -> str:
    """Plain-text digest from an assembled feed (email/Telegram/push share this). Empty sections skip."""
    base = base_url.rstrip("/")
    where = f" · {feed['city']}" if feed.get("city") else ""
    lines = [f"Today in Indian America{where}", ""]
    f = feed.get("festival")
    if f:
        lines.append(f"{f.get('emoji') or ''} {f['name']} is {f['when']} — {f.get('greeting') or ''}".strip())
    if feed.get("tithi"):
        lines.append(f"🌙 {feed['tithi']} — confirm with a panchang")
    ev = feed.get("events") or []
    if ev:
        lines += ["", "📅 Events coming up:"]
        for e in ev[:5]:
            when = e["start_at"].strftime("%a %b %d") if hasattr(e.get("start_at"), "strftime") else ""
            loc = ", ".join(x for x in (e.get("venue_name"), e.get("city")) if x)
            lines.append(f"• {e['name']}" + (f" — {when}" if when else "") + (f" ({loc})" if loc else ""))
        lines.append(f"  {base}/events")
    mv = feed.get("movies") or []
    if mv:
        lines += ["", "🎬 Indian movies in theaters:"]
        lines += [f"• {m['title']}" + (f" ({m['language']})" if m.get("language") else "") for m in mv[:5]]
        lines.append(f"  {base}/movies")
    np = feed.get("new_places") or []
    if np and feed.get("city"):
        lines += ["", f"🆕 New in {feed['city']}:"]
        lines += [f"• {p['name']} ({p['vertical']})" for p in np[:6]]
    pop = feed.get("popular") or []
    if pop and feed.get("city"):
        lines += ["", f"⭐ Popular in {feed['city']}:"]
        lines += [f"• {p['name']} ({p['vertical']})"
                  + (f" — {p['rating']:.1f}★" if p.get("rating") else "") for p in pop[:6]]
    ha = feed.get("help_answer")
    if ha:
        lines += ["", "🙋 Help a neighbor — answer this:",
                  f"• {ha['title']}  {base}/q/{ha['slug']}"]
    qs = feed.get("questions") or []
    if qs:
        lines += ["", "💬 Community questions:"]
        lines += [f"• {q['title']}  {base}/q/{q['slug']}" for q in qs[:4]]
    n = feed.get("nugget")
    if n:
        lines += ["", f"💡 {n['title']}", n["snippet"]]
    lines += ["", f"See more: {base}/today"]
    return "\n".join(lines)


def resolve_context(profile: dict | None, ip_point: tuple[float, float] | None) -> dict[str, Any]:
    """Decide city/state/languages/lat-lng from a signed-in profile, else an IP-approx point."""
    if profile and (profile.get("home_city") or profile.get("languages")):
        return {"city": profile.get("home_city"), "state": profile.get("home_state"),
                "languages": profile.get("languages") or [], "lat": None, "lng": None}
    if ip_point:
        from . import geocode
        c, _s = geocode.city_state(ip_point[0], ip_point[1])   # admin1 is a full name; use city + coords
        return {"city": c, "state": None, "languages": [], "lat": ip_point[0], "lng": ip_point[1]}
    return {"city": None, "state": None, "languages": [], "lat": None, "lng": None}
