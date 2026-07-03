"""Public / owner-facing routes: claim, manage, upgrade, Stripe webhook."""

from __future__ import annotations

import base64
import functools
import html
import pathlib
import time

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

# Drop the real brand logo here (e.g. static/logo.png) and it's served at /logo automatically.
_STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

from .. import payments, submissions, verticals
from ..config import settings
from ..pipeline import compliance, ingest, outreach
from . import i18n
from .auth import verify_captcha
from .landing import CATEGORY_CSS, category_grid
from .common import _page, captcha_field, esc as _esc, state_select

# Text fields shown on the owner edit form (label, restaurant field).
_EDIT_FIELDS = [
    ("Phone", "phone"), ("Email", "email"), ("Website", "website"),
    ("Menu URL", "menu_url"), ("Address", "address_full"), ("City", "city"),
    ("State", "state"), ("Cuisine", "cuisine_type"), ("Region", "region_tag"),
    ("Price range ($, $$, $$$)", "price_range"), ("Festival specials", "festival_specials"),
]
_DIETARY_OPTIONS = ["vegetarian", "vegan", "halal", "jain"]


# Inline SVG logo (a lotus on a warm gradient tile) — served as a real URL so it works as the
# browser favicon AND the social share image. Name-agnostic (placeholder brand).
_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#ffce93"/><stop offset="1" stop-color="#c1440e"/>'
    '</linearGradient></defs><rect width="64" height="64" rx="15" fill="url(#g)"/>'
    '<g fill="#fff" opacity=".95">'
    '<ellipse cx="32" cy="36" rx="5.5" ry="14"/>'
    '<ellipse cx="32" cy="36" rx="5.5" ry="14" transform="rotate(38 32 40)"/>'
    '<ellipse cx="32" cy="36" rx="5.5" ry="14" transform="rotate(-38 32 40)"/>'
    '<ellipse cx="32" cy="38" rx="5" ry="10.5" transform="rotate(70 32 42)"/>'
    '<ellipse cx="32" cy="38" rx="5" ry="10.5" transform="rotate(-70 32 42)"/>'
    '</g></svg>')


def icon(request: Request) -> Response:
    """Favicon — the square Namaste America mark (static/logo-square.*) if present, else lotus."""
    for ext in ("svg", "png", "webp", "jpg", "jpeg"):
        f = _STATIC_DIR / f"logo-square.{ext}"
        if f.exists():
            return FileResponse(f, headers={"Cache-Control": "public, max-age=86400"})
    return Response(_ICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


def brand_logo(request: Request) -> Response:
    """The Namaste America logo. Serves static/logo.<ext> once added; falls back to the lotus mark."""
    for ext in ("svg", "png", "webp", "jpg", "jpeg"):
        f = _STATIC_DIR / f"logo.{ext}"
        if f.exists():
            return FileResponse(f, headers={"Cache-Control": "public, max-age=86400"})
    return icon(request)


@functools.lru_cache(maxsize=1)
def _logo_data_uri() -> str | None:
    """The real square brand logo as a cached data: URI, for embedding in the SVG social card so a
    shared link shows the actual Namaste America mark (not a placeholder)."""
    for ext, mime in (("png", "image/png"), ("webp", "image/webp"),
                      ("jpg", "image/jpeg"), ("jpeg", "image/jpeg")):
        f = _STATIC_DIR / f"logo-square.{ext}"
        if f.exists():
            return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode("ascii")
    return None


def og_image(request: Request) -> Response:
    """A 1200x630 branded social-share card: the real Namaste America logo + brand + tagline,
    so a shared link looks professional and on-brand. SVG keeps it dependency-free; the inline
    lotus mark is the fallback when no logo file is present."""
    plat = html.escape(settings.platform_name)
    ptag = html.escape(settings.platform_tagline)
    aname = html.escape(settings.assistant_name)
    f = "font-family='Segoe UI,Helvetica,Arial,sans-serif'"
    logo = _logo_data_uri()
    if logo:
        mark = (
            "<defs><clipPath id='lc'><rect x='96' y='205' width='220' height='220' rx='48'/></clipPath></defs>"
            f"<image href='{logo}' x='96' y='205' width='220' height='220' "
            "preserveAspectRatio='xMidYMid slice' clip-path='url(#lc)'/>")
        tx = 360
    else:
        mark = (
            "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            "<stop offset='0' stop-color='#ffce93'/><stop offset='1' stop-color='#e8772e'/>"
            "</linearGradient></defs>"
            "<rect x='96' y='220' width='190' height='190' rx='44' fill='url(#g)'/>"
            "<g fill='#fff' opacity='.96' transform='translate(191 315) scale(2.5)'>"
            "<ellipse cx='0' cy='0' rx='5.5' ry='14'/>"
            "<ellipse cx='0' cy='0' rx='5.5' ry='14' transform='rotate(38)'/>"
            "<ellipse cx='0' cy='0' rx='5.5' ry='14' transform='rotate(-38)'/>"
            "<ellipse cx='0' cy='2' rx='5' ry='10.5' transform='rotate(70)'/>"
            "<ellipse cx='0' cy='2' rx='5' ry='10.5' transform='rotate(-70)'/></g>")
        tx = 330
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='630' viewBox='0 0 1200 630'>"
        "<rect width='1200' height='630' fill='#faf8f4'/>"
        "<rect width='1200' height='16' fill='#e8772e'/><rect y='614' width='1200' height='16' fill='#0f9b8e'/>"
        + mark +
        f"<text x='{tx}' y='292' {f} font-size='90' font-weight='700' fill='#222b33'>{plat}</text>"
        f"<text x='{tx + 4}' y='350' {f} font-size='40' fill='#0f9b8e'>{ptag}</text>"
        f"<text x='{tx + 4}' y='406' {f} font-size='29' fill='#667085'>Ask {aname}, your desi friend — by voice or text</text>"
        f"<text x='96' y='566' {f} font-size='25' fill='#9aa0a6'>Indian restaurants · temples · groceries · events · classes · USA</text>"
        "</svg>")
    return Response(svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


_LANDING_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PLAT__ — Find Indian America</title>
<meta name="description" content="__OGDESC__">
<meta property="og:title" content="__PLAT__ — Find Indian America">
<meta property="og:description" content="__OGDESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="__OGURL__">
<meta property="og:image" content="__OGIMG__">
<meta name="twitter:card" content="summary">
<link rel="canonical" href="__OGURL__">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#c1440e">
<script>if('serviceWorker' in navigator){window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js').catch(function(){})})}</script>
<style>
:root{--brand:#c1440e;--brand-d:#a2380b;--bg:#f6f4f1;--panel:#fff;--ink:#1f2430;--muted:#6b7280;--line:#ececec}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);
 background:var(--bg);line-height:1.55}
a{color:var(--brand);text-decoration:none}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 22px;max-width:1080px;margin:0 auto}
.brand{display:flex;align-items:center;gap:11px;color:var(--ink)}
.brand .logo{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
 background:linear-gradient(135deg,#ffd9a0,#ffb56b);font-size:20px}
.brand b{font-size:17px;display:block;line-height:1.1}.brand i{font-style:normal;font-size:12px;color:var(--muted)}
.nav{display:flex;align-items:center;gap:16px;font-size:14px}
.nav .btn{background:var(--brand);color:#fff;padding:9px 16px;border-radius:10px;font-weight:600}
.nav .btn:hover{background:var(--brand-d)}
.hero{max-width:760px;margin:0 auto;text-align:center;padding:46px 20px 8px}
.hero h1{font-size:40px;line-height:1.1;margin:0 0 14px;letter-spacing:-.02em}
.hero .sub{color:var(--muted);font-size:19px;margin:0 auto 28px;max-width:620px}
.search{display:flex;align-items:center;gap:10px;max-width:600px;margin:0 auto;background:#fff;
 border:1px solid #ddd;border-radius:16px;padding:8px 8px 8px 16px;box-shadow:0 6px 22px rgba(0,0,0,.06);text-align:left}
.search:hover{border-color:var(--brand)}.search .si{font-size:18px}
.search .sp{flex:1;color:#9aa0a6;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.search .sb{background:var(--brand);color:#fff;padding:10px 16px;border-radius:11px;font-weight:600;font-size:14px;white-space:nowrap}
.poweredby{color:#9aa0a6;font-size:12px;margin-top:14px}
.section{max-width:1000px;margin:0 auto;padding:34px 20px}
.section h2{text-align:center;font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);margin:0 0 18px}
__CATCSS__
.vals{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}
.val{text-align:center;padding:10px}.val .vi{font-size:26px}
.val h3{margin:8px 0 4px;font-size:16px}.val p{color:var(--muted);font-size:14px;margin:0}
footer{text-align:center;color:#9aa0a6;font-size:14px;padding:22px 20px 48px;border-top:1px solid var(--line);margin-top:14px}
@media(max-width:600px){.hero h1{font-size:30px}.hero .sub{font-size:16px}.search .sp{display:none}.nav .signin{display:none}}
</style></head><body>
<header class="topbar">
 <a class="brand" href="/"><span class="logo">🪷</span><span><b>__PLAT__</b><i>__TAGLINE__</i></span></a>
 <nav class="nav"><a class="signin" href="/submit">Add your business</a><a class="btn" href="/chat">Ask __ANAME__</a></nav>
</header>
<main>
 <section class="hero">
  <h1>Find Indian America with __ANAME__</h1>
  <p class="sub">__SUB__</p>
  <a class="search" href="/chat"><span class="si">🔍</span>
   <span class="sp">Ask anything… “vegetarian thali in Jersey City”</span>
   <span class="sb">Ask __ANAME__ →</span></a>
  <div class="poweredby">Free AI guide · or <a href="/browse">browse by city</a> · restaurants · temples · groceries · sweets · events &amp; more</div>
 </section>
 <section class="section">
  <h2>Explore by category</h2>
  __TILES__
 </section>
 <section class="section">
  <div class="vals">
   <div class="val"><div class="vi">💬</div><h3>Ask in plain English</h3>
    <p>“Sweets shop for Diwali near Edison” — no menus or filters to wrestle with.</p></div>
   <div class="val"><div class="vi">📍</div><h3>Real local listings</h3>
    <p>Restaurants, temples, groceries, classes, events and more, across the USA.</p></div>
   <div class="val"><div class="vi">✨</div><h3>Always free</h3>
    <p>Open to everyone. Own a business? Claim your listing in a tap.</p></div>
  </div>
 </section>
</main>
<footer>Own a business? <a href="/submit">Add your listing</a> or <a href="/portal/login">sign in</a> to manage it.
<br><a href="/about">About</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/contact">Contact</a> · <a href="/faq">FAQ</a> · __PLAT__</footer>
</body></html>"""


def home(request: Request) -> HTMLResponse:
    """Public, shareable landing page: hero + AI search CTA + category grid."""
    plat = html.escape(settings.platform_name)
    aname = html.escape(settings.assistant_name)
    desc = (f"Find Indian restaurants, sweets, temples, events, classes, salons, jewelry and more "
            f"across the USA — with {settings.assistant_name}, your free AI guide.")
    repl = {
        "__PLAT__": plat, "__ANAME__": aname,
        "__TAGLINE__": html.escape(settings.platform_tagline),
        "__SUB__": html.escape(desc), "__TILES__": category_grid(), "__CATCSS__": CATEGORY_CSS,
        # Self-reference /explore (its OWN url) -- not "/" (the chatbot homepage). They're different
        # pages with different content; pointing this page's canonical/og:url at a different page's
        # URL is what caused Search Console's "Duplicate without user-selected canonical" (no
        # canonical tag was present at all before) confusion between them.
        "__OGURL__": html.escape(settings.public_web_url.rstrip("/") + "/explore"),
        "__OGIMG__": html.escape(settings.public_web_url.rstrip("/") + "/icon.svg"),
        "__OGDESC__": html.escape(desc),
    }
    doc = _LANDING_HTML
    for k, v in repl.items():
        doc = doc.replace(k, v)
    return HTMLResponse(doc)


# ----------------------------------------------------------- owner self-submission
_SUB_HITS: dict[str, list[float]] = {}


def _sub_rate_ok(ip: str, limit: int = 5, window: int = 3600) -> bool:
    now = time.time()
    w = [t for t in _SUB_HITS.get(ip, []) if now - t < window]
    if len(w) >= limit:
        _SUB_HITS[ip] = w
        return False
    w.append(now)
    _SUB_HITS[ip] = w
    return True


def submit_get(request: Request) -> HTMLResponse:
    tr = i18n.t(request)
    pre = request.query_params.get("category")
    opts = "".join(
        f"<option value='{v}'{' selected' if v == pre else ''}>"
        f"{html.escape(verticals.VERTICALS[v]['label'])}</option>"
        for v in submissions.SUBMITTABLE)
    body = (
        f"<h2>{_esc(tr['add_business'])}</h2>"
        f"<p class='muted'>{_esc(tr['add_intro'])}</p>"
        "<form method='post' action='/submit'>"
        f"<label>{_esc(tr['category'])}</label><select name='vertical'>{opts}</select>"
        f"<label>{_esc(tr['business_name'])} *</label><input name='name' required>"
        f"<label>{_esc(tr['address'])}</label><input name='address_full'>"
        f"<label>{_esc(tr['city'])}</label><input name='city'>"
        f"<label>{_esc(tr['state'])}</label>{state_select('state')}"
        f"<label>{_esc(tr['phone'])}</label><input name='phone' type='tel'>"
        f"<label>{_esc(tr['your_email'])} *</label><input name='email' type='email' required>"
        f"<label>{_esc(tr['website'])}</label><input name='website' placeholder='https://'>"
        f"<label>{_esc(tr['languages_spoken'])} <span style='font-weight:400;color:#6b7280'>"
        f"({_esc(tr['comma_separated'])})</span></label>"
        "<input name='languages' placeholder='Telugu, Hindi, English'>"
        f"<label>{_esc(tr['anything_else'])}</label>"
        "<input name='note'>"
        # honeypot — bots fill this hidden field; humans don't.
        "<input type='text' name='company' style='position:absolute;left:-9999px' tabindex='-1' autocomplete='off'>"
        + captcha_field() +
        f"<button type='submit'>{_esc(tr['submit_for_review'])}</button></form>")
    return _page(tr["add_business"], body)


async def submit_post(request: Request) -> HTMLResponse:
    form = await request.form()
    if (form.get("company") or "").strip():  # honeypot tripped -> accept silently, drop
        return _page("Thanks", "<h2 class='ok'>Thanks!</h2><p>Your submission was received.</p>")
    ip = (request.client.host if request.client else "?") or "?"
    if not _sub_rate_ok(ip):
        return _page("Slow down", "<h2>Too many submissions</h2>"
                     "<p class='muted'>Please try again later.</p>", status=429)
    if not verify_captcha(form):
        return _page("Could not submit", "<h2 class='err'>The captcha answer was incorrect.</h2>"
                     "<p><a href='/submit'>‹ try again</a></p>", status=400)
    vertical = (form.get("vertical") or "").strip()
    payload = {k: (form.get(k) or "").strip()
               for k in ("name", "address_full", "city", "state", "phone", "email", "website",
                         "languages")}
    res = submissions.submit(vertical, payload, contact_email=payload.get("email"),
                             note=(form.get("note") or "").strip() or None)
    if not res.get("ok"):
        msg = {"name_required": "Please enter your business name.",
               "bad_vertical": "Please pick a category."}.get(res.get("error"), "Could not submit.")
        return _page("Could not submit", f"<h2 class='err'>{msg}</h2>"
                     "<p><a href='/submit'>‹ try again</a></p>", status=400)
    return _page("Submitted", "<h2 class='ok'>&#10003; Thanks — submitted for review!</h2>"
                 "<p>We'll review your listing and publish it soon. "
                 "<a href='/submit'>Add another business</a> · <a href='/chat'>explore the directory</a>.</p>")


def claim_get(request: Request) -> HTMLResponse:
    token = request.query_params.get("token", "")
    claim = outreach.claim_status(token) if token else None
    if claim is None:
        return _page("Invalid claim link",
                     "<h2>Invalid or expired link</h2><p class='muted'>This claim link isn't "
                     "recognized. Please use the link from the message we sent you.</p>", status=404)
    if claim["status"] == "claimed":
        return _page("Already claimed",
                     f"<h2>Already claimed</h2><p>{html.escape(claim['restaurant_name'])} "
                     "has already been claimed. If this wasn't you, contact us.</p>")

    name = html.escape(claim["restaurant_name"])
    loc = ", ".join(x for x in (claim.get("city"), claim.get("state")) if x)
    body = (
        f"<h2>Claim {name}</h2><p class='muted'>{html.escape(loc)}</p>"
        "<p>Verify your email or phone to take ownership of this free listing and keep "
        "its hours, menu and details accurate.</p>"
        "<form method='post' action='/claim'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        "<label>Email</label><input name='email' type='email' placeholder='owner@example.com'>"
        "<label>Phone (optional)</label><input name='phone' type='tel' placeholder='+1 555 123 4567'>"
        "<button type='submit'>Claim my listing</button></form>"
    )
    return _page(f"Claim {name}", body)


async def claim_post(request: Request) -> HTMLResponse:
    form = await request.form()
    token = (form.get("token") or "").strip()
    email = (form.get("email") or "").strip() or None
    phone = (form.get("phone") or "").strip() or None
    if not (email or phone):
        return _page("Contact needed",
                     "<h2 class='err'>Please provide an email or phone</h2>"
                     "<p><a href='javascript:history.back()'>Go back</a></p>", status=400)

    result = outreach.verify_claim(token, owner_email=email, owner_phone=phone)
    if result.get("ok"):
        upgrade = ""
        if settings.featured_for_sale:
            rid = result["restaurant_id"]
            price = f"${settings.stripe_price_cents / 100:.0f}"
            upgrade = (
                "<hr style='margin:20px 0;border:0;border-top:1px solid #eee'>"
                "<p><b>Want more customers?</b> Featured listings appear first when AI "
                "assistants recommend Indian restaurants in your area.</p>"
                f"<a href='/upgrade?id={rid}'><button>Get Featured — {price}"
                f"/{settings.featured_days} days</button></a>")
        manage = (f"<p><a href='/manage?token={html.escape(token)}'>"
                  f"<button>Edit your listing</button></a></p>")
        return _page("Listing claimed",
                     "<h2 class='ok'>&#10003; Listing claimed</h2>"
                     "<p>Thank you — you now own this listing. A <b>✓ Owner-verified</b> badge "
                     "now shows on it in search, the assistant and your city page. Keep your "
                     "details accurate below.</p>"
                     + manage + upgrade)

    reasons = {
        "invalid_token": "This claim link isn't valid.",
        "expired": "This claim link has expired. Contact us for a new one.",
        "claim_claimed": "This listing has already been claimed.",
        "claim_revoked": "This claim link was revoked.",
    }
    msg = reasons.get(result.get("error", ""), "Something went wrong. Please try again.")
    return _page("Could not claim", f"<h2 class='err'>Couldn't claim</h2><p>{msg}</p>", status=400)


def render_edit_form(r: dict, action: str, hidden: str) -> str:
    """Reusable restaurant edit form (used by /manage and the portal)."""
    rows = "".join(
        f"<label>{html.escape(label)}</label>"
        f"<input name='{field}' value='{_esc(r.get(field))}'>"
        for label, field in _EDIT_FIELDS)
    current = set(r.get("dietary_tags") or [])
    checks = "".join(
        f"<label style='font-weight:400'><input type='checkbox' style='width:auto' "
        f"name='dietary' value='{d}'{' checked' if d in current else ''}> {d}</label> "
        for d in _DIETARY_OPTIONS)
    hours_raw = (r.get("hours_json") or {}).get("raw", "") if isinstance(r.get("hours_json"), dict) else ""
    return (
        f"<form method='post' action='{action}'>{hidden}{rows}"
        f"<label>Opening hours</label>"
        f"<input name='hours' value='{_esc(hours_raw)}' placeholder='Mo-Su 11:00-22:00'>"
        f"<label>Dietary</label><div style='margin:6px 0 16px'>{checks}</div>"
        f"<label>Languages spoken (comma-separated)</label>"
        f"<input name='languages_csv' value='{_esc(', '.join(r.get('languages') or []))}' "
        f"placeholder='Telugu, Hindi, English'>"
        f"<button type='submit'>Save changes</button></form>")


def parse_edit_form(form) -> dict:
    edits: dict = {}
    for _, field in _EDIT_FIELDS:
        if field in form:
            edits[field] = (form.get(field) or "").strip() or None
    if "hours" in form:
        hours = (form.get("hours") or "").strip()
        edits["hours_json"] = {"raw": hours} if hours else None
    edits["dietary_tags"] = sorted(set(form.getlist("dietary")))
    if "languages_csv" in form:
        from .. import tags as tagsmod
        edits["languages"] = tagsmod.parse_languages(form.get("languages_csv"))
    return edits


def manage_get(request: Request) -> HTMLResponse:
    token = request.query_params.get("token", "")
    r = outreach.owner_listing(token) if token else None
    if r is None:
        return _page("Not found",
                     "<h2>Listing not found</h2><p class='muted'>This management link is "
                     "invalid, or the listing hasn't been claimed yet.</p>", status=404)
    body = (f"<h2>Manage {html.escape(r['name'])}</h2>"
            "<p class='muted'>Update your details below — changes go live immediately.</p>"
            + render_edit_form(r, "/manage", f"<input type='hidden' name='token' value='{html.escape(token)}'>"))
    return _page(f"Manage {r['name']}", body)


async def manage_post(request: Request) -> HTMLResponse:
    form = await request.form()
    token = (form.get("token") or "").strip()
    r = outreach.owner_listing(token) if token else None
    if r is None:
        return _page("Not found", "<h2>Listing not found</h2>", status=404)
    result = ingest.apply_owner_edits(r["id"], parse_edit_form(form))
    n = result.get("updated", 0)
    msg = f"Saved {n} change(s)." if n else "No changes to save."
    return _page("Saved", f"<h2 class='ok'>&#10003; {msg}</h2>"
                 f"<p><a href='/manage?token={html.escape(token)}'>Back to your listing</a></p>")


def upgrade_get(request: Request) -> HTMLResponse:
    if not settings.featured_for_sale:
        return _page("Unavailable", "<h2>Featured upgrades aren't available yet</h2>"
                     "<p class='muted'>We're focused on growing our audience first — check "
                     "back soon.</p>", status=503)
    try:
        rid = int(request.query_params.get("id", ""))
    except ValueError:
        return _page("Bad request", "<h2>Missing restaurant id</h2>", status=400)
    result = payments.create_checkout_session(rid)
    if not result.get("ok"):
        return _page("Error", "<h2 class='err'>Could not start checkout</h2>", status=502)
    return RedirectResponse(result["url"], status_code=303)


def upgrade_success(request: Request) -> HTMLResponse:
    session_id = request.query_params.get("session_id", "")
    note = ""
    if session_id and payments.enabled():
        try:
            res = payments.fulfill_session(session_id)
            if not res.get("ok"):
                note = f"<p class='muted'>(fulfillment: {html.escape(str(res))})</p>"
        except Exception as exc:
            note = f"<p class='err'>Fulfillment error: {html.escape(type(exc).__name__)}: {html.escape(str(exc))}</p>"
    return _page("Featured!", "<h2 class='ok'>&#10003; Payment received</h2>"
                 "<p>Thank you! Your listing now ranks first in AI recommendations.</p>" + note)


def upgrade_cancel(request: Request) -> HTMLResponse:
    return _page("Checkout cancelled",
                 "<h2>Checkout cancelled</h2><p class='muted'>No charge was made.</p>")


def _optout_apply(request: Request) -> HTMLResponse:
    """Verify the signed unsubscribe link and suppress the contact (idempotent)."""
    contact = (request.query_params.get("c") or "").strip()
    token = (request.query_params.get("t") or "").strip()
    if not contact or not compliance.verify_opt_out(contact, token):
        return _page("Unsubscribe",
                     "<h2 class='err'>Invalid unsubscribe link</h2>"
                     "<p class='muted'>This link isn't recognized. If you keep getting emails, "
                     "tell us via the <a href='/contact'>contact form</a> and we'll remove you.</p>",
                     status=400)
    compliance.suppress(contact, reason="optout", channel="email")
    return _page("Unsubscribed",
                 "<h2 class='ok'>&#10003; You're unsubscribed</h2>"
                 f"<p>{html.escape(contact)} has been removed. You won't receive further "
                 "outreach about claiming a listing.</p>")


def optout_get(request: Request) -> HTMLResponse:
    return _optout_apply(request)


async def optout_post(request: Request) -> HTMLResponse:
    # RFC 8058 one-click unsubscribe (Gmail/Outlook button) POSTs to the same URL.
    return _optout_apply(request)


async def stripe_webhook(request: Request) -> HTMLResponse:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = payments.handle_webhook(payload, sig)
    status = 200 if result.get("ok") else 400
    return HTMLResponse('{"received": true}', status_code=status, media_type="application/json")


routes = [
    # Home (/) is the Dost chatbot (see web/chat.py); the marketing/landing page lives at /explore.
    Route("/explore", home, methods=["GET"]),
    Route("/icon.svg", icon, methods=["GET"]),
    Route("/favicon.ico", icon, methods=["GET"]),
    Route("/og-image.svg", og_image, methods=["GET"]),
    Route("/logo", brand_logo, methods=["GET"]),
    Route("/submit", submit_get, methods=["GET"]),
    Route("/submit", submit_post, methods=["POST"]),
    Route("/claim", claim_get, methods=["GET"]),
    Route("/claim", claim_post, methods=["POST"]),
    Route("/manage", manage_get, methods=["GET"]),
    Route("/manage", manage_post, methods=["POST"]),
    Route("/upgrade", upgrade_get, methods=["GET"]),
    Route("/upgrade/success", upgrade_success, methods=["GET"]),
    Route("/upgrade/cancel", upgrade_cancel, methods=["GET"]),
    Route("/optout", optout_get, methods=["GET"]),
    Route("/optout", optout_post, methods=["POST"]),
    Route("/stripe/webhook", stripe_webhook, methods=["POST"]),
]
