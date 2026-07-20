"""Community social-proof surfaces: a contributor /leaderboard (optionally city-scoped) and public
/u/{code} profiles. Turns the private contributor tier into public recognition — a light engagement
loop that rewards the people adding places, writing reviews, and answering questions. Read-only.
"""

from __future__ import annotations

import html as _html

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from .. import accounts
from ..config import settings
from .common import share_html, state_select
from .landing import _base, _page


def _esc(s) -> str:
    return _html.escape(str(s)) if s is not None else ""


def _display(row: dict) -> str:
    """A shown name for a member — their display_name, else an anonymized handle from their code."""
    name = (row.get("display_name") or "").strip()
    return name or f"Member {(_row_code(row) or '')[:4].upper()}"


def _row_code(row: dict) -> str:
    return row.get("code") or row.get("referral_code") or ""


# --------------------------------------------------------------------------- /leaderboard
def leaderboard_page(request: Request) -> HTMLResponse:
    q = request.query_params
    city = (q.get("city") or "").strip() or None
    state = (q.get("state") or "").strip() or None
    rows = accounts.leaderboard(city=city, state=state, limit=25)
    scope = f" · {_esc(city)}" if city else (f" · {_esc(state)}" if state else " · nationwide")

    form = (
        "<form method='get' style='margin:10px 0 18px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<input name='city' value='{_esc(city or '')}' placeholder='City (e.g. Plano)' "
        "style='padding:8px;border:1px solid #ccc;border-radius:8px'>"
        f"{state_select('state', state or '')}"
        "<button class='cta' type='submit'>Filter</button>"
        "<a href='/leaderboard' style='align-self:center'>Reset</a></form>")

    if rows:
        trs = "".join(
            f"<tr><td style='padding:6px 10px'>{i + 1}</td>"
            f"<td style='padding:6px 10px'><a href='/u/{_esc(_row_code(r))}'>{_esc(_display(r))}</a>"
            + (f" <span class='muted'>· {_esc(r.get('home_city'))}</span>" if r.get("home_city") else "")
            + "</td>"
            f"<td style='padding:6px 10px'>{_esc(r.get('tier'))}</td>"
            f"<td style='padding:6px 10px;text-align:right'><b>{r['points']}</b></td></tr>"
            for i, r in enumerate(rows))
        table = ("<table style='border-collapse:collapse;width:100%'>"
                 "<tr><th style='text-align:left;padding:6px 10px'>#</th>"
                 "<th style='text-align:left;padding:6px 10px'>Contributor</th>"
                 "<th style='text-align:left;padding:6px 10px'>Tier</th>"
                 "<th style='text-align:right;padding:6px 10px'>Points</th></tr>"
                 f"{trs}</table>")
    else:
        table = ("<p class='muted'>No contributors here yet. Be the first — add a place, write a review, "
                 "or answer a question.</p>")

    body = (f"<h1>Community leaderboard <span class='muted' style='font-weight:400'>{scope}</span></h1>"
            "<p class='lead'>The people making this the go-to place for Indians in the USA — adding "
            "listings, writing reviews, and answering questions.</p>"
            f"{form}{table}"
            "<p style='margin-top:18px'><a class='cta' href='/me'>See your rank & badge →</a></p>")
    return _page("Community leaderboard", "Top contributors to the Indian-American community directory.",
                 body, canonical=_base() + "/leaderboard")


# --------------------------------------------------------------------------- /u/{code}
def profile_page(request: Request) -> HTMLResponse:
    code = request.path_params.get("code", "")
    prof = accounts.profile_by_code(code)
    if not prof:
        return _page("Member not found", "", "<h1>Member not found</h1>"
                     "<p><a href='/leaderboard'>See the leaderboard →</a></p>", status=404, noindex=True)
    st = accounts.contributor_stats(prof["email"])
    name = (prof.get("display_name") or "").strip() or f"Member {code[:4].upper()}"
    where = ", ".join(x for x in (prof.get("home_city"), prof.get("home_state")) if x)

    def stat(label, val):
        return (f"<div style='background:#f6f6f6;border-radius:12px;padding:12px 16px;min-width:90px'>"
                f"<div style='font-size:22px;font-weight:700'>{val}</div>"
                f"<div class='muted' style='font-size:13px'>{label}</div></div>")

    badge = st["tier"] or "🌱 New Contributor"
    cards = "".join([stat("Places added", st["added"]), stat("Reviews", st["reviews"]),
                     stat("Answers", st["answered"]), stat("Questions", st["asked"]),
                     stat("Points", st["points"])])
    body = (f"<h1>{_esc(name)}</h1>"
            + (f"<p class='muted'>{_esc(where)}</p>" if where else "")
            + f"<p style='font-size:18px'>{_esc(badge)}</p>"
            + f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin:16px 0'>{cards}</div>"
            + f"<p>{share_html('/u/' + code, f'{name} on {settings.platform_name}')}</p>"
            + "<p style='margin-top:16px'><a href='/leaderboard'>← Community leaderboard</a></p>")
    return _page(f"{name} — contributor profile",
                 f"{name}'s contributions to the Indian-American community directory.",
                 body, canonical=_base() + f"/u/{code}")


routes = [
    Route("/leaderboard", leaderboard_page, methods=["GET"]),
    Route("/u/{code}", profile_page, methods=["GET"]),
]
