"""Concrete agents wrapping the pipeline (blueprint's initial set).

Implemented here: Discovery, Scraper, Cleaner, Outreach, Monitoring, Submission.
(Approval-Assistant and Feedback agents are thin and deferred until there's a UI/
feedback channel to summarise for.)
"""

from __future__ import annotations

from typing import Any

from .. import db
from ..pipeline import feedback, ingest, outreach
from ..pipeline.scrapers import SCRAPERS
from ..pipeline.scrapers.metros import METROS
from ..apparel import pipeline as apparel
from ..events import pipeline as events
from ..groceries import pipeline as groceries
from ..professionals import pipeline as professionals
from ..salons import pipeline as salons
from ..services import pipeline as services
from ..studios import pipeline as studios
from ..sweets import pipeline as sweets
from ..temples import pipeline as temples
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
        # Demand-driven: surface the top zero-result searches so coverage follows real demand.
        try:
            from .. import analytics
            unmet = analytics.top_misses(days=60, limit=15)
        except Exception:
            unmet = []
        return {"total_restaurants": total, "metros": len(METROS),
                "suggested_targets": targets, "unmet_demand": unmet}


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
    description = "Processes raw rows into canonical; deactivates stale (gone) listings."
    default_interval_s = 3600

    def run(self, **params: Any) -> dict[str, Any]:
        result = ingest.process_raw()
        result.update(ingest.deactivate_stale(days=params.get("stale_days", 60)))
        return result


class EnrichmentAgent(Agent):
    name = "enrichment"
    description = "Backfills cultural tags (region, dietary) on under-tagged restaurants."
    default_interval_s = 43200

    def run(self, **params: Any) -> dict[str, Any]:
        return ingest.enrich_existing()


class ApprovalAssistantAgent(Agent):
    name = "approval_assistant"
    description = "Summarizes the pending approval queue for fast human review."
    default_interval_s = 21600

    def run(self, **params: Any) -> dict[str, Any]:
        return ingest.summarize_approvals(limit=params.get("limit", 100))


class FeedbackAgent(Agent):
    name = "feedback"
    description = "Applies safe field corrections from agents/users; routes risky ones."
    default_interval_s = 21600

    def run(self, **params: Any) -> dict[str, Any]:
        return feedback.apply_pending(limit=params.get("limit", 200))


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


class TempleScraperAgent(Agent):
    name = "temple_scraper"
    description = "Scrapes Hindu/Sikh/Jain places of worship across every metro."
    default_interval_s = 172800  # every 2 days (temples change rarely)

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += temples.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class TempleCleanerAgent(Agent):
    name = "temple_cleaner"
    description = "Processes raw temples into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = temples.process_raw()
        result.update(temples.deactivate_stale(days=params.get("stale_days", 90)))
        return result


class GroceryScraperAgent(Agent):
    name = "grocery_scraper"
    description = "Scrapes Indian grocery stores across every metro."
    default_interval_s = 172800

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += groceries.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class GroceryCleanerAgent(Agent):
    name = "grocery_cleaner"
    description = "Processes raw groceries into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = groceries.process_raw()
        result.update(groceries.deactivate_stale(days=params.get("stale_days", 90)))
        return result


class ProfessionalScraperAgent(Agent):
    name = "professional_scraper"
    description = "Scrapes Indian-American healthcare professionals across every metro."
    default_interval_s = 259200  # every 3 days

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += professionals.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class ProfessionalCleanerAgent(Agent):
    name = "professional_cleaner"
    description = "Processes raw professionals into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = professionals.process_raw()
        result.update(professionals.deactivate_stale(days=params.get("stale_days", 120)))
        return result


class SalonScraperAgent(Agent):
    name = "salon_scraper"
    description = "Scrapes Indian beauty salons (threading/henna) across every metro."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += salons.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class SalonCleanerAgent(Agent):
    name = "salon_cleaner"
    description = "Processes raw salons into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = salons.process_raw()
        result.update(salons.deactivate_stale(days=params.get("stale_days", 120)))
        return result


class ApparelScraperAgent(Agent):
    name = "apparel_scraper"
    description = "Scrapes Indian apparel & jewelry stores across every metro."
    default_interval_s = 259200  # every 3 days

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += apparel.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class ApparelCleanerAgent(Agent):
    name = "apparel_cleaner"
    description = "Processes raw apparel/jewelry into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = apparel.process_raw()
        result.update(apparel.deactivate_stale(days=params.get("stale_days", 120)))
        return result


class SweetsScraperAgent(Agent):
    name = "sweets_scraper"
    description = "Scrapes Indian sweets shops (mithai) & bakeries across every metro."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += sweets.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class SweetsCleanerAgent(Agent):
    name = "sweets_cleaner"
    description = "Processes raw sweets/bakeries into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = sweets.process_raw()
        result.update(sweets.deactivate_stale(days=params.get("stale_days", 120)))
        return result


class StudioScraperAgent(Agent):
    name = "studio_scraper"
    description = "Scrapes Indian yoga & cultural studios (dance/music) across every metro."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += studios.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class StudioCleanerAgent(Agent):
    name = "studio_cleaner"
    description = "Processes raw studios into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = studios.process_raw()
        result.update(studios.deactivate_stale(days=params.get("stale_days", 150)))
        return result


class ServiceScraperAgent(Agent):
    name = "service_scraper"
    description = "Scrapes Indian community services (money transfer/immigration/travel)."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or list(METROS)
        total, errors = 0, []
        for metro in metros:
            try:
                total += services.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class ServiceCleanerAgent(Agent):
    name = "service_cleaner"
    description = "Processes raw services into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = services.process_raw()
        result.update(services.deactivate_stale(days=params.get("stale_days", 150)))
        return result


class EventFeedDiscoveryAgent(Agent):
    name = "event_feed_discovery"
    description = "Scans org websites for public iCal calendar feeds (auto-finds event sources)."
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from ..events import discovery
        return discovery.discover_feeds(limit=params.get("limit", 30))


class EventScraperAgent(Agent):
    name = "event_scraper"
    description = "Ingests Indian-American events from public iCalendar feeds."
    default_interval_s = 43200  # twice daily (events are time-sensitive)

    def run(self, **params: Any) -> dict[str, Any]:
        return {"upserted": events.scrape_to_raw()}


class EventCleanerAgent(Agent):
    name = "event_cleaner"
    description = "Processes raw events; auto-approves high-confidence, queues the rest."
    default_interval_s = 21600

    def run(self, **params: Any) -> dict[str, Any]:
        result = events.process_raw()
        result.update(events.purge_old(days=params.get("retention_days", 550)))
        return result


class WebEnrichmentAgent(Agent):
    name = "web_enrichment"
    description = ("Reads each listing's own website (schema.org + Open Graph) for rating, "
                   "price, cuisine, photo, email and social links; refreshes search data.")
    default_interval_s = 86400  # daily; each run rotates through a polite batch per vertical

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import web_enrich
        return web_enrich.enrich_all(
            limit_per_vertical=params.get("limit_per_vertical", 40),
            max_age_days=params.get("max_age_days", 90),
        )


class LifecycleAgent(Agent):
    name = "lifecycle"
    description = ("Archives listings unseen for a very long time (soft-delete, reversible) and "
                  "restores any the scraper has re-seen. Decay, never hard-delete.")
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import lifecycle
        return lifecycle.run(unseen_days=params.get("unseen_days", 180))


class ReportingAgent(Agent):
    name = "reporting"
    description = "Computes the daily health & growth report and emails it."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import reporting
        report = reporting.compute_daily_report()
        emailed = reporting.email_daily_report(report)
        return {"computed": True, "emailed": emailed, "deltas": report.get("deltas", {})}


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
    ApprovalAssistantAgent(),
    FeedbackAgent(),
    OutreachAgent(),
    SubmissionAgent(),
    TempleScraperAgent(),
    TempleCleanerAgent(),
    GroceryScraperAgent(),
    GroceryCleanerAgent(),
    ProfessionalScraperAgent(),
    ProfessionalCleanerAgent(),
    SalonScraperAgent(),
    SalonCleanerAgent(),
    ApparelScraperAgent(),
    ApparelCleanerAgent(),
    SweetsScraperAgent(),
    SweetsCleanerAgent(),
    StudioScraperAgent(),
    StudioCleanerAgent(),
    ServiceScraperAgent(),
    ServiceCleanerAgent(),
    EventFeedDiscoveryAgent(),
    EventScraperAgent(),
    EventCleanerAgent(),
    WebEnrichmentAgent(),
    LifecycleAgent(),
    ReportingAgent(),
    MonitoringAgent(),
]
