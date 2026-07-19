"""Consumer account hub (/me): saved places, followed cities/categories, and personalization
preferences. Same login/session as the business portal (session 'owner_email'); see accounts.py.
This is the foundation the personalized "Today" feed + digests build on."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

import json

from .. import accounts, verticals, webpush
from ..config import settings
from .auth import portal_email, verify_action_token
from .common import _page, esc, share_html, state_select


def _safe_next(raw: str | None, fallback: str = "/me") -> str:
    """Only allow same-site relative redirects (no open-redirect via //host or scheme)."""
    n = (raw or "").strip()
    return n if n.startswith("/") and not n.startswith("//") else fallback


def me_home(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/me/login", status_code=303)
    prof = accounts.get_profile(email) or {}
    saved = accounts.list_saved(email)
    follows = accounts.list_follows(email)

    saved_html = "".join(
        f"<div class='lc'><a href='/listing/{s['vertical']}/{s['id']}'>{esc(s['name'])}</a> "
        f"<span class='muted'>· {esc(verticals.VERTICALS[s['vertical']]['label'])}"
        + (f" · {esc(s['city'])}, {esc(s['state'])}" if s.get('city') else "") + "</span> "
        f"<form method='post' action='/me/unsave' style='display:inline'>"
        f"<input type='hidden' name='vertical' value='{s['vertical']}'>"
        f"<input type='hidden' name='id' value='{s['id']}'>"
        f"<button class='linkbtn' title='Remove'>✕</button></form></div>"
        for s in saved)
    saved_block = (f"<h3>♥ Saved places ({len(saved)})</h3>" + (saved_html or
                   "<p class='muted'>Nothing saved yet — tap ♡ Save on any listing.</p>"))

    cities = [f for f in follows if f["kind"] == "city"]
    city_html = "".join(
        f"<span class='pill'>{esc(c['value'])} "
        f"<form method='post' action='/me/unfollow' style='display:inline'>"
        f"<input type='hidden' name='kind' value='city'><input type='hidden' name='value' value=\"{esc(c['value'])}\">"
        f"<button class='linkbtn'>✕</button></form></span>" for c in cities)
    follow_block = (
        "<h3 style='margin-top:22px'>📍 Cities you follow</h3>"
        f"<div class='pills'>{city_html or '<span class=muted>None yet.</span>'}</div>"
        "<form method='post' action='/me/follow' style='display:flex;gap:8px;margin-top:8px'>"
        "<input type='hidden' name='kind' value='city'>"
        "<input name='value' placeholder='e.g. Plano, TX' style='flex:1'>"
        "<button type='submit'>Follow city</button></form>")

    langs = ", ".join(prof.get("languages") or [])
    fvs = set(prof.get("followed_verticals") or [])
    vchecks = "".join(
        f"<label style='font-weight:400;display:inline-flex;gap:6px;align-items:center;margin:2px 10px 2px 0'>"
        f"<input type='checkbox' name='followed_verticals' value='{k}'{' checked' if k in fvs else ''} "
        f"style='width:auto'> {esc(cfg['label'])}</label>"
        for k, cfg in verticals.VERTICALS.items() if k != "events")
    freq = prof.get("digest_freq") or "weekly"
    freq_opts = "".join(f"<option value='{f}'{' selected' if f == freq else ''}>{f.title()}</option>"
                        for f in ("weekly", "daily", "off"))
    prefs = (
        "<h3 style='margin-top:22px'>⚙ Your preferences</h3>"
        "<form method='post' action='/me/prefs'>"
        f"<label>Display name</label><input name='display_name' value='{esc(prof.get('display_name'))}'>"
        f"<label>Home city</label><input name='home_city' value='{esc(prof.get('home_city'))}' placeholder='e.g. Plano'>"
        f"<label>Home state</label>{state_select('home_state', prof.get('home_state') or '')}"
        f"<label>Languages you speak (comma-separated)</label>"
        f"<input name='languages' value='{esc(langs)}' placeholder='Telugu, Hindi, English'>"
        "<label>Categories you care about</label>"
        f"<div style='margin:6px 0 12px'>{vchecks}</div>"
        "<label style='font-weight:400;display:flex;gap:8px;align-items:center'>"
        f"<input type='checkbox' name='notify_email' value='1'{' checked' if prof.get('notify_email', True) else ''} "
        "style='width:auto'> Email me a digest</label>"
        f"<label>Digest frequency</label><select name='digest_freq'>{freq_opts}</select>"
        "<button type='submit' style='margin-top:12px'>Save preferences</button></form>")

    st = accounts.contributor_stats(email)
    contrib = ""
    if st["tier"]:
        contrib = (
            "<div style='background:#fff7ef;border:1px solid #ffe0c2;border-radius:14px;padding:14px 16px;margin:12px 0'>"
            f"<b>{esc(st['tier'])}</b> · {st['points']} pts "
            f"<span class='muted'>· you've helped others find "
            f"{st['added'] + st['flyers']} place{'s' if (st['added'] + st['flyers']) != 1 else ''}</span>"
            f"<div class='muted' style='font-size:13px;margin-top:4px'>"
            f"{st['added']} added · {st['flyers']} flyers · {st['reviews']} reviews · "
            f"{st['asked']} asked · {st['answered']} answered"
            + (f" · {st['pending']} pending review" if st['pending'] else "") + "</div></div>")
    else:
        contrib = ("<div style='background:#fff7ef;border:1px solid #ffe0c2;border-radius:14px;padding:14px 16px;margin:12px 0'>"
                   "<b>🌱 Start contributing</b> <span class='muted'>— add a place or write a review to help "
                   "the community and earn contributor status.</span> "
                   "<a href='/submit'>Add a place →</a></div>")

    push_block = ""
    if settings.web_push_enabled:
        push_block = (
            "<div style='margin:10px 0'>"
            "<button id='pushbtn' type='button' style='display:inline-block;border:1px solid #b8e6df;"
            "background:#e7f6f4;color:#0c7e74;border-radius:999px;padding:6px 15px;font-size:13px;"
            "font-weight:600;cursor:pointer'>🔔 Enable notifications</button> "
            "<span id='pushmsg' class='muted' style='font-size:13px'></span></div>"
            "<script>(function(){var KEY=" + json.dumps(settings.vapid_public_key) + ";"
            "var b=document.getElementById('pushbtn'),m=document.getElementById('pushmsg');"
            "if(!('serviceWorker'in navigator)||!('PushManager'in window)){if(b)b.style.display='none';return;}"
            "function u2a(s){var p='='.repeat((4-s.length%4)%4);var x=(s+p).replace(/-/g,'+').replace(/_/g,'/');"
            "var r=atob(x),a=new Uint8Array(r.length);for(var i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a;}"
            "navigator.serviceWorker.ready.then(function(reg){reg.pushManager.getSubscription().then(function(s){"
            "if(s){b.textContent='🔔 Notifications on';b.disabled=true;}})});"
            "b.addEventListener('click',function(){Notification.requestPermission().then(function(perm){"
            "if(perm!=='granted'){m.textContent='Permission blocked in your browser.';return;}"
            "navigator.serviceWorker.ready.then(function(reg){reg.pushManager.subscribe({userVisibleOnly:true,"
            "applicationServerKey:u2a(KEY)}).then(function(sub){fetch('/push/subscribe',{method:'POST',"
            "headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:sub})}).then(function(){"
            "b.textContent='🔔 Notifications on';b.disabled=true;})}).catch(function(){"
            "m.textContent='Could not enable — try again.';})})})});})();</script>")

    code = accounts.ensure_referral_code(email)
    invite = f"{settings.public_web_url.rstrip('/')}/portal/register?ref={code}"
    joined = accounts.referral_count(email)
    referral = (
        "<div style='background:#e7f6f4;border:1px solid #b8e6df;border-radius:14px;padding:14px 16px;margin:12px 0'>"
        "<b>🎁 Invite friends</b> <span class='muted'>— share Namaste America with your community"
        + (f"; <b>{joined}</b> joined via you so far" if joined else "") + ".</span>"
        f"<div style='margin:8px 0 0'>{share_html(invite, 'Join me on Namaste America — the guide to Indian America')}</div></div>")

    body = (f"<h2>Welcome{', ' + esc(prof.get('display_name')) if prof.get('display_name') else ''}! 🙏</h2>"
            f"<p class='muted'>{esc(email)} · <a href='/portal'>your business listings</a> · "
            "<a href='/portal/logout'>sign out</a></p>"
            + (f"<div class='ok' style='background:#e7f6ec;border-radius:10px;padding:10px 13px;margin:10px 0'>✓ Saved.</div>"
               if request.query_params.get("ok") else "")
            + contrib + referral + push_block + saved_block + follow_block + prefs)
    return _page("Your account", body)


async def push_subscribe(request: Request) -> JSONResponse:
    email = portal_email(request)
    if not email:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        sub = (await request.json()).get("subscription")
    except Exception:
        sub = None
    return JSONResponse({"ok": bool(sub and webpush.subscribe(email, sub))})


async def push_unsubscribe(request: Request) -> JSONResponse:
    try:
        endpoint = (await request.json()).get("endpoint")
    except Exception:
        endpoint = None
    if endpoint:
        webpush.unsubscribe(endpoint)
    return JSONResponse({"ok": True})


def me_login(request: Request) -> RedirectResponse:
    # Consumers use the same auth as owners; bounce through the existing login, returning to /me.
    return RedirectResponse("/portal/login", status_code=303)


async def prefs_post(request: Request) -> RedirectResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/me/login", status_code=303)
    form = await request.form()
    langs = [s.strip() for s in (form.get("languages") or "").split(",") if s.strip()]
    accounts.upsert_profile(
        email,
        display_name=form.get("display_name"),
        home_city=form.get("home_city"),
        home_state=form.get("home_state"),
        languages=langs,
        followed_verticals=form.getlist("followed_verticals"),
        notify_email=bool(form.get("notify_email")),
        digest_freq=(form.get("digest_freq") or "weekly"),
    )
    return RedirectResponse("/me?ok=1", status_code=303)


async def save_post(request: Request) -> RedirectResponse | JSONResponse:
    email = portal_email(request)
    form = await request.form()
    nxt = _safe_next(form.get("next"))
    if not email:
        return RedirectResponse("/me/login", status_code=303)
    try:
        accounts.save_place(email, (form.get("vertical") or "").strip(), int(form.get("id") or 0))
    except (ValueError, TypeError):
        pass
    return RedirectResponse(nxt, status_code=303)


async def unsave_post(request: Request) -> RedirectResponse:
    email = portal_email(request)
    form = await request.form()
    nxt = _safe_next(form.get("next"))
    if email:
        try:
            accounts.unsave_place(email, (form.get("vertical") or "").strip(), int(form.get("id") or 0))
        except (ValueError, TypeError):
            pass
    return RedirectResponse(nxt, status_code=303)


async def follow_post(request: Request) -> RedirectResponse:
    email = portal_email(request)
    form = await request.form()
    if email:
        accounts.follow(email, (form.get("kind") or "").strip(), form.get("value") or "")
    return RedirectResponse("/me", status_code=303)


async def unfollow_post(request: Request) -> RedirectResponse:
    email = portal_email(request)
    form = await request.form()
    if email:
        accounts.unfollow(email, (form.get("kind") or "").strip(), form.get("value") or "")
    return RedirectResponse("/me", status_code=303)


def unsubscribe(request: Request) -> HTMLResponse:
    """One-click email-digest unsubscribe from a signed token (no login needed; RFC 8058 target)."""
    email = verify_action_token(request.query_params.get("t", ""), "digest_unsub")
    if not email:
        return _page("Unsubscribe", "<h2 class='err'>This unsubscribe link is invalid or expired.</h2>"
                     "<p>Manage your preferences from <a href='/me'>your account</a>.</p>", status=400)
    accounts.set_notify_email(email, False)
    return _page("Unsubscribed", "<h2 class='ok'>✓ You're unsubscribed</h2>"
                 f"<p>{esc(email)} will no longer get the daily digest. Changed your mind? "
                 "<a href='/me'>Turn it back on</a> anytime.</p>")


async def unsubscribe_post(request: Request) -> HTMLResponse:
    return unsubscribe(request)   # RFC 8058 one-click POSTs to the same URL


routes = [
    Route("/me", me_home, methods=["GET"]),
    Route("/me/login", me_login, methods=["GET"]),
    Route("/me/unsubscribe", unsubscribe, methods=["GET"]),
    Route("/me/unsubscribe", unsubscribe_post, methods=["POST"]),
    Route("/push/subscribe", push_subscribe, methods=["POST"]),
    Route("/push/unsubscribe", push_unsubscribe, methods=["POST"]),
    Route("/me/prefs", prefs_post, methods=["POST"]),
    Route("/me/save", save_post, methods=["POST"]),
    Route("/me/unsave", unsave_post, methods=["POST"]),
    Route("/me/follow", follow_post, methods=["POST"]),
    Route("/me/unfollow", unfollow_post, methods=["POST"]),
]
