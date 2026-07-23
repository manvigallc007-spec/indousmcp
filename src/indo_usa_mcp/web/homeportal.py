"""The 'daily portal' that renders below the Dost hero on the homepage — a nripage-style feed of
everything happening in Indian America: Today, upcoming events, movies in theaters, newly-added
businesses, live owner deals, community Q&A, latest news, and the deep-data sections (Insights,
H-1B, leaderboard). Pure read-only assembly over existing data; every section degrades to nothing
when empty, and nothing here can raise (the homepage must always render)."""

from __future__ import annotations

import html

from .. import verticals
from ..config import settings

_BIZ_VERTICALS = ["restaurants", "groceries", "sweets", "salons", "temples", "apparel"]


def _esc(s) -> str:
    return html.escape(str(s)) if s not in (None, "") else ""


def _section(title: str, more_href: str, more_label: str, inner: str) -> str:
    if not inner:
        return ""
    return (f"<section class='psec'><div class='psec-h'><h2>{title}</h2>"
            f"<a href='{more_href}'>{more_label} →</a></div>"
            f"<div class='pgrid'>{inner}</div></section>")


def _card(href: str, title: str, meta: str = "", tag: str = "", thumb: str = "") -> str:
    t = f"<span class='pc-tag'>{_esc(tag)}</span>" if tag else ""
    m = f"<div class='pc-meta'>{meta}</div>" if meta else ""
    img = (f"<img src='{_esc(thumb)}' alt='' loading='lazy' onerror='this.remove()' class='pc-thumb'>"
           if thumb else "")
    return f"<a class='pcard' href='{href}'>{img}<div class='pc-body'>{t}<h3>{_esc(title)}</h3>{m}</div></a>"


# ------------------------------------------------------------------ sections
def _today_card() -> str:
    try:
        from .. import festivals, today
        nf = festivals.next_festival()
        tithi = today.approx_tithi()
        if not nf and not tithi:
            return ""
        parts = []
        if nf:
            d = nf["days_until"]
            when = "today! 🎉" if d == 0 else ("tomorrow" if d == 1 else f"in {d} days")
            parts.append(f"{_esc(nf.get('emoji'))} <b>{_esc(nf['name'])}</b> is {when}")
        if tithi:
            parts.append(f"🌙 {_esc(tithi)} <span class='muted'>(approx.)</span>")
        inner = ("<a class='pcard pwide' href='/today'><div class='pc-body'>"
                 "<span class='pc-tag'>Today in Indian America</span>"
                 f"<h3>{' · '.join(parts)}</h3>"
                 "<div class='pc-meta'>Your daily briefing — festivals, events &amp; more</div>"
                 "</div></a>")
        return f"<section class='psec'><div class='pgrid'>{inner}</div></section>"
    except Exception:
        return ""


def _events() -> str:
    try:
        from ..events import queries as eq
        rows = eq.get_indian_events(limit=6).get("results", [])
        inner = ""
        for e in rows:
            when = e["start_at"].strftime("%a %b %d") if hasattr(e.get("start_at"), "strftime") else ""
            loc = ", ".join(x for x in (e.get("venue_name"), e.get("city")) if x)
            meta = " · ".join(x for x in (when, _esc(loc)) if x)
            inner += _card("/events", e.get("name") or "Event", meta=meta, tag="Event")
        return _section("📅 Upcoming events", "/events", "All events", inner)
    except Exception:
        return ""


def _movies() -> str:
    try:
        from .. import movies
        rows = movies.list_in_theaters(limit=8)
        inner = ""
        for m in rows:
            inner += _card("/movies", m.get("title") or "Movie",
                           meta=_esc(m.get("language") or ""), thumb=m.get("poster_url") or "")
        return _section("🎬 Indian movies in theaters", "/movies", "Showtimes", inner)
    except Exception:
        return ""


def _businesses() -> str:
    """Newly-added listings across a few popular verticals, newest first."""
    try:
        from .. import db
        merged = []
        for v in _BIZ_VERTICALS:
            try:
                tbl = verticals._table(v)
                for r in db.query(
                    f"SELECT id, name, city, state, created_at FROM {tbl} "
                    f"WHERE deleted_at IS NULL AND is_active AND name IS NOT NULL "
                    f"ORDER BY created_at DESC LIMIT 4", ()):
                    r["vertical"] = v
                    merged.append(r)
            except Exception:
                continue
        merged.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
        inner = ""
        for r in merged[:6]:
            loc = ", ".join(x for x in ((r.get("city") or "").title(), (r.get("state") or "").upper()) if x)
            label = verticals.VERTICALS.get(r["vertical"], {}).get("label", r["vertical"])
            inner += _card(f"/listing/{r['vertical']}/{r['id']}", r.get("name") or "",
                           meta=_esc(loc), tag=label)
        return _section("🆕 Newly added businesses", "/browse", "Browse all", inner)
    except Exception:
        return ""


def _deals() -> str:
    try:
        from .. import owner_content
        rows = owner_content.live_offers(limit=6)
        inner = ""
        for o in rows:
            loc = ", ".join(x for x in ((o.get("city") or "").title(), (o.get("state") or "").upper()) if x)
            meta = " · ".join(x for x in (_esc(o.get("name")), _esc(loc)) if x)
            inner += _card(f"/listing/{o['vertical']}/{o['listing_id']}", o.get("title") or "Offer",
                           meta=meta, tag="Deal")
        return _section("🏷️ Deals &amp; offers", "/browse", "Browse", inner)
    except Exception:
        return ""


def _questions() -> str:
    try:
        from .. import qa
        if not qa.enabled():
            return ""
        rows = qa.trending(limit=5)
        inner = ""
        for q in rows:
            n = q.get("answer_count") or 0
            inner += _card(f"/q/{q['slug']}", q.get("title") or "",
                           meta=f"{n} answer{'s' if n != 1 else ''}", tag="Q&amp;A")
        return _section("💬 Community Q&amp;A", "/questions", "Ask or answer", inner)
    except Exception:
        return ""


def _articles() -> str:
    """In-house AI roundups — featured above the raw headline feed so readers stay on-site."""
    try:
        from .. import articles
        if not articles.enabled():
            return ""
        rows = articles.latest(limit=4)
        inner = ""
        for a in rows:
            label = articles.CATEGORIES.get(a.get("category"), a.get("category") or "")
            inner += _card(f"/article/{a['slug']}", a.get("title") or "",
                           meta=_esc(a.get("dek") or ""), tag=label)
        return _section("📰 Indian America — news roundups", "/articles", "All roundups", inner)
    except Exception:
        return ""


def _news() -> str:
    """Latest India/NRI news headlines (filled once the news feed is populated)."""
    try:
        from .. import news
        rows = news.latest(limit=6)
        inner = ""
        for a in rows:
            when = a["published_at"].strftime("%b %d") if hasattr(a.get("published_at"), "strftime") else ""
            meta = " · ".join(x for x in (_esc(a.get("source")), when) if x)
            inner += (f"<a class='pcard' href='{_esc(a['url'])}' target='_blank' rel='noopener nofollow'>"
                      f"<div class='pc-body'><span class='pc-tag'>News</span>"
                      f"<h3>{_esc(a['title'])}</h3><div class='pc-meta'>{meta}</div></div></a>")
        return _section("📰 Latest news for Indians in the USA", "/news", "More news", inner)
    except Exception:
        return ""


def _deepdata() -> str:
    """Insights / H-1B / leaderboard teaser tiles — the 'deep data' credibility row."""
    tiles = [
        ("/insights", "📊", "Where Indians live", "Census demographics by metro &amp; state"),
        ("/employers", "💼", "H-1B visa sponsors", "Top US employers by certified petitions"),
        ("/leaderboard", "🏆", "Top contributors", "The community keeping this current"),
    ]
    inner = "".join(
        f"<a class='pcard pc-deep' href='{h}'><div class='pc-body'>"
        f"<h3>{ico} {t}</h3><div class='pc-meta'>{d}</div></div></a>"
        for h, ico, t, d in tiles)
    return f"<section class='psec'><div class='psec-h'><h2>Explore the data</h2></div><div class='pgrid'>{inner}</div></section>"


def render() -> str:
    """The full portal block. Empty string only if literally every section is empty."""
    plat = _esc(settings.platform_name)
    body = (_today_card() + _articles() + _news() + _events() + _movies() + _businesses()
            + _deals() + _questions() + _deepdata())
    if not body.strip():
        return ""
    return (f"<div class='homeportal'><div class='ph-head'>Explore {plat} "
            "<span class='muted'>— your daily guide to Indian America</span></div>"
            f"{body}</div>")


CSS = """
 .homeportal{width:min(1040px,94vw);margin:40px auto 0;text-align:left;position:relative;
   left:50%;transform:translateX(-50%)}
 .ph-head{font-size:15px;font-weight:700;color:#3a3f4b;margin:0 0 6px;padding-top:22px;
   border-top:1px solid #eee}
 .ph-head .muted{font-weight:400}
 .psec{margin:22px 0}
 .psec-h{display:flex;align-items:baseline;justify-content:space-between;margin:0 0 10px}
 .psec-h h2{font-size:18px;margin:0}
 .psec-h a{font-size:13px;font-weight:600}
 .pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px}
 .pcard{display:flex;flex-direction:column;background:#fff;border:1px solid #ececec;border-radius:12px;
   overflow:hidden;text-decoration:none;color:inherit;transition:.15s}
 .pcard:hover{transform:translateY(-2px);box-shadow:0 10px 22px rgba(16,24,40,.09)}
 .pc-thumb{width:100%;height:120px;object-fit:cover;background:#f3efe9}
 .pc-body{padding:11px 13px}
 .pcard h3{font-size:15px;margin:2px 0 0;line-height:1.3}
 .pc-meta{color:#6b7280;font-size:12.5px;margin-top:5px}
 .pc-tag{font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:#c1440e}
 .pwide{grid-column:1/-1}
 .pwide h3{font-size:17px;font-weight:600}
 .pc-deep h3{font-size:15.5px}
 @media(max-width:560px){.pgrid{grid-template-columns:1fr 1fr}.pc-thumb{height:96px}}
"""
