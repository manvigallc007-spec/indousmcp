"""Concrete agents wrapping the pipeline (blueprint's initial set).

Implemented here: Discovery, Scraper, Cleaner, Outreach, Monitoring, Submission.
(Approval-Assistant and Feedback agents are thin and deferred until there's a UI/
feedback channel to summarise for.)
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .. import db
from ..pipeline import feedback, ingest, outreach
from ..pipeline.scrapers import SCRAPERS
from ..pipeline.scrapers.metros import METROS, scrape_set
from ..apparel import pipeline as apparel
from ..community import pipeline as community
from ..events import pipeline as events
from ..groceries import pipeline as groceries
from ..professionals import pipeline as professionals
from ..salons import pipeline as salons
from ..services import pipeline as services
from ..studios import pipeline as studios
from ..sweets import pipeline as sweets
from ..temples import pipeline as temples
from ..legal import pipeline as legal
from ..education import pipeline as education
from ..realestate import pipeline as realestate
from ..finance import pipeline as finance
from .base import Agent


def _metro_of(lat: Any, lng: Any) -> str | None:
    """Which metro bbox (if any) a coordinate falls in. METROS values are (south, west, north, east)."""
    if lat is None or lng is None:
        return None
    try:
        la, lo = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    for m, (s, w, n, e) in METROS.items():
        if s <= la <= n and w <= lo <= e:
            return m
    return None


class DiscoveryAgent(Agent):
    name = "discovery"
    description = "Finds metros/sources needing coverage; proposes scrape targets."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        # Coverage per metro from canonical data: bucket active listings by their coordinates into
        # each metro's bbox, then flag thin/never-scraped metros.
        coverage = {m: 0 for m in METROS}
        total = placed = 0
        for r in db.query("SELECT lat, lng FROM restaurants WHERE deleted_at IS NULL AND is_active"):
            total += 1
            if (m := _metro_of(r.get("lat"), r.get("lng"))):
                coverage[m] += 1
                placed += 1
        min_per = params.get("min_per_metro", 10)
        targets = [
            {"metro": m, "known": coverage[m], "sources": sorted(SCRAPERS)}
            for m in sorted(METROS, key=lambda m: coverage[m])     # thinnest first
            if coverage[m] < min_per
        ]
        # Demand-driven: surface the top zero-result searches so coverage follows real demand.
        try:
            from .. import analytics
            unmet = analytics.top_misses(days=60, limit=15)
        except Exception:
            unmet = []
        return {"total_restaurants": total, "placed_in_metros": placed, "metros": len(METROS),
                "covered_metros": sum(1 for n in coverage.values() if n >= min_per),
                "suggested_targets": targets, "unmet_demand": unmet}


class ScraperAgent(Agent):
    name = "scraper"
    description = "Runs every scraper across every metro into restaurant_raw."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or scrape_set()
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
        # Tell IndexNow about freshly changed listings so Bing/Copilot/Yandex reindex fast.
        # No-op unless INDEXNOW_KEY is set; the cleaner runs hourly, so a 2h window has overlap.
        try:
            from .. import indexnow
            result["indexnow"] = indexnow.ping_recent(hours=2)
        except Exception:
            pass
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
        metros = params.get("metros") or scrape_set()
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
        metros = params.get("metros") or scrape_set()
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
        metros = params.get("metros") or scrape_set()
        total, errors = 0, []
        for metro in metros:
            try:
                total += professionals.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class NppesScraperAgent(Agent):
    name = "nppes_scraper"
    description = ("Adds Indian-American healthcare providers from the free CMS NPPES registry "
                  "(rotates a few US states per week — polite, no key).")
    default_interval_s = 604800  # weekly — gentle on the public government API

    # Indian-population-heavy states, rotated a few per run (keyed off the ISO week) so we never
    # hammer NPPES. Over ~7 weeks this covers the whole list; pass states=[...] to target manually.
    _STATES = ["CA", "NJ", "NY", "TX", "IL", "GA", "PA", "VA", "FL", "MI", "WA", "MA", "MD",
               "OH", "NC", "AZ", "MN", "CT", "CO", "WI"]

    def run(self, **params: Any) -> dict[str, Any]:
        import datetime
        states = params.get("states")
        if not states:
            per = max(1, int(params.get("states_per_run", 3)))
            start = (datetime.date.today().isocalendar()[1] * per) % len(self._STATES)
            states = [self._STATES[(start + i) % len(self._STATES)] for i in range(per)]
        total, errors = 0, []
        for st in states:
            try:
                total += professionals.scrape_nppes_to_raw(st)
            except Exception as exc:
                errors.append({"state": st, "error": str(exc)})
        return {"source": "nppes", "states": states, "upserted": total, "errors": errors}


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
        metros = params.get("metros") or scrape_set()
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
        metros = params.get("metros") or scrape_set()
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
        metros = params.get("metros") or scrape_set()
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
        metros = params.get("metros") or scrape_set()
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
        metros = params.get("metros") or scrape_set()
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


class CommunityScraperAgent(Agent):
    name = "community_scraper"
    description = "Scrapes Indian community orgs & cultural associations across every metro."
    default_interval_s = 259200  # every 3 days

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or scrape_set()
        total, errors = 0, []
        for metro in metros:
            try:
                total += community.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class CommunityCleanerAgent(Agent):
    name = "community_cleaner"
    description = "Processes raw community orgs into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = community.process_raw()
        result.update(community.deactivate_stale(days=params.get("stale_days", 180)))
        return result


class LegalScraperAgent(Agent):
    name = "legal_scraper"
    description = "Scrapes Indian-American immigration attorneys & law firms across every metro."
    default_interval_s = 259200  # every 3 days

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or scrape_set()
        total, errors = 0, []
        for metro in metros:
            try:
                total += legal.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class LegalCleanerAgent(Agent):
    name = "legal_cleaner"
    description = "Processes raw legal listings into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = legal.process_raw()
        result.update(legal.deactivate_stale(days=params.get("stale_days", 180)))
        return result


class EducationScraperAgent(Agent):
    name = "education_scraper"
    description = "Scrapes Indian-American education & tutoring (heritage/language schools)."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or scrape_set()
        total, errors = 0, []
        for metro in metros:
            try:
                total += education.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class EducationCleanerAgent(Agent):
    name = "education_cleaner"
    description = "Processes raw education listings into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = education.process_raw()
        result.update(education.deactivate_stale(days=params.get("stale_days", 180)))
        return result


class RealEstateScraperAgent(Agent):
    name = "realestate_scraper"
    description = "Scrapes Indian-American realtors & real-estate agencies across every metro."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or scrape_set()
        total, errors = 0, []
        for metro in metros:
            try:
                total += realestate.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class RealEstateCleanerAgent(Agent):
    name = "realestate_cleaner"
    description = "Processes raw real-estate listings into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = realestate.process_raw()
        result.update(realestate.deactivate_stale(days=params.get("stale_days", 180)))
        return result


class FinanceScraperAgent(Agent):
    name = "finance_scraper"
    description = "Scrapes Indian-American CPAs, tax preparers & financial advisors across metros."
    default_interval_s = 259200

    def run(self, **params: Any) -> dict[str, Any]:
        metros = params.get("metros") or scrape_set()
        total, errors = 0, []
        for metro in metros:
            try:
                total += finance.scrape_to_raw(metro)
            except Exception as exc:
                errors.append({"metro": metro, "error": str(exc)})
        return {"upserted": total, "errors": errors}


class FinanceCleanerAgent(Agent):
    name = "finance_cleaner"
    description = "Processes raw finance listings into canonical; deactivates stale ones."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        result = finance.process_raw()
        result.update(finance.deactivate_stale(days=params.get("stale_days", 180)))
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


class RecommendationAgent(Agent):
    name = "recommendation"
    description = "Turns unanswered searches (miss-log) into reviewable build recommendations."
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import recommendations
        out = recommendations.generate(days=params.get("days", 90))
        # Annotate fresh recommendations with a free-LLM research note (no-op without an LLM).
        out.update(recommendations.research_pending(limit=params.get("research_limit", 6)))
        return out


class LinkCheckAgent(Agent):
    name = "link_check"
    description = "Probes listing websites; removes a URL after it's confirmed dead twice (trust)."
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import linkcheck
        return linkcheck.check_links(
            limit_per_vertical=params.get("limit_per_vertical", 50),
            max_age_days=params.get("max_age_days", 14))


class LifecycleAgent(Agent):
    name = "lifecycle"
    description = ("Archives listings unseen for a very long time (soft-delete, reversible) and "
                  "restores any the scraper has re-seen. Decay, never hard-delete.")
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import lifecycle, quality
        out = lifecycle.run(unseen_days=params.get("unseen_days", 180))
        # Also sweep genuinely-unusable low-quality rows out of public view (reversible).
        out["low_quality"] = quality.suppress_low_quality(
            min_confidence=params.get("min_confidence", 0.35), dry_run=False)
        return out


class LearningAgent(Agent):
    name = "learning"
    description = ("Maintains the semantic answer cache (so repeat general questions are answered "
                  "locally, not by the external LLM): prunes stale/rarely-used entries.")
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import learning
        return learning.prune(max_age_days=params.get("max_age_days", 120),
                              max_rows=params.get("max_rows", 5000))


class KnowledgeIndexerAgent(Agent):
    name = "knowledge_indexer"
    description = ("Keeps the RAG knowledge base fresh: seeds curated culture/immigration articles "
                  "and (re)indexes active listings. Idempotent (re-embeds only what changed).")
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import knowledge, knowledge_seed
        out: dict[str, Any] = {"articles": knowledge_seed.seed()}
        out["listings"] = knowledge.index_all_listings(limit_per=params.get("limit_per"))
        return out


class IrsEoAgent(Agent):
    name = "irs_eo"
    description = ("Adds Indian temples & community orgs from the free IRS nonprofit master file "
                  "(coverage OSM/Wikidata miss). DORMANT until IRS_EO_ENABLED=true.")
    default_interval_s = 7776000  # quarterly — the IRS file updates monthly; quarterly is plenty

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        if not settings.irs_eo_enabled:
            return {"skipped": "disabled"}
        from ..pipeline.scrapers import irs
        return irs.import_eo(limit=params.get("limit"))


class SubmissionReviewAgent(Agent):
    name = "submission_review"
    description = ("Auto-approves obviously-good, complete, clearly-Indian business submissions "
                  "(ambiguous ones still wait for a human), shrinking the manual approval queue.")
    default_interval_s = 3600  # hourly

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        if not settings.auto_approve_submissions:
            return {"skipped": "disabled"}
        from .. import submissions
        return submissions.auto_approve_pending(limit=params.get("limit", 50))


class ContactReplyAgent(Agent):
    name = "contact_reply"
    description = ("Reads each new contact message: auto-sends a reply to clearly-routine, "
                  "non-sensitive ones (with a copy kept + emailed to the admin) and drafts the rest "
                  "for human approval in Admin -> Messages. Sensitive topics always wait for a human.")
    default_interval_s = 3600  # hourly

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import inbox
        from ..config import settings
        from ..pipeline import outreach
        auto = drafted = skipped = 0
        base = settings.public_web_url.rstrip("/")
        for m in inbox.pending_for_draft(limit=params.get("limit", 20)):
            res = inbox.draft_and_classify(m)
            reply = res.get("reply")
            if not reply:
                skipped += 1                                   # LLM off -> admin writes it manually
                continue
            can_auto = (settings.auto_reply_routine and res.get("routine")
                        and settings.email_enabled and (m.get("email") or "").strip())
            if can_auto:
                body = (f"{reply}\n\n— This is an automated reply from {settings.platform_name}. "
                        f"Need more help? Just write to us again at {base}/contact.")
                sent = False
                try:
                    sent = outreach.send_email(
                        m["email"], f"Re: {m.get('subject') or 'your message'}", body)
                except Exception:
                    sent = False
                if sent:
                    inbox.mark_auto_replied(m["id"], reply)
                    auto += 1
                    copy_to = settings.report_email or settings.outreach_contact_email
                    if copy_to:                                # keep the admin a copy for reference
                        try:
                            outreach.send_email(
                                copy_to, f"[auto-reply copy] {m.get('subject') or 'contact message'}",
                                f"An automated reply was sent to {m.get('email')}.\n\n"
                                f"THEIR MESSAGE:\n{m.get('body')}\n\nOUR REPLY:\n{reply}")
                        except Exception:
                            pass
                    continue
            inbox.set_draft(m["id"], reply)                    # not routine / couldn't send -> review
            drafted += 1
        return {"auto_replied": auto, "drafted_for_review": drafted, "skipped_no_llm": skipped}


class DemographicsAgent(Agent):
    name = "demographics"
    description = ("Refreshes the free U.S. Census picture of Indians-from-India in the USA — "
                  "population by state/metro, languages spoken, and income/education/work — and "
                  "feeds those stats into Dost's knowledge base. Census updates yearly, so monthly.")
    default_interval_s = 2592000  # monthly — the underlying ACS data changes once a year

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import demographics
        return demographics.refresh_all(year=params.get("year", "2022"))


class H1BAgent(Agent):
    name = "h1b"
    description = ("Aggregates the free DOL H-1B disclosure data (top sponsoring employers, typical "
                  "wages by occupation, top states) into Dost's knowledge base — the diaspora's "
                  "professional/income story. DORMANT until DOL_H1B_DISCLOSURE_URL is set.")
    default_interval_s = 7776000  # quarterly — DOL publishes new disclosure files each quarter

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import labor
        return labor.import_disclosure(**params)


class ReviewModerationAgent(Agent):
    name = "review_moderation"
    description = ("Re-screens held community reviews: auto-publishes ones that are now clean and "
                  "leaves genuinely spam/abusive ones for a human (Admin → Reviews).")
    default_interval_s = 3600  # hourly

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        if not settings.reviews_enabled:
            return {"skipped": "disabled"}
        from .. import reviews
        return reviews.moderate_pending(limit=params.get("limit", 200))


class ReviewAggregatorAgent(Agent):
    name = "review_aggregator"
    description = ("Recomputes each listing's community star-rating from its published reviews so "
                  "the rolled-up score stays correct.")
    default_interval_s = 7200  # every 2 hours

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        if not settings.reviews_enabled:
            return {"skipped": "disabled"}
        from .. import reviews
        return reviews.aggregate_all()


class DiasporaIntelligenceAgent(Agent):
    name = "intelligence"
    description = ("Continuously develops Dost's knowledge about Indians from India in the USA: "
                  "gathers diaspora intelligence from the free web, learns from what users ask, "
                  "promotes web answers into the vector knowledge base, and suppresses non-India "
                  "listings. Vectorized, owned, free.")
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import intelligence
        return intelligence.run(**params)


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

    # Kinds this agent owns: it raises them when a condition is true and auto-resolves them when the
    # condition clears, so the open-alerts list always reflects what ACTUALLY needs a human now.
    MANAGED = {"raw_backlog", "approval_backlog", "stale_data", "agent_failure",
               "messages_waiting", "smtp_unconfigured", "submissions_pending", "feedback_pending",
               "reviews_pending", "festival_calendar_low"}

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        cand: list[dict[str, Any]] = []

        # --- ingestion / data health ---
        backlog = _scalar("SELECT count(*) FROM restaurant_raw WHERE NOT processed")
        if backlog > params.get("backlog_threshold", 500):
            cand.append(_alert("warning", "raw_backlog", f"{backlog} unprocessed raw rows"))
        stale = _scalar("SELECT count(*) FROM restaurants WHERE deleted_at IS NULL "
                        "AND last_seen_at < now() - interval '30 days'")
        if stale > params.get("stale_threshold", 1000):
            cand.append(_alert("info", "stale_data", f"{stale} listings not re-seen in 30d"))

        # --- festival calendar running dry (curated dates; needs a manual yearly extend) ---
        from .. import festivals
        runway = festivals.days_of_runway()
        if festivals.next_festival() is None or runway < params.get("festival_runway_days", 60):
            cand.append(_alert(
                "warning", "festival_calendar_low",
                f"Festival calendar has only {max(runway, 0)}d of dates left — extend "
                f"FESTIVAL_DATES in festivals.py with the next year (countdown/Today/digest go blank "
                f"when it dries up)"))

        # --- HUMAN ATTENTION (escalations: things only a person can clear) ---
        msgs = _scalar("SELECT count(*) FROM contact_messages WHERE status IN ('new','drafted')")
        if msgs:
            cand.append(_alert("warning", "messages_waiting",
                               f"{msgs} contact message(s) need a reply — Admin → Messages"))
            if not settings.email_enabled:
                cand.append(_alert("critical", "smtp_unconfigured",
                                   "Contact replies can't be sent — SMTP isn't configured (set SMTP_* in .env)"))
        subs = _scalar("SELECT count(*) FROM submissions WHERE status='pending'")
        if subs:
            cand.append(_alert("info", "submissions_pending",
                               f"{subs} business submission(s) awaiting review — Admin → Submissions"))
        appr = _scalar("SELECT count(*) FROM approval_queue WHERE status='pending'")
        if appr > params.get("approval_threshold", 50):
            cand.append(_alert("warning", "approval_backlog",
                               f"{appr} listings pending approval — Admin → Approvals"))
        fb = _scalar("SELECT count(*) FROM feedback WHERE status='pending'")
        if fb:
            cand.append(_alert("info", "feedback_pending",
                               f"{fb} correction(s) awaiting review — Admin → Feedback"))
        revs = _scalar("SELECT count(*) FROM reviews WHERE status='pending'")
        if revs:
            cand.append(_alert("info", "reviews_pending",
                               f"{revs} community review(s) awaiting moderation — Admin → Reviews"))

        # --- any agent failing repeatedly in the last 24h ---
        failing = db.query("SELECT agent, count(*) AS n FROM agent_runs WHERE status = 'error' "
                           "AND started_at > now() - interval '1 day' GROUP BY agent ORDER BY n DESC")
        if failing:
            names = ", ".join(f"{f['agent']}({f['n']})" for f in failing[:6])
            # Carry the most recent actual error inline so the alert (and its push) is actionable
            # without drilling into Admin → Agents.
            last = db.query_one(
                "SELECT agent, error FROM agent_runs WHERE status = 'error' AND error IS NOT NULL "
                "AND started_at > now() - interval '1 day' ORDER BY started_at DESC LIMIT 1")
            detail = f"Latest: {last['agent']}: {(last['error'] or '')[:500]}" if last else None
            cand.append(_alert("critical", "agent_failure",
                               f"Agent failures in 24h: {names} — Admin → Agents", details=detail))

        # Reconcile: refresh/raise current issues, auto-resolve managed ones that cleared.
        current = {a["kind"]: a for a in cand}
        open_kinds: set[str] = set()
        resolved = 0
        for r in db.query("SELECT id, kind FROM agent_alerts WHERE NOT resolved"):
            if r["kind"] in self.MANAGED and r["kind"] not in current:
                db.execute("UPDATE agent_alerts SET resolved = true WHERE id = %s", (r["id"],))
                resolved += 1
            else:
                open_kinds.add(r["kind"])
        raised = 0
        newly_critical: list[dict] = []
        for kind, a in current.items():
            if kind in open_kinds:        # keep one open alert per kind, but refresh its text/severity
                db.execute("UPDATE agent_alerts SET message = %s, severity = %s "
                           "WHERE kind = %s AND NOT resolved", (a["message"], a["severity"], kind))
            else:
                db.execute("INSERT INTO agent_alerts (severity, kind, message, details) "
                           "VALUES (%s,%s,%s,%s)", (a["severity"], a["kind"], a["message"],
                                                    Jsonb({"error": a["details"]}) if a.get("details") else None))
                raised += 1
                if a["severity"] == "critical":       # push only when NEWLY raised (not every 30-min tick)
                    newly_critical.append(a)
        for a in newly_critical:
            _notify_critical(a)
        return {"checked": len(cand), "alerts_raised": raised, "alerts_auto_resolved": resolved,
                "critical_pushed": len(newly_critical)}


# ------------------------------------------------------------------------- helpers
def _scalar(sql: str) -> int:
    row = db.query_one(sql)
    return int(list(row.values())[0]) if row else 0


def _alert(severity: str, kind: str, message: str, details: str | None = None) -> dict[str, Any]:
    return {"severity": severity, "kind": kind, "message": message, "details": details}


def _notify_critical(alert: dict) -> None:
    """Best-effort out-of-band push for a newly-raised CRITICAL alert (email to the admin), so a human
    hears about it within the 30-minute monitoring cadence instead of waiting for the daily report.
    Never raises — a delivery failure must not fail the monitoring run."""
    try:
        from ..config import settings
        from ..pipeline import outreach
        to = settings.report_email or settings.outreach_contact_email
        if not to:
            return
        body = alert["message"]
        if alert.get("details"):
            body += f"\n\n{alert['details']}"
        body += f"\n\nAdmin: {settings.public_web_url.rstrip('/')}/admin/ops"
        outreach.send_email(to, f"[{settings.platform_name}] CRITICAL: {alert['kind']}", body)
    except Exception:
        pass


class MoviesAgent(Agent):
    name = "movies"
    description = "Refreshes Indian-language movies now in US theaters (TMDB)."
    default_interval_s = 86400

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import movies
        return movies.refresh()


class LlmEnrichmentAgent(Agent):
    name = "llm_enrichment"
    description = ("Writes grounded LLM descriptions + review summaries for listings that lack them "
                   "and re-embeds each one — the richest signal Dost's chat and vector search read. "
                   "No-op without an LLM key; skips rows whose facts are unchanged.")
    default_interval_s = 86400  # daily — bounded batch, gentle on the free Groq tier

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import enrich_llm
        return enrich_llm.run_all(limit_per=params.get("limit_per", 30))


class CurationAgent(Agent):
    name = "curation"
    description = ("Keeps the public directory clean: merges duplicate listings and retires non-USA "
                   "records — both reversible soft-operations. (Low-quality suppression is handled by "
                   "the lifecycle agent.)")
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import verticals
        return {"duplicates": verticals.dedupe_listings(dry_run=False),
                "non_usa": verticals.purge_non_usa(dry_run=False)}


class GeoBackfillAgent(Agent):
    name = "geo_backfill"
    description = ("Geocodes address-only listings (free Nominatim, throttled and capped) so 'near me' "
                   "distance search works across every vertical.")
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import verticals
        return verticals.backfill_coords(limit=params.get("limit", 200))


class EmbeddingBackfillAgent(Agent):
    name = "embedding_backfill"
    description = ("Embeds any listing left with a NULL vector across ALL verticals AND the knowledge "
                   "base (embeddings disabled at ingest, a failed embed, or a facet/model change) so "
                   "nothing stays invisible to semantic search.")
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        return ingest.backfill_embeddings(only_missing=True)


class FeaturedExpiryAgent(Agent):
    name = "featured_expiry"
    description = ("Clears the stored is_featured flag on listings whose paid featured window has ended "
                   "(featured_until in the past), so expired promos stop shielding them from the "
                   "lifecycle/quality agents (which read the raw column). Runs before lifecycle.")
    default_interval_s = 86400  # daily

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import verticals
        return verticals.expire_featured()


class SocrataScraperAgent(Agent):
    name = "socrata_scraper"
    description = ("Pulls South-Asian restaurants from free city open-data (Socrata/SODA: NYC, Chicago, "
                   "SF) into the raw layer; the cleaner promotes them to canonical listings.")
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from ..pipeline.scrapers.socrata import SOCRATA_SOURCES, import_source
        out: dict[str, Any] = {}
        for key in SOCRATA_SOURCES:
            try:
                out[key] = import_source(key)
            except Exception as exc:                       # one bad dataset must not fail the rest
                out[key] = {"error": str(exc)}
        return out


class OsmVerifyAgent(Agent):
    name = "osm_verify"
    description = ("Cross-checks non-OSM listings (IRS/NPPES/submissions/Socrata/consulates) against "
                   "OpenStreetMap: confirms real places, fills missing phone/website/tags, and raises "
                   "confidence + freshness. Reward-only — a miss never removes anything.")
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        from .. import osm_verify
        return osm_verify.verify_listings(
            limit_per_vertical=params.get("limit_per_vertical", 30),
            max_age_days=params.get("max_age_days", 45))


class TelegramDigestAgent(Agent):
    name = "telegram_digest"
    description = ("Sends opt-in Telegram subscribers a weekly digest: festival countdown + this "
                   "week's events + new listings in their city. No-op without a bot token.")
    default_interval_s = 604800  # weekly

    def run(self, **params: Any) -> dict[str, Any]:
        import time as _t
        from .. import telegram_bot
        if not telegram_bot.enabled():
            return {"skipped": "telegram_disabled"}
        subs = telegram_bot.active_subscribers()
        sent = 0
        for s in subs:
            try:
                telegram_bot.send_message(
                    s["chat_id"], telegram_bot.build_weekly_digest(s.get("city"), s.get("state")))
                sent += 1
            except Exception:
                pass
            _t.sleep(0.3)                                    # gentle on the Telegram API
        return {"subscribers": len(subs), "sent": sent}


class ConsumerDigestAgent(Agent):
    name = "consumer_digest"
    description = ("Sends opted-in consumers their personalized 'Today in Indian America' digest on their "
                   "chosen cadence (daily/weekly) via email AND/OR web push. No-op without SMTP or VAPID; "
                   "one-click email unsubscribe.")
    default_interval_s = 86400  # runs daily; per-user cadence enforced by accounts.due_for_digest()

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        if not (settings.email_enabled or settings.web_push_enabled):
            return {"skipped": "no_channels"}
        from .. import accounts, today, webpush
        from ..pipeline import outreach
        from ..web.auth import make_action_token
        base = settings.public_web_url.rstrip("/")
        emails = pushes = 0
        due = accounts.due_for_digest(limit=params.get("limit", 300),
                                      email_ok=settings.email_enabled, push_ok=settings.web_push_enabled)
        for p in due:
            try:
                feed = today.assemble(city=p.get("home_city"), state=p.get("home_state"),
                                      languages=p.get("languages") or [])
                delivered = False
                if p.get("notify_email") and settings.email_enabled:
                    unsub = f"{base}/me/unsubscribe?t={make_action_token(p['email'], 'digest_unsub', 60*24*90)}"
                    body = (today.render_digest_text(feed, base)
                            + f"\n\n—\nManage your digest: {base}/me\nUnsubscribe: {unsub}")
                    if outreach.send_email(p["email"], "Today in Indian America", body, list_unsubscribe=unsub):
                        emails += 1
                        delivered = True
                if p.get("notify_web") and settings.web_push_enabled:
                    f = feed.get("festival")
                    line = (f"{f['name']} is {f['when']}" if f else
                            (feed["events"][0]["name"] if feed.get("events") else "See what's happening today"))
                    if webpush.send_to_email(p["email"], "Today in Indian America", line, "/today"):
                        pushes += 1
                        delivered = True
                if delivered:
                    accounts.mark_digest_sent(p["email"])
            except Exception:
                continue
        return {"due": len(due), "emails": emails, "pushes": pushes}


class NotificationAgent(Agent):
    name = "notification"
    description = ("Turns pull into push: generates event-driven nudges (new offer on a place you saved, "
                   "new event in a city you follow) and drains the notification outbox — answers to your "
                   "questions and replies to your reviews — over email/web push. No-op without channels.")
    default_interval_s = 1800  # every 30 min

    def run(self, **params: Any) -> dict[str, Any]:
        from ..config import settings
        from .. import notify
        # Generate periodic follow-based nudges first (idempotent via dedupe_key), then deliver.
        offers = self._enqueue_saved_offers(params.get("lookback_days", 3))
        events_n = self._enqueue_followed_events(params.get("lookback_days", 3))
        if not (settings.email_enabled or settings.web_push_enabled):
            return {"skipped": "no_channels", "offer_nudges": offers, "event_nudges": events_n}
        drained = notify.drain(limit=params.get("limit", 200))
        return {"offer_nudges": offers, "event_nudges": events_n, **drained}

    # -- new offer on a place you saved --------------------------------------------------------
    def _enqueue_saved_offers(self, days: int) -> int:
        rows = db.query(
            "SELECT s.email, p.id AS post_id, p.title, p.vertical, p.listing_id "
            "FROM owner_posts p JOIN saved_places s "
            "  ON s.vertical = p.vertical AND s.listing_id = p.listing_id "
            f"WHERE p.status='active' AND p.kind='offer' AND p.created_at > now() - interval '{int(days)} days' "
            "  AND (p.expires_at IS NULL OR p.expires_at > now()) "
            "  AND lower(s.email) <> lower(p.owner_email)", ())
        from .. import notify
        n = 0
        for r in rows:
            if notify.enqueue(r["email"], "New offer at a place you saved", r["title"],
                              url=f"/listing/{r['vertical']}/{r['listing_id']}", kind="saved_offer",
                              dedupe_key=f"saved_offer:{r['post_id']}:{r['email'].lower()}"):
                n += 1
        return n

    # -- new event in a city you follow --------------------------------------------------------
    def _enqueue_followed_events(self, days: int) -> int:
        rows = db.query(
            "SELECT f.email, e.id AS event_id, e.name "
            "FROM events e JOIN follows f "
            "  ON f.kind='city' AND lower(f.value) = lower(e.city || ', ' || e.state) "
            "WHERE e.status='approved' AND e.is_active AND e.deleted_at IS NULL "
            f"  AND e.created_at > now() - interval '{int(days)} days' "
            "  AND (e.start_at IS NULL OR e.start_at > now())", ())
        from .. import notify
        n = 0
        for r in rows:
            if notify.enqueue(r["email"], "New event in a city you follow", r["name"],
                              url="/events", kind="follow_event",
                              dedupe_key=f"follow_event:{r['event_id']}:{r['email'].lower()}"):
                n += 1
        return n


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
    NppesScraperAgent(),
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
    CommunityScraperAgent(),
    CommunityCleanerAgent(),
    LegalScraperAgent(),
    LegalCleanerAgent(),
    EducationScraperAgent(),
    EducationCleanerAgent(),
    RealEstateScraperAgent(),
    RealEstateCleanerAgent(),
    FinanceScraperAgent(),
    FinanceCleanerAgent(),
    EventFeedDiscoveryAgent(),
    EventScraperAgent(),
    EventCleanerAgent(),
    WebEnrichmentAgent(),
    LinkCheckAgent(),
    RecommendationAgent(),
    LifecycleAgent(),
    LearningAgent(),
    KnowledgeIndexerAgent(),
    DemographicsAgent(),
    H1BAgent(),
    ContactReplyAgent(),
    SubmissionReviewAgent(),
    ReviewModerationAgent(),
    ReviewAggregatorAgent(),
    IrsEoAgent(),
    DiasporaIntelligenceAgent(),
    ReportingAgent(),
    MonitoringAgent(),
    MoviesAgent(),
    LlmEnrichmentAgent(),
    CurationAgent(),
    GeoBackfillAgent(),
    EmbeddingBackfillAgent(),
    FeaturedExpiryAgent(),
    SocrataScraperAgent(),
    OsmVerifyAgent(),
    TelegramDigestAgent(),
    ConsumerDigestAgent(),
    NotificationAgent(),
]
