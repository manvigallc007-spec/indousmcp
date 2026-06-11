"""Concrete agents wrapping the pipeline (blueprint's initial set).

Implemented here: Discovery, Scraper, Cleaner, Outreach, Monitoring, Submission.
(Approval-Assistant and Feedback agents are thin and deferred until there's a UI/
feedback channel to summarise for.)
"""

from __future__ import annotations

from typing import Any

from .. import db
from ..pipeline import ingest, outreach
from ..pipeline.scrapers import SCRAPERS
from ..pipeline.scrapers.metros import METROS
from .base import Agent


class DiscoveryAgent(Agent):
    name = "discovery"
    description = "Finds metros/sources needing coverage; proposes scrape targets."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        # Coverage per metro from canonical data; flag thin/never-scraped metros.
        coverage = {m: 0 for m in METROS}
        rows = db.query(
            "SELECT city, state, count(*) AS n FROM restaurants "
            "WHERE deleted_at IS NULL GROUP BY city, state"
        )
        total = sum(r["n"] for r in rows)
        targets = [
            {"metro": m, "known": coverage[m], "sources": sorted(SCRAPERS)}
            for m in METROS
            if coverage[m] < params.get("min_per_metro", 10)
        ]
        return {"total_restaurants": total, "metros": len(METROS), "suggested_targets": targets}


class ScraperAgent(Agent):
    name = "scraper"
    description = "Runs every scraper across every metro into restaurant_raw."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        sources = params.get("sources") or list(SCRAPERS)
        per_source: dict[str, int] = {}
        errors: list[dict[str, str]] = []
        for source in sources:
            for metro in metros:
                try:
                    n = ingest.scrape_to_raw(source, metro)
                    per_source[source] = per_source.get(source, 0) + n
                except Exception as exc:  # one bad source/metro shouldn't halt the rest
                    errors.append({"source": source, "metro": metro, "error": str(exc)})
        return {"upserted": per_source, "errors": errors}


class CleanerAgent(Agent):
    name = "cleaner"
    description = "Processes raw rows into canonical via clean/score/approval."
    default_interval_s = 3600

    def run(self, **params: Any) -> dict[str, Any]:
        return ingest.process_raw()


class EnrichmentAgent(Agent):
    name = "enrichment"
    description = "Backfills cultural tags (region, dietary) on under-tagged restaurants."
    default_interval_s = 43200

    def run(self, **params: Any) -> dict[str, Any]:
        return ingest.enrich_existing()


class OutreachAgent(Agent):
    name = "outreach"
    description = "Drafts claim outreach for eligible unclaimed restaurants."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        return outreach.run_outreach(
            limit=params.get("limit", 20),
            min_confidence=params.get("min_confidence", 0.5),
        )


class SubmissionAgent(Agent):
    name = "submission"
    description = "Submits the MCP to directories/registries (manual stub for now)."
    default_interval_s = 604800

    # Real submission needs per-directory integrations + human review; we record intent.
    _TARGETS = ["mcp-registry", "awesome-mcp-servers", "smithery"]

    def run(self, **params: Any) -> dict[str, Any]:
        return {
            "status": "manual_required",
            "targets": self._TARGETS,
            "note": "Auto-submission disabled; queue these for human submission.",
        }


class MonitoringAgent(Agent):
    name = "monitoring"
    description = "Detects anomalies (backlogs, scraper failures, stale data) -> alerts."
    default_interval_s = 1800

    def run(self, **params: Any) -> dict[str, Any]:
        alerts: list[dict[str, Any]] = []

        backlog = _scalar("SELECT count(*) FROM restaurant_raw WHERE NOT processed")
        if backlog > params.get("backlog_threshold", 500):
            alerts.append(_alert("warning", "raw_backlog", f"{backlog} unprocessed raw rows"))

        pending = _scalar("SELECT count(*) FROM approval_queue WHERE status='pending'")
        if pending > params.get("approval_threshold", 100):
            alerts.append(_alert("warning", "approval_backlog", f"{pending} pending approvals"))

        # Scraper runs in the last day that errored or returned nothing.
        bad = db.query(
            "SELECT agent, status, result, error FROM agent_runs "
            "WHERE agent = 'scraper' AND started_at > now() - interval '1 day' "
            "AND (status = 'error' OR result IS NULL) ORDER BY started_at DESC LIMIT 5"
        )
        if bad:
            alerts.append(_alert("critical", "scraper_failure", f"{len(bad)} bad scraper run(s)"))

        # Data going stale: nothing re-seen in 30 days.
        stale = _scalar(
            "SELECT count(*) FROM restaurants WHERE deleted_at IS NULL "
            "AND last_seen_at < now() - interval '30 days'"
        )
        if stale > params.get("stale_threshold", 1000):
            alerts.append(_alert("info", "stale_data", f"{stale} listings not re-seen in 30d"))

        for a in alerts:
            db.execute(
                "INSERT INTO agent_alerts (severity, kind, message, details) VALUES (%s,%s,%s,%s)",
                (a["severity"], a["kind"], a["message"], None),
            )
        return {"alerts_raised": len(alerts), "alerts": alerts}


# ------------------------------------------------------------------------- helpers
def _scalar(sql: str) -> int:
    row = db.query_one(sql)
    return int(list(row.values())[0]) if row else 0


def _alert(severity: str, kind: str, message: str) -> dict[str, str]:
    return {"severity": severity, "kind": kind, "message": message}


ALL_AGENTS = [
    DiscoveryAgent(),
    ScraperAgent(),
    CleanerAgent(),
    EnrichmentAgent(),
    OutreachAgent(),
    SubmissionAgent(),
    MonitoringAgent(),
]
