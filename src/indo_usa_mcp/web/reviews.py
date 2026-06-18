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

from .. import db, reviews as reviews_mod, tags as tagsmod, verticals
from ..config import settings
from .auth import verify_captcha
from .common import captcha_field
from .landing import _FEATURED, _cathead, _label, _page

_CSS = """<style>
.lh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:2px 0 4px}
.lh .rate{color:#b45309;font-weight:600}.lh .muted{font-size:14px}
.lmeta{color:#4b5563;margin:6px 0}.lmeta a{font-weight:600}
.banner{background:#fff;border:1px solid #cfe6e0;border-left:4px solid #0f9b8e;border-radius:10px;
 padding:12px 14px;margin:12px 0;font-weight:600}.banner.ok{border-left-color:#137333;color:#137333}
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
    return db.query_one(
        f"SELECT id, name, address_full, city, state, lat, lng, phone, website, description, tags, "
        f"is_claimed, rating, rating_count, community_rating, community_rating_count, "
        f"{_FEATURED} AS is_featured FROM {table} "
        f"WHERE id = %s AND deleted_at IS NULL AND is_active", [listing_id])


def _features_html(r: dict) -> str:
    feats = tagsmod.for_display(r.get("tags"), limit=10)
    if not feats:
        return ""
    chips = "".join(f"<span class='fchip'>{html.escape(f)}</span>" for f in feats)
    return f"<div class='feats'>{chips}</div>"


def _ratings_html(r: dict) -> str:
    parts = []
    cr, crc = r.get("community_rating"), r.get("community_rating_count") or 0
    if cr:
        parts.append(f"<span class='rate'>★ {cr:.1f} ({crc} community review"
                     f"{'s' if crc != 1 else ''})</span>")
    if r.get("rating"):
        rc = r.get("rating_count")
        parts.append("<span class='muted'>★ " + html.escape(str(r["rating"]))
                     + (f" ({rc})" if rc else "") + " from the web</span>")
    return " &nbsp;·&nbsp; ".join(parts)


def _reviews_html(items: list[dict]) -> str:
    if not items:
        return "<p class='muted'>No community reviews yet — be the first to write one below.</p>"
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


def _form_html(vertical: str, listing_id: int) -> str:
    stars = "".join(
        f"<input type='radio' id='star{i}' name='rating' value='{i}' required>"
        f"<label for='star{i}' aria-label='{i} star{'s' if i != 1 else ''}'>★</label>"
        for i in (5, 4, 3, 2, 1))
    return (
        f"<h2 style='margin-top:26px'>Write a review</h2>"
        f"<form class='rform' method='post' action='/listing/{vertical}/{listing_id}/review'>"
        "<input class='hp' type='text' name='website' tabindex='-1' autocomplete='off' aria-hidden='true'>"
        "<label>Your rating</label>"
        f"<fieldset class='stars'>{stars}</fieldset>"
        "<label>Your review <span style='font-weight:400;color:#6b7280'>(optional)</span></label>"
        "<textarea name='body' rows='4' maxlength='2000' "
        "placeholder='What was your experience? Be honest and helpful.'></textarea>"
        "<label>Your name <span style='font-weight:400;color:#6b7280'>(optional)</span></label>"
        "<input type='text' name='name' maxlength='120' placeholder='Anonymous'>"
        f"{captcha_field()}"
        "<button type='submit'>Submit review</button>"
        "<p class='muted' style='font-size:12.5px;margin-top:10px'>Reviews are moderated. Be "
        "respectful and on-topic — spam and abuse are removed.</p></form>")


def _jsonld(vertical: str, r: dict, items: list[dict]) -> str:
    biz: dict = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": r["name"],
                 "address": {"@type": "PostalAddress", "addressLocality": r.get("city"),
                             "addressRegion": r.get("state"), "streetAddress": r.get("address_full")}}
    if r.get("phone"):
        biz["telephone"] = r["phone"]
    if r.get("website"):
        biz["url"] = r["website"]
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
    loc = ", ".join(x for x in (r.get("city"), (r["state"].upper() if r.get("state") else None)) if x)
    addr = r.get("address_full") or loc
    label = _label(v)
    ratings = _ratings_html(r)
    links = " &nbsp;·&nbsp; ".join(x for x in (
        (f"<a href='{html.escape(r['website'])}' rel='nofollow'>Website</a>" if r.get("website") else ""),
        (f"<a href='tel:{html.escape(r['phone'])}'>{html.escape(r['phone'])}</a>" if r.get("phone") else ""),
    ) if x)
    verified = " <span style='color:#1565c0;font-weight:600'>✓ Owner-verified</span>" if r.get("is_claimed") else ""

    ok = request.query_params.get("ok")
    banner = ""
    if ok == "published":
        banner = "<div class='banner ok'>✓ Thanks! Your review is now live.</div>"
    elif ok == "pending":
        banner = ("<div class='banner'>✓ Thanks! Your review was received and will appear "
                  "after a quick moderation check.</div>")

    body = (
        _CSS
        + f"<nav class='crumbs'><a href='/browse'>Browse</a> › "
        + f"<a href='/browse/{v}'>{html.escape(label)}</a> › {html.escape(r['name'])}</nav>"
        + _cathead(v)
        + banner
        + f"<h1>{html.escape(r['name'])}{verified}</h1>"
        + (f"<div class='lh'>{ratings}</div>" if ratings else "")
        + (f"<p class='lmeta'>📍 {html.escape(addr)}</p>" if addr else "")
        + (f"<p class='lmeta'>{links}</p>" if links else "")
        + (f"<p>{html.escape(r.get('description') or '')}</p>" if r.get("description") else "")
        + _features_html(r)
        + "<h2 style='margin-top:26px'>Community reviews</h2>"
        + _reviews_html(items)
        + _form_html(v, listing_id))
    desc = (f"{r['name']} — Indian {label} in {loc}. Read community reviews and ratings, contact "
            "details, and share your own experience.")
    return _page(f"{r['name']} · {label} · {settings.platform_name}", desc, body,
                 jsonld=_jsonld(v, r, items))


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


routes = [
    Route("/listing/{vertical}/{id}", listing_page, methods=["GET"]),
    Route("/listing/{vertical}/{id}/review", review_post, methods=["POST"]),
]
