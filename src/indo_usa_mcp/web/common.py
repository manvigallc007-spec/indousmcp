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


_ADMIN_NAV = [
    ("Overview", "/admin"), ("Dashboard", "/admin/dashboard"), ("Data", "/admin/data/restaurants"),
    ("Geography", "/admin/geo/restaurants"), ("Quality", "/admin/quality/restaurants"),
    ("Moderation", "/admin/moderation"), ("Messages", "/admin/messages"),
    ("Approvals", "/admin/approvals"), ("Feedback", "/admin/feedback"),
    ("Submissions", "/admin/submissions"),
    ("Events", "/admin/events"), ("Claims", "/admin/claims"), ("Agents", "/admin/agents"),
    ("Traffic", "/admin/traffic"), ("Misses", "/admin/misses"),
    ("Recommendations", "/admin/recommendations"),
    ("Payments", "/admin/payments"), ("Reports", "/admin/reports"),
]


def admin_page(title: str, body: str, active: str = "", status: int = 200) -> HTMLResponse:
    """Wide layout with a nav bar for the admin dashboard."""
    nav = " ".join(
        f"<a href='{href}' class='{'on' if label == active else ''}'>{label}</a>"
        for label, href in _ADMIN_NAV
    )
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Admin</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;max-width:1100px;
   margin:0 auto;padding:0 16px 60px;color:#1a1a1a;line-height:1.45}}
 header{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;
   border-bottom:1px solid #eee;padding:14px 0;margin-bottom:20px}}
 nav a{{margin-right:14px;text-decoration:none;color:#444;font-size:14px}}
 nav a.on{{color:{_BRAND};font-weight:600}}
 h2{{margin:0 0 6px}} h3{{margin:24px 0 8px}}
 table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}}
 th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #eee;vertical-align:top}}
 th{{color:#666;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}}
 .cards{{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}}
 .kpi{{border:1px solid #e6e6e6;border-radius:12px;padding:14px 18px;min-width:150px}}
 .kpi b{{font-size:24px;display:block}} .kpi span{{color:#666;font-size:13px}}
 a{{color:{_BRAND}}} .muted{{color:#666;font-size:13px}} .ok{{color:#137333}} .err{{color:#c5221f}}
 .warn{{color:#b06000}}
 button,.btn{{background:{_BRAND};color:#fff;border:0;padding:7px 12px;border-radius:7px;
   font-size:13px;cursor:pointer;text-decoration:none;display:inline-block}}
 .btn.gray{{background:#666}} input,select{{padding:8px;border:1px solid #ccc;border-radius:7px;font-size:14px}}
 form.inline{{display:inline}}
 .bar{{background:{_BRAND};height:10px;border-radius:5px;display:inline-block}}
</style></head><body>
<header><div><a href="/" style="display:inline-flex;align-items:center;gap:8px;text-decoration:none">
 <img src="/logo" alt="{html.escape(settings.platform_name)}" style="height:34px;width:auto;max-width:150px;border-radius:8px">
 <b style="font-size:18px;color:#1a1a1a">{html.escape(settings.platform_name)}</b></a><span class="muted"> admin</span></div>
 <nav>{nav} <a href='/admin/logout'>Logout</a></nav></header>
<h2>{html.escape(title)}</h2>{body}</body></html>"""
    return HTMLResponse(doc, status_code=status)
