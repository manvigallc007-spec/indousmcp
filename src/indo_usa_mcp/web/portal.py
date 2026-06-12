"""Customer portal: passwordless magic-link login + owner listing management."""

from __future__ import annotations

import html

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import db, payments, verticals
from ..config import settings
from ..pipeline import outreach
from .auth import make_magic_token, portal_email, verify_magic_token
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


def login_get(request: Request) -> HTMLResponse:
    return _page("Owner sign in",
                 "<h2>Manage your listing</h2>"
                 "<p class='muted'>Enter your email and we'll send you a secure sign-in link "
                 "— no password needed.</p>"
                 "<form method='post' action='/portal/login'>"
                 "<label>Email</label><input name='email' type='email' autofocus>"
                 "<button type='submit'>Email me a link</button></form>")


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


def dashboard(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    listings = _owned(email)
    if not listings:
        return _page("No listings", f"<h2>No listings for {esc(email)}</h2>"
                     "<p class='muted'>Claim a listing first, or contact us.</p>")
    rows = ""
    for x in listings:
        status = ("<span class='ok'>★ featured</span>" if x["is_featured"]
                  else ("active" if x["is_active"] else "<span class='err'>inactive</span>"))
        upgrade = ""
        if x["vertical"] == "restaurants" and not x["is_featured"] and payments.enabled():
            upgrade = f" · <a href='/upgrade?id={x['id']}'>Get featured</a>"
        rows += (f"<tr><td><a href='/portal/edit/{x['vertical']}/{x['id']}'>{esc(x['name'])}</a></td>"
                 f"<td class='muted'>{x['vertical']}</td>"
                 f"<td>{esc(x['city'])}, {esc(x['state'])}</td><td>{status}{upgrade}</td></tr>")
    body = (f"<h2>Your listings</h2><p class='muted'>{esc(email)} · "
            f"<a href='/portal/logout'>sign out</a></p>"
            f"<table style='width:100%'>{rows}</table>")
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
    Route("/portal", dashboard, methods=["GET"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_get, methods=["GET"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_post, methods=["POST"]),
    Route("/portal/logout", logout, methods=["GET"]),
]
