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
from .pipeline import outreach

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
        return _page(
            "Listing claimed",
            "<h2 class='ok'>&#10003; Listing claimed</h2>"
            "<p>Thank you — you now own this listing. We'll follow up to help you update "
            "hours, menu, photos and more.</p>" + upgrade,
        )

    reasons = {
        "invalid_token": "This claim link isn't valid.",
        "expired": "This claim link has expired. Contact us for a new one.",
        "claim_claimed": "This listing has already been claimed.",
        "claim_revoked": "This claim link was revoked.",
    }
    msg = reasons.get(result.get("error", ""), "Something went wrong. Please try again.")
    return _page("Could not claim", f"<h2 class='err'>Couldn't claim</h2><p>{msg}</p>", status=400)


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
