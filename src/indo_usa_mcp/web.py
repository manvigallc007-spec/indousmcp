"""Owner-facing claim web page (blueprint §7).

A tiny server-rendered Starlette app, separate from the agent MCP endpoint. Restaurant
owners arrive via the claim link in an outreach message
(`.../claim?type=restaurant&id=<id>&token=<token>`), confirm an email/phone, and take
ownership of their listing (flips restaurants.is_claimed).

Run:  python -m indo_usa_mcp.web   (defaults to 0.0.0.0:8080)
"""

from __future__ import annotations

import html

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from . import payments
from .config import settings
from .pipeline import ingest, outreach

# Text fields shown on the owner edit form (label, restaurant field).
_EDIT_FIELDS = [
    ("Phone", "phone"), ("Email", "email"), ("Website", "website"),
    ("Menu URL", "menu_url"), ("Address", "address_full"), ("City", "city"),
    ("State", "state"), ("Cuisine", "cuisine_type"), ("Region", "region_tag"),
    ("Price range ($, $$, $$$)", "price_range"), ("Festival specials", "festival_specials"),
]
_DIETARY_OPTIONS = ["vegetarian", "vegan", "halal", "jain"]

_BRAND = "#c1440e"


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;max-width:560px;
   margin:48px auto;padding:0 16px;color:#1a1a1a;line-height:1.5}}
 .card{{border:1px solid #e6e6e6;border-radius:14px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
 h2{{margin:0 0 8px}} label{{font-size:14px;font-weight:600}}
 input{{width:100%;padding:11px;margin:6px 0 16px;border:1px solid #ccc;border-radius:9px;
   font-size:15px;box-sizing:border-box}}
 button{{background:{_BRAND};color:#fff;border:0;padding:12px 20px;border-radius:9px;
   font-size:15px;cursor:pointer}}
 .muted{{color:#666;font-size:14px}} .ok{{color:#137333}} .err{{color:#c5221f}}
</style></head><body><div class="card">{body}</div>
<p class="muted" style="text-align:center;margin-top:20px">
 {html.escape(settings.platform_name)} — claim your free listing</p>
</body></html>"""
    return HTMLResponse(doc, status_code=status)


def home(request: Request) -> HTMLResponse:
    return _page(
        settings.platform_name,
        f"<h2>{html.escape(settings.platform_name)}</h2>"
        "<p class='muted'>An agent-first directory of Indian restaurants in the USA. "
        "This site is where restaurant owners claim their listing.</p>",
    )


def claim_get(request: Request) -> HTMLResponse:
    token = request.query_params.get("token", "")
    claim = outreach.claim_status(token) if token else None

    if claim is None:
        return _page(
            "Invalid claim link",
            "<h2>Invalid or expired link</h2><p class='muted'>This claim link isn't "
            "recognized. Please use the link from the message we sent you.</p>",
            status=404,
        )
    if claim["status"] == "claimed":
        return _page(
            "Already claimed",
            f"<h2>Already claimed</h2><p>{html.escape(claim['restaurant_name'])} "
            "has already been claimed. If this wasn't you, contact us.</p>",
        )

    name = html.escape(claim["restaurant_name"])
    loc = ", ".join(x for x in (claim.get("city"), claim.get("state")) if x)
    body = (
        f"<h2>Claim {name}</h2>"
        f"<p class='muted'>{html.escape(loc)}</p>"
        "<p>Verify your email or phone to take ownership of this free listing and keep "
        "its hours, menu and details accurate.</p>"
        "<form method='post' action='/claim'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        "<label>Email</label>"
        "<input name='email' type='email' placeholder='owner@example.com'>"
        "<label>Phone (optional)</label>"
        "<input name='phone' type='tel' placeholder='+1 555 123 4567'>"
        "<button type='submit'>Claim my listing</button></form>"
    )
    return _page(f"Claim {name}", body)


async def claim_post(request: Request) -> HTMLResponse:
    form = await request.form()
    token = (form.get("token") or "").strip()
    email = (form.get("email") or "").strip() or None
    phone = (form.get("phone") or "").strip() or None

    if not (email or phone):
        return _page(
            "Contact needed",
            "<h2 class='err'>Please provide an email or phone</h2>"
            "<p><a href='javascript:history.back()'>Go back</a></p>",
            status=400,
        )

    result = outreach.verify_claim(token, owner_email=email, owner_phone=phone)
    if result.get("ok"):
        upgrade = ""
        if payments.enabled():
            rid = result["restaurant_id"]
            price = f"${settings.stripe_price_cents / 100:.0f}"
            upgrade = (
                f"<hr style='margin:20px 0;border:0;border-top:1px solid #eee'>"
                f"<p><b>Want more customers?</b> Featured listings appear first when AI "
                f"assistants recommend Indian restaurants in your area.</p>"
                f"<a href='/upgrade?id={rid}'><button>Get Featured — {price}"
                f"/{settings.featured_days} days</button></a>"
            )
        manage = (f"<p><a href='/manage?token={html.escape(token)}'>"
                  f"<button>Edit your listing</button></a></p>")
        return _page(
            "Listing claimed",
            "<h2 class='ok'>&#10003; Listing claimed</h2>"
            "<p>Thank you — you now own this listing. Keep your details accurate below.</p>"
            + manage + upgrade,
        )

    reasons = {
        "invalid_token": "This claim link isn't valid.",
        "expired": "This claim link has expired. Contact us for a new one.",
        "claim_claimed": "This listing has already been claimed.",
        "claim_revoked": "This claim link was revoked.",
    }
    msg = reasons.get(result.get("error", ""), "Something went wrong. Please try again.")
    return _page("Could not claim", f"<h2 class='err'>Couldn't claim</h2><p>{msg}</p>", status=400)


def _esc(value) -> str:
    return html.escape(str(value)) if value not in (None, "") else ""


def manage_get(request: Request) -> HTMLResponse:
    token = request.query_params.get("token", "")
    r = outreach.owner_listing(token) if token else None
    if r is None:
        return _page("Not found",
                     "<h2>Listing not found</h2><p class='muted'>This management link is "
                     "invalid, or the listing hasn't been claimed yet.</p>", status=404)

    rows = "".join(
        f"<label>{html.escape(label)}</label>"
        f"<input name='{field}' value='{_esc(r.get(field))}'>"
        for label, field in _EDIT_FIELDS
    )
    current = set(r.get("dietary_tags") or [])
    checks = "".join(
        f"<label style='font-weight:400'><input type='checkbox' style='width:auto' "
        f"name='dietary' value='{d}'{' checked' if d in current else ''}> {d}</label> "
        for d in _DIETARY_OPTIONS
    )
    hours_raw = (r.get("hours_json") or {}).get("raw", "") if isinstance(r.get("hours_json"), dict) else ""
    body = (
        f"<h2>Manage {html.escape(r['name'])}</h2>"
        f"<p class='muted'>Update your details below — changes go live immediately.</p>"
        f"<form method='post' action='/manage'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        f"{rows}"
        f"<label>Opening hours</label>"
        f"<input name='hours' value='{_esc(hours_raw)}' placeholder='Mo-Su 11:00-22:00'>"
        f"<label>Dietary</label><div style='margin:6px 0 16px'>{checks}</div>"
        f"<button type='submit'>Save changes</button></form>"
    )
    return _page(f"Manage {r['name']}", body)


async def manage_post(request: Request) -> HTMLResponse:
    form = await request.form()
    token = (form.get("token") or "").strip()
    r = outreach.owner_listing(token) if token else None
    if r is None:
        return _page("Not found", "<h2>Listing not found</h2>", status=404)

    edits: dict = {}
    for _, field in _EDIT_FIELDS:
        if field in form:
            edits[field] = (form.get(field) or "").strip() or None
    if "hours" in form:
        hours = (form.get("hours") or "").strip()
        edits["hours_json"] = {"raw": hours} if hours else None
    edits["dietary_tags"] = sorted(set(form.getlist("dietary")))

    result = ingest.apply_owner_edits(r["id"], edits)
    n = result.get("updated", 0)
    msg = (f"Saved {n} change(s)." if n else "No changes to save.")
    body = (f"<h2 class='ok'>&#10003; {msg}</h2>"
            f"<p><a href='/manage?token={html.escape(token)}'>Back to your listing</a></p>")
    return _page("Saved", body)


def upgrade_get(request: Request) -> HTMLResponse:
    """Start a Stripe Checkout for a featured-listing purchase."""
    if not payments.enabled():
        return _page("Unavailable",
                     "<h2>Featured upgrades aren't enabled yet</h2>"
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
    return _page(
        "Featured!",
        "<h2 class='ok'>&#10003; You're featured</h2>"
        "<p>Payment received — your listing now ranks first in AI recommendations. "
        "Thank you for supporting the directory!</p>",
    )


def upgrade_cancel(request: Request) -> HTMLResponse:
    return _page("Checkout cancelled",
                 "<h2>Checkout cancelled</h2><p class='muted'>No charge was made.</p>")


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
    Route("/stripe/webhook", stripe_webhook, methods=["POST"]),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.web_host, port=settings.web_port)


if __name__ == "__main__":
    main()
