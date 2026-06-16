"""Customer portal: passwordless magic-link login + owner listing management."""

from __future__ import annotations

import html
import secrets

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import analytics, db, payments, verticals
from ..config import settings
from ..pipeline import outreach
from .auth import (google_auth_url, google_exchange, make_magic_token, portal_email,
                   verify_magic_token)
from .common import _page, esc


def _owned(email: str) -> list[dict]:
    """All listings owned by this email: restaurants they claimed + any listing emailed to them."""
    owned: dict[tuple, dict] = {}
    for r in db.query(
        "SELECT r.id, r.name, r.city, r.state, r.is_featured, r.featured_until, r.is_active "
        "FROM claims c JOIN restaurants r ON r.id = c.restaurant_id "
        "WHERE lower(c.owner_email) = lower(%s) AND c.status = 'claimed' AND r.deleted_at IS NULL",
        (email,),
    ):
        owned[("restaurants", r["id"])] = {"vertical": "restaurants", **r}
    for v, cfg in verticals.VERTICALS.items():
        for r in db.query(
            f"SELECT id, name, city, state, is_featured, featured_until, is_active "
            f"FROM {cfg['table']} WHERE lower(email) = lower(%s) AND deleted_at IS NULL", (email,)):
            owned[(v, r["id"])] = {"vertical": v, **r}
    return list(owned.values())


_GBTN = ("<a href='/portal/google' style='display:block;text-align:center;background:#fff;"
         "border:1px solid #dadce0;border-radius:8px;padding:11px;font-weight:600;color:#3c4043;"
         "text-decoration:none;margin-bottom:12px'>Sign in with Google</a>"
         "<p class='muted' style='text-align:center;margin:4px 0 12px'>— or —</p>")

_TILE = ("display:inline-block;border:1px solid #e6e6e6;border-radius:12px;padding:12px 16px;"
         "text-decoration:none;color:#1a1a1a;font-weight:600;background:#fff")


def _engage_html() -> str:
    """Invite owners/visitors to ask, add, or request data (encourages engagement)."""
    a = esc(settings.assistant_name)
    return (
        "<div style='border-top:1px solid #eee;margin-top:22px;padding-top:18px'>"
        "<h3 style='margin:0 0 4px'>Get the most out of " + esc(settings.platform_name) + "</h3>"
        "<p class='muted' style='margin:0 0 12px'>Can't find what you need? Ask " + a + ", add it "
        "yourself, or tell us what you'd like to see — we'll work on adding it.</p>"
        "<div style='display:flex;flex-wrap:wrap;gap:10px'>"
        f"<a style='{_TILE}' href='/'>💬 Ask {a} a question</a>"
        f"<a style='{_TILE}' href='/submit'>➕ Add a business</a>"
        f"<a style='{_TILE}' href='/contact'>📨 Request data or suggest a category</a></div></div>")


def login_get(request: Request) -> HTMLResponse:
    google = _GBTN if settings.google_oauth_enabled else ""
    return _page("Register or sign in your business",
                 "<h2>Register or sign in your business</h2>"
                 "<p class='muted'>Sign in to add your business and keep its details up to date — "
                 "it's free. New here? Just sign in, then add your listing.</p>"
                 + google +
                 "<form method='post' action='/portal/login'>"
                 "<label>Email</label><input name='email' type='email' autofocus>"
                 "<button type='submit'>Email me a sign-in link</button></form>"
                 "<p class='muted' style='margin-top:14px'>Prefer to just add a listing without an "
                 "account? <a href='/submit'>Add your business →</a></p>")


async def login_post(request: Request) -> HTMLResponse:
    email = ((await request.form()).get("email") or "").strip().lower()
    sent = "<h2 class='ok'>Check your email</h2><p>If you manage any listings, a sign-in " \
           "link is on its way. It expires in %d minutes.</p>" % settings.magic_link_ttl_minutes
    if email and _owned(email):
        token = make_magic_token(email)
        link = f"{settings.public_web_url.rstrip('/')}/portal/auth?t={token}"
        if settings.email_enabled:
            try:
                outreach.send_email(email, f"Sign in to {settings.platform_name}",
                                    f"Click to sign in (expires soon):\n{link}")
            except Exception:
                pass
        else:
            # Dev convenience when SMTP isn't configured: show the link directly.
            sent += f"<p class='muted'>Dev mode (no SMTP): <a href='{esc(link)}'>sign-in link</a></p>"
    return _page("Check your email", sent)


def auth(request: Request) -> HTMLResponse:
    email = verify_magic_token(request.query_params.get("t", ""))
    if not email:
        return _page("Link expired", "<h2 class='err'>Invalid or expired link</h2>"
                     "<p><a href='/portal/login'>Request a new one</a></p>", status=401)
    request.session["owner_email"] = email
    return RedirectResponse("/portal", status_code=303)


def google_login(request: Request) -> HTMLResponse:
    if not settings.google_oauth_enabled:
        return RedirectResponse("/portal/login", status_code=303)
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state           # CSRF: verified on callback
    return RedirectResponse(google_auth_url(state), status_code=303)


def google_callback(request: Request) -> HTMLResponse:
    qs = request.query_params
    saved = request.session.pop("oauth_state", None)
    if not settings.google_oauth_enabled or qs.get("error"):
        return RedirectResponse("/portal/login", status_code=303)
    if not qs.get("state") or qs.get("state") != saved:
        return _page("Sign-in error", "<h2 class='err'>Couldn't verify the sign-in</h2>"
                     "<p><a href='/portal/login'>Try again</a></p>", status=400)
    email = google_exchange(qs.get("code") or "")
    if not email:
        return _page("Sign-in error", "<h2 class='err'>Google sign-in failed</h2>"
                     "<p><a href='/portal/login'>Try again</a></p>", status=401)
    request.session["owner_email"] = email
    return RedirectResponse("/portal", status_code=303)


def dashboard(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    listings = _owned(email)
    if not listings:
        return _page("Add your business", f"<h2>Welcome, {esc(email)}! 🙏</h2>"
                     "<p class='muted'>You're signed in. You don't have any listings yet — add your "
                     "business and it'll appear here once approved.</p>"
                     "<p><a href='/submit' style='display:inline-block;background:#e8772e;color:#fff;"
                     "border-radius:9px;padding:11px 20px;font-weight:600;text-decoration:none'>"
                     "➕ Add your business</a></p>"
                     "<p class='muted' style='margin-top:14px'>Already listed? Claim it from its page "
                     "to link it to your account. · <a href='/portal/logout'>Sign out</a></p>"
                     + _engage_html())
    rows = ""
    for x in listings:
        status = ("<span class='ok'>★ featured</span>" if x["is_featured"]
                  else ("active" if x["is_active"] else "<span class='err'>inactive</span>"))
        upgrade = ""
        if x["vertical"] == "restaurants" and not x["is_featured"] and settings.featured_for_sale:
            upgrade = f" · <a href='/upgrade?id={x['id']}'>Get featured</a>"
        reach = analytics.reach_for(x["vertical"], x["id"], days=30)
        rows += (f"<tr><td><a href='/portal/edit/{x['vertical']}/{x['id']}'>{esc(x['name'])}</a></td>"
                 f"<td class='muted'>{x['vertical']}</td>"
                 f"<td>{esc(x['city'])}, {esc(x['state'])}</td>"
                 f"<td>{reach} <span class='muted'>shown (30d)</span></td>"
                 f"<td>{status}{upgrade}</td></tr>")
    body = (f"<h2>Your listings</h2><p class='muted'>{esc(email)} · "
            f"<a href='/portal/logout'>sign out</a></p>"
            "<p class='muted'>“Shown” = times an AI assistant or visitor surfaced your listing.</p>"
            f"<table style='width:100%'>{rows}</table>" + _engage_html())
    return _page("Your listings", body)


def _edit_form(vertical: str, rec: dict) -> str:
    cfg = verticals.VERTICALS[vertical]
    rows = "".join(f"<label>{f}</label><input name='{f}' value='{esc(rec.get(f))}'>"
                   for f in cfg["edit_fields"])
    if cfg["has_hours"]:
        hr = (rec.get("hours_json") or {}).get("raw", "") if isinstance(rec.get("hours_json"), dict) else ""
        rows += f"<label>Opening hours</label><input name='hours' value='{esc(hr)}'>"
    if cfg["has_dietary"]:
        rows += (f"<label>Dietary (comma-separated)</label>"
                 f"<input name='dietary_csv' value='{esc(','.join(rec.get('dietary_tags') or []))}'>")
    return (f"<form method='post' action='/portal/edit/{vertical}/{rec['id']}'>{rows}"
            f"<button>Save changes</button></form>")


def _require_owner(request: Request, vertical: str, rec_id: int):
    email = portal_email(request)
    if not email:
        return None, RedirectResponse("/portal/login", status_code=303)
    if any(o["vertical"] == vertical and o["id"] == rec_id for o in _owned(email)):
        return verticals.get_record(vertical, rec_id), None
    return None, _page("Not allowed", "<h2 class='err'>That listing isn't yours</h2>", status=403)


def edit_get(request: Request) -> HTMLResponse:
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec, resp = _require_owner(request, vertical, rec_id)
    if resp:
        return resp
    body = (f"<h2>Edit {esc(rec['name'])}</h2>"
            "<p class='muted'>Changes go live immediately. "
            "<a href='/portal'>‹ back to your listings</a></p>" + _edit_form(vertical, rec))
    return _page(f"Edit {rec['name']}", body)


async def edit_post(request: Request) -> HTMLResponse:
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec, resp = _require_owner(request, vertical, rec_id)
    if resp:
        return resp
    cfg = verticals.VERTICALS[vertical]
    form = await request.form()
    edits = {f: (form.get(f) or "").strip() or None for f in cfg["edit_fields"] if f in form}
    if cfg["has_hours"] and "hours" in form:
        hv = (form.get("hours") or "").strip()
        edits["hours_json"] = {"raw": hv} if hv else None
    if cfg["has_dietary"] and "dietary_csv" in form:
        edits["dietary_tags"] = sorted(t.strip() for t in (form.get("dietary_csv") or "").split(",") if t.strip())
    result = verticals.apply_edits(vertical, rec_id, edits)
    n = result.get("updated", 0)
    return _page("Saved", f"<h2 class='ok'>&#10003; Saved {n} change(s)</h2>"
                 f"<p><a href='/portal/edit/{vertical}/{rec_id}'>Keep editing</a> · "
                 f"<a href='/portal'>your listings</a></p>")


def logout(request: Request) -> RedirectResponse:
    request.session.pop("owner_email", None)
    return RedirectResponse("/portal/login", status_code=303)


routes = [
    Route("/portal/login", login_get, methods=["GET"]),
    Route("/portal/login", login_post, methods=["POST"]),
    Route("/portal/auth", auth, methods=["GET"]),
    Route("/portal/google", google_login, methods=["GET"]),
    Route("/portal/google/callback", google_callback, methods=["GET"]),
    Route("/portal", dashboard, methods=["GET"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_get, methods=["GET"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_post, methods=["POST"]),
    Route("/portal/logout", logout, methods=["GET"]),
]
