"""Public per-listing detail page + community review submission.

  GET  /listing/<vertical>/<id>          -> full listing details, community + web ratings, the
                                            published reviews, and a "Write a review" form.
  POST /listing/<vertical>/<id>/review   -> honeypot + captcha + per-IP rate-limit & daily dedupe,
                                            then reviews.submit (auto-publish clean / hold flagged).

Reuses landing._page (public shell + JSON-LD), common.captcha_field, auth.verify_captcha and the
honeypot pattern from the contact/submission forms. No email is shown anywhere.
"""

from __future__ import annotations

import html
import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import accounts, db, reviews as reviews_mod, tags as tagsmod, verticals
from ..config import settings
from . import i18n, seo
from .auth import portal_email, verify_captcha
from .common import captcha_field
from .landing import _FEATURED, _cathead, _label, _page

_CSS = """<style>
.lh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:2px 0 4px}
.lh .rate{color:#b45309;font-weight:600}.lh .muted{font-size:14px}
.lmeta{color:#4b5563;margin:6px 0}.lmeta a{font-weight:600}
.banner{background:#fff;border:1px solid #cfe6e0;border-left:4px solid #0f9b8e;border-radius:10px;
 padding:12px 14px;margin:12px 0;font-weight:600}.banner.ok{border-left-color:#137333;color:#137333}
.langs{color:#0f766e;font-weight:600;margin:8px 0}
.feats{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.fchip{background:#f3efe9;border:1px solid #e7e0d6;border-radius:999px;padding:4px 11px;font-size:13px;color:#5b6470}
.rev{background:#fff;border:1px solid #ececec;border-radius:12px;padding:13px 15px;margin:10px 0}
.rev .rstars{color:#f5a623;font-size:17px;letter-spacing:1px}
.rev .rbody{margin:5px 0;color:#26303a}.rev .meta{color:#6b7280;font-size:13px}
.rform{background:#fff;border:1px solid #ececec;border-radius:14px;padding:16px 18px;margin:14px 0}
.rform label{display:block;font-weight:600;font-size:14px;margin:12px 0 4px;color:#3a4654}
.rform textarea,.rform input[type=text]{width:100%;padding:11px 12px;border:1.5px solid #e3ddd3;
 border-radius:11px;font:inherit;font-size:15px;background:#fff}
.rform textarea:focus,.rform input[type=text]:focus{outline:0;border-color:#e8772e;box-shadow:0 0 0 4px #e8772e22}
.rform .hp{position:absolute;left:-9999px}
.rform button{margin-top:14px;background:#c1440e;color:#fff;border:0;padding:12px 22px;border-radius:11px;
 font-size:15px;font-weight:600;cursor:pointer}.rform button:hover{filter:brightness(1.05)}
.stars{display:inline-flex;flex-direction:row-reverse;border:0;padding:0;margin:4px 0;gap:3px}
.stars input{position:absolute;left:-9999px}
.stars label{font-size:32px;color:#d8d8d8;cursor:pointer;line-height:1}
.stars input:checked~label,.stars label:hover,.stars label:hover~label{color:#f5a623}
</style>"""


def _fetch(vertical: str, listing_id: int) -> dict | None:
    table = verticals._table(vertical)
    # Vertical-specific facet columns (cuisine_type, religion, ...) if present -- needed for the
    # data-derived meta-description clause (seo.primary_facet); not in the base generic column list.
    facet_cols = seo.facet_select_cols(verticals._table_columns(table))
    facet_sel = ("," + ",".join(facet_cols)) if facet_cols else ""
    return db.query_one(
        f"SELECT id, name, address_full, city, state, lat, lng, phone, email, website, description, "
        f"tags, languages, is_claimed, rating, rating_count, community_rating, community_rating_count, "
        f"photo_url{facet_sel}, updated_at, {_FEATURED} AS is_featured FROM {table} "
        f"WHERE id = %s AND deleted_at IS NULL AND is_active", [listing_id])


_COMPLETE_FIELDS = ("phone", "email", "website", "address_full", "lat", "photo_url",
                    "description", "languages")


def _trust_html(r: dict) -> str:
    """A small trust/freshness line: profile completeness + last-updated month + edit CTA."""
    have = sum(1 for f in _COMPLETE_FIELDS if r.get(f) not in (None, "", []))
    pct = round(100 * have / len(_COMPLETE_FIELDS))
    parts = [f"<span class='muted'>{pct}% complete</span>"]
    upd = r.get("updated_at")
    if hasattr(upd, "strftime"):
        parts.append(f"<span class='muted'>Updated {upd.strftime('%b %Y')}</span>")
    parts.append("<a href='#suggest'>Suggest an edit</a>")
    return "<p class='lmeta' style='font-size:13px'>" + " &nbsp;·&nbsp; ".join(parts) + "</p>"


def _suggest_form(vertical: str, listing_id: int) -> str:
    return (
        f"<details id='suggest' style='margin-top:24px'>"
        f"<summary style='cursor:pointer;font-weight:600;color:#c1440e'>✎ Suggest an edit</summary>"
        f"<form class='rform' method='post' action='/listing/{vertical}/{listing_id}/suggest'>"
        "<p class='muted' style='margin:6px 0 4px'>Spot something wrong or missing — wrong phone, "
        "closed, moved, hours? Tell us and we'll review it.</p>"
        "<input class='hp' type='text' name='website' tabindex='-1' autocomplete='off' aria-hidden='true'>"
        "<label>What should we fix?</label>"
        "<textarea name='body' rows='3' maxlength='2000' required "
        "placeholder='e.g. The phone number is wrong; new hours are 11am-9pm.'></textarea>"
        "<label>Your email <span style='font-weight:400;color:#6b7280'>(optional, if we need to follow up)</span></label>"
        "<input type='text' name='email' maxlength='200' placeholder='you@example.com'>"
        f"{captcha_field()}"
        "<button type='submit'>Send suggestion</button></form></details>")


def _features_html(r: dict) -> str:
    feats = tagsmod.for_display(r.get("tags"), limit=10)
    if not feats:
        return ""
    chips = "".join(f"<span class='fchip'>{html.escape(f)}</span>" for f in feats)
    return f"<div class='feats'>{chips}</div>"


def _ratings_html(r: dict, tr: dict) -> str:
    parts = []
    cr, crc = r.get("community_rating"), r.get("community_rating_count") or 0
    if cr:
        parts.append(f"<span class='rate'>★ {cr:.1f} ({crc} {html.escape(tr['community'])})</span>")
    if r.get("rating"):
        rc = r.get("rating_count")
        parts.append("<span class='muted'>★ " + html.escape(str(r["rating"]))
                     + (f" ({rc})" if rc else "") + f" {html.escape(tr['from_web'])}</span>")
    return " &nbsp;·&nbsp; ".join(parts)


def _reviews_html(items: list[dict], tr: dict) -> str:
    if not items:
        return f"<p class='muted'>{html.escape(tr['no_reviews'])}</p>"
    out = []
    for r in items:
        n = int(r["rating"])
        stars = "★" * n + "☆" * (5 - n)
        who = html.escape(r.get("author_name") or "Anonymous")
        when = (r["created_at"].strftime("%b %d, %Y")
                if hasattr(r.get("created_at"), "strftime") else "")
        title = f"<b>{html.escape(r['title'])}</b><br>" if r.get("title") else ""
        body = html.escape(r.get("body") or "")
        out.append(
            f"<div class='rev'><div class='rstars' aria-label='{n} out of 5'>{stars}</div>"
            f"<div class='rbody'>{title}{body}</div>"
            f"<div class='meta'>— {who}{(' · ' + when) if when else ''}</div></div>")
    return "".join(out)


def _form_html(vertical: str, listing_id: int, tr: dict) -> str:
    stars = "".join(
        f"<input type='radio' id='star{i}' name='rating' value='{i}' required>"
        f"<label for='star{i}' aria-label='{i} star{'s' if i != 1 else ''}'>★</label>"
        for i in (5, 4, 3, 2, 1))
    opt = html.escape(tr["optional"])
    return (
        f"<h2 style='margin-top:26px'>{html.escape(tr['write_review'])}</h2>"
        f"<form class='rform' method='post' action='/listing/{vertical}/{listing_id}/review'>"
        "<input class='hp' type='text' name='website' tabindex='-1' autocomplete='off' aria-hidden='true'>"
        f"<label>{html.escape(tr['your_rating'])}</label>"
        f"<fieldset class='stars'>{stars}</fieldset>"
        f"<label>{html.escape(tr['your_review'])} <span style='font-weight:400;color:#6b7280'>({opt})</span></label>"
        f"<textarea name='body' rows='4' maxlength='2000' placeholder='{html.escape(tr['review_placeholder'])}'></textarea>"
        f"<label>{html.escape(tr['your_name'])} <span style='font-weight:400;color:#6b7280'>({opt})</span></label>"
        "<input type='text' name='name' maxlength='120' placeholder='Anonymous'>"
        f"{captcha_field()}"
        f"<button type='submit'>{html.escape(tr['submit_review'])}</button>"
        f"<p class='muted' style='font-size:12.5px;margin-top:10px'>{html.escape(tr['review_note'])}</p></form>")


def _jsonld(vertical: str, r: dict, items: list[dict]) -> str:
    biz: dict = {"@context": "https://schema.org", "@type": seo.schema_type(vertical), "name": r["name"],
                 "address": {"@type": "PostalAddress", "addressLocality": r.get("city"),
                             "addressRegion": r.get("state"), "streetAddress": r.get("address_full")}}
    if r.get("phone"):
        biz["telephone"] = r["phone"]
    if r.get("website"):
        biz["url"] = r["website"]
    if r.get("photo_url"):
        biz["image"] = r["photo_url"]
    if r.get("lat") and r.get("lng"):
        biz["geo"] = {"@type": "GeoCoordinates", "latitude": r["lat"], "longitude": r["lng"]}
    if r.get("community_rating"):
        biz["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": round(r["community_rating"], 1),
                                  "reviewCount": r.get("community_rating_count") or len(items),
                                  "bestRating": 5, "worstRating": 1}
    if items:
        biz["review"] = [{
            "@type": "Review",
            "reviewRating": {"@type": "Rating", "ratingValue": int(x["rating"]),
                             "bestRating": 5, "worstRating": 1},
            "author": {"@type": "Person", "name": x.get("author_name") or "Anonymous"},
            **({"reviewBody": x["body"]} if x.get("body") else {}),
        } for x in items[:20]]
    return json.dumps(biz, ensure_ascii=False, default=str)


_SAVE_CSS = ("display:inline-block;border:1.5px solid #e57373;border-radius:999px;padding:5px 14px;"
             "font-size:14px;font-weight:600;text-decoration:none;cursor:pointer;background:#fff;color:#c5221f")


_SENTIMENT_LABEL = {"positive": "😊 Mostly positive", "mixed": "😐 Mixed reviews",
                    "negative": "😕 Mixed-to-negative"}


def _aspects_html(ai: dict) -> str:
    """Structured 'what people mention' chips + overall sentiment, grounded in real reviews (Phase 4)."""
    aspects = ai.get("aspects") or []
    if not aspects:
        return ""
    chips = "".join(f"<span class='fchip'>{html.escape(a)}</span>" for a in aspects)
    sent = _SENTIMENT_LABEL.get(ai.get("sentiment"), "")
    tag = f"<span class='muted' style='font-size:13px;margin-left:4px'>· {sent}</span>" if sent else ""
    return (f"<div class='feats' style='margin:6px 0 2px'>"
            f"<span class='muted' style='font-size:13px;margin-right:2px'>What people mention:</span>"
            f"{chips}{tag}</div>")


def _save_button(request: Request, v: str, listing_id: int) -> str:
    """♡ Save / ♥ Saved toggle. Anonymous visitors get a link to sign in first. No-JS (form POST +
    redirect back), so it works everywhere."""
    email = portal_email(request)
    back = f"/listing/{v}/{listing_id}"
    if not email:
        return (f"<a href='/portal/login' style='{_SAVE_CSS}' title='Sign in to save'>♡ Save</a>")
    hidden = (f"<input type='hidden' name='vertical' value='{v}'>"
              f"<input type='hidden' name='id' value='{listing_id}'>"
              f"<input type='hidden' name='next' value='{html.escape(back)}'>")
    if accounts.is_saved(email, v, listing_id):
        return (f"<form method='post' action='/me/unsave' style='display:inline'>{hidden}"
                f"<button style='{_SAVE_CSS};background:#c5221f;color:#fff'>♥ Saved</button></form>")
    return (f"<form method='post' action='/me/save' style='display:inline'>{hidden}"
            f"<button style='{_SAVE_CSS}'>♡ Save</button></form>")


def listing_page(request: Request) -> HTMLResponse:
    v = request.path_params["vertical"]
    if v == "events":                          # events are date-based + agent-managed -> calendar
        return RedirectResponse("/events", status_code=307)
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    try:
        listing_id = int(request.path_params["id"])
    except (ValueError, TypeError):
        return _page("Not found", "Unknown listing.", "<h1>Not found</h1>", status=404)
    r = _fetch(v, listing_id)
    if not r:
        return _page("Listing not found", "This listing isn't available.",
                     "<h1>Listing not found</h1><p class='muted'>It may have been removed. "
                     "<a href='/browse'>Browse the directory</a> or "
                     "<a href='/chat'>ask the assistant</a>.</p>", status=404)

    items = reviews_mod.list_for_listing(v, listing_id, limit=30)
    tr = i18n.t(request)                                    # UI labels in the visitor's language
    try:                                                   # LLM-polished description + review gist
        from .. import enrich_llm
        ai = enrich_llm.get(v, listing_id) or {}
    except Exception:
        ai = {}
    loc = ", ".join(x for x in (r.get("city"), (r["state"].upper() if r.get("state") else None)) if x)
    addr = r.get("address_full") or loc
    label = _label(v)
    ratings = _ratings_html(r, tr)
    links = " &nbsp;·&nbsp; ".join(x for x in (
        (f"<a href='{html.escape(r['website'])}' rel='nofollow'>Website</a>" if r.get("website") else ""),
        (f"<a href='tel:{html.escape(r['phone'])}'>{html.escape(r['phone'])}</a>" if r.get("phone") else ""),
    ) if x)
    verified = (f" <span style='color:#1565c0;font-weight:600'>✓ {html.escape(tr['owner_verified'])}</span>"
                if r.get("is_claimed") else "")

    ok = request.query_params.get("ok")
    banner = ""
    if ok == "published":
        banner = f"<div class='banner ok'>✓ {html.escape(tr['review_live'])}</div>"
    elif ok == "pending":
        banner = f"<div class='banner'>✓ {html.escape(tr['review_pending'])}</div>"
    elif ok == "suggest":
        banner = "<div class='banner ok'>✓ Thanks — we'll review your suggestion.</div>"

    body = (
        _CSS
        + f"<nav class='crumbs'><a href='/browse'>{html.escape(tr['browse'])}</a> › "
        + f"<a href='/browse/{v}'>{html.escape(label)}</a> › {html.escape(r['name'])}</nav>"
        + _cathead(v)
        + banner
        + f"<h1>{html.escape(r['name'])}{verified}</h1>"
        + f"<p style='margin:6px 0 10px'>{_save_button(request, v, listing_id)}</p>"
        + (f"<img src='{html.escape(r['photo_url'])}' alt='{html.escape(r['name'])}' loading='lazy' "
           f"onerror='this.remove()' style='width:100%;max-height:300px;object-fit:cover;"
           f"border-radius:14px;margin:8px 0'>" if r.get("photo_url") else "")
        + (f"<div class='lh'>{ratings}</div>" if ratings else "")
        + (f"<p class='lmeta'>📍 {html.escape(addr)}</p>" if addr else "")
        + (f"<p class='lmeta'>{links}</p>" if links else "")
        + _trust_html(r)
        + (f"<p>{html.escape(ai.get('description') or r.get('description') or '')}</p>"
           if (ai.get("description") or r.get("description")) else "")
        + (f"<p class='langs'>🗣 {html.escape(tr['speaks'])}: {html.escape(', '.join(r['languages']))}</p>"
           if r.get("languages") else "")
        + _features_html(r)
        + f"<h2 style='margin-top:26px'>{html.escape(tr['community_reviews'])}</h2>"
        + (f"<div class='banner'>💬 {html.escape(ai['review_summary'])}</div>"
           if ai.get("review_summary") else "")
        + _aspects_html(ai)
        + _reviews_html(items, tr)
        + _form_html(v, listing_id, tr)
        + _suggest_form(v, listing_id))
    facet = seo.primary_facet(r)
    # NOT pre-escaped: _page() html.escape()s the whole `desc` string once, same as the rest of it.
    facet_clause = f" {facet}." if facet else ""
    desc = (f"{r['name']} — Indian {label} in {loc}.{facet_clause} Read community reviews and ratings, "
            "contact details, and share your own experience.")
    return _page(f"{r['name']} · {label} · {settings.platform_name}", desc, body,
                 jsonld=_jsonld(v, r, items), canonical=f"{settings.public_web_url.rstrip('/')}/listing/{v}/{listing_id}",
                 image=r.get("photo_url") or "")


def _err(vertical: str, listing_id: int, msg: str) -> HTMLResponse:
    return _page("Review", msg,
                 f"<h1 class='err' style='color:#c5221f'>{html.escape(msg)}</h1>"
                 f"<p><a href='/listing/{vertical}/{listing_id}'>&#8592; Back to the listing</a></p>",
                 status=400)


async def review_post(request: Request) -> HTMLResponse:
    v = request.path_params["vertical"]
    try:
        listing_id = int(request.path_params["id"])
    except (ValueError, TypeError):
        return _page("Not found", "Unknown listing.", "<h1>Not found</h1>", status=404)
    if v not in reviews_mod.REVIEWABLE or reviews_mod._listing(v, listing_id) is None:
        return _page("Listing not found", "This listing isn't available.",
                     "<h1>Listing not found</h1>", status=404)

    form = await request.form()
    if (form.get("website") or "").strip():        # honeypot: bots fill it -> silently accept
        return RedirectResponse(f"/listing/{v}/{listing_id}?ok=pending", status_code=303)
    if not (form.get("rating") or "").strip():
        return _err(v, listing_id, "Please choose a star rating (1 to 5).")
    if not verify_captcha(form):
        return _err(v, listing_id, "The captcha answer was incorrect.")

    ip = request.client.host if request.client else None
    if ip and reviews_mod.recent_for_ip(ip, listing_id) >= 1:
        return _err(v, listing_id, "You've already reviewed this listing — thank you!")
    if ip and reviews_mod.ip_count_today(ip) >= settings.reviews_per_ip_per_day:
        return _err(v, listing_id, "You've submitted several reviews today. Please try again tomorrow.")

    res = reviews_mod.submit(v, listing_id, form.get("rating"), body=form.get("body") or "",
                             name=form.get("name") or "", ip=ip, source="web")
    if not res.get("ok"):
        msg = {"bad_rating": "Please choose a rating from 1 to 5 stars.",
               "reviews_disabled": "Reviews are currently turned off.",
               "listing_not_found": "This listing isn't available."}.get(
                   res.get("error"), "Sorry, we couldn't save your review. Please try again.")
        return _err(v, listing_id, msg)
    return RedirectResponse(f"/listing/{v}/{listing_id}?ok={res['status']}", status_code=303)


async def suggest_post(request: Request) -> HTMLResponse:
    """Crowdsourced correction -> the admin inbox (Admin → Messages). Same honeypot + captcha as the
    contact/review forms. Reuses inbox.create_message so it needs no new table or moderation flow."""
    from .. import inbox
    v = request.path_params["vertical"]
    try:
        listing_id = int(request.path_params["id"])
    except (ValueError, TypeError):
        return _page("Not found", "Unknown listing.", "<h1>Not found</h1>", status=404)
    if v not in verticals.VERTICALS:
        return _page("Not found", "Unknown category.", "<h1>Not found</h1>", status=404)
    r = _fetch(v, listing_id)
    if not r:
        return _page("Listing not found", "This listing isn't available.",
                     "<h1>Listing not found</h1>", status=404)

    form = await request.form()
    if (form.get("website") or "").strip():            # honeypot -> silently accept
        return RedirectResponse(f"/listing/{v}/{listing_id}?ok=suggest", status_code=303)
    body = (form.get("body") or "").strip()
    if not body:
        return _err(v, listing_id, "Please describe what should be fixed.")
    if not verify_captcha(form):
        return _err(v, listing_id, "The captcha answer was incorrect.")

    base = settings.public_web_url.rstrip("/")
    subject = f"Edit suggestion: {r['name']} [{base}/listing/{v}/{listing_id}]"
    ip = request.client.host if request.client else None
    try:
        inbox.create_message("(edit suggestion)", form.get("email") or "", subject, body, ip)
    except Exception:
        pass
    return RedirectResponse(f"/listing/{v}/{listing_id}?ok=suggest", status_code=303)


routes = [
    Route("/listing/{vertical}/{id}", listing_page, methods=["GET"]),
    Route("/listing/{vertical}/{id}/review", review_post, methods=["POST"]),
    Route("/listing/{vertical}/{id}/suggest", suggest_post, methods=["POST"]),
]
