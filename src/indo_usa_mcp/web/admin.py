"""Admin dashboard routes (password-gated). Mounted under /admin."""

from __future__ import annotations

import datetime as dt

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import analytics, db, payments, quality, recommendations, reporting, submissions, verticals
from ..agents import AGENTS, run_agent
from ..events import pipeline as events
from ..config import settings
from ..pipeline import ingest
from .auth import admin_enabled, login_admin, logout_admin, require_admin
from .common import _page, admin_page, esc

_VKEYS = list(verticals.VERTICALS)


# ------------------------------------------------------------------------- login
def login_get(request: Request) -> HTMLResponse:
    if not admin_enabled():
        return _page("Admin disabled", "<h2>Admin is disabled</h2>"
                     "<p class='muted'>Set ADMIN_PASSWORD to enable the dashboard.</p>", status=503)
    return _page("Admin login",
                 "<h2>Admin login</h2><form method='post' action='/admin/login'>"
                 "<label>Password</label><input name='password' type='password' autofocus>"
                 "<button type='submit'>Sign in</button></form>")


async def login_post(request: Request) -> HTMLResponse:
    from .security import too_many_attempts, record_attempt, clear_attempts
    ip = (request.client.host if request.client else "?") or "?"
    if too_many_attempts(ip):
        return _page("Admin login", "<h2 class='err'>Too many attempts</h2>"
                     "<p class='muted'>Please wait a few minutes and try again.</p>", status=429)
    form = await request.form()
    if login_admin(request, (form.get("password") or "")):
        clear_attempts(ip)
        return RedirectResponse("/admin", status_code=303)
    record_attempt(ip)
    return _page("Admin login", "<h2 class='err'>Wrong password</h2>"
                 "<p><a href='/admin/login'>Try again</a></p>", status=401)


def logout(request: Request) -> RedirectResponse:
    logout_admin(request)
    return RedirectResponse("/admin/login", status_code=303)


# ----------------------------------------------------------------------- overview
def overview(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    cards = []
    for key, cfg in verticals.VERTICALS.items():
        total = verticals.count_records(key)
        feat = verticals.count_records(key, flt="featured")
        claimed = verticals.count_records(key, flt="claimed")
        cards.append(f"<div class='kpi'><b>{total}</b><span>{cfg['label']}</span>"
                     f"<div class='muted'>{feat} featured · {claimed} claimed</div></div>")
    pend_appr = _scalar("SELECT count(*) FROM approval_queue WHERE status='pending'")
    pend_fb = _scalar("SELECT count(*) FROM feedback WHERE status='pending'")
    alerts = _scalar("SELECT count(*) FROM agent_alerts WHERE NOT resolved")
    errs = _scalar("SELECT count(*) FROM agent_runs WHERE status='error' AND started_at > now() - interval '24 hours'")
    cards.append(f"<div class='kpi'><b>{pend_appr}</b><span>Pending approvals</span></div>")
    cards.append(f"<div class='kpi'><b>{pend_fb}</b><span>Pending feedback</span></div>")
    cards.append(f"<div class='kpi'><b class='{'err' if alerts else ''}'>{alerts}</b><span>Open alerts</span></div>")
    cards.append(f"<div class='kpi'><b class='{'err' if errs else ''}'>{errs}</b><span>Agent errors (24h)</span></div>")

    agents_tbl = _agent_health_table()
    body = (f"<div class='cards'>{''.join(cards)}</div>"
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
            rows += (f"<tr><td>{name}</td><td class='{cls}'>{r['status']}</td>"
                     f"<td class='muted'>{esc(r['started_at'])}</td>"
                     f"<td class='muted'>{r['duration_ms'] or ''} ms</td></tr>")
        else:
            rows += f"<tr><td>{name}</td><td class='muted'>never run</td><td></td><td></td></tr>"
    return f"<table><tr><th>Agent</th><th>Last status</th><th>When</th><th>Duration</th></tr>{rows}</table>"


# --------------------------------------------------------------------- data browse
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
def approvals(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    digest = ingest.summarize_approvals(limit=100)
    trs = "".join(
        f"<tr><td>{it['id']}</td><td>{it['change_type']}</td>"
        f"<td class='{'warn' if it['risk']=='high' else ''}'>{it['risk']}</td>"
        f"<td>{it['confidence']}</td><td>{esc(it['summary'])}</td>"
        f"<td>{_approve_btns(it['id'])}</td></tr>" for it in digest["items"])
    body = (f"<p class='muted'>{digest['pending']} pending · by risk {digest['by_risk']}</p>"
            f"<table><tr><th>ID</th><th>Type</th><th>Risk</th><th>Conf</th><th>Summary</th>"
            f"<th></th></tr>{trs}</table>")
    return admin_page("Approvals", body, active="Approvals")


def _approve_btns(aid: int) -> str:
    return (f"<form method='post' action='/admin/approvals' class='inline'>"
            f"<input type='hidden' name='id' value='{aid}'><input type='hidden' name='op' value='approve'>"
            f"<button>Approve</button></form> "
            f"<form method='post' action='/admin/approvals' class='inline'>"
            f"<input type='hidden' name='id' value='{aid}'><input type='hidden' name='op' value='reject'>"
            f"<button class='btn gray'>Reject</button></form>")


async def approvals_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    form = await request.form()
    aid, op = int(form.get("id")), form.get("op")
    if op == "approve":
        ingest.apply_approval(aid, reviewed_by="admin")
    else:
        ingest.reject_approval(aid, reviewed_by="admin")
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
    day_rows = "".join(f"<tr><td class='muted'>{x['day']}</td><td>{x['n']}</td></tr>"
                       for x in t["by_day"])
    recent = analytics.recent_calls(40)
    rec_rows = "".join(
        f"<tr><td class='muted'>{esc(c['created_at'])}</td><td>{esc(c['tool'])}</td>"
        f"<td>{esc(c['client'] or '(unknown)')}</td><td>{esc(c['args'])}</td>"
        f"<td>{c['result_count'] if c['result_count'] is not None else ''}</td></tr>" for c in recent)
    body = (f"<div class='cards'>{cards}</div>"
            "<p class='muted'>Every AI-agent call to an MCP tool is logged here. "
            "Client/agent names appear when the agent identifies itself.</p>"
            f"<h3>By tool (30d)</h3><table><tr><th>Tool</th><th>Calls</th><th></th>"
            f"<th>Last</th></tr>{tool_rows or '<tr><td colspan=4 class=muted>No calls yet.</td></tr>'}</table>"
            f"<h3>By agent/client</h3><table><tr><th>Client</th><th>Calls</th></tr>{client_rows}</table>"
            f"<h3>By day</h3><table><tr><th>Day</th><th>Calls</th></tr>{day_rows}</table>"
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

        def act(op, label, gray=False):
            return (f"<form method='post' action='/admin/submissions' class='inline'>"
                    f"<input type='hidden' name='id' value='{x['id']}'>"
                    f"<button class='btn{' gray' if gray else ''}' name='op' value='{op}'>{label}</button></form> ")
        label = verticals.VERTICALS.get(x["vertical"], {}).get("label", x["vertical"])
        rows += (f"<tr><td>{esc(label)}</td>"
                 f"<td><b>{esc(p.get('name'))}</b><br><span class='muted'>{esc(loc)}</span>{note}</td>"
                 f"<td class='muted'>{esc(contact)}<br>{esc(x.get('contact_email'))}</td>"
                 f"<td>{act('approve', 'Approve &amp; publish')}{act('reject', 'Reject', True)}</td></tr>")
    cards = (f"<div class='cards'><div class='kpi'><b>{s['pending']}</b><span>pending</span></div>"
             f"<div class='kpi'><b>{s['approved']}</b><span>approved</span></div>"
             f"<div class='kpi'><b>{s['rejected']}</b><span>rejected</span></div></div>")
    table = (f"<table><tr><th>Category</th><th>Business</th><th>Contact</th><th></th></tr>{rows}</table>"
             if rows else "<p class='muted'>No pending submissions. Owners add listings at "
             "<a href='/submit'>/submit</a>.</p>")
    return admin_page("Submissions", cards + table, active="Submissions")


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


routes = [
    Route("/admin/login", login_get, methods=["GET"]),
    Route("/admin/login", login_post, methods=["POST"]),
    Route("/admin/logout", logout, methods=["GET"]),
    Route("/admin", overview, methods=["GET"]),
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
    Route("/admin/agents", agents_page, methods=["GET"]),
    Route("/admin/agents", agents_action, methods=["POST"]),
    Route("/admin/traffic", traffic_page, methods=["GET"]),
    Route("/admin/misses", misses_page, methods=["GET"]),
    Route("/admin/recommendations", recommendations_page, methods=["GET"]),
    Route("/admin/recommendations", recommendations_action, methods=["POST"]),
    Route("/admin/payments", payments_page, methods=["GET"]),
    Route("/admin/reports", reports_page, methods=["GET"]),
    Route("/admin/reports", reports_action, methods=["POST"]),
]
