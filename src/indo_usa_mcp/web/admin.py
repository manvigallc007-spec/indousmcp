"""Admin dashboard routes (password-gated). Mounted under /admin."""

from __future__ import annotations

import datetime as dt

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import db, payments, quality, reporting, verticals
from ..agents import AGENTS, run_agent
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
    form = await request.form()
    if login_admin(request, (form.get("password") or "")):
        return RedirectResponse("/admin", status_code=303)
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
    body = (f"<p>{tabs}</p><p class='muted'>Filter: {filters} · "
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
    dtr = "".join(
        f"<tr><td>{esc(d['name'])}</td><td>{esc(d['city'])}, {esc(d['state'])}</td><td>{d['n']}</td>"
        f"<td>{' '.join(f'<a href=\"/admin/data/{vertical}/{i}\">#{i}</a>' for i in d['ids'])}</td></tr>"
        for d in dupes)
    body = (f"<p>{tabs}</p><p class='muted'>{s['total']} active records · "
            "click an issue to see affected records, then fix them inline.</p>"
            f"<div class='cards'>{cards}</div>"
            "<p><form method='post' action='/admin/quality' class='inline'>"
            f"<input type='hidden' name='vertical' value='{vertical}'>"
            "<button>Normalize city/state now</button></form></p>"
            + (f"<h3>Possible duplicates ({len(dupes)})</h3><table><tr><th>Name</th>"
               f"<th>Location</th><th>Count</th><th>Records</th></tr>{dtr}</table>" if dupes else
               "<p class='muted'>No duplicate groups found.</p>"))
    return admin_page(f"Quality · {verticals.VERTICALS[vertical]['label']}", body, active="Quality")


async def quality_action(request: Request) -> HTMLResponse:
    if (r := require_admin(request)):
        return r
    vertical = (await request.form()).get("vertical")
    if vertical in verticals.VERTICALS:
        verticals.normalize_geography(vertical)
    return RedirectResponse(f"/admin/quality/{vertical}", status_code=303)


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
    pay_tbl = ""
    if payments.enabled():
        rows = payments.recent_payments(20)
        trs = "".join(
            f"<tr><td>{esc(p['id'][:24])}</td>"
            f"<td>${(p['amount'] or 0)/100:.2f} {esc((p['currency'] or '').upper())}</td>"
            f"<td>{esc(p['status'])}</td>"
            f"<td class='muted'>{dt.datetime.utcfromtimestamp(p['created']).isoformat() if p['created'] else ''}</td></tr>"
            for p in rows)
        pay_tbl = (f"<h3>Recent Stripe payments</h3><table><tr><th>Session</th><th>Amount</th>"
                   f"<th>Status</th><th>Created (UTC)</th></tr>{trs}</table>") if rows else \
            "<p class='muted'>No Stripe payments yet.</p>"
    else:
        pay_tbl = "<p class='muted'>Stripe not configured — showing internal featured placements only.</p>"
    return admin_page("Payments", f"<div class='cards'>{cards}</div>" + pay_tbl, active="Payments")


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


routes = [
    Route("/admin/login", login_get, methods=["GET"]),
    Route("/admin/login", login_post, methods=["POST"]),
    Route("/admin/logout", logout, methods=["GET"]),
    Route("/admin", overview, methods=["GET"]),
    Route("/admin/data/{vertical}", data_list, methods=["GET"]),
    Route("/admin/geo/{vertical}", geo_page, methods=["GET"]),
    Route("/admin/quality/{vertical}", quality_page, methods=["GET"]),
    Route("/admin/quality", quality_action, methods=["POST"]),
    Route("/admin/data/{vertical}/{id:int}", data_detail, methods=["GET"]),
    Route("/admin/data/{vertical}/{id:int}", data_edit, methods=["POST"]),
    Route("/admin/data/{vertical}/{id:int}/action", data_action, methods=["POST"]),
    Route("/admin/approvals", approvals, methods=["GET"]),
    Route("/admin/approvals", approvals_action, methods=["POST"]),
    Route("/admin/feedback", feedback_list, methods=["GET"]),
    Route("/admin/feedback", feedback_action, methods=["POST"]),
    Route("/admin/claims", claims, methods=["GET"]),
    Route("/admin/agents", agents_page, methods=["GET"]),
    Route("/admin/agents", agents_action, methods=["POST"]),
    Route("/admin/payments", payments_page, methods=["GET"]),
    Route("/admin/reports", reports_page, methods=["GET"]),
    Route("/admin/reports", reports_action, methods=["POST"]),
]
