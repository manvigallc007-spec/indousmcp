"""Admin dashboard routes (password-gated). Mounted under /admin."""

from __future__ import annotations

import datetime as dt

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import (analytics, db, inbox, payments, quality, recommendations, reporting, reviews,
                submissions, verticals)
from ..agents import AGENTS, run_agent
from ..events import pipeline as events
from ..config import settings
from ..pipeline import ingest, outreach
from .auth import admin_enabled, login_admin, logout_admin, require_admin
from .common import _page, admin_page, esc, sparkline, trend_badge

_VKEYS = list(verticals.VERTICALS)


# ------------------------------------------------------------------------- login
def login_get(request: Request) -> HTMLResponse:
    if not admin_enabled():
        return _page("Admin disabled", "<h2>Admin is disabled</h2>"
                     "<p class='muted'>Set ADMIN_PASSWORD to enable the dashboard.</p>", status=503)
    return _page("Admin login",
                 "<h2>Admin login</h2><form method='post' action='/admin/login'>"
                 "<label>Username</label><input name='username' autofocus autocomplete='username'>"
                 "<label>Password</label>"
                 "<input name='password' type='password' autocomplete='current-password'>"
                 "<button type='submit'>Sign in</button></form>")


async def login_post(request: Request) -> HTMLResponse:
    from .security import too_many_attempts, record_attempt, clear_attempts
    ip = (request.client.host if request.client else "?") or "?"
    if too_many_attempts(ip):
        return _page("Admin login", "<h2 class='err'>Too many attempts</h2>"
                     "<p class='muted'>Please wait a few minutes and try again.</p>", status=429)
    form = await request.form()
    if login_admin(request, form.get("username") or "", form.get("password") or ""):
        clear_attempts(ip)
        return RedirectResponse("/admin", status_code=303)
    record_attempt(ip)
    return _page("Admin login", "<h2 class='err'>Wrong username or password</h2>"
                 "<p><a href='/admin/login'>Try again</a></p>", status=401)


def logout(request: Request) -> RedirectResponse:
    logout_admin(request)
    return RedirectResponse("/admin/login", status_code=303)


# ----------------------------------------------------------------------- overview
def overview(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    # Action center: linked cards for everything that needs a human, so the work is one click away.
    msgs = _scalar("SELECT count(*) FROM contact_messages WHERE status IN ('new','drafted')")
    pend_appr = _scalar("SELECT count(*) FROM approval_queue WHERE status='pending'")
    pend_sub = _scalar("SELECT count(*) FROM submissions WHERE status='pending'")
    pend_fb = _scalar("SELECT count(*) FROM feedback WHERE status='pending'")
    alerts = _scalar("SELECT count(*) FROM agent_alerts WHERE NOT resolved")
    errs = _scalar("SELECT count(*) FROM agent_runs WHERE status='error' AND started_at > now() - interval '24 hours'")

    def acard(n: int, label: str, href: str, danger: bool = False) -> str:
        b = f"<b class='{'err' if (danger and n) else ''}'>{n}</b>"
        return f"<a class='kpi act' href='{href}'>{b}<span>{esc(label)}</span></a>"
    action = "".join([
        acard(msgs, "New messages", "/admin/messages"),
        acard(pend_appr, "Pending approvals", "/admin/approvals"),
        acard(pend_sub, "New submissions", "/admin/submissions"),
        acard(pend_fb, "Pending feedback", "/admin/feedback"),
        acard(alerts, "Open alerts", "/admin/agents", danger=True),
        acard(errs, "Agent errors (24h)", "/admin/agents", danger=True),
    ])

    cards = []
    for key, cfg in verticals.VERTICALS.items():
        total = verticals.count_records(key)
        feat = verticals.count_records(key, flt="featured")
        claimed = verticals.count_records(key, flt="claimed")
        cards.append(f"<div class='kpi'><b>{total}</b><span>{cfg['label']}</span>"
                     f"<div class='muted'>{feat} featured · {claimed} claimed</div></div>")

    agents_tbl = _agent_health_table()
    body = (f"<h3>Needs attention</h3><div class='cards'>{action}</div>"
            f"<h3>Directory</h3><div class='cards'>{''.join(cards)}</div>"
            "<h3>Agent health</h3>" + agents_tbl)
    return admin_page("Overview", body, active="Overview")


def _agent_health_table() -> str:
    runs = db.query(
        "SELECT DISTINCT ON (agent) agent, status, started_at, duration_ms "
        "FROM agent_runs ORDER BY agent, started_at DESC")
    by_agent = {r["agent"]: r for r in runs}
    rows = ""
    for name in AGENTS:
        r = by_agent.get(name)
        if r:
            cls = "ok" if r["status"] == "success" else ("err" if r["status"] == "error" else "warn")
            rows += (f"<tr><td><a href='/admin/agents/{name}'>{esc(name)}</a></td><td class='{cls}'>{r['status']}</td>"
                     f"<td class='muted'>{esc(r['started_at'])}</td>"
                     f"<td class='muted'>{r['duration_ms'] or ''} ms</td></tr>")
        else:
            rows += f"<tr><td><a href='/admin/agents/{name}'>{esc(name)}</a></td><td class='muted'>never run</td><td></td><td></td></tr>"
    return f"<table><tr><th>Agent</th><th>Last status</th><th>When</th><th>Duration</th></tr>{rows}</table>"


# --------------------------------------------------------------------- data browse
def _entity_row(label: str, href: str, count: int) -> str:
    return f"<a class='kpi act' href='{href}'><b>{count}</b><span>{esc(label)}</span></a>"


def unified_search(request: Request) -> HTMLResponse:
    """Cross-entity router: search or browse every vertical + movies + employers + knowledge in one
    place, then hop into that entry's own canonical edit page (this page never edits anything itself)."""
    if (r := require_admin(request)):
        return r
    from .. import h1b, knowledge, movies
    q = request.query_params.get("q") or None

    if not q:
        cards = [_entity_row(verticals.VERTICALS[v]["label"], f"/admin/data/{v}",
                             verticals.count_records(v)) for v in _VKEYS]
        cards.append(_entity_row("Movies", "/admin/movies", movies.count_admin()))
        cards.append(_entity_row("Employers", "/admin/employers", h1b.count_admin()))
        cards.append(_entity_row("Knowledge", "/admin/knowledge", knowledge.count_admin()))
        body = (f"<form method='get' class='inline'><input name='q' placeholder='search everything' "
                f"autofocus> <button>Search</button></form>"
                f"<p class='muted'>Or browse an entity type directly:</p>"
                f"<div class='cards'>{''.join(cards)}</div>")
        return admin_page("Search all", body, active="Search all")

    sections = ""
    for v in _VKEYS:
        rows = verticals.list_records(v, q=q, limit=8)
        if not rows:
            continue
        trs = "".join(f"<tr><td>{x['id']}</td>"
                      f"<td><a href='/admin/data/{v}/{x['id']}'>{esc(x['name'])}</a></td>"
                      f"<td>{esc(x['city'])}, {esc(x['state'])}</td></tr>" for x in rows)
        sections += (f"<h3>{esc(verticals.VERTICALS[v]['label'])}</h3>"
                    f"<table><tr><th>ID</th><th>Name</th><th>Location</th></tr>{trs}</table>")
    for label, href, rows_fn, name_key in (
        ("Movies", "/admin/movies", lambda: movies.list_admin(q=q, limit=8), "title"),
        ("Employers", "/admin/employers", lambda: h1b.list_admin(q=q, limit=8), "employer"),
        ("Knowledge", "/admin/knowledge", lambda: knowledge.list_admin(q=q, limit=8), "title"),
    ):
        rows = rows_fn()
        if not rows:
            continue
        trs = "".join(f"<tr><td>{x['id']}</td>"
                      f"<td><a href='{href}/{x['id']}'>{esc(x.get(name_key) or x['id'])}</a></td></tr>"
                      for x in rows)
        sections += f"<h3>{label}</h3><table><tr><th>ID</th><th>Name</th></tr>{trs}</table>"

    body = (f"<form method='get' class='inline'><input name='q' value='{esc(q)}'> "
            f"<button>Search</button></form>"
            + (sections or "<p class='muted'>No matches.</p>"))
    return admin_page(f"Search: {q}", body, active="Search all")


def data_list(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical = request.path_params["vertical"]
    if vertical not in verticals.VERTICALS:
        return admin_page("Not found", "<p>Unknown vertical.</p>", status=404)
    q = request.query_params.get("q") or None
    flt = request.query_params.get("filter") or None
    state = request.query_params.get("state") or None
    city = request.query_params.get("city") or None
    page = max(int(request.query_params.get("page", "1") or 1), 1)
    per = 50
    rows = verticals.list_records(vertical, q=q, flt=flt, state=state, city=city,
                                  limit=per, offset=(page - 1) * per)
    total = verticals.count_records(vertical, q=q, flt=flt, state=state, city=city)

    tabs = " · ".join(f"<a href='/admin/data/{v}'>{verticals.VERTICALS[v]['label']}"
                      f"{' ◀' if v == vertical else ''}</a>" for v in _VKEYS)
    filters = " ".join(
        f"<a href='/admin/data/{vertical}?filter={f}'>{f}</a>"
        for f in ("active", "featured", "claimed", "inactive"))
    geo_ctx = ""
    if state or city:
        loc = ", ".join(x for x in (city, state) if x)
        geo_ctx = (f"<p class='muted'>Location: <b>{esc(loc)}</b> "
                   f"· <a href='/admin/data/{vertical}'>clear</a></p>")
    trs = ""
    for x in rows:
        badges = " ".join(b for b in (
            "★" if x["is_featured"] else "", "claimed" if x["is_claimed"] else "",
            "" if x["is_active"] else "<span class='err'>inactive</span>") if b)
        trs += (f"<tr><td>{x['id']}</td>"
                f"<td><a href='/admin/data/{vertical}/{x['id']}'>{esc(x['name'])}</a></td>"
                f"<td>{esc(x['city'])}, {esc(x['state'])}</td><td>{esc(x['region_tag'])}</td>"
                f"<td>{x['confidence_score']}</td><td>{badges}</td></tr>")
    pages = (total + per - 1) // per
    nav = (f"<span class='muted'>{total} records · page {page}/{max(pages,1)}</span> "
           + (f"<a href='?page={page-1}'>‹ prev</a> " if page > 1 else "")
           + (f"<a href='?page={page+1}'>next ›</a>" if page < pages else ""))
    add_btn = (f"<p><a class='btn' href='/admin/data/{vertical}/new'>+ Add listing</a></p>"
               if vertical != "events" else "")
    body = (f"<p>{tabs}</p>{add_btn}<p class='muted'>Filter: {filters} · "
            f"<a href='/admin/data/{vertical}'>all</a> · "
            f"<a href='/admin/geo/{vertical}'>by location ▸</a></p>{geo_ctx}"
            f"<form method='get' class='inline'><input name='q' placeholder='search name/city' "
            f"value='{esc(q)}'> <button>Search</button></form>"
            f"<table><tr><th>ID</th><th>Name</th><th>Location</th><th>Region</th>"
            f"<th>Conf</th><th></th></tr>{trs}</table>{nav}")
    return admin_page(f"Data · {verticals.VERTICALS[vertical]['label']}", body, active="Data")


# -------------------------------------------------------------------- geography
def geo_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical = request.path_params["vertical"]
    if vertical not in verticals.VERTICALS:
        return admin_page("Not found", "<p>Unknown vertical.</p>", status=404)
    state = request.query_params.get("state") or None
    tabs = " · ".join(f"<a href='/admin/geo/{v}'>{verticals.VERTICALS[v]['label']}"
                      f"{' ◀' if v == vertical else ''}</a>" for v in _VKEYS)

    if state is None:  # country -> states
        rows = verticals.geo_summary(vertical)
        trs = "".join(
            f"<tr><td><a href='/admin/geo/{vertical}?state={esc(x['state'])}'>{esc(x['state'])}</a></td>"
            f"<td>{x['n']}</td></tr>" for x in rows)
        body = (f"<p>{tabs}</p><p class='muted'>USA · {len(rows)} states · "
                f"click a state to drill into cities</p>"
                f"<table><tr><th>State</th><th>Active records</th></tr>{trs}</table>")
        return admin_page(f"Geography · {verticals.VERTICALS[vertical]['label']}", body, active="Geography")

    rows = verticals.geo_summary(vertical, state=state)  # state -> cities
    trs = "".join(
        f"<tr><td><a href='/admin/data/{vertical}?state={esc(state)}&city={esc(x['city'])}'>"
        f"{esc(x['city'])}</a></td><td>{x['n']}</td>"
        f"<td><a href='/admin/data/{vertical}?state={esc(state)}&city={esc(x['city'])}'>view ▸</a></td></tr>"
        for x in rows)
    body = (f"<p><a href='/admin/geo/{vertical}'>‹ all states</a> · "
            f"<a href='/admin/data/{vertical}?state={esc(state)}'>view all {esc(state)} ▸</a></p>"
            f"<h3>{esc(state)} — cities</h3>"
            f"<table><tr><th>City</th><th>Records</th><th></th></tr>{trs}</table>")
    return admin_page(f"Geography · {esc(state)}", body, active="Geography")


# ----------------------------------------------------------------- data quality
def quality_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical = request.path_params["vertical"]
    if vertical not in verticals.VERTICALS:
        return admin_page("Not found", "<p>Unknown vertical.</p>", status=404)
    issue = request.query_params.get("issue") or None
    tabs = " · ".join(f"<a href='/admin/quality/{v}'>{verticals.VERTICALS[v]['label']}"
                      f"{' ◀' if v == vertical else ''}</a>" for v in _VKEYS)

    if issue and issue in quality.ISSUES:  # drill into a specific issue
        rows = quality.flagged(vertical, issue, limit=200)
        trs = "".join(
            f"<tr><td><a href='/admin/data/{vertical}/{x['id']}'>{esc(x['name'])}</a></td>"
            f"<td>{esc(x['city'])}, {esc(x['state'])}</td><td>{esc(x['region_tag'])}</td>"
            f"<td>{x['confidence_score']}</td></tr>" for x in rows)
        body = (f"<p><a href='/admin/quality/{vertical}'>‹ quality overview</a></p>"
                f"<h3>{quality.ISSUES[issue][0]} — {len(rows)} records</h3>"
                f"<table><tr><th>Name</th><th>Location</th><th>Region</th><th>Conf</th></tr>{trs}</table>")
        return admin_page(f"Quality · {quality.ISSUES[issue][0]}", body, active="Quality")

    s = quality.summary(vertical)
    cards = "".join(
        f"<a class='kpi' href='/admin/quality/{vertical}?issue={k}' style='text-decoration:none;color:inherit'>"
        f"<b class='{'warn' if s[k] else ''}'>{s[k]}</b><span>{label}</span></a>"
        for k, (label, _) in quality.ISSUES.items())
    dupes = quality.duplicates(vertical, limit=40)

    def _merge_btn(ids):
        keep, drops = ids[0], ids[1:]
        return (f"<form method='post' action='/admin/quality/merge' class='inline'>"
                f"<input type='hidden' name='vertical' value='{vertical}'>"
                f"<input type='hidden' name='keep' value='{keep}'>"
                f"<input type='hidden' name='drop' value='{','.join(str(i) for i in drops)}'>"
                f"<button class='btn gray'>Merge → keep #{keep}</button></form>")
    dtr = "".join(
        f"<tr><td>{esc(d['name'])}</td><td>{esc(d['city'])}, {esc(d['state'])}</td><td>{d['n']}</td>"
        f"<td>{' '.join(f'<a href=\"/admin/data/{vertical}/{i}\">#{i}</a>' for i in d['ids'])}</td>"
        f"<td>{_merge_btn(d['ids'])}</td></tr>"
        for d in dupes)
    n_unusable = quality.suppress_low_quality(dry_run=True)["total"]
    suppress_btn = (f"<form method='post' action='/admin/quality' class='inline'>"
                    f"<input type='hidden' name='vertical' value='{vertical}'>"
                    "<input type='hidden' name='op' value='suppress'>"
                    f"<button class='btn gray'>Suppress {n_unusable} unusable row(s) "
                    "— all verticals</button></form>"
                    if n_unusable else "<span class='muted'>· no unusable rows 🎉</span>")
    body = (f"<p>{tabs}</p><p class='muted'>{s['total']} active records · "
            "click an issue to see affected records, then fix them inline.</p>"
            f"<div class='cards'>{cards}</div>"
            "<p><form method='post' action='/admin/quality' class='inline'>"
            f"<input type='hidden' name='vertical' value='{vertical}'>"
            "<button>Normalize city/state now</button></form> " + suppress_btn + "</p>"
            + (f"<h3>Possible duplicates ({len(dupes)})</h3>"
               "<p class='muted'>Merge fills the keeper's empty fields from the others, then "
               "soft-deletes them.</p><table><tr><th>Name</th><th>Location</th><th>Count</th>"
               f"<th>Records</th><th></th></tr>{dtr}</table>" if dupes else
               "<p class='muted'>No duplicate groups found.</p>"))
    return admin_page(f"Quality · {verticals.VERTICALS[vertical]['label']}", body, active="Quality")


async def quality_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    vertical = form.get("vertical")
    if form.get("op") == "suppress":
        quality.suppress_low_quality(dry_run=False)
    elif vertical in verticals.VERTICALS:
        verticals.normalize_geography(vertical)
    return RedirectResponse(f"/admin/quality/{vertical}", status_code=303)


async def quality_merge(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    vertical = form.get("vertical")
    if vertical in verticals.VERTICALS:
        keep = int(form.get("keep"))
        drops = [int(x) for x in (form.get("drop") or "").split(",") if x.strip()]
        if drops:
            verticals.merge_duplicates(vertical, keep, drops)
    return RedirectResponse(f"/admin/quality/{vertical}", status_code=303)


_NEW_BASE = ["name", "address_full", "city", "state", "lat", "lng", "phone", "email", "website"]


def data_new(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical = request.path_params["vertical"]
    if vertical not in verticals.VERTICALS or vertical == "events":
        return admin_page("Not allowed",
                          "<p>Listings can't be hand-added to this category"
                          f"{' (events are agent-managed)' if vertical == 'events' else ''}.</p>",
                          status=404)
    cfg = verticals.VERTICALS[vertical]
    extra = [f for f in cfg["edit_fields"] if f not in _NEW_BASE]
    rows = "".join(f"<label>{f}{' *' if f == 'name' else ''}</label><input name='{f}'>"
                   for f in _NEW_BASE + extra)
    if cfg["has_hours"]:
        rows += "<label>hours (e.g. Mo-Su 10:00-21:00)</label><input name='hours'>"
    if cfg["has_dietary"]:
        rows += "<label>dietary_tags (comma-separated)</label><input name='dietary_csv'>"
    rows += "<label>languages (comma-separated)</label><input name='languages' placeholder='Telugu, Hindi, English'>"
    body = (f"<p><a href='/admin/data/{vertical}'>‹ back to {vertical}</a></p>"
            f"<h3>Add a {verticals.VERTICALS[vertical]['label']} listing</h3>"
            "<p class='muted'>Manually add a business OSM doesn't have. Name is required; "
            "lat/lng (optional) auto-fills city/state. Saved as source=admin, active immediately, "
            "with a description + tags + embedding generated automatically.</p>"
            f"<form method='post' action='/admin/data/{vertical}/new'>{rows}"
            "<button>Create listing</button></form>")
    return admin_page("Add listing", body, active="Data")


async def data_create(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical = request.path_params["vertical"]
    if vertical not in verticals.VERTICALS or vertical == "events":
        return admin_page("Not allowed", "<p>Cannot add records here.</p>", status=404)
    form = await request.form()
    data = {k: form.get(k) for k in form.keys()}
    if "dietary_csv" in form:
        data["dietary_tags"] = sorted(
            t.strip() for t in (form.get("dietary_csv") or "").split(",") if t.strip())
    res = verticals.create_record(vertical, data)
    if res.get("ok"):
        return RedirectResponse(f"/admin/data/{vertical}/{res['id']}", status_code=303)
    msg = {"name_required": "Name is required.",
           "duplicate": "A listing with this name + location already exists.",
           "events_are_agent_managed": "Events are managed by agents."}.get(
        res.get("error"), "Could not create the listing.")
    return admin_page("Could not add", f"<p class='err'>{msg}</p>"
                      f"<p><a href='/admin/data/{vertical}/new'>‹ try again</a></p>", status=400)


def data_detail(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    rec = verticals.get_record(vertical, rec_id)
    if rec is None:
        return admin_page("Not found", "<p>Record not found.</p>", status=404)
    cfg = verticals.VERTICALS[vertical]

    # Action buttons (feature / active / delete).
    def act(op, label, gray=False):
        return (f"<form method='post' action='/admin/data/{vertical}/{rec_id}/action' class='inline'>"
                f"<input type='hidden' name='op' value='{op}'>"
                f"<button class='btn{' gray' if gray else ''}'>{label}</button></form> ")
    actions = act("feature", "Feature 30d") + act("unfeature", "Unfeature", True)
    actions += act("deactivate" if rec["is_active"] else "activate",
                   "Deactivate" if rec["is_active"] else "Reactivate", True)
    actions += act("delete" if rec["deleted_at"] is None else "restore",
                   "Soft-delete" if rec["deleted_at"] is None else "Restore", True)

    # Edit form.
    field_rows = "".join(
        f"<label>{f}</label><input name='{f}' value='{esc(rec.get(f))}'>" for f in cfg["edit_fields"])
    if cfg["has_hours"]:
        hr = (rec.get("hours_json") or {}).get("raw", "") if isinstance(rec.get("hours_json"), dict) else ""
        field_rows += f"<label>hours</label><input name='hours' value='{esc(hr)}'>"
    if cfg["has_dietary"]:
        field_rows += (f"<label>dietary_tags (comma-separated)</label>"
                       f"<input name='dietary_csv' value='{esc(','.join(rec.get('dietary_tags') or []))}'>")
    field_rows += (f"<label>languages (comma-separated)</label>"
                   f"<input name='languages_csv' value='{esc(','.join(rec.get('languages') or []))}'>")
    edit_form = (f"<form method='post' action='/admin/data/{vertical}/{rec_id}'>"
                 f"{field_rows}<button>Save edits</button></form>")

    meta = (f"<p class='muted'>v{rec['version']} · conf {rec['confidence_score']} · "
            f"featured_until {esc(rec.get('featured_until'))} · source {esc(rec.get('source_name'))} "
            f"· <a href='{esc(rec.get('source_url'))}'>source</a></p>")
    body = (f"<p><a href='/admin/data/{vertical}'>‹ back to {vertical}</a></p>"
            f"<h3>{esc(rec['name'])} <span class='muted'>#{rec_id}</span></h3>{meta}"
            f"<p>{actions}</p><h3>Edit</h3>{edit_form}")
    return admin_page(f"{rec['name']}", body, active="Data")


async def data_edit(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
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
    verticals.apply_edits(vertical, rec_id, edits)
    return RedirectResponse(f"/admin/data/{vertical}/{rec_id}", status_code=303)


async def data_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical, rec_id = request.path_params["vertical"], int(request.path_params["id"])
    op = (await request.form()).get("op")
    if op == "feature":
        verticals.set_featured(vertical, rec_id, days=settings.featured_days)
    elif op == "unfeature":
        verticals.unset_featured(vertical, rec_id)
    elif op == "activate":
        verticals.set_active(vertical, rec_id, True)
    elif op == "deactivate":
        verticals.set_active(vertical, rec_id, False)
    elif op == "delete":
        verticals.set_deleted(vertical, rec_id, True)
    elif op == "restore":
        verticals.set_deleted(vertical, rec_id, False)
    return RedirectResponse(f"/admin/data/{vertical}/{rec_id}", status_code=303)


# ------------------------------------------------------------------- approvals
_SELECT_ALL = ("<input type='checkbox' title='select all' onclick=\"for(var c of this.closest('form')"
               ".querySelectorAll('[name=ids]'))c.checked=this.checked\">")


def approvals(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    digest = ingest.summarize_approvals(limit=100)
    trs = "".join(
        f"<tr><td><input type='checkbox' name='ids' value=\"{it['id']}\"></td>"
        f"<td>{it['id']}</td><td>{it['change_type']}</td>"
        f"<td class='{'warn' if it['risk']=='high' else ''}'>{it['risk']}</td>"
        f"<td>{it['confidence']}</td><td>{esc(it['summary'])}</td>"
        f"<td><button name='one' value=\"{it['id']}:approve\">Approve</button> "
        f"<button class='btn gray' name='one' value=\"{it['id']}:reject\">Reject</button></td></tr>"
        for it in digest["items"])
    bulk = ("<div style='margin:10px 0'><button name='bulk' value='approve'>Approve selected</button> "
            "<button class='btn gray' name='bulk' value='reject'>Reject selected</button></div>")
    body = (f"<p class='muted'>{digest['pending']} pending · by risk {digest['by_risk']}</p>"
            "<form method='post' action='/admin/approvals'>" + bulk
            + f"<table><tr><th>{_SELECT_ALL}</th><th>ID</th><th>Type</th><th>Risk</th><th>Conf</th>"
            + f"<th>Summary</th><th></th></tr>{trs}</table>" + (bulk if trs else "") + "</form>")
    return admin_page("Approvals", body, active="Approvals")


async def approvals_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()

    def act(aid: int, op: str) -> None:
        if op == "approve":
            ingest.apply_approval(aid, reviewed_by="admin")
        else:
            ingest.reject_approval(aid, reviewed_by="admin")
    if form.get("bulk"):                                   # bulk approve/reject the checked rows
        op = form.get("bulk")
        for sid in form.getlist("ids"):
            try:
                act(int(sid), op)
            except (TypeError, ValueError):
                pass
    elif form.get("one"):                                  # a single row's button ("id:op")
        sid, _, op = (form.get("one") or "").partition(":")
        try:
            act(int(sid), op or "reject")
        except (TypeError, ValueError):
            pass
    elif form.get("id"):                                   # legacy single form
        try:
            act(int(form.get("id")), form.get("op") or "reject")
        except (TypeError, ValueError):
            pass
    return RedirectResponse("/admin/approvals", status_code=303)


# --------------------------------------------------------------------- feedback
def feedback_list(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    rows = db.query(
        "SELECT f.id, f.field, f.proposed_value, f.reason, f.status, f.source, r.name "
        "FROM feedback f JOIN restaurants r ON r.id=f.restaurant_id "
        "WHERE f.status IN ('pending','needs_review') ORDER BY f.created_at DESC LIMIT 100")
    trs = "".join(
        f"<tr><td>{x['id']}</td><td>{esc(x['name'])}</td><td>{esc(x['field'])}</td>"
        f"<td>{esc(x['proposed_value'])}</td><td>{esc(x['status'])}</td><td>{esc(x['source'])}</td></tr>"
        for x in rows)
    body = ("<p><form method='post' action='/admin/feedback' class='inline'>"
            "<button>Apply all pending</button></form></p>"
            f"<table><tr><th>ID</th><th>Listing</th><th>Field</th><th>Proposed</th>"
            f"<th>Status</th><th>Source</th></tr>{trs}</table>")
    return admin_page("Feedback", body, active="Feedback")


async def feedback_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    from ..pipeline import feedback as fb
    fb.apply_pending()
    return RedirectResponse("/admin/feedback", status_code=303)


# ------------------------------------------------------------------------ events
def events_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    pend = events.pending(limit=100)
    rows = ""
    for e in pend:
        rows += (
            f"<tr><td>{esc(e['name'])}</td><td>{esc(e['category'])}</td>"
            f"<td>{esc(e['venue_name'])}</td><td>{esc(e['city'])}, {esc(e['state'])}</td>"
            f"<td class='muted'>{esc(e['start_at'])}</td><td>{e['confidence_score']}</td>"
            f"<td><a href='{esc(e['source_url'])}'>src</a></td>"
            f"<td>{_event_btns(e['id'])}</td></tr>")
    stats = verticals.VERTICALS["events"]["queries"].stats()
    feeds = db.query_one(
        "SELECT count(*) FILTER (WHERE found AND active) AS found, count(*) AS scanned "
        "FROM event_feed_sources") or {"found": 0, "scanned": 0}
    body = (f"<div class='cards'>"
            f"<div class='kpi'><b>{stats['upcoming']}</b><span>upcoming (live)</span></div>"
            f"<div class='kpi'><b class='{'warn' if stats['pending'] else ''}'>{stats['pending']}</b>"
            f"<span>pending approval</span></div>"
            f"<div class='kpi'><b>{stats['past']}</b><span>past (kept)</span></div>"
            f"<div class='kpi'><b>{feeds['found']}</b><span>discovered feeds</span>"
            f"<div class='muted'>{feeds['scanned']} sites scanned</div></div></div>"
            "<p class='muted'>Events are ingested automatically from iCal feeds; high-confidence "
            "ones auto-approve, the rest wait here. Past events are kept and date-filtered.</p>"
            + (f"<h3>Pending approval ({len(pend)})</h3><table><tr><th>Event</th><th>Category</th>"
               f"<th>Venue</th><th>Location</th><th>When</th><th>Conf</th><th></th><th></th></tr>"
               f"{rows}</table>" if pend else "<p class='ok'>Nothing pending. 🎉</p>"))
    return admin_page("Events", body, active="Events")


def _event_btns(eid: int) -> str:
    return (f"<form method='post' action='/admin/events' class='inline'>"
            f"<input type='hidden' name='id' value='{eid}'><input type='hidden' name='op' value='approve'>"
            f"<button>Approve</button></form> "
            f"<form method='post' action='/admin/events' class='inline'>"
            f"<input type='hidden' name='id' value='{eid}'><input type='hidden' name='op' value='reject'>"
            f"<button class='btn gray'>Reject</button></form>")


async def events_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    events.set_status(int(form.get("id")), "approved" if form.get("op") == "approve" else "rejected")
    return RedirectResponse("/admin/events", status_code=303)


# ----------------------------------------------------------------------- claims
def claims(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    rows = db.query(
        "SELECT c.id, r.name, c.channel, c.status, c.owner_email, c.created_at "
        "FROM claims c JOIN restaurants r ON r.id=c.restaurant_id "
        "ORDER BY c.created_at DESC LIMIT 100")
    trs = "".join(
        f"<tr><td>{x['id']}</td><td>{esc(x['name'])}</td><td>{esc(x['channel'])}</td>"
        f"<td>{esc(x['status'])}</td><td>{esc(x['owner_email'])}</td>"
        f"<td class='muted'>{esc(x['created_at'])}</td></tr>" for x in rows)
    body = (f"<table><tr><th>ID</th><th>Listing</th><th>Channel</th><th>Status</th>"
            f"<th>Owner</th><th>Created</th></tr>{trs}</table>")
    return admin_page("Claims", body, active="Claims")


# ------------------------------------------------------------------------ agents
def agents_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    health = _agent_health_table()
    run_btns = " ".join(
        f"<form method='post' action='/admin/agents' class='inline'>"
        f"<input type='hidden' name='agent' value='{n}'><button>Run {n}</button></form>"
        for n in AGENTS)
    recent = db.query(
        "SELECT agent, status, started_at, duration_ms, error FROM agent_runs "
        "ORDER BY started_at DESC LIMIT 25")
    rtr = "".join(
        f"<tr><td>{esc(x['agent'])}</td>"
        f"<td class='{'ok' if x['status']=='success' else 'err'}'>{x['status']}</td>"
        f"<td class='muted'>{esc(x['started_at'])}</td><td>{x['duration_ms'] or ''}</td>"
        f"<td class='err'>{esc((x['error'] or '')[:80])}</td></tr>" for x in recent)
    alerts = db.query("SELECT id, severity, kind, message, created_at FROM agent_alerts "
                      "WHERE NOT resolved ORDER BY created_at DESC LIMIT 25")
    atr = "".join(
        f"<tr><td class='warn'>{esc(a['severity'])}</td><td>{esc(a['kind'])}</td>"
        f"<td>{esc(a['message'])}</td><td>"
        f"<form method='post' action='/admin/agents' class='inline'>"
        f"<input type='hidden' name='resolve' value='{a['id']}'>"
        f"<button class='btn gray'>Resolve</button></form></td></tr>" for a in alerts)
    body = (health + "<h3>Run an agent now</h3><p>" + run_btns + "</p>"
            + (f"<h3>Open alerts</h3><table><tr><th>Severity</th><th>Kind</th><th>Message</th>"
               f"<th></th></tr>{atr}</table>" if alerts else "")
            + f"<h3>Recent runs</h3><table><tr><th>Agent</th><th>Status</th><th>When</th>"
              f"<th>ms</th><th>Error</th></tr>{rtr}</table>")
    return admin_page("Agents", body, active="Agents")


async def agents_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    if form.get("resolve"):
        db.execute("UPDATE agent_alerts SET resolved = true WHERE id = %s", (int(form.get("resolve")),))
    elif form.get("agent") in AGENTS:
        run_agent(form.get("agent"))
    return RedirectResponse("/admin/agents", status_code=303)


def agent_detail(request: Request) -> HTMLResponse:
    """Drill into one agent: what it does + its recent runs and any error messages."""
    if (r := require_admin(request)):
        return r
    name = request.path_params["name"]
    if name not in AGENTS:
        return admin_page("Agent", "<p class='err'>Unknown agent.</p>", active="Agents", status=404)
    agent = AGENTS[name]
    runs = db.query("SELECT status, started_at, duration_ms, error, result FROM agent_runs "
                    "WHERE agent = %s ORDER BY started_at DESC LIMIT 30", (name,))
    rows = "".join(
        f"<tr><td class='muted'>{esc(str(r['started_at'])[:19])}</td>"
        f"<td class='{'ok' if r['status'] == 'success' else 'err'}'>{esc(r['status'])}</td>"
        f"<td>{r['duration_ms'] or ''} ms</td>"
        f"<td class='err'>{esc((r['error'] or '')[:240])}</td>"
        f"<td class='muted'>{esc(str(r['result'] or '')[:200])}</td></tr>" for r in runs)
    runbtn = ("<form method='post' action='/admin/agents' class='inline'>"
              f"<input type='hidden' name='agent' value='{esc(name)}'>"
              "<button>Run now</button></form>")
    body = (f"<p class='muted'>{esc(agent.description)} · runs {esc(_every(agent.default_interval_s))}</p>"
            f"<p>{runbtn} &nbsp; <a href='/admin/agents'>&#8249; all agents</a></p>"
            "<h3>Recent runs</h3><table><tr><th>When (UTC)</th><th>Status</th><th>Duration</th>"
            f"<th>Error</th><th>Result</th></tr>"
            f"{rows or '<tr><td colspan=5 class=muted>No runs recorded yet.</td></tr>'}</table>")
    return admin_page(f"Agent · {name}", body, active="Agents")


# ----------------------------------------------------------------------- coverage matrix
def coverage_page(request: Request) -> HTMLResponse:
    """Active listings per category x state — so you can see coverage and spot gaps to fill."""
    if (r := require_admin(request)):
        return r
    data: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for v, cfg in verticals.VERTICALS.items():
        try:
            rows = db.query(f"SELECT state, count(*) AS n FROM {cfg['table']} "
                            "WHERE deleted_at IS NULL AND is_active AND state IS NOT NULL "
                            "AND state <> '' GROUP BY state")
        except Exception:
            rows = []
        cells = {r["state"]: int(r["n"]) for r in rows}
        data[v] = cells
        totals[v] = sum(cells.values())

    state_tot: dict[str, int] = {}
    for cells in data.values():
        for st, n in cells.items():
            state_tot[st] = state_tot.get(st, 0) + n
    top_states = [s for s, _ in sorted(state_tot.items(), key=lambda x: x[1], reverse=True)[:14]]

    def _cell(n: int) -> str:
        if not n:
            return "<td style='background:#fdecec;color:#c5221f;text-align:center'>0</td>"
        bg = "#fff7e6" if n < 5 else "#eaf7ee"
        return f"<td style='background:{bg};text-align:center'>{n}</td>"
    head = "<th>Category</th>" + "".join(f"<th>{esc(s)}</th>" for s in top_states) + "<th>Total</th>"
    rows_html = ""
    for v, cfg in sorted(verticals.VERTICALS.items(), key=lambda kv: totals[kv[0]], reverse=True):
        tds = "".join(_cell(data[v].get(s, 0)) for s in top_states)
        rows_html += f"<tr><td><b>{esc(cfg['label'])}</b></td>{tds}<td><b>{totals[v]}</b></td></tr>"
    foot = ("<tr><td><b>Total</b></td>"
            + "".join(f"<td style='text-align:center'><b>{state_tot.get(s, 0)}</b></td>" for s in top_states)
            + f"<td><b>{sum(totals.values())}</b></td></tr>")
    thin = sorted(totals.items(), key=lambda kv: kv[1])[:3]
    body = (f"<p class='muted'>Active listings per category × state (top {len(top_states)} states by "
            f"volume). <span style='background:#fdecec;color:#c5221f;padding:1px 6px'>red</span> = a "
            f"gap (0). Live total: <b>{sum(totals.values()):,}</b> across <b>{len(state_tot)}</b> "
            "states. Thinnest categories: "
            + ", ".join(f"{verticals.VERTICALS[v]['label']} ({n})" for v, n in thin) + ".</p>"
            "<div style='overflow-x:auto'><table><tr>" + head + "</tr>" + rows_html + foot + "</table></div>"
            "<p class='muted' style='margin-top:10px'>Fill a gap with "
            "<code>cli collect --state &lt;ST&gt;</code> or <code>cli collect --metro &lt;name&gt;</code>.</p>")
    return admin_page("Coverage", body, active="Coverage")


# ---------------------------------------------------------------------- payments
def payments_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    fs = verticals.featured_summary()
    price = settings.stripe_price_cents / 100
    est = fs["total"] * price
    cards = "".join(f"<div class='kpi'><b>{n}</b><span>{k} featured</span></div>"
                    for k, n in fs["by_vertical"].items())
    cards += (f"<div class='kpi'><b>${est:,.0f}</b><span>Est. monthly revenue</span>"
              f"<div class='muted'>{fs['total']} × ${price:.0f}</div></div>")
    pay_tbl = "<p class='muted'>Stripe not configured — showing internal featured placements only.</p>"
    if payments.enabled():
        try:
            rows = payments.recent_payments(20)
            trs = "".join(
                f"<tr><td>{esc(str(p.get('id') or '')[:24])}</td>"
                f"<td>${(p.get('amount') or 0) / 100:.2f} {esc((p.get('currency') or '').upper())}</td>"
                f"<td>{esc(p.get('status'))}</td>"
                f"<td class='muted'>{_ts(p.get('created'))}</td></tr>"
                for p in rows)
            pay_tbl = (f"<h3>Recent Stripe payments</h3><table><tr><th>Session</th><th>Amount</th>"
                       f"<th>Status</th><th>Created (UTC)</th></tr>{trs}</table>") if rows else \
                "<p class='muted'>Stripe connected — no payments yet.</p>"
        except Exception as exc:  # never 500 the page; show the cause
            pay_tbl = (f"<p class='err'>Couldn't load Stripe payments: "
                       f"{esc(type(exc).__name__)}: {esc(str(exc))}</p>")
    return admin_page("Payments", f"<div class='cards'>{cards}</div>" + pay_tbl, active="Payments")


def _ts(epoch) -> str:
    try:
        return dt.datetime.fromtimestamp(int(epoch), tz=dt.timezone.utc).isoformat() if epoch else ""
    except (ValueError, TypeError, OSError):
        return ""


# ----------------------------------------------------------------------- traffic
def traffic_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    t = analytics.traffic_summary(days=30)
    cards = (f"<div class='kpi'><b>{t['total_calls']}</b><span>tool calls (30d)</span></div>"
             f"<div class='kpi'><b>{t['calls_today']}</b><span>today</span></div>"
             f"<div class='kpi'><b>{t['distinct_clients']}</b><span>distinct agents</span></div>")
    max_tool = max((x["n"] for x in t["by_tool"]), default=1)
    tool_rows = "".join(
        f"<tr><td>{esc(x['tool'])}</td><td>{x['n']}</td>"
        f"<td><span class='bar' style='width:{int(120 * x['n'] / max_tool)}px'></span></td>"
        f"<td class='muted'>{esc(x['last'])}</td></tr>" for x in t["by_tool"])
    client_rows = "".join(
        f"<tr><td>{esc(x['client'])}</td><td>{x['n']}</td></tr>" for x in t["by_client"])
    recent = analytics.recent_calls(40)
    rec_rows = "".join(
        f"<tr><td class='muted'>{esc(c['created_at'])}</td><td>{esc(c['tool'])}</td>"
        f"<td>{esc(c['client'] or '(unknown)')}</td><td>{esc(c['args'])}</td>"
        f"<td>{c['result_count'] if c['result_count'] is not None else ''}</td></tr>" for c in recent)
    pv = analytics.pageview_summary(days=30)
    pv_top = "".join(f"<tr><td>{esc(p['path'])}</td><td>{p['n']}</td></tr>" for p in pv["top_paths"])
    pv_spark = sparkline(analytics.pageviews_daily(30), width=280, height=44)
    pv_section = (
        "<h3>Site pageviews <span class='muted'>(first-party — counts even when GA is blocked)</span></h3>"
        f"<div class='cards'><div class='kpi act'><b>{pv['total']}</b><span>pageviews (30d)</span></div>"
        f"<div class='kpi act'><b>{pv['today']}</b><span>today</span></div>"
        + (f"<div class='kpi act' style='min-width:300px'>{pv_spark}"
           "<span>daily pageviews (30d)</span></div>" if pv_spark else "") + "</div>"
        "<div style='display:flex;gap:28px;flex-wrap:wrap'>"
        "<div><b>Top pages (30d)</b><table><tr><th>Page</th><th>Views</th></tr>"
        f"{pv_top or '<tr><td colspan=2 class=muted>No views yet.</td></tr>'}</table></div></div>")

    # View → action funnel across all listings (a health signal + owner-value proof).
    conv = analytics.conversion_summary(30)
    conv_section = (
        "<h3 style='margin-top:30px'>Listing engagement funnel <span class='muted'>(30d)</span></h3>"
        "<div class='cards'>"
        f"<div class='kpi'><b>{conv['view']}</b><span>page views</span></div>"
        f"<div class='kpi'><b>{conv['taps']}</b><span>actions (call/site/directions)</span></div>"
        f"<div class='kpi act'><b>{conv['ctr']}%</b><span>click-through</span></div>"
        f"<div class='kpi'><b>{conv['call']}</b><span>calls</span></div>"
        f"<div class='kpi'><b>{conv['website']}</b><span>website taps</span></div>"
        f"<div class='kpi'><b>{conv['directions']}</b><span>directions</span></div></div>")

    # "What to add next" teaser — the top unmet-demand searches (full list on the Misses page).
    misses = analytics.top_misses(days=60, limit=6)
    miss_rows = "".join(
        f"<tr><td><b>{esc(m['query'])}</b></td>"
        f"<td>{esc(', '.join(x for x in (m.get('city'), m.get('state')) if x))}</td>"
        f"<td>{m['n']}</td></tr>" for m in misses)
    miss_section = (
        "<h3 style='margin-top:30px'>What to add next "
        "<span class='muted'>· top zero-result searches (60d)</span></h3>"
        + (f"<table><tr><th>Query / filter</th><th>Location</th><th>Misses</th></tr>{miss_rows}</table>"
           "<p class='muted'><a href='/admin/misses'>Full unmet-demand list →</a></p>"
           if miss_rows else "<p class='muted'>No unmet-demand searches recorded yet.</p>"))

    calls_spark = sparkline(analytics.calls_daily(30), width=280, height=44)
    body = (pv_section + conv_section + miss_section
            + "<h3 style='margin-top:30px'>Agent traffic (MCP tools)</h3>"
            f"<div class='cards'>{cards}"
            + (f"<div class='kpi' style='min-width:300px'>{calls_spark}"
               "<span>daily tool calls (30d)</span></div>" if calls_spark else "") + "</div>"
            "<p class='muted'>Every AI-agent call to an MCP tool is logged here. "
            "Client/agent names appear when the agent identifies itself.</p>"
            f"<h3>By tool (30d)</h3><table><tr><th>Tool</th><th>Calls</th><th></th>"
            f"<th>Last</th></tr>{tool_rows or '<tr><td colspan=4 class=muted>No calls yet.</td></tr>'}</table>"
            f"<h3>By agent/client</h3><table><tr><th>Client</th><th>Calls</th></tr>{client_rows}</table>"
            f"<h3>Recent calls</h3><table><tr><th>When</th><th>Tool</th><th>Agent</th>"
            f"<th>Args</th><th>Results</th></tr>{rec_rows}</table>")

    top = analytics.top_listings(days=30, limit=15)
    if top:
        top_rows = ""
        for x in top:
            rec = verticals.get_record(x["vertical"], x["record_id"])
            nm = esc(rec["name"]) if rec else f"#{x['record_id']}"
            top_rows += (f"<tr><td><a href='/admin/data/{x['vertical']}/{x['record_id']}'>{nm}</a></td>"
                         f"<td class='muted'>{x['vertical']}</td><td>{x['impressions']}</td></tr>")
        body += (f"<h3>Most-shown listings (30d)</h3>"
                 "<p class='muted'>How often each listing was surfaced to an agent — a reach "
                 "signal for owners and for selling featured placement.</p>"
                 f"<table><tr><th>Listing</th><th>Vertical</th><th>Impressions</th></tr>{top_rows}</table>")
    return admin_page("Traffic", body, active="Traffic")


# ----------------------------------------------------------------------- reports
def reports_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    history = db.query("SELECT report_date, metrics FROM daily_reports "
                       "ORDER BY report_date DESC LIMIT 14")
    if not history:
        body = ("<p class='muted'>No reports yet.</p>"
                "<form method='post' action='/admin/reports'><button>Generate now</button></form>")
        return admin_page("Reports", body, active="Reports")
    latest = history[0]["metrics"]
    pre = f"<pre style='white-space:pre-wrap'>{esc(reporting.render_text({'metrics': latest, 'deltas': {}}))}</pre>"
    # Growth trend (active totals per vertical, last 14 days).
    trend_rows = ""
    for h in reversed(history):
        g = h["metrics"].get("growth", {}).get("verticals", {})
        cells = "".join(f"<td>{g.get(k, {}).get('total', 0)}</td>" for k in _VKEYS)
        trend_rows += f"<tr><td class='muted'>{h['report_date']}</td>{cells}</tr>"
    trend = (f"<h3>14-day trend (active records)</h3><table><tr><th>Date</th>"
             + "".join(f"<th>{verticals.VERTICALS[k]['label']}</th>" for k in _VKEYS)
             + f"</tr>{trend_rows}</table>")
    body = ("<form method='post' action='/admin/reports'><button>Regenerate today</button></form>"
            + pre + trend)
    return admin_page("Reports", body, active="Reports")


async def reports_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    reporting.compute_daily_report()
    return RedirectResponse("/admin/reports", status_code=303)


def _scalar(sql: str) -> int:
    row = db.query_one(sql)
    return int(list(row.values())[0]) if row else 0


def recommendations_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    from .. import assistant
    llm_on = assistant.llm_active()
    s = recommendations.summary()
    recs = recommendations.list_pending()
    rows = ""
    for x in recs:
        loc = ", ".join(f for f in (x.get("city"), x.get("state")) if f)
        tag = {"new_vertical": "🧩 new vertical", "new_topic": "❓ new topic"}.get(
            x["kind"], f"📈 {esc(x.get('vertical'))}")

        def btn(op, label, gray=False):
            return (f"<form method='post' action='/admin/recommendations' class='inline'>"
                    f"<input type='hidden' name='id' value='{x['id']}'>"
                    f"<button class='btn{' gray' if gray else ''}' name='op' value='{op}'>{label}</button></form> ")
        actions = btn("dismiss", "Dismiss", True)
        if (x.get("action") or "").startswith("scrape:"):
            actions = btn("approve_scrape", "Approve &amp; scrape") + actions
        else:
            actions = btn("approve", "Approve") + actions
        if llm_on and not x.get("research"):
            actions = btn("research", "🔎 Research") + actions
        research_html = (f"<div class='muted' style='margin-top:6px;white-space:pre-line'>"
                         f"🔎 {esc(x['research'])}</div>" if x.get("research") else "")
        rows += (f"<tr><td>{tag}<br><span class='muted'>{esc(loc)}</span></td>"
                 f"<td>{esc(x['suggestion'])}{research_html}</td><td>{x['n_misses']}</td>"
                 f"<td>{actions}</td></tr>")
    cards = (f"<div class='cards'><div class='kpi'><b>{s['pending']}</b><span>pending</span></div>"
             f"<div class='kpi'><b>{s['approved']}</b><span>approved</span></div>"
             f"<div class='kpi'><b>{s['done']}</b><span>done</span></div>"
             f"<div class='kpi'><b>{s['dismissed']}</b><span>dismissed</span></div></div>")
    table = (f"<table><tr><th>Type / area</th><th>Recommendation</th><th>Demand</th><th></th></tr>{rows}</table>"
             if rows else "<p class='muted'>No pending recommendations. The agent generates these "
             "from unanswered searches (see <a href='/admin/misses'>Misses</a>).</p>")
    research_hint = (" A free-LLM 🔎 research note (mission-fit, category & best free source) is "
                     "added automatically; use “Research” to (re)run it on any row."
                     if llm_on else " Configure an LLM to get automatic 🔎 research notes.")
    body = ("<p class='muted'>Demand-driven build suggestions, generated from searches that "
            "returned nothing. Approve to act (scrape / add / outreach), or dismiss." + research_hint
            + "</p>" + cards + table)
    return admin_page("Recommendations", body, active="Recommendations")


async def recommendations_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    try:
        rid = int(form.get("id"))
    except (TypeError, ValueError):
        return RedirectResponse("/admin/recommendations", status_code=303)
    op = form.get("op")
    if op == "approve":
        recommendations.approve(rid)
    elif op == "approve_scrape":
        recommendations.approve(rid, run_scrape=True)
    elif op == "dismiss":
        recommendations.dismiss(rid)
    elif op == "research":
        recommendations.research_one(rid)
    return RedirectResponse("/admin/recommendations", status_code=303)


def misses_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    misses = analytics.top_misses(days=60, limit=40)
    rows = "".join(
        f"<tr><td><b>{esc(m['query'])}</b></td>"
        f"<td>{esc(', '.join(x for x in (m.get('city'), m.get('state')) if x))}</td>"
        f"<td>{m['n']}</td><td>{m['sources']}</td>"
        f"<td class='muted'>{esc(str(m['last_seen'])[:16])}</td></tr>"
        for m in misses)
    body = ("<p class='muted'>Searches (from AI agents and the chatbot) that returned "
            "<b>zero</b> results in the last 60 days — your ranked “what to add next” list. "
            "Fill the top ones via <a href='/admin/data/restaurants/new'>Add listing</a>, owner "
            "<a href='/submit'>submissions</a>, or by scraping that metro.</p>"
            + (f"<table><tr><th>Query / filter</th><th>Location</th><th>Misses</th>"
               f"<th>Sources</th><th>Last</th></tr>{rows}</table>"
               if rows else "<p class='muted'>No unmet-demand searches recorded yet.</p>"))
    return admin_page("Unmet demand", body, active="Misses")


def submissions_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    s = submissions.summary()
    pend = submissions.list_pending()
    rows = ""
    for x in pend:
        p = x["payload"] if isinstance(x["payload"], dict) else {}
        loc = ", ".join(f for f in (p.get("city"), p.get("state")) if f)
        contact = " · ".join(f for f in (p.get("phone"), p.get("website")) if f)
        note = f"<div class='muted'>{esc(x.get('note'))}</div>" if x.get("note") else ""

        paid = x.get("paid_featured_days")
        paid_badge = (f" <span class='ok'>💰 Paid — {paid}d</span>" if paid else "")
        reject_confirm = (" onsubmit=\"return confirm('This submission was PAID. Rejecting it will not "
                          "refund the owner automatically — refund via Stripe first. Continue?')\""
                          if paid else "")

        def act(op, label, gray=False, form_attr=""):
            return (f"<form method='post' action='/admin/submissions' class='inline'{form_attr}>"
                    f"<input type='hidden' name='id' value='{x['id']}'>"
                    f"<button class='btn{' gray' if gray else ''}' name='op' value='{op}'>{label}</button></form> ")
        label = verticals.VERTICALS.get(x["vertical"], {}).get("label", x["vertical"])
        rows += (f"<tr><td>{esc(label)}</td>"
                 f"<td><b>{esc(p.get('name'))}</b>{paid_badge}<br><span class='muted'>{esc(loc)}</span>{note}</td>"
                 f"<td class='muted'>{esc(contact)}<br>{esc(x.get('contact_email'))}</td>"
                 f"<td>{act('approve', 'Approve &amp; publish')}"
                 f"{act('reject', 'Reject', True, reject_confirm)}</td></tr>")
    cards = (f"<div class='cards'><div class='kpi'><b>{s['pending']}</b><span>pending</span></div>"
             f"<div class='kpi'><b>{s['approved']}</b><span>approved</span></div>"
             f"<div class='kpi'><b>{s['rejected']}</b><span>rejected</span></div></div>")
    # Paid-but-rejected submissions need a manual Stripe refund — surface them so they can't be missed.
    unresolved = submissions.list_paid_unresolved()
    refund_callout = ""
    if unresolved:
        items = "".join(
            f"<li>{esc((u['payload'] or {}).get('name'))} — {u['paid_featured_days']}d paid · "
            f"<code>{esc(u.get('stripe_session_id'))}</code></li>" for u in unresolved)
        refund_callout = (f"<div class='banner warn' style='margin:10px 0'>💸 {len(unresolved)} paid "
                          f"submission(s) were rejected — refund via the Stripe dashboard (search the "
                          f"session id):<ul>{items}</ul></div>")
    table = (f"<table><tr><th>Category</th><th>Business</th><th>Contact</th><th></th></tr>{rows}</table>"
             if rows else "<p class='muted'>No pending submissions. Owners add listings at "
             "<a href='/submit'>/submit</a>.</p>")
    return admin_page("Submissions", cards + refund_callout + table, active="Submissions")


async def submissions_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    try:
        sid = int(form.get("id"))
    except (TypeError, ValueError):
        return RedirectResponse("/admin/submissions", status_code=303)
    op = form.get("op")
    if op == "approve":
        submissions.approve(sid)
    elif op == "reject":
        submissions.reject(sid)
    return RedirectResponse("/admin/submissions", status_code=303)


_REVIEW_TABS = ["pending", "published", "rejected"]


def reviews_page(request: Request) -> HTMLResponse:
    """Moderate community reviews. Clean ones auto-publish; flagged ones land in 'pending' here."""
    if (r := require_admin(request)):
        return r
    show = request.query_params.get("show") or "pending"
    if show not in _REVIEW_TABS:
        show = "pending"
    c = reviews.counts()
    items = reviews.list_by_status(show, limit=200)

    def _stars(n) -> str:
        n = int(n or 0)
        return "★" * n + "☆" * (5 - n)

    rows = ""
    for x in items:
        v, lid = x["vertical"], x["listing_id"]
        listing = reviews._listing(v, lid)
        lname = esc(listing["name"]) if listing else f"{esc(v)} #{lid}"
        link = f"<a href='/listing/{esc(v)}/{lid}' target='_blank' rel='noopener'>{lname}</a>"
        who = esc(x.get("author_name") or "Anonymous")
        text = esc((x.get("body") or "")[:600]) or "<span class='muted'>(rating only)</span>"
        flag = (f"<div class='warn'>flagged: {esc(x.get('flagged_reason'))}</div>"
                if x.get("flagged_reason") else "")

        def act(op: str, label: str, gray: bool = False) -> str:
            return (f"<form method='post' action='/admin/reviews' class='inline'>"
                    f"<input type='hidden' name='id' value='{x['id']}'>"
                    f"<input type='hidden' name='show' value='{show}'>"
                    f"<button class='btn{' gray' if gray else ''}' name='op' value='{op}'>{label}</button></form> ")
        if show == "pending":
            actions = act("approve", "Approve &amp; publish") + act("reject", "Reject", True)
        elif show == "published":
            actions = act("reject", "Remove", True)
        else:
            actions = act("approve", "Restore")
        rows += (f"<tr><td style='color:#f5a623;white-space:nowrap'>{_stars(x['rating'])}</td>"
                 f"<td>{link}<br><span class='muted'>— {who} · {esc(str(x.get('created_at'))[:16])}</span>{flag}</td>"
                 f"<td>{text}</td><td>{actions}</td></tr>")

    def _tab(name: str) -> str:
        n = c.get(name, 0)
        style = "font-weight:700;color:#c1440e" if name == show else "color:#475467"
        return f"<a href='/admin/reviews?show={name}' style='{style}'>{name.title()} ({n})</a>"

    tabs = " &nbsp;·&nbsp; ".join(_tab(t) for t in _REVIEW_TABS)
    table = (f"<table><tr><th>Rating</th><th>Listing / author</th><th>Review</th><th></th></tr>{rows}</table>"
             if rows else f"<p class='muted'>No {esc(show)} reviews.</p>")
    body = (f"<p class='muted'>Visitor star-ratings &amp; reviews. Clean ones auto-publish; spam or "
            f"abusive ones are held here for you. <b>{c.get('pending', 0)}</b> awaiting moderation.</p>"
            f"<div style='margin:10px 0 4px'>{tabs}</div>{table}")
    return admin_page("Reviews", body, active="Reviews")


async def reviews_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    show = form.get("show") if form.get("show") in _REVIEW_TABS else "pending"
    try:
        rid = int(form.get("id"))
    except (TypeError, ValueError):
        return RedirectResponse(f"/admin/reviews?show={show}", status_code=303)
    op = form.get("op")
    if op == "approve":
        reviews.approve(rid)
    elif op == "reject":
        reviews.reject(rid, reason="removed by admin")
    return RedirectResponse(f"/admin/reviews?show={show}", status_code=303)


def _qa_act(id: int, op: str, label: str, gray: bool = False) -> str:
    return (f"<form method='post' action='/admin/qa' class='inline'>"
            f"<input type='hidden' name='id' value='{id}'>"
            f"<button class='btn{' gray' if gray else ''}' name='op' value='{op}'>{label}</button></form> ")


def qa_page(request: Request) -> HTMLResponse:
    """Moderate community Q&A. Clean questions/answers auto-publish; spam/abusive ones wait here."""
    if (r := require_admin(request)):
        return r
    from .. import qa
    pq, pa = qa.list_pending_questions(), qa.list_pending_answers()
    qrows = "".join(
        f"<tr><td><a href='/q/{esc(q['slug'])}' target='_blank' rel='noopener'>{esc(q['title'])}</a>"
        + (f"<div class='warn'>flagged: {esc(q['flagged_reason'])}</div>" if q.get("flagged_reason") else "")
        + (f"<div class='muted'>{esc((q.get('body') or '')[:300])}</div>" if q.get("body") else "")
        + f"<span class='muted'>{esc(str(q.get('created_at'))[:16])}</span></td>"
        f"<td>{_qa_act(q['id'], 'approve_q', 'Approve') + _qa_act(q['id'], 'reject_q', 'Reject', True)}</td></tr>"
        for q in pq)
    arows = "".join(
        f"<tr><td><b>{esc(a['question_title'])}</b>"
        f"<div>{esc((a.get('body') or '')[:400])}</div>"
        f"<span class='muted'>— {esc(a.get('author_email') or 'anon')}</span></td>"
        f"<td>{_qa_act(a['id'], 'approve_a', 'Approve') + _qa_act(a['id'], 'reject_a', 'Reject', True)}</td></tr>"
        for a in pa)
    body = ("<p class='muted'>Community questions &amp; answers held for review (spam/abuse screened; "
            "clean ones auto-publish).</p>"
            f"<h3>Questions ({len(pq)})</h3>"
            + (f"<table><tr><th>Question</th><th></th></tr>{qrows}</table>" if qrows
               else "<p class='muted'>None pending.</p>")
            + f"<h3 style='margin-top:22px'>Answers ({len(pa)})</h3>"
            + (f"<table><tr><th>Answer</th><th></th></tr>{arows}</table>" if arows
               else "<p class='muted'>None pending.</p>"))
    return admin_page("Q&A", body, active="Q&A")


async def qa_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    from .. import qa
    form = await request.form()
    try:
        rid = int(form.get("id"))
    except (TypeError, ValueError):
        return RedirectResponse("/admin/qa", status_code=303)
    op = form.get("op")
    if op in ("approve_q", "reject_q"):
        qa.moderate_question(rid, op == "approve_q")
    elif op in ("approve_a", "reject_a"):
        qa.moderate_answer(rid, op == "approve_a")
    return RedirectResponse("/admin/qa", status_code=303)


def _ago(ts) -> str:
    import datetime
    if not ts:
        return "—"
    try:
        delta = datetime.datetime.now(datetime.timezone.utc) - ts
        if delta.days >= 1:
            return f"{delta.days}d ago"
        h = delta.seconds // 3600
        return f"{h}h ago" if h else f"{max(1, delta.seconds // 60)}m ago"
    except Exception:
        return str(ts)[:16]


def dashboard_page(request: Request) -> HTMLResponse:
    """#7: a live data dashboard — per-category freshness, the latest updated listings, KB status."""
    if (r := require_admin(request)):
        return r
    fresh, recent = "", []
    for v, cfg in verticals.VERTICALS.items():
        t = cfg["table"]
        try:
            agg = db.query_one(
                f"SELECT count(*) FILTER (WHERE deleted_at IS NULL AND is_active) AS active, "
                f"count(*) FILTER (WHERE created_at > now() - interval '7 days') AS new7, "
                f"max(updated_at) AS last FROM {t}")
        except Exception:
            continue
        fresh += (f"<tr><td><a href='/admin/data/{v}'>{esc(cfg['label'])}</a></td>"
                  f"<td>{agg['active']}</td><td>{('+' + str(agg['new7'])) if agg['new7'] else '—'}</td>"
                  f"<td class='muted'>{_ago(agg['last'])}</td></tr>")
        try:
            for r in db.query(f"SELECT name, city, state, updated_at, source_name FROM {t} "
                              f"WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 6"):
                recent.append({"vertical": v, **r})
        except Exception:
            pass
    recent = sorted((r for r in recent if r.get("updated_at")),
                    key=lambda r: r["updated_at"], reverse=True)[:25]
    rrows = "".join(
        f"<tr><td>{esc(r.get('name'))}</td><td>{esc(r['vertical'])}</td>"
        f"<td class='muted'>{esc(r.get('city'))}, {esc(r.get('state'))}</td>"
        f"<td class='muted'>{esc(r.get('source_name'))}</td>"
        f"<td class='muted'>{_ago(r.get('updated_at'))}</td></tr>" for r in recent)
    try:
        from .. import knowledge
        kb = knowledge.stats()
        kbline = (f"<div class='cards'><div class='kpi'><b>{kb['documents']}</b><span>KB documents</span></div>"
                  f"<div class='kpi'><b>{kb['chunks']}</b><span>KB chunks</span></div>"
                  f"<div class='kpi'><b>{kb['embedded_chunks']}</b><span>embedded</span></div></div>")
    except Exception:
        kbline = ""
    body = ("<p class='muted'>Live data freshness and the latest updates across the directory.</p>"
            "<h3>By category</h3>"
            f"<table><tr><th>Category</th><th>Active</th><th>New (7d)</th><th>Last updated</th></tr>{fresh}</table>"
            "<h3>Latest updated listings</h3>"
            + (f"<table><tr><th>Name</th><th>Category</th><th>Location</th><th>Source</th><th>Updated</th></tr>{rrows}</table>"
               if rrows else "<p class='muted'>No recent updates.</p>")
            + "<h3>Knowledge base (Dost's RAG)</h3>"
            + (kbline or "<p class='muted'>Empty — run <code>kb-seed</code> / <code>kb-index</code>.</p>"))
    return admin_page("Dashboard", body, active="Dashboard")


def _flagged_table(flagged: list, remove_all_op: str, *, geo: bool = False) -> str:
    """Render one flagged group as a checkbox form (remove selected / all / one-by-one)."""
    if not flagged:
        return "<p class='muted'>Nothing flagged \U0001f389 — the guardrails are holding.</p>"
    extra_head = "<th>Why</th>" if geo else ""
    rows = "".join(
        f"<tr><td><input type='checkbox' name='ids' value=\"{x['vertical']}:{x['id']}\"></td>"
        f"<td><a href='/admin/data/{x['vertical']}/{x['id']}'>{esc(x['name'])}</a></td>"
        f"<td>{esc(x['vertical'])}</td><td class='muted'>{esc(x.get('city'))}, {esc(x.get('state'))}</td>"
        + (f"<td class='muted'>{esc(x.get('reason'))}"
           + (" <b>(review)</b>" if x.get('confidence') == 'review' else "") + "</td>" if geo else "")
        + f"<td><button class='btn gray' name='one' value=\"{x['vertical']}:{x['id']}\">Remove</button></td></tr>"
        for x in flagged)
    high = sum(1 for x in flagged if x.get("confidence") != "review")
    all_label = (f"Remove all {high} confirmed" if geo else f"Remove all {len(flagged)} flagged")
    bulk = (f"<div style='margin:10px 0'><button name='op' value='remove_selected'>Remove selected</button> "
            f"<button class='btn gray' name='op' value='{remove_all_op}'>{all_label}</button></div>")
    return ("<form method='post' action='/admin/moderation'>" + bulk
            + f"<table><tr><th>{_SELECT_ALL}</th><th>Name</th><th>Category</th><th>Location</th>"
            + f"{extra_head}<th></th></tr>{rows}</table></form>")


def moderation_page(request: Request) -> HTMLResponse:
    """#5: review listings flagged as not-India-from-India OR physically outside the USA, and
    remove them (reversible)."""
    if (r := require_admin(request)):
        return r
    flagged = verticals.flagged_non_india()
    non_usa = verticals.flagged_non_usa()
    intro = ("<p class='muted'>Listings whose name suggests they are NOT India-from-India "
             "(Native American / West Indian / brand homonyms). Review and remove anything that "
             "doesn't represent India or Indians — removal is reversible. You can also remove any "
             "listing from its <a href='/admin/data/restaurants'>Data</a> page.</p>")
    geo_intro = ("<h3>Outside the USA</h3><p class='muted'>Listings that look physically outside "
                 "the USA (foreign scrape bleed). <b>Confirmed</b> = coordinates outside the US or "
                 "an explicit non-US country (safe to remove in bulk). Rows marked <b>(review)</b> "
                 "have only a softer hint — a city in India, or a non-US <i>state</i>, with no "
                 "coordinates to confirm — so eyeball those before removing. All removals are "
                 "reversible.</p>")
    body = (intro + _flagged_table(flagged, "remove_all")
            + geo_intro + _flagged_table(non_usa, "remove_all_non_usa", geo=True))
    return admin_page("Moderation", body, active="Moderation")


async def moderation_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    op = form.get("op")

    def _remove(token: str) -> None:
        v, _, sid = (token or "").partition(":")
        if v in verticals.VERTICALS and sid.isdigit():
            verticals.set_deleted(v, int(sid), True)
    if op == "remove_all":
        verticals.purge_excluded(dry_run=False)
    elif op == "remove_all_non_usa":
        verticals.purge_non_usa(dry_run=False)
    elif op == "remove_selected":
        for token in form.getlist("ids"):
            _remove(token)
    elif form.get("one"):
        _remove(form.get("one"))
    elif op == "remove":                                   # legacy: separate vertical + id fields
        v = form.get("vertical")
        try:
            rid = int(form.get("id"))
        except (TypeError, ValueError):
            rid = None
        if v in verticals.VERTICALS and rid:
            verticals.set_deleted(v, rid, True)
    return RedirectResponse("/admin/moderation", status_code=303)


# ------------------------------------------------------------------ contact messages (inbox)
def _msg_card(m: dict) -> str:
    when = str(m.get("created_at") or "")[:16]
    head = (f"<b>{esc(m.get('subject') or '(no subject)')}</b> "
            f"<span class='muted'>— {esc(m.get('name') or 'Anonymous')} &lt;{esc(m.get('email'))}&gt;"
            f" · {esc(when)} · {esc(m.get('status'))}</span>")
    bodytxt = esc(m.get("body") or "").replace("\n", "<br>")
    draft = esc(m.get("draft_reply") or "")
    return (
        "<div class='card' style='margin:12px 0'>" + head +
        f"<p style='white-space:pre-wrap;margin:8px 0;color:#333'>{bodytxt}</p>"
        "<form method='post' action='/admin/messages' style='margin:0'>"
        f"<input type='hidden' name='id' value='{m['id']}'>"
        "<label class='muted'>Reply (AI-drafted — review &amp; edit before sending):</label>"
        f"<textarea name='draft' rows='5' style='width:100%;padding:10px;border:1px solid #ccc;"
        f"border-radius:8px;font:inherit;font-size:14px'>{draft}</textarea>"
        "<div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap'>"
        "<button name='action' value='send'>Approve &amp; send</button>"
        "<button name='action' value='save' class='btn gray'>Save draft</button>"
        "<button name='action' value='draft' class='btn gray'>AI redraft</button>"
        "<button name='action' value='close' class='btn gray'>Close</button>"
        "</div></form></div>")


def messages_page(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    flash = {"sent": "<p class='ok'>&#10003; Reply sent.</p>",
             "smtp": "<p class='err'>Saved, but SMTP isn't configured — set SMTP_* to actually send.</p>",
             "empty": "<p class='err'>Add a reply before sending.</p>",
             "reopened": "<p class='ok'>Re-opened for a follow-up — edit the reply below and re-send.</p>",
             }.get(request.query_params.get("flash"), "")
    show = request.query_params.get("show", "needs")
    if show not in ("needs", "replied", "auto", "all"):
        show = "needs"
    pending = inbox.list_messages("drafted") + inbox.list_messages("new")   # drafted first
    recent = inbox.recent_replies(40)

    def _tab(key: str, label: str) -> str:
        on = " style='background:var(--brand);color:#fff;border-color:var(--brand)'" if show == key else ""
        return f"<a class='btn gray'{on} href='/admin/messages?show={key}'>{esc(label)}</a>"
    tabs = ("<div style='display:flex;gap:6px;flex-wrap:wrap;margin:10px 0'>"
            + _tab("needs", f"Needs you ({len(pending)})") + _tab("replied", "Replied")
            + _tab("auto", "Auto-replied") + _tab("all", "All") + "</div>")
    body = flash + ("<p class='muted'>The agent auto-replies to clearly-routine notes (a copy is kept "
                    "here + emailed to you) and drafts the rest for your review. Sensitive topics "
                    "always wait for you.</p>") + tabs

    if show in ("needs", "all"):
        if pending:
            body += f"<h3>Needs a reply ({len(pending)})</h3>" + "".join(_msg_card(m) for m in pending)
        elif show == "needs":
            body += "<p class='ok'>&#10003; Nothing waiting — you're all caught up.</p>"
    if show == "auto":
        rep = [m for m in recent if m.get("status") == "auto_replied"]
    elif show == "replied":
        rep = [m for m in recent if m.get("status") == "replied"]
    elif show == "all":
        rep = recent
    else:
        rep = []
    if rep:
        def _rrow(m: dict) -> str:
            by = "&#129302; auto" if m.get("status") == "auto_replied" else "&#9995; you"
            act = ("<form method='post' action='/admin/messages' class='inline'>"
                   f"<input type='hidden' name='id' value='{m['id']}'>"
                   "<button class='btn gray' name='action' value='followup'>Follow up</button></form>")
            return (f"<tr><td>{esc(str(m.get('reply_sent_at') or '')[:16])}</td>"
                    f"<td>{esc(m.get('email'))}</td><td>{esc(m.get('subject') or '')}</td>"
                    f"<td>{by}</td><td>{act}</td></tr>")
        rows = "".join(_rrow(m) for m in rep)
        body += ("<h3>Replied <span class='muted'>(your reference copy)</span></h3>"
                 "<p class='muted'>Auto-reply look wrong? “Follow up” re-opens it so you can correct "
                 "and re-send.</p>"
                 f"<table><tr><th>When</th><th>To</th><th>Subject</th><th>By</th><th></th></tr>{rows}</table>")
    return admin_page("Messages", body, active="Messages")


async def messages_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    try:
        mid = int(form.get("id"))
    except (TypeError, ValueError):
        return RedirectResponse("/admin/messages", status_code=303)
    action = form.get("action")
    draft = (form.get("draft") or "").strip()
    m = inbox.get_message(mid)
    if not m:
        return RedirectResponse("/admin/messages", status_code=303)
    flash = ""
    if action == "send":
        if not draft:
            flash = "empty"
        else:
            inbox.set_draft(mid, draft)
            sent = False
            try:
                sent = outreach.send_email(m["email"], f"Re: {m.get('subject') or 'your message'}", draft)
            except Exception:
                sent = False
            if sent:
                inbox.mark_replied(mid)
                flash = "sent"
            else:
                flash = "smtp"
    elif action == "save":
        inbox.set_draft(mid, draft)
    elif action == "draft":
        new_draft = inbox.compose_draft(m)
        inbox.set_draft(mid, new_draft or draft or "")
    elif action == "followup":                            # an auto-reply was wrong -> re-open it
        inbox.set_status(mid, "drafted")
        flash = "reopened"
    elif action == "close":
        inbox.set_status(mid, "closed")
    return RedirectResponse(f"/admin/messages?flash={flash}" if flash else "/admin/messages",
                            status_code=303)


# ------------------------------------------------------------------ operations (agentic overview)
def _every(secs: int) -> str:
    if secs % 86400 == 0:
        d = secs // 86400
        return {1: "daily", 7: "weekly", 30: "monthly", 90: "quarterly"}.get(d, f"every {d} days")
    if secs % 3600 == 0:
        h = secs // 3600
        return "hourly" if h == 1 else f"every {h}h"
    if secs % 60 == 0:
        return f"every {secs // 60} min"
    return f"every {secs}s"


def ops_page(request: Request) -> HTMLResponse:
    """What the agents run autonomously, what's escalated to you, and what only you can do."""
    if (r := require_admin(request)):
        return r
    # 1) Open escalations (critical first) — agents raise these only when a human is needed.
    alerts = db.query("SELECT id, severity, kind, message FROM agent_alerts WHERE NOT resolved "
                      "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
                      "created_at DESC")
    if alerts:
        arows = "".join(
            f"<tr><td class=\"{'err' if a['severity']=='critical' else ('warn' if a['severity']=='warning' else 'muted')}\">"
            f"{esc(a['severity'])}</td><td>{esc(a['message'])}</td>"
            f"<td><form method='post' action='/admin/agents' class='inline'>"
            f"<input type='hidden' name='resolve' value='{a['id']}'>"
            f"<button class='btn gray'>Resolve</button></form></td></tr>" for a in alerts)
        alerts_html = (f"<table><tr><th>Severity</th><th>What needs attention</th><th></th></tr>"
                       f"{arows}</table>")
    else:
        alerts_html = ("<p class='ok'>&#10003; Nothing needs your attention right now — the agents "
                       "are handling it.</p>")

    # 2) Your queues — the only recurring manual work (live counts).
    msgs = _scalar("SELECT count(*) FROM contact_messages WHERE status IN ('new','drafted')")
    appr = _scalar("SELECT count(*) FROM approval_queue WHERE status='pending'")
    subs = _scalar("SELECT count(*) FROM submissions WHERE status='pending'")
    fb = _scalar("SELECT count(*) FROM feedback WHERE status='pending'")
    revs = _scalar("SELECT count(*) FROM reviews WHERE status='pending'")

    def q(n: int, label: str, href: str) -> str:
        return f"<a class='kpi act' href='{href}'><b>{n}</b><span>{esc(label)}</span></a>"
    queues = (q(msgs, "Reply to messages", "/admin/messages") + q(appr, "Review approvals", "/admin/approvals")
              + q(subs, "Review submissions", "/admin/submissions") + q(fb, "Review corrections", "/admin/feedback")
              + q(revs, "Moderate reviews", "/admin/reviews"))

    # 3) Agent roster — what each agent does continuously (self-documenting from the registry).
    last = {r["agent"]: r for r in db.query(
        "SELECT DISTINCT ON (agent) agent, status, started_at FROM agent_runs "
        "ORDER BY agent, started_at DESC")}
    rrows = ""
    for name, agent in AGENTS.items():
        r = last.get(name)
        when = (f"<span class='{'ok' if r['status']=='success' else 'err'}'>{esc(r['status'])}</span> "
                f"<span class='muted'>{esc(str(r['started_at'])[:16])}</span>") if r else \
               "<span class='muted'>not yet run</span>"
        rrows += (f"<tr><td><b>{esc(name)}</b></td><td>{esc(agent.description)}</td>"
                  f"<td class='muted'>{esc(_every(agent.default_interval_s))}</td><td>{when}</td></tr>")
    roster = (f"<table><tr><th>Agent</th><th>What it does (continuously)</th><th>Runs</th>"
              f"<th>Last run</th></tr>{rrows}</table>")

    note = ("<p class='muted'>The agents run on their own schedule — they discover, scrape, clean, "
            "enrich, geo-locate, rank, index knowledge, learn from searches, draft message replies, "
            "and watch for problems — and they <b>escalate to you</b> only when a human is required "
            "(top). Your recurring job is just the queues above; everything else is automatic. "
            "Drafts and submissions are <b>never published or sent</b> without your approval.</p>")
    body = (f"<h3>&#128680; Needs your attention</h3>{alerts_html}"
            f"<h3>Your queues</h3><div class='cards'>{queues}</div>"
            f"<h3>What the agents do ({len(AGENTS)} agents)</h3>{note}{roster}")
    return admin_page("Operations", body, active="Operations")


routes = [
    Route("/admin/login", login_get, methods=["GET"]),
    Route("/admin/login", login_post, methods=["POST"]),
    Route("/admin/logout", logout, methods=["GET"]),
    Route("/admin", overview, methods=["GET"]),
    Route("/admin/ops", ops_page, methods=["GET"]),
    Route("/admin/dashboard", dashboard_page, methods=["GET"]),
    Route("/admin/data", unified_search, methods=["GET"]),
    Route("/admin/moderation", moderation_page, methods=["GET"]),
    Route("/admin/moderation", moderation_action, methods=["POST"]),
    Route("/admin/coverage", coverage_page, methods=["GET"]),
    Route("/admin/messages", messages_page, methods=["GET"]),
    Route("/admin/messages", messages_action, methods=["POST"]),
    Route("/admin/data/{vertical}", data_list, methods=["GET"]),
    Route("/admin/data/{vertical}/new", data_new, methods=["GET"]),
    Route("/admin/data/{vertical}/new", data_create, methods=["POST"]),
    Route("/admin/geo/{vertical}", geo_page, methods=["GET"]),
    Route("/admin/quality/{vertical}", quality_page, methods=["GET"]),
    Route("/admin/quality", quality_action, methods=["POST"]),
    Route("/admin/quality/merge", quality_merge, methods=["POST"]),
    Route("/admin/data/{vertical}/{id:int}", data_detail, methods=["GET"]),
    Route("/admin/data/{vertical}/{id:int}", data_edit, methods=["POST"]),
    Route("/admin/data/{vertical}/{id:int}/action", data_action, methods=["POST"]),
    Route("/admin/approvals", approvals, methods=["GET"]),
    Route("/admin/approvals", approvals_action, methods=["POST"]),
    Route("/admin/feedback", feedback_list, methods=["GET"]),
    Route("/admin/feedback", feedback_action, methods=["POST"]),
    Route("/admin/events", events_page, methods=["GET"]),
    Route("/admin/events", events_action, methods=["POST"]),
    Route("/admin/claims", claims, methods=["GET"]),
    Route("/admin/submissions", submissions_page, methods=["GET"]),
    Route("/admin/submissions", submissions_action, methods=["POST"]),
    Route("/admin/reviews", reviews_page, methods=["GET"]),
    Route("/admin/reviews", reviews_action, methods=["POST"]),
    Route("/admin/qa", qa_page, methods=["GET"]),
    Route("/admin/qa", qa_action, methods=["POST"]),
    Route("/admin/agents", agents_page, methods=["GET"]),
    Route("/admin/agents", agents_action, methods=["POST"]),
    Route("/admin/agents/{name}", agent_detail, methods=["GET"]),
    Route("/admin/traffic", traffic_page, methods=["GET"]),
    Route("/admin/misses", misses_page, methods=["GET"]),
    Route("/admin/recommendations", recommendations_page, methods=["GET"]),
    Route("/admin/recommendations", recommendations_action, methods=["POST"]),
    Route("/admin/payments", payments_page, methods=["GET"]),
    Route("/admin/reports", reports_page, methods=["GET"]),
    Route("/admin/reports", reports_action, methods=["POST"]),
]
