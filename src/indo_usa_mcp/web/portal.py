"""Customer portal: passwordless magic-link login + owner listing management."""

from __future__ import annotations

import html
import re
import secrets

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import analytics, db, onboard, payments, submissions, verticals
from ..config import settings
from ..pipeline import outreach
from .auth import (check_login, create_user, get_user, google_auth_url, google_exchange,
                   make_action_token, portal_email, set_password, set_verified,
                   verify_action_token, verify_captcha, verify_magic_token)
from .common import _page, captcha_field, esc, state_select

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


def _send_or_show(email: str, purpose: str, subject: str, intro: str) -> str:
    """Email a verify/reset link; in dev (no SMTP) return an inline link to show on the page."""
    ttl = 1440 if purpose == "verify" else 60
    path = "/portal/verify" if purpose == "verify" else "/portal/reset"
    link = f"{settings.public_web_url.rstrip('/')}{path}?t={make_action_token(email, purpose, ttl)}"
    if settings.email_enabled:
        try:
            outreach.send_email(email, f"{settings.platform_name}: {subject}",
                                f"{intro}\n\n{link}\n\nThis link expires soon. "
                                "If you didn't request it, you can ignore this email.")
        except Exception:
            pass
        return ""
    return f"<p class='muted'>Dev mode (no SMTP): <a href='{esc(link)}'>{esc(subject)} link</a></p>"


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
    return _page("Sign in",
                 "<h2>Sign in</h2>"
                 "<p class='muted'>Sign in to add and manage your business listing.</p>"
                 + google +
                 "<form method='post' action='/portal/login'>"
                 "<label>Email</label><input name='email' type='email' autofocus required>"
                 "<label>Password</label><input name='password' type='password' required>"
                 "<button type='submit'>Sign in</button></form>"
                 "<p class='muted' style='margin-top:12px'>New here? "
                 "<a href='/portal/register'>Create an account</a> · "
                 "<a href='/portal/forgot'>Forgot password?</a></p>")


async def login_post(request: Request) -> HTMLResponse:
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    u = check_login(email, form.get("password") or "")
    if not u:
        return _page("Sign-in failed", "<h2 class='err'>Email or password is incorrect</h2>"
                     "<p><a href='/portal/login'>Try again</a> · "
                     "<a href='/portal/forgot'>Forgot password?</a></p>", status=401)
    if not u.get("email_verified"):
        note = _send_or_show(email, "verify", "Verify your email",
                             "Please verify your email to finish signing in:")
        return _page("Verify your email", "<h2>Please verify your email first</h2>"
                     f"<p>We've sent a verification link to <b>{esc(email)}</b>. Click it, then sign "
                     "in.</p>" + note)
    request.session["owner_email"] = email
    return RedirectResponse("/portal", status_code=303)


def register_get(request: Request) -> HTMLResponse:
    if portal_email(request):
        return RedirectResponse("/portal", status_code=303)
    google = _GBTN if settings.google_oauth_enabled else ""
    return _page("Register your business",
                 "<h2>Register your business</h2>"
                 "<p class='muted'>Create a free account to add and manage your business — found by "
                 "people and AI across the USA.</p>"
                 + google +
                 "<form method='post' action='/portal/register'>"
                 "<label>Email</label><input name='email' type='email' required autofocus>"
                 "<label>Password (min 8 characters)</label>"
                 "<input name='password' type='password' minlength='8' required>"
                 "<label>Confirm password</label>"
                 "<input name='password2' type='password' minlength='8' required>"
                 + captcha_field() +
                 "<label style='font-weight:400;display:flex;gap:8px;align-items:flex-start;margin:6px 0 14px'>"
                 "<input type='checkbox' name='accept' value='1' required style='width:auto;margin-top:4px'>"
                 "<span>I agree to the <a href='/terms' target='_blank'>Terms</a> &amp; "
                 "<a href='/privacy' target='_blank'>Privacy Policy</a>.</span></label>"
                 "<button type='submit'>Create account</button></form>"
                 "<p class='muted' style='margin-top:12px'>Already have an account? "
                 "<a href='/portal/login'>Sign in</a></p>")


async def register_post(request: Request) -> HTMLResponse:
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    pw, pw2 = form.get("password") or "", form.get("password2") or ""
    err = None
    if not _valid_email(email):
        err = "Please enter a valid email address."
    elif len(pw) < 8:
        err = "Password must be at least 8 characters."
    elif pw != pw2:
        err = "The passwords don't match."
    elif not form.get("accept"):
        err = "Please accept the Terms and Privacy Policy to continue."
    elif not verify_captcha(form):
        err = "The captcha answer was incorrect — please try again."
    if err:
        return _page("Registration", "<h2 class='err'>Couldn't create your account</h2>"
                     f"<p>{esc(err)}</p><p><a href='/portal/register'>&#8592; Back to registration</a></p>",
                     status=400)
    if not create_user(email, pw).get("ok"):
        return _page("Account exists", "<h2>You already have an account</h2>"
                     f"<p>{esc(email)} is already registered. <a href='/portal/login'>Sign in</a> or "
                     "<a href='/portal/forgot'>reset your password</a>.</p>")
    note = _send_or_show(email, "verify", "Verify your email",
                         f"Welcome to {settings.platform_name}! Confirm your email to activate your account:")
    return _page("Check your email", "<h2 class='ok'>Almost there — check your email</h2>"
                 f"<p>We sent a verification link to <b>{esc(email)}</b>. Click it to activate your "
                 "account, then sign in.</p>" + note)


def verify_email(request: Request) -> HTMLResponse:
    email = verify_action_token(request.query_params.get("t", ""), "verify")
    if not email:
        return _page("Link expired", "<h2 class='err'>Invalid or expired verification link</h2>"
                     "<p><a href='/portal/login'>Sign in</a> to get a new one, or "
                     "<a href='/portal/register'>register</a>.</p>", status=401)
    set_verified(email)
    request.session["owner_email"] = email                 # using the emailed link proves ownership
    return RedirectResponse("/portal", status_code=303)


def forgot_get(request: Request) -> HTMLResponse:
    return _page("Reset your password",
                 "<h2>Reset your password</h2>"
                 "<p class='muted'>Enter your account email and we'll send a reset link.</p>"
                 "<form method='post' action='/portal/forgot'>"
                 "<label>Email</label><input name='email' type='email' required autofocus>"
                 + captcha_field() +
                 "<button type='submit'>Send reset link</button></form>"
                 "<p class='muted' style='margin-top:12px'><a href='/portal/login'>Back to sign in</a></p>")


async def forgot_post(request: Request) -> HTMLResponse:
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    if not verify_captcha(form):
        return _page("Reset", "<h2 class='err'>The captcha answer was incorrect</h2>"
                     "<p><a href='/portal/forgot'>Try again</a></p>", status=400)
    note = ""
    if _valid_email(email) and get_user(email):
        note = _send_or_show(email, "reset", "Reset your password",
                             "We received a request to reset your password. Click to choose a new one:")
    return _page("Check your email", "<h2 class='ok'>Check your email</h2>"
                 f"<p>If an account exists for <b>{esc(email)}</b>, a password-reset link is on its "
                 "way. It expires soon.</p>" + note)


def reset_get(request: Request) -> HTMLResponse:
    token = request.query_params.get("t", "")
    if not verify_action_token(token, "reset"):
        return _page("Link expired", "<h2 class='err'>Invalid or expired reset link</h2>"
                     "<p><a href='/portal/forgot'>Request a new one</a></p>", status=401)
    return _page("Choose a new password",
                 "<h2>Choose a new password</h2>"
                 "<form method='post' action='/portal/reset'>"
                 f"<input type='hidden' name='t' value='{esc(token)}'>"
                 "<label>New password (min 8 characters)</label>"
                 "<input name='password' type='password' minlength='8' required autofocus>"
                 "<label>Confirm password</label>"
                 "<input name='password2' type='password' minlength='8' required>"
                 "<button type='submit'>Set new password</button></form>")


async def reset_post(request: Request) -> HTMLResponse:
    form = await request.form()
    email = verify_action_token(form.get("t") or "", "reset")
    if not email:
        return _page("Link expired", "<h2 class='err'>Invalid or expired reset link</h2>"
                     "<p><a href='/portal/forgot'>Request a new one</a></p>", status=401)
    pw, pw2 = form.get("password") or "", form.get("password2") or ""
    if len(pw) < 8 or pw != pw2:
        return _page("Reset", "<h2 class='err'>Passwords must match and be at least 8 characters</h2>"
                     "<p>Please go back and try again.</p>", status=400)
    set_password(email, pw)
    set_verified(email)
    request.session["owner_email"] = email
    return _page("Password updated", "<h2 class='ok'>&#10003; Password updated</h2>"
                 "<p>You're signed in. <a href='/portal'>Go to your dashboard &#8594;</a></p>")


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


_ADD_BTN = ("<a href='/portal/add' style='display:inline-block;background:#e8772e;color:#fff;"
            "border-radius:9px;padding:11px 20px;font-weight:600;text-decoration:none'>"
            "➕ Add your business</a>")


def _subs_html(email: str) -> str:
    """An owner's still-pending submissions, with a delete button each."""
    subs = [s for s in submissions.list_for_owner(email) if s.get("status") == "pending"]
    if not subs:
        return ""
    rows = ""
    for s in subs:
        p = s.get("payload") or {}
        loc = ", ".join(x for x in (p.get("city"), p.get("state")) if x)
        rows += (f"<tr><td>{esc(p.get('name'))}</td><td class='muted'>{esc(s['vertical'])}</td>"
                 f"<td class='muted'>{esc(loc)}</td><td><span class='muted'>pending review</span></td>"
                 f"<td><form method='post' action='/portal/submission/{s['id']}/delete' "
                 "style='display:inline' onsubmit=\"return confirm('Delete this submission?')\">"
                 "<button type='submit' style='width:auto;background:#b91c1c;padding:7px 13px;"
                 "font-size:13px'>Delete</button></form></td></tr>")
    return ("<h3 style='margin-top:26px'>Pending submissions</h3>"
            "<p class='muted'>Awaiting review before they go live — you can delete one you no longer "
            f"want.</p><table style='width:100%'>{rows}</table>")


def dashboard(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    banner = ("<div class='ok' style='background:#e7f6ec;border-radius:10px;padding:11px 14px;"
              "margin-bottom:14px'>✓ Submitted for review — it'll go live once approved.</div>"
              if request.query_params.get("added") else "")
    subs = _subs_html(email)
    listings = _owned(email)
    if not listings:
        return _page("Add your business", banner + f"<h2>Welcome, {esc(email)}! 🙏</h2>"
                     "<p class='muted'>You're signed in. Add your business and it'll appear here once "
                     "approved — we'll auto-fill the details for you to verify.</p>"
                     f"<p>{_ADD_BTN}</p>" + subs +
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
    body = (banner + f"<h2>Your listings</h2><p class='muted'>{esc(email)} · "
            f"<a href='/portal/logout'>sign out</a></p>"
            "<p class='muted'>“Shown” = times an AI assistant or visitor surfaced your listing.</p>"
            f"<table style='width:100%'>{rows}</table>"
            f"<p style='margin-top:14px'>{_ADD_BTN}</p>" + subs + _engage_html())
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
    rows += (f"<label>Languages spoken (comma-separated)</label>"
             f"<input name='languages_csv' value='{esc(','.join(rec.get('languages') or []))}' "
             f"placeholder='Telugu, Hindi, English'>")
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
    if "languages_csv" in form:
        from .. import tags as tagsmod
        edits["languages"] = tagsmod.parse_languages(form.get("languages_csv"))
    result = verticals.apply_edits(vertical, rec_id, edits)
    n = result.get("updated", 0)
    return _page("Saved", f"<h2 class='ok'>&#10003; Saved {n} change(s)</h2>"
                 f"<p><a href='/portal/edit/{vertical}/{rec_id}'>Keep editing</a> · "
                 f"<a href='/portal'>your listings</a></p>")


# ------------------------------------------------------------------ guided "add a business" onboarding
def add_get(request: Request) -> HTMLResponse:
    if not portal_email(request):
        return RedirectResponse("/portal/login", status_code=303)
    opts = "".join(f"<option value='{v}'>{esc(verticals.VERTICALS[v]['label'])}</option>"
                   for v in submissions.SUBMITTABLE)
    return _page("Add your business",
                 "<h2>Add your business</h2>"
                 "<p class='muted'>Just tell us the name and where it is — we'll fill in the rest "
                 "from public sources for you to check, then submit.</p>"
                 "<form method='post' action='/portal/add'>"
                 f"<label>Category</label><select name='vertical'>{opts}</select>"
                 "<label>Business name</label><input name='name' required autofocus>"
                 f"<label>State</label>{state_select('state', required=True)}"
                 "<label>City</label><input name='city' required placeholder='e.g. Plano'>"
                 "<button type='submit'>Find my business →</button></form>"
                 "<p class='muted' style='margin-top:12px'><a href='/portal'>‹ back to your listings</a></p>")


def _fld(label: str, key: str, cand: dict, ph: str = "") -> str:
    return (f"<label>{esc(label)}</label>"
            f"<input name='{key}' value='{esc(cand.get(key) or '')}' placeholder='{esc(ph)}'>")


async def add_post(request: Request) -> HTMLResponse:
    """Step 2: look the business up from public sources and show a prefilled form to verify."""
    if not portal_email(request):
        return RedirectResponse("/portal/login", status_code=303)
    form = await request.form()
    vertical = (form.get("vertical") or "").strip()
    name = (form.get("name") or "").strip()
    state = (form.get("state") or "").strip()
    city = (form.get("city") or "").strip()
    if vertical not in submissions.SUBMITTABLE or not name:
        return _page("Add your business", "<h2 class='err'>Please enter a business name and category</h2>"
                     "<p><a href='/portal/add'>‹ back</a></p>", status=400)
    cand = onboard.lookup(name, city, state, vertical)
    photo = (f"<img src='{esc(cand['photo_url'])}' alt='' onerror='this.remove()' style='width:100%;"
             f"max-height:220px;object-fit:cover;border-radius:12px;margin:6px 0'>"
             if cand.get("photo_url") else "")
    body = (f"<h2>Verify {esc(name)}</h2>"
            "<p class='muted'>We pre-filled what we found from public sources. Check it, fix anything, "
            "then submit — your listing is reviewed before it goes live.</p>" + photo
            + "<form method='post' action='/portal/add/confirm'>"
            f"<input type='hidden' name='vertical' value='{esc(vertical)}'>"
            f"<input type='hidden' name='photo_url' value='{esc(cand.get('photo_url') or '')}'>"
            + _fld("Business name", "name", cand)
            + _fld("Address", "address_full", cand)
            + _fld("City", "city", cand)
            + f"<label>State</label>{state_select('state', cand.get('state') or state)}"
            + _fld("Phone", "phone", cand) + _fld("Email", "email", cand)
            + _fld("Website", "website", cand)
            + _fld("Opening hours", "hours", cand, "e.g. Mon-Sun 11am-9pm")
            + _fld("Languages spoken", "languages", cand, "Telugu, Hindi, English")
            + "<button type='submit'>Submit for review</button></form>"
            "<p class='muted' style='margin-top:12px'><a href='/portal/add'>‹ start over</a></p>")
    return _page(f"Verify {name}", body)


async def add_confirm(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    form = await request.form()
    vertical = (form.get("vertical") or "").strip()
    payload = {k: (form.get(k) or "").strip() for k in
               ("name", "address_full", "city", "state", "phone", "email", "website", "languages")}
    if (form.get("photo_url") or "").strip():
        payload["photo_url"] = form.get("photo_url").strip()
    if (form.get("hours") or "").strip():
        payload["hours_json"] = {"raw": form.get("hours").strip()}
    res = submissions.submit(vertical, payload, contact_email=email, note="owner onboarding")
    if not res.get("ok"):
        return _page("Couldn't submit", "<h2 class='err'>Please add a business name and category</h2>"
                     "<p><a href='/portal/add'>‹ back</a></p>", status=400)
    return RedirectResponse("/portal?added=1", status_code=303)


async def submission_delete(request: Request) -> RedirectResponse:
    email = portal_email(request)
    if email:
        try:
            submissions.delete_for_owner(int(request.path_params["id"]), email)
        except (ValueError, TypeError):
            pass
    return RedirectResponse("/portal", status_code=303)


def logout(request: Request) -> RedirectResponse:
    request.session.pop("owner_email", None)
    return RedirectResponse("/portal/login", status_code=303)


routes = [
    Route("/portal/login", login_get, methods=["GET"]),
    Route("/portal/login", login_post, methods=["POST"]),
    Route("/portal/register", register_get, methods=["GET"]),
    Route("/portal/register", register_post, methods=["POST"]),
    Route("/portal/verify", verify_email, methods=["GET"]),
    Route("/portal/forgot", forgot_get, methods=["GET"]),
    Route("/portal/forgot", forgot_post, methods=["POST"]),
    Route("/portal/reset", reset_get, methods=["GET"]),
    Route("/portal/reset", reset_post, methods=["POST"]),
    Route("/portal/auth", auth, methods=["GET"]),
    Route("/portal/google", google_login, methods=["GET"]),
    Route("/portal/google/callback", google_callback, methods=["GET"]),
    Route("/portal", dashboard, methods=["GET"]),
    Route("/portal/add", add_get, methods=["GET"]),
    Route("/portal/add", add_post, methods=["POST"]),
    Route("/portal/add/confirm", add_confirm, methods=["POST"]),
    Route("/portal/submission/{id:int}/delete", submission_delete, methods=["POST"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_get, methods=["GET"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_post, methods=["POST"]),
    Route("/portal/logout", logout, methods=["GET"]),
]
