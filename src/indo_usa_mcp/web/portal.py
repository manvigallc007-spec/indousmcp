"""Customer portal: passwordless magic-link login + owner listing management."""

from __future__ import annotations

import html
import re
import secrets

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import accounts, analytics, db, flyer, onboard, owner_content, payments, \
    reviews as reviews_mod, submissions, verticals
from ..config import settings
from ..events import pipeline as events
from ..pipeline import outreach
from .auth import (check_login, create_user, get_user, google_auth_url, google_exchange,
                   make_action_token, portal_email, set_password, set_verified,
                   verify_action_token, verify_captcha, verify_magic_token)
from .common import _page, captcha_field, esc, sparkline, state_select, trend_badge

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
    """All listings owned by this email: any vertical they CLAIMED (via the claim flow) + any listing
    whose contact email matches (self-added)."""
    owned: dict[tuple, dict] = {}
    cols = "id, name, city, state, is_featured, featured_until, is_active"
    for c in db.query("SELECT vertical, record_id FROM claims "
                      "WHERE lower(owner_email) = lower(%s) AND status = 'claimed'", (email,)):
        v = c["vertical"]
        if v not in verticals.VERTICALS:
            continue
        r = db.query_one(f"SELECT {cols} FROM {verticals._table(v)} "
                         f"WHERE id = %s AND deleted_at IS NULL", (c["record_id"],))
        if r:
            owned[(v, r["id"])] = {"vertical": v, **r}
    for v, cfg in verticals.VERTICALS.items():
        for r in db.query(f"SELECT {cols} FROM {cfg['table']} "
                          f"WHERE lower(email) = lower(%s) AND deleted_at IS NULL", (email,)):
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
                 f"<input type='hidden' name='ref' value='{esc(request.query_params.get('ref') or '')}'>"
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
    if (form.get("ref") or "").strip():                    # attribute the referral (first-touch, never self)
        try:
            accounts.attribute_referral(email, form.get("ref"))
        except Exception:
            pass
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
        if not x["is_featured"] and settings.featured_for_sale:   # any vertical, not just restaurants
            upgrade = f" · <a href='/upgrade?id={x['id']}&vertical={x['vertical']}'>Get featured</a>"
        reach = analytics.reach_for(x["vertical"], x["id"], days=30)
        tr_ = analytics.listing_trend(x["vertical"], x["id"], 30)
        badge = trend_badge(tr_["delta_pct"]) if tr_["views"] or tr_["prev_views"] else ""
        rows += (f"<tr><td><a href='/portal/listing/{x['vertical']}/{x['id']}'>{esc(x['name'])}</a></td>"
                 f"<td class='muted'>{x['vertical']}</td>"
                 f"<td>{esc(x['city'])}, {esc(x['state'])}</td>"
                 f"<td>{reach} <span class='muted'>shown</span> · {tr_['views']} "
                 f"<span class='muted'>views (30d)</span> {badge}</td>"
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
            f"<a href='/portal/listing/{vertical}/{rec_id}'>Offers &amp; reviews</a> · "
            "<a href='/portal'>‹ back to your listings</a></p>" + _edit_form(vertical, rec))
    return _page(f"Edit {rec['name']}", body)


# ----------------------------------------------------------------- owner engagement (offers + review replies)
def listing_manage(request: Request) -> HTMLResponse:
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec, resp = _require_owner(request, vertical, rec_id)
    if resp:
        return resp
    email = portal_email(request)
    posts = owner_content.owner_posts(vertical, rec_id, email)
    revs = reviews_mod.list_for_listing(vertical, rec_id, limit=30, status="published")
    draft_for = request.query_params.get("draft_review")

    plist = "".join(
        f"<div class='lc'><b>{esc(p['title'])}</b> <span class='muted'>· {esc(p['kind'])}"
        + (f" · until {esc(str(p['expires_at'])[:10])}" if p.get("expires_at") else "") + "</span>"
        + (f"<p style='margin:4px 0 0'>{esc(p['body'])}</p>" if p.get("body") else "")
        + f"<form method='post' action='/portal/listing/{vertical}/{rec_id}/offer/{p['id']}/delete' "
        "style='display:inline'><button class='linkbtn'>Remove</button></form></div>"
        for p in posts) or "<p class='muted'>No active offers.</p>"
    offers = (f"<h3>Offers &amp; announcements</h3>{plist}"
              f"<form method='post' action='/portal/listing/{vertical}/{rec_id}/offer'>"
              "<select name='kind'><option value='offer'>Offer / promo</option>"
              "<option value='announcement'>Announcement</option></select>"
              "<label>Title</label><input name='title' required maxlength='120' "
              "placeholder='e.g. 20% off thalis this weekend'>"
              "<label>Details (optional)</label><input name='body' maxlength='600'>"
              "<label>Expires (optional)</label><input name='expires_at' type='date'>"
              "<button type='submit'>Post</button></form>")

    rblocks = []
    for r in revs:
        n = int(r["rating"])
        stars = "★" * n + "☆" * (5 - n)
        reply = (f"<div class='muted' style='margin:4px 0'>↳ <b>Your reply:</b> {esc(r['owner_reply'])}</div>"
                 if r.get("owner_reply") else "")
        draft = ""
        if draft_for and str(r["id"]) == draft_for:
            d = owner_content.ai_reply_draft(rec["name"], r)
            draft = esc(d or "")
        rblocks.append(
            f"<div class='lc'><div>{stars} <span class='muted'>· {esc(r.get('author_name') or 'Anonymous')}</span></div>"
            + (f"<p style='margin:4px 0'>{esc(r.get('body') or '')}</p>" if r.get("body") else "")
            + reply
            + f"<form method='post' action='/portal/listing/{vertical}/{rec_id}/reply'>"
            f"<input type='hidden' name='review_id' value='{r['id']}'>"
            f"<textarea name='text' rows='2' maxlength='600' style='width:100%' "
            f"placeholder='Write a public reply…'>{draft}</textarea>"
            f"<button type='submit'>{'Update reply' if r.get('owner_reply') else 'Reply'}</button> "
            + (f"<a class='muted' href='/portal/listing/{vertical}/{rec_id}?draft_review={r['id']}#r{r['id']}'>"
               "✨ Draft with AI</a>" if not draft else "")
            + f"</form><span id='r{r['id']}'></span></div>")
    reviews_html = "<h3 style='margin-top:22px'>Reviews</h3>" + ("".join(rblocks) or
                   "<p class='muted'>No reviews yet.</p>")

    m30 = analytics.listing_metrics(vertical, rec_id, 30)
    m7 = analytics.listing_metrics(vertical, rec_id, 7)
    trend = analytics.listing_trend(vertical, rec_id, 30)
    spark = sparkline(analytics.listing_daily_views(vertical, rec_id, 30), width=260, height=44)

    def _stat(label: str, val30: int, val7: int) -> str:
        return ("<div style='display:inline-block;min-width:110px;margin:4px 10px 4px 0;padding:10px 14px;"
                "border:1px solid #ece6dd;border-radius:12px;text-align:center'>"
                f"<b style='font-size:22px;display:block;line-height:1.1'>{val30}</b>"
                f"<span class='muted' style='font-size:12px'>{label}<br>{val7} last 7d</span></div>")
    # Headline: views with a period-over-period trend, and a click-through rate (taps ÷ views).
    headline = (
        "<div style='display:flex;flex-wrap:wrap;gap:20px;align-items:center;margin:8px 0 6px'>"
        "<div><b style='font-size:30px'>" + str(trend["views"]) + "</b> "
        f"<span class='muted'>views (30d)</span> {trend_badge(trend['delta_pct'])} "
        f"<span class='muted' style='font-size:12px'>vs prior 30d ({trend['prev_views']})</span></div>"
        + (f"<div><b style='font-size:30px'>{trend['ctr']}%</b> "
           "<span class='muted'>click-through</span><br>"
           f"<span class='muted' style='font-size:12px'>{trend['taps']} calls/website/directions taps</span></div>")
        + (f"<div style='margin-left:auto'>{spark}<div class='muted' style='font-size:11px;"
           "text-align:center'>daily views</div></div>" if spark else "")
        + "</div>")
    metrics = (
        "<h3>Performance <span class='muted' style='font-size:13px;font-weight:400'>· last 30 days</span></h3>"
        + headline
        + "<div style='margin:8px 0 4px'>"
        + _stat("shown", analytics.reach_for(vertical, rec_id, 30), analytics.reach_for(vertical, rec_id, 7))
        + _stat("page views", m30["view"], m7["view"])
        + _stat("calls", m30["call"], m7["call"])
        + _stat("website taps", m30["website"], m7["website"])
        + _stat("directions", m30["directions"], m7["directions"])
        + "</div><p class='muted' style='font-size:12px'>“Shown” = surfaced by search/AI. Views &amp; taps "
        "are real visits to your public page. Click-through = how many viewers then called, tapped your "
        "website, or got directions.</p>")

    body = (f"<h2>{esc(rec['name'])}</h2>"
            f"<p class='muted'><a href='/portal/edit/{vertical}/{rec_id}'>Edit details</a> · "
            f"<a href='/listing/{vertical}/{rec_id}' target='_blank'>View public page</a> · "
            "<a href='/portal'>‹ your listings</a></p>"
            + metrics + offers + reviews_html)
    return _page(f"Manage {rec['name']}", body)


async def offer_create(request: Request) -> HTMLResponse:
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec, resp = _require_owner(request, vertical, rec_id)
    if resp:
        return resp
    form = await request.form()
    owner_content.create_post(vertical, rec_id, portal_email(request), kind=(form.get("kind") or "offer"),
                              title=(form.get("title") or ""), body=(form.get("body") or ""),
                              expires_at=(form.get("expires_at") or None))
    return RedirectResponse(f"/portal/listing/{vertical}/{rec_id}", status_code=303)


async def offer_delete(request: Request) -> HTMLResponse:
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec, resp = _require_owner(request, vertical, rec_id)
    if resp:
        return resp
    owner_content.remove_post(int(request.path_params["post_id"]), portal_email(request))
    return RedirectResponse(f"/portal/listing/{vertical}/{rec_id}", status_code=303)


async def review_reply(request: Request) -> HTMLResponse:
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec, resp = _require_owner(request, vertical, rec_id)
    if resp:
        return resp
    form = await request.form()
    try:
        owner_content.reply_to_review(int(form.get("review_id") or 0), vertical, rec_id,
                                      (form.get("text") or ""))
    except (ValueError, TypeError):
        pass
    return RedirectResponse(f"/portal/listing/{vertical}/{rec_id}", status_code=303)


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
                 "<label>Website <span style='font-weight:400;color:#6b7280'>(optional — we'll auto-fill "
                 "the details for you)</span></label><input name='website' placeholder='https://'>"
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
    website = (form.get("website") or "").strip()
    cand = onboard.lookup(name, city, state, vertical, website=website or None)
    cand = onboard.ai_fill(vertical, cand)                 # LLM-fill the category fields it can
    cfg = verticals.VERTICALS[vertical]
    photo = (f"<img src='{esc(cand['photo_url'])}' alt='' onerror='this.remove()' style='width:100%;"
             f"max-height:220px;object-fit:cover;border-radius:12px;margin:6px 0'>"
             if cand.get("photo_url") else "")
    # Vertical-specific category fields (cuisine_type, *_type, ...) — everything in edit_fields not
    # already covered by the fixed inputs below. This is what makes AI-filled category data reach the
    # submission instead of being silently dropped.
    _fixed = {"phone", "email", "website", "address_full", "city", "state"}
    extra = "".join(_fld(f.replace("_", " ").title(), f, cand)
                    for f in cfg["edit_fields"] if f not in _fixed)
    if cfg.get("has_dietary"):
        extra += (f"<label>Dietary (comma-separated)</label><input name='dietary_csv' "
                  f"value='{esc(','.join(cand.get('dietary_tags') or []))}' "
                  f"placeholder='vegetarian, vegan, halal'>")
    from .. import describe
    desc_preview = esc(describe.describe(vertical, {**cand, "vertical": vertical}))
    plan_html = _plan_picker()
    body = (f"<h2>Verify {esc(name)}</h2>"
            "<p class='muted'>We pre-filled what we found. Check it, fix anything, then submit — your "
            "listing is reviewed before it goes live.</p>" + photo
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
            + extra
            + (f"<p class='muted' style='margin-top:8px'>Preview: {desc_preview}</p>" if desc_preview else "")
            + plan_html
            + "<button type='submit'>Submit for review</button></form>"
            "<p class='muted' style='margin-top:12px'><a href='/portal/add'>‹ start over</a></p>")
    return _page(f"Verify {name}", body)


def _plan_picker() -> str:
    """Free vs paid featured-duration radios — only shown when the operator has enabled Stripe sales."""
    if not settings.featured_for_sale:
        return ""
    from .. import payments
    rows = ("<label style='display:block;margin:4px 0'><input type='radio' name='plan' value='free' "
            "checked> Free listing</label>")
    for o in payments.duration_options():
        rows += (f"<label style='display:block;margin:4px 0'><input type='radio' name='plan' "
                 f"value='{o['days']}'> ⭐ Featured — {esc(o['label'])}</label>")
    return ("<fieldset style='border:1px solid #e2e0dd;border-radius:10px;padding:10px 14px;margin:14px 0'>"
            "<legend style='font-size:13px;color:#6b7280'>Visibility (optional)</legend>"
            f"{rows}<p class='muted' style='font-size:12px;margin:6px 0 0'>Featured listings rank higher "
            "in browse &amp; search. Reviewed before going live, same as free.</p></fieldset>")


async def add_confirm(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    form = await request.form()
    vertical = (form.get("vertical") or "").strip()
    payload = {k: (form.get(k) or "").strip() for k in
               ("name", "address_full", "city", "state", "phone", "email", "website", "languages")}
    # Vertical-specific category fields (cuisine_type, *_type, ...) — collect what the review form showed.
    cfg = verticals.VERTICALS.get(vertical, {})
    _fixed = {"phone", "email", "website", "address_full", "city", "state"}
    for f in cfg.get("edit_fields", []):
        if f not in _fixed and form.get(f) is not None:
            payload[f] = (form.get(f) or "").strip()
    if cfg.get("has_dietary") and form.get("dietary_csv") is not None:
        payload["dietary_tags"] = [t.strip() for t in (form.get("dietary_csv") or "").split(",") if t.strip()]
    if (form.get("photo_url") or "").strip():
        payload["photo_url"] = form.get("photo_url").strip()
    if (form.get("hours") or "").strip():
        payload["hours_json"] = {"raw": form.get("hours").strip()}
    # ALWAYS submit first, identically for free and paid — so the approval decision can't be
    # influenced by payment (payment only takes effect at approval, in submissions.approve).
    res = submissions.submit(vertical, payload, contact_email=email, note="owner onboarding")
    if not res.get("ok"):
        return _page("Couldn't submit", "<h2 class='err'>Please add a business name and category</h2>"
                     "<p><a href='/portal/add'>‹ back</a></p>", status=400)
    plan = (form.get("plan") or "free").strip()
    if plan != "free" and settings.featured_for_sale:
        try:
            from .. import payments
            sess = payments.create_submission_premium_session(res["id"], days=int(plan))
            if sess.get("ok") and sess.get("url"):
                return RedirectResponse(sess["url"], status_code=303)
        except Exception:
            pass                                           # Stripe hiccup -> don't lose the free submission
    return RedirectResponse("/portal?added=1", status_code=303)


async def submission_delete(request: Request) -> RedirectResponse:
    email = portal_email(request)
    if email:
        try:
            submissions.delete_for_owner(int(request.path_params["id"]), email)
        except (ValueError, TypeError):
            pass
    return RedirectResponse("/portal", status_code=303)


# ----------------------------------------------------------------- flyer upload
_FLYER_VERTICAL_OPTS = [(k, v["label"]) for k, v in verticals.VERTICALS.items() if k != "events"] \
    + [("events", "Events")]


def flyer_get(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    if not settings.flyer_uploads_enabled:
        return _page("Upload a flyer",
                     "<h2>Flyer upload isn't available yet</h2>"
                     "<p class='muted'>This feature needs a vision-capable LLM configured on the "
                     "server. Check back soon, or <a href='/portal/add'>add your business manually</a>.</p>")
    past = flyer.list_for_uploader(email)
    rows = "".join(
        f"<div class='lc'><b>{esc((u.get('vertical_guess') or 'unclassified').title())}</b> "
        f"<span class='muted'>· {esc(u['status'])} · {esc(str(u['created_at'])[:16])}</span>"
        + (f" · <a href='/portal/flyer/{u['id']}/review'>review</a>" if u["status"] == "extracted" else "")
        + "</div>" for u in past)
    return _page("Upload a flyer",
                 "<h2>Upload a flyer</h2>"
                 "<p class='muted'>Upload an event poster or business promo — we'll read it and "
                 "pre-fill a listing for you to check before it's submitted for review.</p>"
                 "<form method='post' action='/portal/flyer' enctype='multipart/form-data'>"
                 "<label>Flyer image (JPG, PNG or WEBP)</label>"
                 "<input type='file' name='image' accept='image/jpeg,image/png,image/webp' required>"
                 "<button type='submit'>Read my flyer →</button></form>"
                 + (f"<h3 style='margin-top:24px'>Your uploads</h3>{rows}" if rows else ""))


async def flyer_post(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    if not settings.flyer_uploads_enabled:
        return _page("Unavailable", "<h2>Flyer upload isn't available yet</h2>", status=503)
    form = await request.form()
    upload = form.get("image")
    if upload is None or not getattr(upload, "filename", None):
        return _page("Upload a flyer", "<h2 class='err'>Please choose an image</h2>"
                     "<p><a href='/portal/flyer'>‹ back</a></p>", status=400)
    data = await upload.read()
    res = flyer.create_upload(email, data, upload.content_type or "")
    if not res.get("ok"):
        msg = {"unsupported_image_type": "Please upload a JPG, PNG, or WEBP image.",
               "image_too_large": f"Image is too large (max {settings.max_upload_mb}MB)."}.get(
            res.get("error"), "Couldn't process that image.")
        return _page("Upload a flyer", f"<h2 class='err'>{esc(msg)}</h2>"
                     "<p><a href='/portal/flyer'>‹ try again</a></p>", status=400)
    return RedirectResponse(f"/portal/flyer/{res['id']}/review", status_code=303)


def _flyer_field(label: str, name: str, value: str, ph: str = "", input_type: str = "text") -> str:
    return (f"<label>{esc(label)}</label>"
            f"<input type='{input_type}' name='{name}' value='{esc(value)}' placeholder='{esc(ph)}'>")


def flyer_review_get(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    upload = flyer.get_upload(int(request.path_params["id"]), email)
    if upload is None:
        return _page("Not found", "<h2>Flyer not found</h2>", status=404)
    ex = upload.get("extracted") or {}
    opts = "".join(
        f"<option value='{k}'{' selected' if k == upload.get('vertical_guess') else ''}>{esc(lbl)}</option>"
        for k, lbl in _FLYER_VERTICAL_OPTS)
    img = (f"<img src='/uploads/{esc(upload['image_path'])}' alt='' style='width:100%;max-height:280px;"
          f"object-fit:cover;border-radius:12px;margin:6px 0'>")
    note = ("<p class='muted'>We couldn't automatically read this image — please fill in the details "
            "below.</p>" if upload.get("error") else
            "<p class='muted'>Here's what we read from your flyer — check it, fix anything, then submit.</p>")
    body = (f"<h2>Review your flyer</h2>{note}{img}"
            f"<form method='post' action='/portal/flyer/{upload['id']}/confirm'>"
            f"<label>Category</label><select name='vertical'>{opts}</select>"
            + _flyer_field("Name / event title", "name", ex.get("name") or "")
            + _flyer_field("Description", "description", ex.get("description") or "")
            + "<fieldset style='border:1px solid #e2e0dd;border-radius:10px;padding:10px 14px;margin:14px 0'>"
            "<legend style='font-size:13px;color:#6b7280'>Events only</legend>"
            + _flyer_field("Start date", "start_date", ex.get("start_date") or "", input_type="date")
            + _flyer_field("Start time", "start_time", ex.get("start_time") or "", input_type="time")
            + _flyer_field("End date", "end_date", ex.get("end_date") or "", input_type="date")
            + _flyer_field("Venue", "venue_name", ex.get("venue_name") or "")
            + _flyer_field("Organizer", "organizer", ex.get("organizer") or "")
            + _flyer_field("Event category", "category", ex.get("category") or "")
            + "</fieldset>"
            + _flyer_field("Address", "address_full", ex.get("address_full") or "")
            + _flyer_field("City", "city", ex.get("city") or "")
            + f"<label>State</label>{state_select('state', ex.get('state') or '')}"
            + _flyer_field("Phone", "phone", ex.get("phone") or "")
            + _flyer_field("Website", "website", ex.get("website") or "")
            + _flyer_field("Contact email (events only)", "email", ex.get("email") or "")
            + "<button type='submit'>Submit for review</button></form>"
            "<p class='muted' style='margin-top:12px'><a href='/portal/flyer'>‹ back</a></p>")
    return _page("Review your flyer", body)


async def flyer_confirm_post(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    upload_id = int(request.path_params["id"])
    upload = flyer.get_upload(upload_id, email)
    if upload is None:
        return _page("Not found", "<h2>Flyer not found</h2>", status=404)
    form = await request.form()
    vertical = (form.get("vertical") or "").strip()
    valid = {k for k, _ in _FLYER_VERTICAL_OPTS}
    if vertical not in valid:
        return _page("Review your flyer", "<h2 class='err'>Please pick a category</h2>"
                     f"<p><a href='/portal/flyer/{upload_id}/review'>‹ back</a></p>", status=400)
    name = (form.get("name") or "").strip()
    if not name:
        return _page("Review your flyer", "<h2 class='err'>Please enter a name / event title</h2>"
                     f"<p><a href='/portal/flyer/{upload_id}/review'>‹ back</a></p>", status=400)

    if vertical == "events":
        start_date = (form.get("start_date") or "").strip()
        if not start_date:
            return _page("Review your flyer", "<h2 class='err'>Please enter a start date for the event</h2>"
                         f"<p><a href='/portal/flyer/{upload_id}/review'>‹ back</a></p>", status=400)
        start_time = (form.get("start_time") or "").strip() or "00:00"
        end_date = (form.get("end_date") or "").strip()
        rec = {
            "name": name, "venue_name": (form.get("venue_name") or "").strip() or None,
            "address_full": (form.get("address_full") or "").strip() or None,
            "city": (form.get("city") or "").strip() or None,
            "state": (form.get("state") or "").strip() or None,
            "phone": (form.get("phone") or "").strip() or None,
            "email": (form.get("email") or "").strip() or None,
            "website": (form.get("website") or "").strip() or None,
            "organizer": (form.get("organizer") or "").strip() or None,
            "category": (form.get("category") or "").strip() or None,
            "start_at": f"{start_date}T{start_time}",
            "end_at": f"{end_date}T{start_time}" if end_date else None,
            "festival_specials": (form.get("description") or "").strip()[:500] or None,
        }
        res = events.submit_flyer_event(rec)
        if not res.get("ok"):
            msg = {"missing_required_fields": "Please enter a name and start date.",
                  "duplicate_event": "This event looks like a duplicate of one already listed."}.get(
                res.get("error"), "Couldn't submit this event.")
            return _page("Review your flyer", f"<h2 class='err'>{esc(msg)}</h2>"
                         f"<p><a href='/portal/flyer/{upload_id}/review'>‹ back</a></p>", status=400)
        flyer.mark_submitted(upload_id, event_id=res["id"])
    else:
        payload = {"name": name, "address_full": (form.get("address_full") or "").strip(),
                  "city": (form.get("city") or "").strip(), "state": (form.get("state") or "").strip(),
                  "phone": (form.get("phone") or "").strip(), "website": (form.get("website") or "").strip()}
        desc = (form.get("description") or "").strip()
        if desc:
            payload["description"] = desc
        res = submissions.submit(vertical, payload, contact_email=email, note="flyer upload")
        if not res.get("ok"):
            return _page("Review your flyer", "<h2 class='err'>Couldn't submit — please check the "
                         "category and name</h2>"
                         f"<p><a href='/portal/flyer/{upload_id}/review'>‹ back</a></p>", status=400)
        flyer.mark_submitted(upload_id, submission_id=res["id"])
    return RedirectResponse("/portal/flyer?added=1", status_code=303)


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
    Route("/portal/flyer", flyer_get, methods=["GET"]),
    Route("/portal/flyer", flyer_post, methods=["POST"]),
    Route("/portal/flyer/{id:int}/review", flyer_review_get, methods=["GET"]),
    Route("/portal/flyer/{id:int}/confirm", flyer_confirm_post, methods=["POST"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_get, methods=["GET"]),
    Route("/portal/edit/{vertical}/{id:int}", edit_post, methods=["POST"]),
    Route("/portal/listing/{vertical}/{id:int}", listing_manage, methods=["GET"]),
    Route("/portal/listing/{vertical}/{id:int}/offer", offer_create, methods=["POST"]),
    Route("/portal/listing/{vertical}/{id:int}/offer/{post_id:int}/delete", offer_delete, methods=["POST"]),
    Route("/portal/listing/{vertical}/{id:int}/reply", review_reply, methods=["POST"]),
    Route("/portal/logout", logout, methods=["GET"]),
]
