"""Daily health & growth report (blueprint: monitoring + growth pulse).

compute_daily_report() snapshots the system into daily_reports (one row/day, upsert), with
deltas vs the previous day. email_daily_report() sends a plain-text summary via SMTP when
configured. Surfaced on /admin/reports and runnable via `cli report`.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from . import db
from .config import settings
from .pipeline import outreach
from .verticals import VERTICALS

# (canonical table, raw table) per vertical for backlog/growth counts.
_RAW = {"restaurants": "restaurant_raw", "temples": "temple_raw", "groceries": "grocery_raw",
        "professionals": "professional_raw", "salons": "salon_raw", "events": "event_raw",
        "apparel": "apparel_raw", "sweets": "sweets_raw", "studios": "studio_raw",
        "services": "service_raw", "community": "community_raw", "legal": "legal_raw",
        "education": "education_raw", "realestate": "realestate_raw", "finance": "finance_raw"}


def _scalar(sql: str, params=None) -> int:
    row = db.query_one(sql, params)
    return int(list(row.values())[0]) if row and list(row.values())[0] is not None else 0


def compute_daily_report() -> dict[str, Any]:
    """Compute today's metrics, store them, and return {metrics, deltas}."""
    health: dict[str, Any] = {}
    growth: dict[str, Any] = {}

    # ---- Health: agents (last 24h) ----
    health["agent_runs_24h"] = _scalar(
        "SELECT count(*) FROM agent_runs WHERE started_at > now() - interval '24 hours'")
    health["agent_errors_24h"] = _scalar(
        "SELECT count(*) FROM agent_runs WHERE status='error' AND started_at > now() - interval '24 hours'")
    health["open_alerts"] = _scalar("SELECT count(*) FROM agent_alerts WHERE NOT resolved")
    health["approvals_pending"] = _scalar(
        "SELECT count(*) FROM approval_queue WHERE status='pending'")
    health["feedback_pending"] = _scalar(
        "SELECT count(*) FROM feedback WHERE status='pending'")
    health["tool_calls_24h"] = _scalar(
        "SELECT count(*) FROM tool_log WHERE created_at > now() - interval '24 hours'")

    # ---- Per-vertical totals + today's new (growth) + raw backlog (health) ----
    per_vertical = {}
    for key, cfg in VERTICALS.items():
        table = cfg["table"]
        per_vertical[key] = {
            "total": _scalar(f"SELECT count(*) FROM {table} WHERE deleted_at IS NULL AND is_active"),
            "new_today": _scalar(
                f"SELECT count(*) FROM {table} WHERE created_at::date = current_date"),
            "claimed": _scalar(f"SELECT count(*) FROM {table} WHERE is_claimed"),
            "featured": _scalar(
                f"SELECT count(*) FROM {table} WHERE is_featured "
                f"AND (featured_until IS NULL OR featured_until > now())"),
        }
        health.setdefault("raw_backlog", {})[key] = _scalar(
            f"SELECT count(*) FROM {_RAW[key]} WHERE NOT processed")
    growth["verticals"] = per_vertical
    growth["claims_today"] = _scalar(
        "SELECT count(*) FROM claims WHERE claimed_at::date = current_date")
    growth["featured_total"] = sum(v["featured"] for v in per_vertical.values())

    metrics = {"health": health, "growth": growth}

    # Deltas vs the most recent previous report.
    prev = db.query_one(
        "SELECT metrics FROM daily_reports WHERE report_date < current_date "
        "ORDER BY report_date DESC LIMIT 1")
    deltas = _deltas(metrics, prev["metrics"] if prev else None)

    db.execute(
        "INSERT INTO daily_reports (report_date, metrics) VALUES (current_date, %s) "
        "ON CONFLICT (report_date) DO UPDATE SET metrics = EXCLUDED.metrics, created_at = now()",
        (Jsonb(metrics),))
    return {"metrics": metrics, "deltas": deltas}


def _deltas(today: dict, prev: dict | None) -> dict[str, Any]:
    if not prev:
        return {}
    out = {}
    for key in today["growth"]["verticals"]:
        now_t = today["growth"]["verticals"][key]["total"]
        prev_t = prev.get("growth", {}).get("verticals", {}).get(key, {}).get("total", now_t)
        out[key] = now_t - prev_t
    return out


def email_daily_report(report: dict | None = None) -> bool:
    """Email the daily summary via SMTP. No-op (returns False) if email isn't configured."""
    if not settings.email_enabled:
        return False
    report = report or compute_daily_report()
    to = settings.report_email or settings.outreach_contact_email
    return outreach.send_email(to, f"{settings.platform_name} — daily report", render_text(report))


def render_text(report: dict) -> str:
    m, d = report["metrics"], report.get("deltas", {})
    h, g = m["health"], m["growth"]
    lines = [f"{settings.platform_name} — daily report", ""]
    lines.append("DATA (active / +today / claimed / featured):")
    for key, v in g["verticals"].items():
        delta = d.get(key, 0)
        sign = f" (+{delta})" if delta > 0 else (f" ({delta})" if delta else "")
        lines.append(f"  {key:<12} {v['total']}{sign}  +{v['new_today']} today  "
                     f"{v['claimed']} claimed  {v['featured']} featured")
    lines += ["", "HEALTH:",
              f"  agent runs 24h: {h['agent_runs_24h']}  errors: {h['agent_errors_24h']}",
              f"  open alerts: {h['open_alerts']}",
              f"  pending approvals: {h['approvals_pending']}  feedback: {h['feedback_pending']}",
              f"  agent tool-calls (24h): {h.get('tool_calls_24h', 0)}",
              f"  raw backlog: {h.get('raw_backlog', {})}",
              "", f"Featured (live paid placements): {g['featured_total']}",
              f"New claims today: {g['claims_today']}"]
    return "\n".join(lines)
