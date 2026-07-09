"""Admin management for movies, H-1B sponsors, and knowledge-base articles -- entities that live
outside the verticals.VERTICALS registry, so they don't go through web/admin.py's registry-driven
data_list/data_detail/data_action. Same interaction pattern (action buttons + edit form), standalone.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import h1b, knowledge, movies
from .auth import require_admin
from .common import admin_page, esc

_PER_PAGE = 50


# ------------------------------------------------------------------------------- shared helpers
def _act(base: str, op: str, label: str, gray: bool = False) -> str:
    return (f"<form method='post' action='{base}/action' class='inline'>"
            f"<input type='hidden' name='op' value='{op}'>"
            f"<button class='btn{' gray' if gray else ''}'>{label}</button></form> ")


def _action_buttons(base: str, is_active: bool, deleted: bool) -> str:
    return (_act(base, "deactivate" if is_active else "activate",
                "Deactivate" if is_active else "Reactivate", True)
            + _act(base, "restore" if deleted else "delete",
                  "Restore" if deleted else "Soft-delete", True))


def _status_badge(is_active: bool) -> str:
    return "" if is_active else "<span class='err'>inactive</span>"


def _filter_bar(base: str, q: str | None) -> str:
    return (f"<form method='get' class='inline'><input name='q' placeholder='search' "
            f"value='{esc(q)}'> <button>Search</button></form> "
            f"<span class='muted'>Filter: <a href='{base}?filter=active'>active</a> &middot; "
            f"<a href='{base}?filter=inactive'>inactive</a> &middot; <a href='{base}'>all</a></span>")


def _pagination(total: int, page: int, per: int) -> str:
    pages = (total + per - 1) // per
    nav = f"<span class='muted'>{total} records &middot; page {page}/{max(pages, 1)}</span> "
    if page > 1:
        nav += f"<a href='?page={page - 1}'>&lsaquo; prev</a> "
    if page < pages:
        nav += f"<a href='?page={page + 1}'>next &rsaquo;</a>"
    return nav


def _page_num(request: Request) -> int:
    return max(int(request.query_params.get("page", "1") or 1), 1)


# ------------------------------------------------------------------------------------- movies
def movies_list(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    q = request.query_params.get("q") or None
    flt = request.query_params.get("filter") or None
    page = _page_num(request)
    rows = movies.list_admin(q=q, flt=flt, limit=_PER_PAGE, offset=(page - 1) * _PER_PAGE)
    total = movies.count_admin(q=q, flt=flt)
    trs = "".join(
        f"<tr><td>{x['id']}</td>"
        f"<td><a href='/admin/movies/{x['id']}'>{esc(x['title'])}</a></td>"
        f"<td>{esc(x['language'])}</td><td>{esc(x['release_date'])}</td>"
        f"<td>{'now playing' if x['now_playing'] else ''}</td>"
        f"<td>{_status_badge(x['is_active'])}</td></tr>" for x in rows)
    body = (f"{_filter_bar('/admin/movies', q)}"
            f"<table><tr><th>ID</th><th>Title</th><th>Language</th><th>Release</th>"
            f"<th>Now playing</th><th></th></tr>{trs}</table>{_pagination(total, page, _PER_PAGE)}")
    return admin_page("Movies", body, active="Movies")


def movies_detail(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    movie_id = int(request.path_params["id"])
    m = movies.get_movie(movie_id)
    if m is None:
        return admin_page("Not found", "<p>Movie not found.</p>", status=404)
    base = f"/admin/movies/{movie_id}"
    actions = _action_buttons(base, m["is_active"], m["deleted_at"] is not None)
    field_rows = "".join(
        f"<label>{f}</label><input name='{f}' value='{esc(m.get(f))}'>"
        for f in ("title", "original_title", "language", "poster_url", "overview",
                  "release_date", "ticket_url"))
    genres_csv = ",".join(m.get("genres") or [])
    field_rows += (f"<label>genres (comma-separated)</label>"
                   f"<input name='genres_csv' value='{esc(genres_csv)}'>")
    edit_form = f"<form method='post' action='{base}'>{field_rows}<button>Save edits</button></form>"
    meta = (f"<p class='muted'>tmdb_id {m['tmdb_id']} &middot; now_playing {m['now_playing']} "
            f"&middot; popularity {m['popularity']} &middot; fetched_at {esc(m.get('fetched_at'))} "
            f"&mdash; these are data-driven, refreshed daily from TMDB, not editable here.</p>")
    body = (f"<p><a href='/admin/movies'>&lsaquo; back to movies</a></p>"
            f"<h3>{esc(m['title'])} <span class='muted'>#{movie_id}</span></h3>{meta}"
            f"<p>{actions}</p><h3>Edit</h3>{edit_form}")
    return admin_page(m["title"], body, active="Movies")


async def movies_edit(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    movie_id = int(request.path_params["id"])
    form = await request.form()
    edits = {f: (form.get(f) or "").strip() or None
             for f in ("title", "original_title", "language", "poster_url", "overview",
                       "release_date", "ticket_url") if f in form}
    if "genres_csv" in form:
        edits["genres"] = [t.strip() for t in (form.get("genres_csv") or "").split(",") if t.strip()]
    movies.apply_edits(movie_id, edits)
    return RedirectResponse(f"/admin/movies/{movie_id}", status_code=303)


async def movies_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    movie_id = int(request.path_params["id"])
    op = (await request.form()).get("op")
    if op == "activate":
        movies.set_active(movie_id, True)
    elif op == "deactivate":
        movies.set_active(movie_id, False)
    elif op == "delete":
        movies.set_deleted(movie_id, True)
    elif op == "restore":
        movies.set_deleted(movie_id, False)
    return RedirectResponse(f"/admin/movies/{movie_id}", status_code=303)


# ---------------------------------------------------------------------------------- employers
def employers_list(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    q = request.query_params.get("q") or None
    flt = request.query_params.get("filter") or None
    page = _page_num(request)
    rows = h1b.list_admin(q=q, flt=flt, limit=_PER_PAGE, offset=(page - 1) * _PER_PAGE)
    total = h1b.count_admin(q=q, flt=flt)
    trs = "".join(
        f"<tr><td>{x['id']}</td>"
        f"<td><a href='/admin/employers/{x['id']}'>{esc(x['display_name'] or x['employer'])}</a></td>"
        f"<td>{x['certified']:,}</td><td>{esc(x.get('median_wage'))}</td>"
        f"<td>{_status_badge(x['is_active'])}</td></tr>" for x in rows)
    body = (f"{_filter_bar('/admin/employers', q)}"
            f"<table><tr><th>ID</th><th>Employer</th><th>Certified</th><th>Median wage</th>"
            f"<th></th></tr>{trs}</table>{_pagination(total, page, _PER_PAGE)}")
    return admin_page("Employers", body, active="Employers")


def employers_detail(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    sponsor_id = int(request.path_params["id"])
    s = h1b.get_sponsor(sponsor_id)
    if s is None:
        return admin_page("Not found", "<p>Sponsor not found.</p>", status=404)
    base = f"/admin/employers/{sponsor_id}"
    actions = _action_buttons(base, s["is_active"], s["deleted_at"] is not None)
    field_rows = "".join(
        f"<label>{f}</label><input name='{f}' value='{esc(s.get(f))}'>"
        for f in ("display_name", "median_wage", "fiscal_year"))
    for f in ("top_titles", "top_states", "top_cities"):
        csv = ",".join(s.get(f) or [])
        field_rows += (f"<label>{f} (comma-separated)</label>"
                       f"<input name='{f}_csv' value='{esc(csv)}'>")
    edit_form = f"<form method='post' action='{base}'>{field_rows}<button>Save edits</button></form>"
    meta = (f"<p class='muted'>employer {esc(s['employer'])} (upsert key, not editable) "
            f"&middot; certified {s['certified']:,} (recomputed every DOL import, not editable here)"
            f"</p>")
    body = (f"<p><a href='/admin/employers'>&lsaquo; back to employers</a></p>"
            f"<h3>{esc(s['display_name'] or s['employer'])} <span class='muted'>#{sponsor_id}</span>"
            f"</h3>{meta}<p>{actions}</p><h3>Edit</h3>{edit_form}")
    return admin_page(s["display_name"] or s["employer"], body, active="Employers")


async def employers_edit(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    sponsor_id = int(request.path_params["id"])
    form = await request.form()
    edits = {f: (form.get(f) or "").strip() or None
             for f in ("display_name", "median_wage", "fiscal_year") if f in form}
    if "median_wage" in edits and edits["median_wage"] is not None:
        try:
            edits["median_wage"] = int(edits["median_wage"])
        except ValueError:
            edits.pop("median_wage")
    for f in ("top_titles", "top_states", "top_cities"):
        key = f"{f}_csv"
        if key in form:
            edits[f] = [t.strip() for t in (form.get(key) or "").split(",") if t.strip()]
    h1b.apply_edits(sponsor_id, edits)
    return RedirectResponse(f"/admin/employers/{sponsor_id}", status_code=303)


async def employers_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    sponsor_id = int(request.path_params["id"])
    op = (await request.form()).get("op")
    if op == "activate":
        h1b.set_active(sponsor_id, True)
    elif op == "deactivate":
        h1b.set_active(sponsor_id, False)
    elif op == "delete":
        h1b.set_deleted(sponsor_id, True)
    elif op == "restore":
        h1b.set_deleted(sponsor_id, False)
    return RedirectResponse(f"/admin/employers/{sponsor_id}", status_code=303)


# ---------------------------------------------------------------------------------- knowledge
def knowledge_list(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    q = request.query_params.get("q") or None
    flt = request.query_params.get("filter") or None
    page = _page_num(request)
    rows = knowledge.list_admin(q=q, flt=flt, limit=_PER_PAGE, offset=(page - 1) * _PER_PAGE)
    total = knowledge.count_admin(q=q, flt=flt)
    trs = "".join(
        f"<tr><td>{x['id']}</td>"
        f"<td><a href='/admin/knowledge/{x['id']}'>{esc(x['title'] or x['source_ref'])}</a></td>"
        f"<td>{esc(x['source_type'])}</td><td>{esc(x.get('vertical'))}</td>"
        f"<td>{_status_badge(x['is_active'])}</td></tr>" for x in rows)
    body = (f"{_filter_bar('/admin/knowledge', q)}"
            f"<table><tr><th>ID</th><th>Title</th><th>Source type</th><th>Vertical</th>"
            f"<th></th></tr>{trs}</table>{_pagination(total, page, _PER_PAGE)}")
    return admin_page("Knowledge", body, active="Knowledge")


def knowledge_detail(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    doc_id = int(request.path_params["id"])
    d = knowledge.get_document(doc_id)
    if d is None:
        return admin_page("Not found", "<p>Article not found.</p>", status=404)
    base = f"/admin/knowledge/{doc_id}"
    actions = _action_buttons(base, d["is_active"], d["deleted_at"] is not None)
    field_rows = "".join(
        f"<label>{f}</label><input name='{f}' value='{esc(d.get(f))}'>" for f in ("title", "url", "lang"))
    edit_form = f"<form method='post' action='{base}'>{field_rows}<button>Save edits</button></form>"
    meta = (f"<p class='muted'>source {esc(d['source_type'])}:{esc(d['source_ref'])} "
            f"&middot; vertical {esc(d.get('vertical')) or '(general)'}</p>")
    content_note = (
        "<p class='muted'>Content is generated by curated articles / the H-1B data importer / listing "
        "sync, and will be overwritten by the next scheduled refresh &mdash; editing wording isn't "
        "supported yet. Edit the source in <code>knowledge_seed.py</code>/<code>labor.py</code> and "
        "re-run the seed/import, or pause/delete this article to remove it from chat answers now.</p>")
    body = (f"<p><a href='/admin/knowledge'>&lsaquo; back to knowledge</a></p>"
            f"<h3>{esc(d['title'] or d['source_ref'])} <span class='muted'>#{doc_id}</span></h3>{meta}"
            f"<p>{actions}</p><h3>Edit (metadata only)</h3>{edit_form}{content_note}"
            f"<h3>Content (read-only)</h3><textarea readonly rows='14' style='width:100%'>"
            f"{esc(d.get('content'))}</textarea>")
    return admin_page(d["title"] or d["source_ref"], body, active="Knowledge")


async def knowledge_edit(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    doc_id = int(request.path_params["id"])
    form = await request.form()
    edits = {f: (form.get(f) or "").strip() or None for f in ("title", "url", "lang") if f in form}
    knowledge.apply_edits_metadata(doc_id, edits)
    return RedirectResponse(f"/admin/knowledge/{doc_id}", status_code=303)


async def knowledge_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    doc_id = int(request.path_params["id"])
    op = (await request.form()).get("op")
    if op == "activate":
        knowledge.set_active(doc_id, True)
    elif op == "deactivate":
        knowledge.set_active(doc_id, False)
    elif op == "delete":
        knowledge.set_deleted(doc_id, True)
    elif op == "restore":
        knowledge.set_deleted(doc_id, False)
    return RedirectResponse(f"/admin/knowledge/{doc_id}", status_code=303)


routes = [
    Route("/admin/movies", movies_list, methods=["GET"]),
    Route("/admin/movies/{id:int}", movies_detail, methods=["GET"]),
    Route("/admin/movies/{id:int}", movies_edit, methods=["POST"]),
    Route("/admin/movies/{id:int}/action", movies_action, methods=["POST"]),
    Route("/admin/employers", employers_list, methods=["GET"]),
    Route("/admin/employers/{id:int}", employers_detail, methods=["GET"]),
    Route("/admin/employers/{id:int}", employers_edit, methods=["POST"]),
    Route("/admin/employers/{id:int}/action", employers_action, methods=["POST"]),
    Route("/admin/knowledge", knowledge_list, methods=["GET"]),
    Route("/admin/knowledge/{id:int}", knowledge_detail, methods=["GET"]),
    Route("/admin/knowledge/{id:int}", knowledge_edit, methods=["POST"]),
    Route("/admin/knowledge/{id:int}/action", knowledge_action, methods=["POST"]),
]
