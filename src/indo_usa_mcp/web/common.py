"""Shared HTML shell + helpers for the web app (public, admin, portal)."""

from __future__ import annotations

import html

from starlette.responses import HTMLResponse

from ..config import settings

_BRAND = "#c1440e"


def esc(value) -> str:
    return html.escape(str(value)) if value not in (None, "") else ""


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
</style></head><body>
<a href="/" style="display:flex;align-items:center;gap:10px;text-decoration:none;margin-bottom:18px">
 <img src="/logo" alt="{html.escape(settings.platform_name)}" style="height:42px;width:auto;max-width:180px;border-radius:10px">
 <b style="color:#1a1a1a;font-size:18px">{html.escape(settings.platform_name)}</b></a>
<div class="card">{body}</div>
<p class="muted" style="text-align:center;margin-top:20px"><a href="/">&#8592; Back to {html.escape(settings.platform_name)}</a></p>
</body></html>"""
    return HTMLResponse(doc, status_code=status)


# Grouped admin nav: (section label, [(item label, href), ...]).
_ADMIN_NAV = [
    ("", [("Overview", "/admin"), ("Operations", "/admin/ops"), ("Dashboard", "/admin/dashboard")]),
    ("Listings", [("Data", "/admin/data/restaurants"), ("Geography", "/admin/geo/restaurants"),
                  ("Quality", "/admin/quality/restaurants"), ("Moderation", "/admin/moderation")]),
    ("Inbox", [("Messages", "/admin/messages"), ("Submissions", "/admin/submissions"),
               ("Approvals", "/admin/approvals"), ("Feedback", "/admin/feedback"),
               ("Claims", "/admin/claims")]),
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
 <nav>{nav} <a href='/admin/logout'>Logout</a></nav></header>
<h2>{html.escape(title)}</h2>{body}</body></html>"""
    return HTMLResponse(doc, status_code=status)
