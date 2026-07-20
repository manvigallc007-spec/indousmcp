"""/today — the personalized "Today in Indian America" daily feed (see today.py). Signed-in visitors
get it for their saved city + languages; everyone else gets a location-approx feed plus a prominent
"save your city" call to action (the daily-habit retention hook)."""

from __future__ import annotations

import html

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from .. import accounts, today as today_mod, verticals
from ..config import settings
from . import geoip
from .auth import portal_email
from .landing import _label, _page


def _esc(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else ""


def _when(dt) -> str:
    return dt.strftime("%a %b %d") if hasattr(dt, "strftime") else ""


def _section(title: str, inner: str) -> str:
    return (f"<section style='margin:22px 0'><h2 style='font-size:18px;margin:0 0 10px'>{title}</h2>"
            f"{inner}</section>") if inner else ""


def _render(feed: dict, *, signed_in: bool, has_city: bool) -> str:
    plat = _esc(settings.platform_name)
    loc = _esc(feed.get("city")) or "across the USA"
    parts = [f"<h1>Today in Indian America <span class='muted' style='font-weight:400'>· {loc}</span></h1>"]

    # Festival + approximate tithi
    f = feed.get("festival")
    if f:
        parts.append(
            "<div style='background:#fff3dc;border:1px solid #ffd9a0;border-radius:14px;padding:14px 16px'>"
            f"<div style='font-size:16px'>{_esc(f.get('emoji'))} <b>{_esc(f['name'])}</b> is "
            f"{_esc(f['when'])}</div>"
            + (f"<div class='muted'>{_esc(f.get('greeting'))}</div>" if f.get("greeting") else "")
            + (f"<div class='muted' style='margin-top:4px;font-size:13px'>🌙 {_esc(feed['tithi'])} "
               "— confirm with a panchang</div>" if feed.get("tithi") else "")
            + "</div>")
    elif feed.get("tithi"):
        parts.append(f"<p class='muted'>🌙 {_esc(feed['tithi'])} — approximate; confirm with a panchang</p>")

    # Events near you
    ev = feed.get("events") or []
    if ev:
        rows = "".join(
            f"<div class='lc'><a href='/events'>{_esc(e['name'])}</a> "
            f"<span class='muted'>{('· ' + _when(e.get('start_at'))) if _when(e.get('start_at')) else ''}"
            + (f" · {_esc(e.get('venue_name') or e.get('city'))}" if (e.get('venue_name') or e.get('city')) else "")
            + "</span></div>" for e in ev)
        parts.append(_section("📅 Events coming up" + (f" near {loc}" if feed.get("city") else ""),
                              rows + "<p><a href='/events'>See all events →</a></p>"))

    # New movies in your language
    mv = feed.get("movies") or []
    if mv:
        rows = "".join(
            f"<div class='lc'><a href='/movies'>{_esc(m['title'])}</a> "
            f"<span class='muted'>{('· ' + _esc(m.get('language'))) if m.get('language') else ''}</span></div>"
            for m in mv)
        parts.append(_section("🎬 Indian movies in theaters",
                              rows + "<p><a href='/movies'>All movies + showtimes →</a></p>"))

    # New places in your city; else the top-rated fallback so the section is never empty
    np = feed.get("new_places") or []
    if np:
        rows = "".join(
            f"<div class='lc'>{_esc(p['name'])} "
            f"<span class='muted'>· {_esc(_label(p['vertical']))}</span></div>" for p in np)
        parts.append(_section(f"🆕 New in {_esc(feed.get('city'))}", rows))
    else:
        pop = feed.get("popular") or []
        if pop:
            rows = "".join(
                f"<div class='lc'><a href='/listing/{p['vertical']}/{p['id']}'>{_esc(p['name'])}</a> "
                f"<span class='muted'>· {_esc(_label(p['vertical']))}"
                + (f" · {p['rating']:.1f}★" if p.get("rating") else "") + "</span></div>" for p in pop)
            parts.append(_section(f"⭐ Popular in {_esc(feed.get('city'))}", rows))

    # Help answer this — one unanswered question the viewer could answer today
    ha = feed.get("help_answer")
    if ha:
        parts.append(_section(
            "🙋 Help a neighbor",
            f"<div class='lc'><a href='/q/{_esc(ha['slug'])}'>{_esc(ha['title'])}</a> "
            "<span class='muted'>· no answers yet</span></div>"
            "<p><a href='/questions'>Answer this →</a></p>"))

    # Trending community questions
    qs = feed.get("questions") or []
    if qs:
        rows = "".join(
            f"<div class='lc'><a href='/q/{_esc(q['slug'])}'>{_esc(q['title'])}</a> "
            f"<span class='muted'>· {q['answer_count']} answer{'s' if q['answer_count'] != 1 else ''}</span></div>"
            for q in qs)
        parts.append(_section("💬 Community questions",
                              rows + "<p><a href='/questions'>Ask or answer →</a></p>"))

    # Did-you-know nugget
    n = feed.get("nugget")
    if n:
        parts.append(_section("💡 Did you know?",
                              f"<div class='lc'><b>{_esc(n['title'])}</b>"
                              f"<p class='muted' style='margin:6px 0 0'>{_esc(n['snippet'])}</p>"
                              f"<p style='margin:8px 0 0'><a href='/chat'>Ask Dost more →</a></p></div>"))

    # Retention CTA — capture a city so we can personalize + send a daily digest
    if not signed_in:
        parts.append(
            "<div style='background:#e7f6f4;border:1px solid #b8e6df;border-radius:14px;padding:16px;margin-top:20px'>"
            "<b>Make this yours.</b> <span class='muted'>Sign in and save your city to get a personalized "
            "feed + an optional daily digest of what's happening near you.</span>"
            "<p style='margin:10px 0 0'><a class='cta' href='/portal/login'>Sign in / create account →</a></p></div>")
    elif not has_city:
        parts.append(
            "<div style='background:#e7f6f4;border:1px solid #b8e6df;border-radius:14px;padding:16px;margin-top:20px'>"
            "<b>Set your city</b> <span class='muted'>to personalize this feed and your digest.</span>"
            "<p style='margin:10px 0 0'><a class='cta' href='/me'>Update your preferences →</a></p></div>")

    return "".join(parts)


def today_page(request: Request) -> HTMLResponse:
    email = portal_email(request)
    profile = accounts.get_profile(email) if email else None
    ip_point = None
    if not (profile and profile.get("home_city")):
        ip_point = geoip.approx_point(geoip.client_ip(request))
    ctx = today_mod.resolve_context(profile, ip_point)
    feed = today_mod.assemble(**ctx)
    body = _render(feed, signed_in=bool(email), has_city=bool(profile and profile.get("home_city")))
    desc = ("Today in Indian America: festivals, events, new Indian movies, and fresh local listings "
            "for the Indian community in the USA — updated daily.")
    return _page("Today in Indian America", desc, body, canonical=settings.public_web_url.rstrip("/") + "/today")


routes = [Route("/today", today_page, methods=["GET"])]
