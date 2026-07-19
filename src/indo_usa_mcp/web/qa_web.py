"""Ask-the-community Q&A web surface: /ask (compose), /questions (browse), /q/{slug} (indexable
detail with QAPage JSON-LD), plus answer + upvote actions. Asking/answering/voting require the same
login as the rest of the account features; browsing + reading are public (for SEO + AI answer engines)."""

from __future__ import annotations

import html
import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import qa, verticals
from ..config import settings
from .auth import portal_email
from .common import share_html, state_select
from .landing import _base, _page


def _esc(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else ""


def _dost_name() -> str:
    return _esc(settings.assistant_name)


def questions_page(request: Request) -> HTMLResponse:
    if not qa.enabled():
        return _page("Not found", "Unavailable.", "<h1>Not found</h1>", status=404)
    qs = qa.list_questions(limit=60)
    rows = "".join(
        f"<div class='lc'><a href='/q/{_esc(q['slug'])}'>{_esc(q['title'])}</a>"
        f"<div class='muted' style='font-size:13px'>"
        + (f"📍 {_esc(q['city'])} · " if q.get("city") else "")
        + f"{q['answer_count']} answer{'s' if q['answer_count'] != 1 else ''}</div></div>"
        for q in qs) or "<p class='muted'>No questions yet — be the first to ask!</p>"
    body = ("<h1>Ask the community</h1>"
            "<p class='muted'>Real questions from Indians across the USA — answered by "
            f"{_dost_name()} and the community.</p>"
            "<p><a class='cta' href='/ask'>Ask a question →</a></p>" + rows)
    desc = ("Community questions & answers for Indians in the USA — visas, taxes, temples, restaurants, "
            "newcomer life and more, answered by Dost and the community.")
    return _page("Ask the community · Q&A", desc, body, canonical=_base() + "/questions")


def ask_get(request: Request) -> HTMLResponse:
    if not qa.enabled():
        return _page("Not found", "Unavailable.", "<h1>Not found</h1>", status=404)
    if not portal_email(request):
        return RedirectResponse("/portal/login", status_code=303)
    opts = "".join(f"<option value='{v}'>{_esc(cfg['label'])}</option>"
                   for v, cfg in verticals.VERTICALS.items() if v != "events")
    body = ("<h1>Ask a question</h1>"
            "<p class='muted'>Ask anything about Indian life in the USA — Dost answers instantly, and "
            "the community can chime in.</p>"
            "<form method='post' action='/ask'>"
            "<label>Your question</label>"
            "<input name='title' required minlength='12' maxlength='200' "
            "placeholder='e.g. Telugu-speaking pediatrician in Plano who takes Aetna?'>"
            "<label>More detail (optional)</label>"
            "<textarea name='body' rows='4' maxlength='2000' style='width:100%'></textarea>"
            f"<label>Category (optional)</label><select name='vertical'><option value=''>—</option>{opts}</select>"
            "<label>City (optional)</label><input name='city' placeholder='e.g. Plano'>"
            f"<label>State (optional)</label>{state_select('state')}"
            "<button type='submit' style='margin-top:10px'>Post question</button></form>")
    return _page("Ask a question", "Ask the Indian-American community a question.", body,
                 canonical=_base() + "/ask", noindex=True)


async def ask_post(request: Request) -> HTMLResponse:
    email = portal_email(request)
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    form = await request.form()
    res = qa.create_question(
        (form.get("title") or ""), body=(form.get("body") or ""), asker_email=email,
        city=(form.get("city") or ""), state=(form.get("state") or ""),
        vertical=(form.get("vertical") or "") or None,
        ip=(request.client.host if request.client else None))
    if not res.get("ok"):
        msg = {"too_short": "Please write a fuller question (at least 12 characters).",
               "too_long": "That's a bit long — please shorten it.",
               "qa_disabled": "Q&A isn't available right now."}.get(res.get("error"), "Couldn't post that.")
        return _page("Couldn't post", "Couldn't post your question.",
                     f"<h2 class='err'>{_esc(msg)}</h2><p><a href='/ask'>‹ back</a></p>", status=400)
    if res["status"] != "published":
        return _page("Under review", "Your question is under review.",
                     "<h2 class='ok'>✓ Thanks — your question is under review.</h2>"
                     "<p>We screen new posts to keep things useful; it'll appear shortly. "
                     "<a href='/questions'>Browse other questions</a>.</p>")
    return RedirectResponse(f"/q/{res['slug']}", status_code=303)


def _answer_html(a: dict, signed_in: bool) -> str:
    who = (f"<b style='color:#0f9b8e'>✨ {_dost_name()}</b>" if a["is_ai"] else "<b>Community</b>")
    vote = ""
    if signed_in and not a["is_ai"]:
        vote = (f"<form method='post' action='/answer/{a['id']}/vote' style='display:inline'>"
                f"<button class='linkbtn' title='Upvote'>▲ {a['upvotes']}</button></form>")
    elif not a["is_ai"]:
        vote = f"<span class='muted'>▲ {a['upvotes']}</span>"
    return (f"<div class='lc'><div style='display:flex;justify-content:space-between;gap:10px'>"
            f"<span>{who}</span>{vote}</div>"
            f"<p style='margin:6px 0 0;white-space:pre-wrap'>{_esc(a['body'])}</p></div>")


def _qa_jsonld(q: dict) -> str:
    ans = [a for a in q["answers"]]
    top = ans[0] if ans else None
    data = {"@context": "https://schema.org", "@type": "QAPage",
            "mainEntity": {"@type": "Question", "name": q["title"], "text": q.get("body") or q["title"],
                           "answerCount": len(ans),
                           "dateCreated": str(q["created_at"])}}
    if top:
        data["mainEntity"]["acceptedAnswer"] = {"@type": "Answer", "text": top["body"],
                                                "upvoteCount": int(top.get("upvotes") or 0)}
    if len(ans) > 1:
        data["mainEntity"]["suggestedAnswer"] = [
            {"@type": "Answer", "text": a["body"], "upvoteCount": int(a.get("upvotes") or 0)}
            for a in ans[1:]]
    return json.dumps(data)


def question_page(request: Request) -> HTMLResponse:
    if not qa.enabled():
        return _page("Not found", "Unavailable.", "<h1>Not found</h1>", status=404)
    q = qa.get_question(request.path_params["slug"])
    if not q:
        return _page("Question not found", "This question isn't available.",
                     "<h1>Not found</h1><p><a href='/questions'>Browse questions</a></p>", status=404)
    qa.bump_views(q["id"])
    email = portal_email(request)
    loc = ", ".join(x for x in (q.get("city"), q.get("state")) if x)
    answers = "".join(_answer_html(a, bool(email)) for a in q["answers"]) \
        or f"<p class='muted'>No answers yet. {'Be the first to answer!' if email else ''}</p>"
    if email:
        answer_form = (f"<h3 style='margin-top:20px'>Your answer</h3>"
                       f"<form method='post' action='/q/{_esc(q['slug'])}/answer'>"
                       "<textarea name='body' rows='4' required maxlength='2000' style='width:100%' "
                       "placeholder='Share what you know…'></textarea>"
                       "<button type='submit' style='margin-top:8px'>Post answer</button></form>")
    else:
        answer_form = ("<p style='margin-top:18px'><a class='cta' href='/portal/login'>Sign in to answer "
                       "or upvote →</a></p>")
    body = (f"<nav class='crumbs'><a href='/questions'>Q&amp;A</a> › {_esc(q['title'])}</nav>"
            f"<h1>{_esc(q['title'])}</h1>"
            + f"<p style='margin:6px 0 10px'>{share_html('/q/' + q['slug'], q['title'])}</p>"
            + (f"<p class='muted'>📍 {_esc(loc)}</p>" if loc else "")
            + (f"<p style='white-space:pre-wrap'>{_esc(q['body'])}</p>" if q.get("body") else "")
            + f"<h2 style='margin-top:22px'>{len(q['answers'])} answer"
            + ("s" if len(q["answers"]) != 1 else "") + "</h2>"
            + answers + answer_form)
    desc = (q.get("body") or q["title"])[:180]
    return _page(q["title"] + " · Q&A", desc, body, jsonld=_qa_jsonld(q),
                 canonical=_base() + f"/q/{q['slug']}")


async def answer_post(request: Request) -> HTMLResponse:
    email = portal_email(request)
    slug = request.path_params["slug"]
    if not email:
        return RedirectResponse("/portal/login", status_code=303)
    q = qa.get_question(slug)
    if not q:
        return _page("Not found", "Question not found.", "<h1>Not found</h1>", status=404)
    form = await request.form()
    qa.add_answer(q["id"], (form.get("body") or ""), email,
                  ip=(request.client.host if request.client else None))
    return RedirectResponse(f"/q/{slug}", status_code=303)


async def vote_post(request: Request) -> RedirectResponse:
    email = portal_email(request)
    try:
        aid = int(request.path_params["id"])
    except (ValueError, TypeError):
        return RedirectResponse("/questions", status_code=303)
    ref = request.headers.get("referer", "")
    back = ref if ref.startswith(_base()) or ref.startswith("/") else "/questions"
    if email:
        qa.vote_answer(aid, email)
    else:
        return RedirectResponse("/portal/login", status_code=303)
    return RedirectResponse(back or "/questions", status_code=303)


routes = [
    Route("/questions", questions_page, methods=["GET"]),
    Route("/ask", ask_get, methods=["GET"]),
    Route("/ask", ask_post, methods=["POST"]),
    Route("/q/{slug}", question_page, methods=["GET"]),
    Route("/q/{slug}/answer", answer_post, methods=["POST"]),
    Route("/answer/{id}/vote", vote_post, methods=["POST"]),
]
