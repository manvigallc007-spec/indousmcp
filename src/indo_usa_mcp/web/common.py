"""Shared HTML shell + helpers for the web app (public, admin, portal)."""

from __future__ import annotations

import html

from starlette.responses import HTMLResponse

from ..config import settings

_BRAND = "#c1440e"


def esc(value) -> str:
    return html.escape(str(value)) if value not in (None, "") else ""


def sparkline(values: list[int], *, width: int = 120, height: int = 30, color: str = _BRAND) -> str:
    """A tiny inline-SVG sparkline (area under a line) from a series of ints. No external libraries,
    so it renders under our CSP. Returns '' for an all-zero/empty series."""
    if not values or max(values) == 0:
        return ""
    n = len(values)
    hi = max(values)
    step = width / max(n - 1, 1)
    pad = 3
    ih = height - pad * 2
    pts = [(i * step, pad + ih - (v / hi) * ih) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{height} " + line + f" {width},{height}"
    return (f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
            f"preserveAspectRatio='none' role='img' aria-label='trend'>"
            f"<polygon points='{area}' fill='{color}' opacity='0.12'/>"
            f"<polyline points='{line}' fill='none' stroke='{color}' stroke-width='1.5' "
            f"stroke-linejoin='round'/></svg>")


def trend_badge(delta_pct: int) -> str:
    """A ▲/▼ colored delta badge for a period-over-period percentage change."""
    if delta_pct > 0:
        return f"<span style='color:#0f8a4f;font-weight:600'>▲ {delta_pct}%</span>"
    if delta_pct < 0:
        return f"<span style='color:#c0392b;font-weight:600'>▼ {abs(delta_pct)}%</span>"
    return "<span class='muted'>—</span>"


# US states + DC + the common territories, as (code, name) — for a consistent state dropdown so the
# stored value is always a clean 2-letter USPS code (city stays free-text).
from ..pipeline.clean import _US_STATES as _ST  # full-name -> code

_STATES: list[tuple[str, str]] = sorted(
    ((code, full.title()) for full, code in _ST.items()), key=lambda x: x[1]
) + [("PR", "Puerto Rico"), ("GU", "Guam"), ("VI", "U.S. Virgin Islands"),
     ("AS", "American Samoa"), ("MP", "Northern Mariana Islands")]


def state_select(name: str = "state", selected: str = "", required: bool = False) -> str:
    """A US-state <select>; value = 2-letter USPS code. `selected` may be a code or full name."""
    from ..pipeline.clean import normalize_state
    sel = (normalize_state(selected) or "").strip().upper()
    opts = ["<option value=''>Select a state…</option>"]
    opts += [f"<option value='{c}'{' selected' if c == sel else ''}>{html.escape(n)} ({c})</option>"
             for c, n in _STATES]
    return f"<select name='{html.escape(name)}'{' required' if required else ''}>{''.join(opts)}</select>"


def captcha_field() -> str:
    """Captcha form fields: Cloudflare Turnstile widget if configured, else a signed math challenge.
    Shared by the registration form and the public contact form."""
    from .auth import make_captcha
    if settings.turnstile_enabled:
        return (f"<div class='cf-turnstile' data-sitekey='{esc(settings.turnstile_site_key)}'></div>"
                "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js' async defer></script>")
    c = make_captcha()
    return (f"<label>{esc(c['question'])}</label>"
            "<input name='captcha' inputmode='numeric' autocomplete='off' required>"
            f"<input type='hidden' name='captcha_token' value='{esc(c['token'])}'>")


# Cross-promotion for sibling apps (same operator) — mirrors the "From our family of apps" section
# on biryanihub.co, but placed at the top (below the header) rather than the footer, per request.
# Fully inline-styled so it drops cleanly into any of the site's several independent page templates
# without needing a matching CSS class in each one's own <style> block. Palette matches the existing
# festival-banner look (chat.py's countdown strip / ogimage.py's festival card) for visual consistency.
_PARTNER_APPS = [
    ("https://biryanihub.co", "🍛", "BiryaniHub.co"),
    ("https://caterbid.co", "🍽", "CaterBid.co"),
]


def partner_bar() -> str:
    links = "".join(
        f"<a href='{url}' target='_blank' rel='noopener' "
        "style='color:#b4530f;font-weight:600;text-decoration:none;margin:0 10px;white-space:nowrap'>"
        f"{emoji} {html.escape(name)}</a>" for url, emoji, name in _PARTNER_APPS)
    return (
        "<div style='background:#fff3dc;border-bottom:1px solid #ffd9a0;padding:8px 16px;"
        "text-align:center;font-size:13px;color:#8a6a40'>"
        "<span style='margin-right:6px'>✨ From our family of apps:</span>"
        f"{links}</div>")


# ------------------------------------------------------------------ shared site header / nav
# Single source of truth for the top menu so every page shell (landing, chat, owner card, about,
# /explore, error pages) shows the SAME items. (href, label). The last item is styled as a CTA.
NAV_ITEMS: list[tuple[str, str]] = [
    ("/", "Home"),
    ("/today", "☀ Today"),
    ("/articles", "📰 News"),
    ("/events", "📅 Events"),
    ("/browse", "Browse"),
    ("/questions", "💬 Q&A"),
    ("/insights", "📊 Insights"),
    ("/find", "🔎 Search"),
    ("/me", "♥ Saved"),
    ("/for-business", "List your business"),
    ("/chat", "Ask Dost"),
]


def nav_html(active: str = "") -> str:
    """The shared sticky site header: logo + the full menu. Horizontally scrollable on mobile so every
    item stays reachable (never hidden). `active` is a path (e.g. '/browse') to highlight the current
    item. Self-contained markup; pair with NAV_CSS in the page's <style>."""
    plat = html.escape(settings.platform_name)
    links = ""
    for href, label in NAV_ITEMS:
        cls = "nav-cta" if href == "/chat" else ""
        if active and (active == href or (href != "/" and active.startswith(href))):
            cls = (cls + " on").strip()
        links += (f"<a href='{href}'" + (f" class='{cls}'" if cls else "")
                  + (" aria-current='page'" if "on" in cls else "") + f">{html.escape(label)}</a>")
    return (
        "<header class='site-header'>"
        f"<a class='site-brand' href='/'><img src='/logo' alt='{plat}'><span>{plat}</span></a>"
        f"<nav class='site-nav' aria-label='Main'>{links}</nav>"
        "</header>")


# Self-contained (explicit hex, no CSS vars) so it renders identically inside every shell's own <style>.
NAV_CSS = """
 .site-header{display:flex;align-items:center;gap:14px;background:#fff;border-bottom:1px solid #ececec;
   padding:10px 18px;position:sticky;top:0;z-index:50}
 .site-brand{display:inline-flex;align-items:center;gap:9px;text-decoration:none;color:#1f2430;
   font-weight:800;flex:0 0 auto}
 .site-brand img{height:32px;width:auto;max-width:150px;border-radius:8px;display:block}
 .site-brand span{font-size:16px;white-space:nowrap}
 .site-nav{display:flex;align-items:center;gap:5px;overflow-x:auto;scrollbar-width:none;
   -webkit-overflow-scrolling:touch;flex:1 1 auto}
 .site-nav::-webkit-scrollbar{display:none}
 .site-nav a{color:#3a3f4b;text-decoration:none;font-weight:600;font-size:14px;white-space:nowrap;
   padding:7px 10px;border-radius:8px;flex:0 0 auto}
 .site-nav a:hover{background:#f5f1ec;color:#c1440e}
 .site-nav a.on{color:#c1440e}
 .site-nav a.nav-cta{background:#c1440e;color:#fff;margin-left:4px}
 .site-nav a.nav-cta:hover{background:#a5380b;color:#fff}
 @media(max-width:760px){.site-brand span{display:none}}
"""


def share_html(path_or_url: str, title: str) -> str:
    """A small share bar (native share sheet with copy-link fallback + a WhatsApp button — the
    diaspora's dominant channel). `path_or_url` may be a site path; it's made absolute. Self-contained:
    the tiny handler is defined idempotently, so dropping this into many templates is safe."""
    url = path_or_url if "://" in path_or_url else settings.public_web_url.rstrip("/") + path_or_url
    u, t = html.escape(url, quote=True), html.escape(title, quote=True)
    import urllib.parse
    wa = "https://wa.me/?text=" + urllib.parse.quote(f"{title} {url}")
    btn = ("display:inline-block;border:1px solid #d9d5cf;background:#fff;border-radius:999px;"
           "padding:5px 13px;font-size:13px;font-weight:600;color:#3a4654;text-decoration:none;cursor:pointer")
    return (
        "<span class='sharebar' style='display:inline-flex;gap:8px;flex-wrap:wrap;align-items:center'>"
        f"<button type='button' style='{btn}' data-u=\"{u}\" data-t=\"{t}\" onclick='naShare(this)'>↗ Share</button>"
        f"<a style='{btn};color:#128c7e' href='{html.escape(wa, quote=True)}' target='_blank' rel='noopener'>WhatsApp</a>"
        "</span>"
        "<script>window.naShare=window.naShare||function(b){var u=b.dataset.u,t=b.dataset.t;"
        "if(navigator.share){navigator.share({title:t,url:u}).catch(function(){})}"
        "else if(navigator.clipboard){navigator.clipboard.writeText(u);b.textContent='Copied!';"
        "setTimeout(function(){b.textContent='↗ Share'},1500)}else{prompt('Copy this link:',u)}};</script>")


def analytics_tag() -> str:
    """Google Analytics (GA4) gtag snippet for the <head>, or '' when GOOGLE_ANALYTICS_ID is unset.
    The measurement ID is public (it's visible in page source), so it's plain config, not a secret."""
    gid = (settings.google_analytics_id or "").strip()
    if not gid:
        return ""
    g = html.escape(gid)
    return (f'<script async src="https://www.googletagmanager.com/gtag/js?id={g}"></script>'
            "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
            f"gtag('js',new Date());gtag('config','{g}');</script>")


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    """Narrow card layout for public / owner-facing pages."""
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{analytics_tag()}
<style>
 :root{{--brand:#e8772e;--brand-d:#cf6212;--accent:#0f9b8e;--ink:#222b33;--muted:#667085;--line:#ece6dd}}
 *{{box-sizing:border-box}}
 body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;max-width:520px;
   margin:0 auto;min-height:100vh;padding:38px 18px;color:var(--ink);line-height:1.55;
   background:linear-gradient(180deg,#fff7ef 0,#faf8f4 260px)}}
 .card{{background:#fff;border:1px solid var(--line);border-radius:18px;padding:30px 28px;
   box-shadow:0 14px 44px rgba(16,24,40,.09);border-top:4px solid var(--brand)}}
 h2{{margin:0 0 8px;font-size:24px;letter-spacing:-.01em}} h3{{margin:20px 0 8px;font-size:18px}}
 p{{margin:0 0 14px}}
 label{{display:block;font-size:13.5px;font-weight:600;color:#3a4654;margin-top:6px}}
 input{{width:100%;padding:12px 13px;margin:6px 0 14px;border:1.5px solid #e3ddd3;border-radius:11px;
   font-size:15px;background:#fff;transition:.15s}}
 input:focus{{outline:0;border-color:var(--brand);box-shadow:0 0 0 4px #e8772e22}}
 button{{background:linear-gradient(135deg,var(--brand),var(--brand-d));color:#fff;border:0;
   padding:13px 22px;border-radius:11px;font-size:15px;font-weight:600;cursor:pointer;width:100%;
   transition:.15s;box-shadow:0 6px 16px #e8772e33}}
 button:hover{{filter:brightness(1.05);transform:translateY(-1px)}}
 a{{color:var(--brand);text-decoration:none}} a:hover{{text-decoration:underline}}
 table a{{font-weight:600}}
 .muted{{color:var(--muted);font-size:14px}} .ok{{color:#137333}} .err{{color:#c5221f}}
 table{{width:100%;border-collapse:collapse;font-size:14px;margin:6px 0}}
 td,th{{padding:9px 6px;border-bottom:1px solid #f0ece5;text-align:left}}
 body{{max-width:none;padding:0}}
 .cardwrap{{max-width:520px;margin:0 auto;padding:26px 18px}}
{NAV_CSS}
</style></head><body>
{nav_html()}
<div class="cardwrap"><div class="card">{body}</div>
<p class="muted" style="text-align:center;margin-top:20px"><a href="/">&#8592; Back to {html.escape(settings.platform_name)}</a></p>
</div></body></html>"""
    return HTMLResponse(doc, status_code=status)


# Grouped admin nav: (section label, [(item label, href), ...]).
_ADMIN_NAV = [
    ("", [("Overview", "/admin"), ("Operations", "/admin/ops"), ("Dashboard", "/admin/dashboard"),
          ("Search all", "/admin/data")]),
    ("Listings", [("Data", "/admin/data/restaurants"), ("Coverage", "/admin/coverage"),
                  ("Geography", "/admin/geo/restaurants"), ("Quality", "/admin/quality/restaurants"),
                  ("Moderation", "/admin/moderation")]),
    ("Content", [("Movies", "/admin/movies"), ("Employers", "/admin/employers"),
                 ("Knowledge", "/admin/knowledge")]),
    ("Inbox", [("Messages", "/admin/messages"), ("Submissions", "/admin/submissions"),
               ("Reviews", "/admin/reviews"), ("Q&A", "/admin/qa"), ("Approvals", "/admin/approvals"),
               ("Feedback", "/admin/feedback"), ("Claims", "/admin/claims")]),
    ("Growth", [("Events", "/admin/events"), ("Recommendations", "/admin/recommendations"),
                ("Misses", "/admin/misses"), ("Payments", "/admin/payments")]),
    ("System", [("Agents", "/admin/agents"), ("Traffic", "/admin/traffic"),
                ("Reports", "/admin/reports")]),
]


def _nav_badges() -> dict[str, int]:
    """Cheap counts of items needing attention, shown as red badges in the admin nav."""
    from .. import db
    out: dict[str, int] = {}
    q = {
        "Messages": "SELECT count(*) FROM contact_messages WHERE status IN ('new','drafted')",
        "Approvals": "SELECT count(*) FROM approval_queue WHERE status = 'pending'",
        "Submissions": "SELECT count(*) FROM submissions WHERE status = 'pending'",
        "Reviews": "SELECT count(*) FROM reviews WHERE status = 'pending'",
        "Q&A": "SELECT (SELECT count(*) FROM questions WHERE status='pending') "
               "+ (SELECT count(*) FROM answers WHERE status='pending')",
        "Feedback": "SELECT count(*) FROM feedback WHERE status = 'pending'",
    }
    for label, sql in q.items():
        try:
            row = db.query_one(sql)
            n = int(list(row.values())[0]) if row else 0
            if n:
                out[label] = n
        except Exception:
            pass
    return out


def admin_page(title: str, body: str, active: str = "", status: int = 200) -> HTMLResponse:
    """Wide layout with a grouped nav bar (+ attention badges) for the admin dashboard."""
    badges = _nav_badges()

    def _link(label: str, href: str) -> str:
        b = f"<span class='badge'>{badges[label]}</span>" if badges.get(label) else ""
        return f"<a href='{href}' class='{'on' if label == active else ''}'>{label}{b}</a>"

    nav = "".join(
        "<span class='navgrp'>" + (f"<span class='navsec'>{sec}</span>" if sec else "")
        + "".join(_link(lbl, href) for lbl, href in items) + "</span>"
        for sec, items in _ADMIN_NAV)
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Admin</title>
<style>
 :root{{--brand:#e8772e;--brand-d:#cf6212;--accent:#0f9b8e;--ink:#222b33;--muted:#667085;--line:#ece6dd}}
 *{{box-sizing:border-box}}
 body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;max-width:1140px;
   margin:0 auto;padding:0 18px 64px;color:var(--ink);line-height:1.5;background:#faf8f4}}
 header{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;
   background:#fff;border-bottom:1px solid var(--line);padding:12px 18px;margin:0 -18px 22px;
   position:sticky;top:0;z-index:5}}
 nav{{display:flex;flex-wrap:wrap;align-items:center;gap:2px}}
 .navgrp{{display:inline-flex;align-items:center;gap:2px;padding:2px 4px;border-radius:9px}}
 .navgrp+.navgrp{{border-left:1px solid var(--line);margin-left:4px;padding-left:8px}}
 .navsec{{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:#a9b1bd;margin-right:3px}}
 nav a{{text-decoration:none;color:#475467;font-size:13.5px;padding:6px 9px;border-radius:8px}}
 nav a:hover{{background:#f3efe9}} nav a.on{{color:#fff;background:var(--brand)}}
 .badge{{display:inline-block;background:#e5484d;color:#fff;font-size:11px;font-weight:700;
   border-radius:999px;padding:1px 7px;margin-left:5px;vertical-align:middle}}
 nav a.on .badge{{background:#fff;color:var(--brand)}}
 h2{{margin:4px 0 8px;font-size:24px;letter-spacing:-.01em}} h3{{margin:26px 0 10px;font-size:17px}}
 table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #f0ece5;vertical-align:top}}
 th{{color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}}
 .cards{{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}}
 .kpi{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px 18px;min-width:160px;
   box-shadow:0 4px 14px rgba(16,24,40,.05)}}
 .kpi b{{font-size:26px;display:block;line-height:1.1;color:var(--ink)}} .kpi span{{color:var(--muted);font-size:13px}}
 .kpi.act{{border-left:4px solid var(--brand)}} a.kpi{{text-decoration:none}} a.kpi:hover{{box-shadow:0 8px 22px rgba(16,24,40,.10)}}
 a{{color:var(--brand)}} .muted{{color:var(--muted);font-size:13px}} .ok{{color:#137333}} .err{{color:#c5221f}}
 .warn{{color:#b06000}}
 button,.btn{{background:var(--brand);color:#fff;border:0;padding:8px 14px;border-radius:9px;
   font-size:13px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block;transition:.12s}}
 button:hover,.btn:hover{{filter:brightness(1.05)}}
 .btn.gray{{background:#6b7280}} input,select,textarea{{padding:9px;border:1.5px solid #e3ddd3;border-radius:9px;font-size:14px}}
 form.inline{{display:inline}}
 .bar{{background:var(--brand);height:10px;border-radius:5px;display:inline-block}}
</style></head><body>
<header><div><a href="/" style="display:inline-flex;align-items:center;gap:8px;text-decoration:none">
 <img src="/logo" alt="{html.escape(settings.platform_name)}" style="height:34px;width:auto;max-width:150px;border-radius:8px">
 <b style="font-size:18px;color:#1a1a1a">{html.escape(settings.platform_name)}</b></a><span class="muted"> admin</span></div>
 <nav>{nav} <a href='/' target='_blank' rel='noopener'>↗ View site</a> <a href='/admin/logout'>Logout</a></nav></header>
<h2>{html.escape(title)}</h2>{body}</body></html>"""
    return HTMLResponse(doc, status_code=status)
