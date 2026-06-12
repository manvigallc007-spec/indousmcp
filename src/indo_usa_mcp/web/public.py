"""Public / owner-facing routes: claim, manage, upgrade, Stripe webhook."""

from __future__ import annotations

import html

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import payments, verticals
from ..config import settings
from ..pipeline import compliance, ingest, outreach
from .common import _page, esc as _esc

# Text fields shown on the owner edit form (label, restaurant field).
_EDIT_FIELDS = [
    ("Phone", "phone"), ("Email", "email"), ("Website", "website"),
    ("Menu URL", "menu_url"), ("Address", "address_full"), ("City", "city"),
    ("State", "state"), ("Cuisine", "cuisine_type"), ("Region", "region_tag"),
    ("Price range ($, $$, $$$)", "price_range"), ("Festival specials", "festival_specials"),
]
_DIETARY_OPTIONS = ["vegetarian", "vegan", "halal", "jain"]


_CAT_ICONS = {
    "restaurants": "🍛", "temples": "🛕", "groceries": "🛒", "professionals": "🩺",
    "salons": "💇", "events": "🎉", "apparel": "👗", "sweets": "🍬", "studios": "🧘",
    "services": "💸",
}


def home(request: Request) -> HTMLResponse:
    """Public, shareable landing page: hero + category grid + CTA to the assistant."""
    plat = html.escape(settings.platform_name)
    brand = "#c1440e"
    desc = ("Find Indian restaurants, sweets, temples, events, classes, salons, jewelry and "
            "more across the USA — with a friendly AI guide.")
    og_url = html.escape(settings.public_web_url.rstrip("/") + "/")
    tiles = "".join(
        f"<a class='tile' href='/chat'><span>{_CAT_ICONS.get(k, '•')}</span>"
        f"{html.escape(cfg['label'])}</a>"
        for k, cfg in verticals.VERTICALS.items())
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{plat} — Indian-American directory</title>
<meta name="description" content="{html.escape(desc)}">
<meta property="og:title" content="{plat}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{og_url}">
<meta name="twitter:card" content="summary">
<style>
 *{{box-sizing:border-box}}
 body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;margin:0;color:#1a1a1a;
   background:#faf7f5;line-height:1.5}}
 .hero{{text-align:center;padding:64px 20px 36px;max-width:680px;margin:0 auto}}
 .hero h1{{font-size:34px;margin:0 0 10px}} .hero p{{color:#555;font-size:18px;margin:0 0 24px}}
 .cta{{background:{brand};color:#fff;border:0;padding:15px 28px;border-radius:12px;font-size:17px;
   text-decoration:none;display:inline-block;cursor:pointer}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;
   max-width:760px;margin:8px auto 50px;padding:0 18px}}
 .tile{{background:#fff;border:1px solid #eee;border-radius:14px;padding:18px;text-decoration:none;
   color:#1a1a1a;font-weight:600;font-size:15px;display:flex;align-items:center;gap:10px}}
 .tile span{{font-size:24px}} .tile:hover{{border-color:{brand}}}
 footer{{text-align:center;color:#888;font-size:14px;padding:0 20px 40px}}
 footer a{{color:{brand}}}
</style></head><body>
<div class="hero">
 <h1>{plat}</h1>
 <p>{html.escape(desc)}</p>
 <a class="cta" href="/chat">Ask the assistant →</a>
</div>
<div class="grid">{tiles}</div>
<footer>Own a business? <a href="/portal/login">Sign in</a> to claim &amp; manage your listing.</footer>
</body></html>"""
    return HTMLResponse(doc)


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
        if payments.enabled():
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
                     "<p>Thank you — you now own this listing. Keep your details accurate below.</p>"
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
    if not payments.enabled():
        return _page("Unavailable", "<h2>Featured upgrades aren't enabled yet</h2>"
                     "<p class='muted'>Please check back soon.</p>", status=503)
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
                     f"reply to {html.escape(settings.outreach_contact_email)} and we'll remove you.</p>",
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
    Route("/", home, methods=["GET"]),
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
