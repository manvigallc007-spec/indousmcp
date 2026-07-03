"""Operator CLI for the diaspora pipeline.

    python -m indo_usa_mcp.cli init-db
    python -m indo_usa_mcp.cli scrape --metro bay_area [--source osm_overpass]
    python -m indo_usa_mcp.cli process
    python -m indo_usa_mcp.cli approvals [--all]
    python -m indo_usa_mcp.cli approve <id>
    python -m indo_usa_mcp.cli reject <id>
    python -m indo_usa_mcp.cli seed
    python -m indo_usa_mcp.cli backfill-embeddings [--all]
    python -m indo_usa_mcp.cli agents | agent <name> | agents-loop [--once]
    python -m indo_usa_mcp.cli stats
"""

from __future__ import annotations

import argparse
import json
import sys

from . import db, queries
from .agents import AGENTS, run_agent
from .agents.scheduler import run_loop
from .pipeline import feedback, ingest, outreach, seed
from .pipeline.scrapers import SCRAPERS
from .pipeline.scrapers.metros import SCRAPE_REGIONS
from .events import pipeline as events
from .events import queries as event_queries
from .groceries import pipeline as groceries
from .groceries import queries as grocery_queries
from .professionals import pipeline as professionals
from .professionals import queries as professional_queries
from .salons import pipeline as salons
from .salons import queries as salon_queries
from .temples import pipeline as temples
from .temples import queries as temple_queries
from .apparel import pipeline as apparel, queries as apparel_queries
from .sweets import pipeline as sweets, queries as sweets_queries
from .studios import pipeline as studios, queries as studio_queries
from .services import pipeline as services, queries as service_queries
from .community import pipeline as community, queries as community_queries
from .legal import pipeline as legal, queries as legal_queries
from .education import pipeline as education, queries as education_queries
from .realestate import pipeline as realestate, queries as realestate_queries
from .finance import pipeline as finance, queries as finance_queries


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_init_db(_: argparse.Namespace) -> None:
    db.init_db()
    print("Schema applied.")


def cmd_scrape(args: argparse.Namespace) -> None:
    print(f"Scraping source={args.source} metro={args.metro} ...")
    n = ingest.scrape_to_raw(args.source, args.metro)
    print(f"Upserted {n} raw observation(s) into restaurant_raw.")


def cmd_process(_: argparse.Namespace) -> None:
    result = ingest.process_raw()
    _print(result)


def cmd_caterbid_import(_: argparse.Namespace) -> None:
    from .config import settings
    if not (settings.caterbid_database_url or "").strip():
        print("CATERBID_DATABASE_URL is not set — nothing to import.")
        print("Set it (and CATERBID_QUERY if caterbid's schema differs) in .env, then re-run.")
        return
    print("Importing caterbid.co restaurants (own DB, every row tagged 'catering')...")
    n = ingest.scrape_to_raw("caterbid", "caterbid")
    print(f"Upserted {n} raw observation(s) into restaurant_raw.")
    _print(ingest.process_raw())


def cmd_socrata_import(args: argparse.Namespace) -> None:
    from .pipeline.scrapers.socrata import SOCRATA_SOURCES, import_source
    keys = [args.source] if args.source else list(SOCRATA_SOURCES)
    for key in keys:
        print(f"Importing Socrata source '{key}' ...")
        _print(import_source(key))
    print("Processing into restaurants ...")
    _print(ingest.process_raw())


def cmd_kb_index(args: argparse.Namespace) -> None:
    from . import knowledge
    if args.vertical:
        _print(knowledge.index_listings(args.vertical, limit=args.limit))
    else:
        print("Indexing all listings into the knowledge base ...")
        _print(knowledge.index_all_listings(limit_per=args.limit))


def cmd_kb_search(args: argparse.Namespace) -> None:
    from . import knowledge
    _print(knowledge.search(args.query, vertical=args.vertical, limit=args.limit or 6))


def cmd_kb_stats(_: argparse.Namespace) -> None:
    from . import knowledge
    _print(knowledge.stats())


def cmd_kb_seed(_: argparse.Namespace) -> None:
    from . import knowledge_seed
    print("Seeding curated culture/immigration/tax knowledge ...")
    _print(knowledge_seed.seed())


def cmd_intelligence(_: argparse.Namespace) -> None:
    from . import intelligence
    print("Running the diaspora-intelligence cycle (free web -> compose -> vector knowledge base)...")
    _print(intelligence.run())


def cmd_approvals(args: argparse.Namespace) -> None:
    status = "" if args.all else "WHERE status = 'pending'"
    rows = db.query(
        f"SELECT id, change_type, natural_key, risk, confidence, status, created_at "
        f"FROM approval_queue {status} ORDER BY created_at DESC LIMIT 50"
    )
    _print(rows)


def cmd_approve(args: argparse.Namespace) -> None:
    ingest.apply_approval(args.id)
    print(f"Approved and applied #{args.id}.")


def cmd_reject(args: argparse.Namespace) -> None:
    ingest.reject_approval(args.id)
    print(f"Rejected #{args.id}.")


def cmd_outreach(args: argparse.Namespace) -> None:
    result = outreach.run_outreach(limit=args.limit, min_confidence=args.min_confidence)
    _print(result)


def cmd_verify_claim(args: argparse.Namespace) -> None:
    result = outreach.verify_claim(args.token, owner_email=args.email, owner_phone=args.phone)
    _print(result)


def cmd_outreach_status(_: argparse.Namespace) -> None:
    from .pipeline import compliance
    _print(compliance.gate_status())


def cmd_suppress(args: argparse.Namespace) -> None:
    from .pipeline import compliance
    compliance.suppress(args.contact, reason=args.reason, note="manual via cli")
    _print({"suppressed": compliance.normalize_contact(args.contact), "reason": args.reason,
            "total_suppressed": compliance.suppression_count()})


def cmd_agents(_: argparse.Namespace) -> None:
    _print(
        [
            {"name": a.name, "description": a.description, "interval_s": a.default_interval_s}
            for a in AGENTS.values()
        ]
    )


def cmd_agent_run(args: argparse.Namespace) -> None:
    _print(run_agent(args.name))


def cmd_agents_loop(args: argparse.Namespace) -> None:
    run_loop(once=args.once)


def cmd_seed(_: argparse.Namespace) -> None:
    _print(seed.load_seed())


def cmd_backfill_embeddings(args: argparse.Namespace) -> None:
    _print(ingest.backfill_embeddings(only_missing=not args.all))


def cmd_enrich(_: argparse.Namespace) -> None:
    _print(ingest.enrich_existing())


def cmd_deactivate_stale(args: argparse.Namespace) -> None:
    _print(ingest.deactivate_stale(days=args.days))


def cmd_purge_non_diaspora(args: argparse.Namespace) -> None:
    from . import verticals
    _print(verticals.purge_excluded(dry_run=not args.apply))


def cmd_purge_non_usa(args: argparse.Namespace) -> None:
    from . import verticals
    _print(verticals.purge_non_usa(dry_run=not args.apply))


def cmd_telegram_bot(args: argparse.Namespace) -> None:
    from . import telegram_bot
    telegram_bot.poll_loop()


def cmd_dedupe(args: argparse.Namespace) -> None:
    from . import verticals
    _print(verticals.dedupe_listings(dry_run=not args.apply))


def cmd_enrich_llm(args: argparse.Namespace) -> None:
    from . import enrich_llm
    if args.vertical:
        _print(enrich_llm.run(args.vertical, limit=args.limit))
    else:
        _print(enrich_llm.run_all(limit_per=args.limit))


def cmd_movies_refresh(args: argparse.Namespace) -> None:
    from . import movies
    _print(movies.refresh())


def cmd_llm_check(args: argparse.Namespace) -> None:
    from . import assistant
    _print(assistant.diagnose())


def cmd_osm_verify(args: argparse.Namespace) -> None:
    from . import osm_verify
    _print(osm_verify.verify_listings(limit_per_vertical=args.limit))


def cmd_consulates_seed(args: argparse.Namespace) -> None:
    from . import consulates
    _print(consulates.seed())


def cmd_curate(args: argparse.Namespace) -> None:
    from . import curation
    _print(curation.run(apply=args.apply))


def cmd_backfill_geo(args: argparse.Namespace) -> None:
    from . import verticals
    _print(verticals.backfill_coords(limit=args.limit))


def cmd_demographics_refresh(args: argparse.Namespace) -> None:
    from . import demographics
    print("Population (state + metro):")
    _print(demographics.refresh(year=args.year))
    print("Languages spoken at home (B16001, no key needed):")
    _print(demographics.refresh_languages(year=args.year))
    print("Income/education/work for Asian-Indians (S0201 — needs free CENSUS_API_KEY):")
    _print(demographics.refresh_profile(year=args.year))
    print("Feeding stats into the knowledge base:")
    _print(demographics.to_knowledge())
    print("Top Indian-American metros:")
    for r in demographics.top("metro", 12):
        print(f"  {r['indian_population']:>8,}  {r['name']}")


def cmd_h1b_import(args: argparse.Namespace) -> None:
    from . import labor
    _print(labor.import_disclosure(source=args.source, fiscal_year=args.year, max_rows=args.limit))


def cmd_irs_import(args: argparse.Namespace) -> None:
    from .pipeline.scrapers import irs
    _print(irs.import_eo(limit=args.limit))


def cmd_collect(args: argparse.Namespace) -> None:
    """Scrape EVERY vertical for a metro / state / all metros, run NPPES for the state(s), then
    process raw -> canonical. Curation (tags/descriptions/embeddings/geo) is a separate step after."""
    from .agents import AGENTS, run_agent
    from .pipeline.scrapers.metros import METROS, _METRO_STATE

    if args.metro:
        if args.metro not in METROS:
            print(f"Unknown metro '{args.metro}'. Known: {', '.join(sorted(METROS))}")
            return
        metros = [args.metro]
        states = [s] if (s := _METRO_STATE.get(args.metro)) else []
    elif args.state:
        st = args.state.upper()
        metros = sorted(m for m, s in _METRO_STATE.items() if s == st)
        states = [st]
        if not metros:
            print(f"No metros defined for state {st}.")
            return
    elif args.all:
        metros, states = sorted(METROS), []
        print("WARNING: --all scrapes every vertical across all metros — this is heavy and slow.")
    else:
        print("Pass --metro <name>, --state <ST>, or --all.")
        return

    skip = {"nppes_scraper", "event_scraper", "event_feed_discovery"}
    scrapers = (["scraper"] if "scraper" in AGENTS else []) \
        + [n for n in AGENTS if n.endswith("_scraper") and n not in skip]
    cleaners = (["cleaner"] if "cleaner" in AGENTS else []) \
        + [n for n in AGENTS if n.endswith("_cleaner")]

    print(f"Scraping {len(scrapers)} verticals x {len(metros)} metro(s): {', '.join(metros)}")
    for a in scrapers:
        r = run_agent(a, metros=metros)
        print(f"  scrape {a:<22} {r['status']}  {r.get('result') or r.get('error', '')}")
    if states and "nppes_scraper" in AGENTS:
        print(f"NPPES healthcare providers for {', '.join(states)} ...")
        r = run_agent("nppes_scraper", states=states)
        print(f"  scrape nppes_scraper       {r['status']}  {r.get('result') or r.get('error', '')}")
    print("Processing raw -> canonical ...")
    for a in cleaners:
        r = run_agent(a)
        print(f"  clean  {a:<22} {r['status']}")
    print("Done. Curate next: enhance-data  ·  backfill-geo  ·  kb-seed  ·  kb-index")


def cmd_approval_digest(_: argparse.Namespace) -> None:
    _print(ingest.summarize_approvals())


def cmd_feedback(args: argparse.Namespace) -> None:
    _print(feedback.submit_correction(
        args.id, args.field, args.value, reason=args.reason or "", source="human"))


def cmd_feature(args: argparse.Namespace) -> None:
    days = None if args.permanent else args.days
    _print(ingest.set_featured(args.id, days=days))


def cmd_unfeature(args: argparse.Namespace) -> None:
    _print(ingest.unset_featured(args.id))


def cmd_query(args: argparse.Namespace) -> None:
    """Call the same functions the MCP tools use, so terminal == agent's view."""
    if args.id is not None:
        _print(queries.get_restaurant_details(args.id) or {"error": "not_found", "id": args.id})
    elif args.text:
        _print(queries.search_restaurants_by_text(
            args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(queries.get_indian_restaurants(
            lat=args.lat, lng=args.lng, radius_miles=args.radius,
            city=args.city, state=args.state, region_tag=args.region,
            dietary_tags=args.dietary, featured_only=args.featured, limit=args.limit))


def cmd_temples_scrape(args: argparse.Namespace) -> None:
    print(f"Scraping temples for region={args.metro} ...")
    n = temples.scrape_to_raw(args.metro)
    print(f"Upserted {n} raw temple observation(s).")


def cmd_temples_process(_: argparse.Namespace) -> None:
    _print(temples.process_raw())


def cmd_temples_wikidata(_: argparse.Namespace) -> None:
    print("Importing notable US Hindu temples from Wikidata (CC0)...")
    n = temples.scrape_wikidata_to_raw()
    print(f"Upserted {n} raw temple observation(s).")
    _print(temples.process_raw())


def cmd_temples_stats(_: argparse.Namespace) -> None:
    _print(temple_queries.stats())


def cmd_temples_query(args: argparse.Namespace) -> None:
    if args.text:
        _print(temple_queries.search_temples_by_text(
            args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(temple_queries.get_indian_temples(
            lat=args.lat, lng=args.lng, radius_miles=args.radius, city=args.city,
            state=args.state, religion=args.religion, limit=args.limit))


def cmd_groceries_scrape(args: argparse.Namespace) -> None:
    print(f"Scraping groceries for region={args.metro} ...")
    n = groceries.scrape_to_raw(args.metro)
    print(f"Upserted {n} raw grocery observation(s).")


def cmd_groceries_process(_: argparse.Namespace) -> None:
    _print(groceries.process_raw())


def cmd_groceries_stats(_: argparse.Namespace) -> None:
    _print(grocery_queries.stats())


def cmd_groceries_query(args: argparse.Namespace) -> None:
    if args.text:
        _print(grocery_queries.search_groceries_by_text(
            args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(grocery_queries.get_indian_groceries(
            lat=args.lat, lng=args.lng, radius_miles=args.radius, city=args.city,
            state=args.state, region_tag=args.region, limit=args.limit))


def cmd_report(_: argparse.Namespace) -> None:
    from . import reporting
    report = reporting.compute_daily_report()
    print(reporting.render_text(report))


def cmd_quality(_: argparse.Namespace) -> None:
    from . import quality
    _print(quality.scan_all())


def cmd_traffic(_: argparse.Namespace) -> None:
    from . import analytics
    _print(analytics.traffic_summary())


def cmd_search_all(args: argparse.Namespace) -> None:
    from . import verticals
    _print(verticals.search_all(args.text, city=args.city, state=args.state, limit=args.limit))


def cmd_normalize_geo(_: argparse.Namespace) -> None:
    from . import verticals
    _print([verticals.normalize_geography(v) for v in verticals.VERTICALS])


def cmd_enhance_data(args: argparse.Namespace) -> None:
    from . import verticals
    targets = [args.vertical] if args.vertical else list(verticals.VERTICALS)
    _print([verticals.enhance_existing(v) for v in targets])


def cmd_web_enrich(args: argparse.Namespace) -> None:
    from . import web_enrich
    if args.vertical:
        _print(web_enrich.enrich_vertical(args.vertical, limit=args.limit, max_age_days=args.max_age_days))
    else:
        _print(web_enrich.enrich_all(limit_per_vertical=args.limit, max_age_days=args.max_age_days))


def cmd_professionals_scrape(args: argparse.Namespace) -> None:
    print(f"Scraping professionals for region={args.metro} ...")
    n = professionals.scrape_to_raw(args.metro)
    print(f"Upserted {n} raw professional observation(s).")


def cmd_professionals_nppes(args: argparse.Namespace) -> None:
    print(f"Scraping NPPES providers for state={args.state.upper()} (free CMS registry) ...")
    n = professionals.scrape_nppes_to_raw(args.state, limit_per=args.limit)
    print(f"Upserted {n} raw provider(s). Run professionals-process, then backfill-geo for coords.")


def cmd_professionals_process(_: argparse.Namespace) -> None:
    _print(professionals.process_raw())


def cmd_professionals_stats(_: argparse.Namespace) -> None:
    _print(professional_queries.stats())


def cmd_professionals_query(args: argparse.Namespace) -> None:
    if args.text:
        _print(professional_queries.search_professionals_by_text(
            args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(professional_queries.get_indian_professionals(
            lat=args.lat, lng=args.lng, radius_miles=args.radius, city=args.city,
            state=args.state, profession_type=args.type, limit=args.limit))


def cmd_salons_scrape(args: argparse.Namespace) -> None:
    print(f"Scraping salons for region={args.metro} ...")
    n = salons.scrape_to_raw(args.metro)
    print(f"Upserted {n} raw salon observation(s).")


def cmd_salons_process(_: argparse.Namespace) -> None:
    _print(salons.process_raw())


def cmd_salons_stats(_: argparse.Namespace) -> None:
    _print(salon_queries.stats())


def cmd_salons_query(args: argparse.Namespace) -> None:
    if args.text:
        _print(salon_queries.search_salons_by_text(
            args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(salon_queries.get_indian_salons(
            lat=args.lat, lng=args.lng, radius_miles=args.radius, city=args.city,
            state=args.state, tag=args.tag, limit=args.limit))


# Retail-style verticals added in batch — identical CLI surface, dispatched by name.
# (pipeline module, queries module, list fn, search fn)
_BATCH_VERTICALS = {
    "apparel": (apparel, apparel_queries, apparel_queries.get_indian_apparel,
                apparel_queries.search_apparel_by_text),
    "sweets": (sweets, sweets_queries, sweets_queries.get_indian_sweets,
               sweets_queries.search_sweets_by_text),
    "studios": (studios, studio_queries, studio_queries.get_indian_studios,
                studio_queries.search_studios_by_text),
    "services": (services, service_queries, service_queries.get_indian_services,
                 service_queries.search_services_by_text),
    "community": (community, community_queries, community_queries.get_indian_community,
                  community_queries.search_community_by_text),
    "legal": (legal, legal_queries, legal_queries.get_indian_legal,
              legal_queries.search_legal_by_text),
    "education": (education, education_queries, education_queries.get_indian_education,
                  education_queries.search_education_by_text),
    "realestate": (realestate, realestate_queries, realestate_queries.get_indian_realestate,
                   realestate_queries.search_realestate_by_text),
    "finance": (finance, finance_queries, finance_queries.get_indian_finance,
                finance_queries.search_finance_by_text),
}


def cmd_bv_scrape(args: argparse.Namespace) -> None:
    pipe = _BATCH_VERTICALS[args.vertical][0]
    print(f"Scraping {args.vertical} for region={args.metro} ...")
    print(f"Upserted {pipe.scrape_to_raw(args.metro)} raw {args.vertical} observation(s).")


def cmd_bv_process(args: argparse.Namespace) -> None:
    _print(_BATCH_VERTICALS[args.vertical][0].process_raw())


def cmd_bv_stats(args: argparse.Namespace) -> None:
    _print(_BATCH_VERTICALS[args.vertical][1].stats())


def cmd_bv_query(args: argparse.Namespace) -> None:
    _, _, get_fn, search_fn = _BATCH_VERTICALS[args.vertical]
    if args.text:
        _print(search_fn(args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(get_fn(lat=args.lat, lng=args.lng, radius_miles=args.radius, city=args.city,
                      state=args.state, tag=args.tag, limit=args.limit))


def cmd_events_discover(args: argparse.Namespace) -> None:
    from .events import discovery
    _print(discovery.discover_feeds(limit=args.limit))


def cmd_events_scrape(_: argparse.Namespace) -> None:
    print(f"Ingesting events from {len(events.scraper._feeds())} iCal feed(s)...")
    print(f"Upserted {events.scrape_to_raw()} raw event observation(s).")


def cmd_events_process(_: argparse.Namespace) -> None:
    _print(events.process_raw())


def cmd_events_stats(_: argparse.Namespace) -> None:
    _print(event_queries.stats())


def cmd_events_query(args: argparse.Namespace) -> None:
    if args.text:
        _print(event_queries.search_events_by_text(args.text, city=args.city, state=args.state, limit=args.limit))
    else:
        _print(event_queries.get_indian_events(
            city=args.city, state=args.state, category=args.category,
            include_past=args.include_past, limit=args.limit))


def cmd_events_approvals(_: argparse.Namespace) -> None:
    _print(events.pending())


def cmd_events_approve(args: argparse.Namespace) -> None:
    events.set_status(args.id, "approved")
    print(f"Approved event #{args.id}.")


def cmd_events_reject(args: argparse.Namespace) -> None:
    events.set_status(args.id, "rejected")
    print(f"Rejected event #{args.id}.")


def cmd_stats(_: argparse.Namespace) -> None:
    _print(queries.stats())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="diaspora", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Apply SQL migrations").set_defaults(func=cmd_init_db)

    sp = sub.add_parser("scrape", help="Run a scraper into restaurant_raw")
    sp.add_argument("--metro", required=True, choices=SCRAPE_REGIONS,
                    metavar="REGION", help="a metro or 'usa' for nationwide")
    sp.add_argument("--source", default="osm_overpass", choices=sorted(SCRAPERS))
    sp.set_defaults(func=cmd_scrape)

    sub.add_parser("process", help="Process raw -> canonical/approval").set_defaults(
        func=cmd_process
    )

    sub.add_parser("caterbid-import",
                   help="Import the operator's own caterbid.co restaurants (DB-direct, tagged catering)"
                   ).set_defaults(func=cmd_caterbid_import)

    ssp = sub.add_parser("socrata-import",
                         help="Import South-Asian restaurants from city open data (Socrata SODA)")
    ssp.add_argument("--source", help="one Socrata source key (default: all). e.g. nyc_restaurants")
    ssp.set_defaults(func=cmd_socrata_import)

    kbi = sub.add_parser("kb-index", help="Index listings into the knowledge base (RAG)")
    kbi.add_argument("--vertical", help="one vertical (default: all)")
    kbi.add_argument("--limit", type=int, help="cap rows per vertical")
    kbi.set_defaults(func=cmd_kb_index)
    kbs = sub.add_parser("kb-search", help="Search the knowledge base")
    kbs.add_argument("--query", required=True)
    kbs.add_argument("--vertical")
    kbs.add_argument("--limit", type=int, default=6)
    kbs.set_defaults(func=cmd_kb_search)
    sub.add_parser("kb-stats", help="Knowledge base stats").set_defaults(func=cmd_kb_stats)
    sub.add_parser("kb-seed", help="Seed curated culture/immigration/tax knowledge articles"
                   ).set_defaults(func=cmd_kb_seed)
    sub.add_parser("intelligence", help="Run one diaspora-intelligence cycle (gather/learn/promote/curate)"
                   ).set_defaults(func=cmd_intelligence)

    ap = sub.add_parser("approvals", help="List approval-queue items")
    ap.add_argument("--all", action="store_true", help="Include resolved items")
    ap.set_defaults(func=cmd_approvals)

    av = sub.add_parser("approve", help="Approve & apply an item")
    av.add_argument("id", type=int)
    av.set_defaults(func=cmd_approve)

    rj = sub.add_parser("reject", help="Reject an item")
    rj.add_argument("id", type=int)
    rj.set_defaults(func=cmd_reject)

    ou = sub.add_parser("outreach", help="Draft claim outreach for unclaimed restaurants")
    ou.add_argument("--limit", type=int, default=20)
    ou.add_argument("--min-confidence", type=float, default=0.5, dest="min_confidence")
    ou.set_defaults(func=cmd_outreach)

    sub.add_parser("outreach-status", help="Show outreach compliance gate + daily quota").set_defaults(
        func=cmd_outreach_status)
    sup = sub.add_parser("suppress", help="Add a contact (email/phone) to the opt-out suppression list")
    sup.add_argument("contact")
    sup.add_argument("--reason", default="manual", choices=("optout", "bounce", "complaint", "manual"))
    sup.set_defaults(func=cmd_suppress)

    vc = sub.add_parser("verify-claim", help="Verify a claim token (owner takes ownership)")
    vc.add_argument("token")
    vc.add_argument("--email")
    vc.add_argument("--phone")
    vc.set_defaults(func=cmd_verify_claim)

    sub.add_parser("agents", help="List registered autonomous agents").set_defaults(
        func=cmd_agents
    )

    ar = sub.add_parser("agent", help="Run a single agent now (audited in agent_runs)")
    ar.add_argument("name", choices=sorted(AGENTS))
    ar.set_defaults(func=cmd_agent_run)

    al = sub.add_parser("agents-loop", help="Run the agent scheduler")
    al.add_argument("--once", action="store_true", help="One due-check pass, then exit")
    al.set_defaults(func=cmd_agents_loop)

    sub.add_parser("seed", help="Load fictional seed restaurants for local testing").set_defaults(
        func=cmd_seed
    )

    be = sub.add_parser("backfill-embeddings", help="(Re)compute embeddings for canonical rows")
    be.add_argument("--all", action="store_true", help="Recompute all, not just missing")
    be.set_defaults(func=cmd_backfill_embeddings)

    sub.add_parser("enrich", help="Backfill region/dietary tags on under-tagged rows").set_defaults(
        func=cmd_enrich
    )

    ds = sub.add_parser("deactivate-stale", help="Mark unclaimed listings not seen recently inactive")
    ds.add_argument("--days", type=int, default=60)
    ds.set_defaults(func=cmd_deactivate_stale)

    pnd = sub.add_parser("purge-non-diaspora",
                         help="Find/remove Native-American & other non-India-'Indian' listings")
    pnd.add_argument("--apply", action="store_true",
                     help="Actually soft-delete (default: dry-run, just report matches)")
    pnd.set_defaults(func=cmd_purge_non_diaspora)

    pnu = sub.add_parser("purge-non-usa",
                         help="Find/remove listings physically OUTSIDE the USA (foreign scrape bleed)")
    pnu.add_argument("--apply", action="store_true",
                     help="Soft-delete high-confidence matches (default: dry-run report). "
                          "'review' hints (non-US state, no coords) are never auto-removed")
    pnu.set_defaults(func=cmd_purge_non_usa)

    sub.add_parser("telegram-bot",
                   help="Run the Telegram bot front-end (long-poll; needs TELEGRAM_BOT_TOKEN)"
                   ).set_defaults(func=cmd_telegram_bot)

    dd = sub.add_parser("dedupe",
                        help="Merge duplicate listings (same name+city AND same physical place)")
    dd.add_argument("--apply", action="store_true",
                    help="Actually merge + soft-delete losers (default: dry-run report)")
    dd.set_defaults(func=cmd_dedupe)

    el = sub.add_parser("enrich-llm",
                        help="LLM-polish grounded descriptions + review summaries (needs an LLM)")
    el.add_argument("--vertical", help="One vertical (default: all)")
    el.add_argument("--limit", type=int, default=30, help="Listings per vertical per run")
    el.set_defaults(func=cmd_enrich_llm)

    sub.add_parser("movies-refresh",
                   help="Refresh Indian movies in US theaters from TMDB (needs TMDB_API_KEY)"
                   ).set_defaults(func=cmd_movies_refresh)

    sub.add_parser("consulates-seed",
                   help="Seed Indian consulates + embassy (services vertical, deduped)"
                   ).set_defaults(func=cmd_consulates_seed)

    sub.add_parser("llm-check",
                   help="Diagnose the live assistant: prints LLM config + a real ping to the "
                        "provider with the exact failure reason (never prints the key)"
                   ).set_defaults(func=cmd_llm_check)

    ov = sub.add_parser("osm-verify",
                        help="Cross-check non-OSM listings against OpenStreetMap: confirm + fill "
                             "missing phone/website/tags + raise confidence (reward-only)")
    ov.add_argument("--limit", type=int, default=30, help="Rows to check per vertical (default 30)")
    ov.set_defaults(func=cmd_osm_verify)

    cu = sub.add_parser("curate",
                        help="Cleanup sweep for acquired data: merge dupes + remove non-USA + "
                             "suppress unusable, then a quality snapshot (dry-run unless --apply)")
    cu.add_argument("--apply", action="store_true", help="Actually run the cleanup (reversible)")
    cu.set_defaults(func=cmd_curate)

    bg = sub.add_parser("backfill-geo",
                        help="Forward-geocode address-only listings (Census/Nominatim) so they sort by distance")
    bg.add_argument("--limit", type=int, default=200, help="Max rows per vertical per run")
    bg.set_defaults(func=cmd_backfill_geo)

    dg = sub.add_parser("demographics-refresh",
                        help="Pull Asian-Indian population by state/metro from the free Census ACS API")
    dg.add_argument("--year", default="2022", help="ACS 5-year vintage, e.g. 2022")
    dg.set_defaults(func=cmd_demographics_refresh)

    h1 = sub.add_parser("h1b-import",
                        help="Aggregate the free DOL H-1B disclosure file (sponsors, wages) into the KB")
    h1.add_argument("--source", default=None, help="URL or local path (defaults to DOL_H1B_DISCLOSURE_URL)")
    h1.add_argument("--year", default=None, help="Fiscal year label, e.g. 2024")
    h1.add_argument("--limit", type=int, default=None, help="Max rows to read (for a quick sample)")
    h1.set_defaults(func=cmd_h1b_import)

    ir = sub.add_parser("irs-import",
                        help="Add Indian temples & community orgs from the free IRS nonprofit master file")
    ir.add_argument("--limit", type=int, default=None, help="Max records to add (for a quick sample)")
    ir.set_defaults(func=cmd_irs_import)

    co = sub.add_parser("collect",
                        help="Scrape ALL verticals for a metro/state/all + NPPES, then process")
    cog = co.add_mutually_exclusive_group(required=True)
    cog.add_argument("--metro", help="one metro, e.g. dallas")
    cog.add_argument("--state", help="all metros in a state, e.g. TX")
    cog.add_argument("--all", action="store_true", help="every vertical across all metros (heavy)")
    co.set_defaults(func=cmd_collect)

    sub.add_parser("approval-digest", help="Human-readable summary of pending approvals").set_defaults(
        func=cmd_approval_digest
    )

    fb = sub.add_parser("feedback", help="Submit a field correction (applied by feedback agent)")
    fb.add_argument("--id", type=int, required=True, help="restaurant id")
    fb.add_argument("--field", required=True, help="e.g. phone, website, region_tag")
    fb.add_argument("--value", required=True)
    fb.add_argument("--reason", default="")
    fb.set_defaults(func=cmd_feedback)

    ft = sub.add_parser("feature", help="Mark a restaurant as a paid featured listing")
    ft.add_argument("--id", type=int, required=True)
    ft.add_argument("--days", type=int, default=30, help="featured window length (default 30)")
    ft.add_argument("--permanent", action="store_true", help="no expiry")
    ft.set_defaults(func=cmd_feature)

    uf = sub.add_parser("unfeature", help="Remove a featured listing")
    uf.add_argument("--id", type=int, required=True)
    uf.set_defaults(func=cmd_unfeature)

    q = sub.add_parser("query", help="Query restaurants exactly as the MCP tools do")
    q.add_argument("--city")
    q.add_argument("--state")
    q.add_argument("--region", help="region_tag, e.g. 'Punjabi', 'South Indian'")
    q.add_argument("--dietary", nargs="+", help="e.g. --dietary vegetarian jain")
    q.add_argument("--lat", type=float)
    q.add_argument("--lng", type=float)
    q.add_argument("--radius", type=float, default=10.0, help="miles (with --lat/--lng)")
    q.add_argument("--featured", action="store_true")
    q.add_argument("--text", help="free-text/semantic search")
    q.add_argument("--id", type=int, help="fetch one restaurant + version history")
    q.add_argument("--limit", type=int, default=10)
    q.set_defaults(func=cmd_query)

    # ---- Phase 2: temples vertical ----
    ts = sub.add_parser("temples-scrape", help="Scrape Hindu/Sikh/Jain temples for a region")
    ts.add_argument("--metro", required=True, choices=SCRAPE_REGIONS, metavar="REGION")
    ts.set_defaults(func=cmd_temples_scrape)
    sub.add_parser("temples-wikidata", help="Import notable US Hindu temples from Wikidata (CC0)"
                   ).set_defaults(func=cmd_temples_wikidata)

    sub.add_parser("temples-process", help="Process raw temples -> canonical").set_defaults(
        func=cmd_temples_process)
    sub.add_parser("temples-stats", help="Temple row counts & coverage").set_defaults(
        func=cmd_temples_stats)

    tq = sub.add_parser("temples-query", help="Query temples as the MCP tools do")
    tq.add_argument("--city")
    tq.add_argument("--state")
    tq.add_argument("--religion", help="hindu | sikh | jain")
    tq.add_argument("--text", help="semantic search")
    tq.add_argument("--lat", type=float)
    tq.add_argument("--lng", type=float)
    tq.add_argument("--radius", type=float, default=15.0)
    tq.add_argument("--limit", type=int, default=10)
    tq.set_defaults(func=cmd_temples_query)

    # ---- Phase 2: groceries vertical ----
    gs = sub.add_parser("groceries-scrape", help="Scrape Indian grocery stores for a region")
    gs.add_argument("--metro", required=True, choices=SCRAPE_REGIONS, metavar="REGION")
    gs.set_defaults(func=cmd_groceries_scrape)

    sub.add_parser("groceries-process", help="Process raw groceries -> canonical").set_defaults(
        func=cmd_groceries_process)
    sub.add_parser("groceries-stats", help="Grocery row counts & coverage").set_defaults(
        func=cmd_groceries_stats)

    gq = sub.add_parser("groceries-query", help="Query groceries as the MCP tools do")
    gq.add_argument("--city")
    gq.add_argument("--state")
    gq.add_argument("--region", help="region_tag, e.g. 'Gujarati'")
    gq.add_argument("--text", help="semantic search")
    gq.add_argument("--lat", type=float)
    gq.add_argument("--lng", type=float)
    gq.add_argument("--radius", type=float, default=15.0)
    gq.add_argument("--limit", type=int, default=10)
    gq.set_defaults(func=cmd_groceries_query)

    sub.add_parser("report", help="Compute & print the daily health/growth report").set_defaults(
        func=cmd_report)
    sub.add_parser("quality", help="Data-quality scan across verticals").set_defaults(
        func=cmd_quality)
    sub.add_parser("traffic", help="Agent traffic: tool-call analytics").set_defaults(
        func=cmd_traffic)
    sa = sub.add_parser("search-all", help="Search across all verticals (as the search_all tool)")
    sa.add_argument("text")
    sa.add_argument("--city")
    sa.add_argument("--state")
    sa.add_argument("--limit", type=int, default=10)
    sa.set_defaults(func=cmd_search_all)
    sub.add_parser("normalize-geo", help="Backfill city/state normalization across verticals").set_defaults(
        func=cmd_normalize_geo)
    ed = sub.add_parser("enhance-data", help="Backfill descriptions + geocode + embeddings (search quality)")
    ed.add_argument("--vertical", choices=("restaurants", "temples", "groceries"))
    ed.set_defaults(func=cmd_enhance_data)
    we = sub.add_parser("web-enrich",
                        help="Scrape listings' own websites for rating/price/cuisine/photo/socials")
    we.add_argument("--vertical", choices=("restaurants", "temples", "groceries",
                                           "professionals", "salons", "events"))
    we.add_argument("--limit", type=int, default=40, help="Max sites per vertical per run")
    we.add_argument("--max-age-days", type=int, default=90, dest="max_age_days",
                    help="Re-enrich a listing only if older than this")
    we.set_defaults(func=cmd_web_enrich)
    # ---- Phase 2: professionals vertical ----
    ps = sub.add_parser("professionals-scrape", help="Scrape Indian doctors/dentists/clinics")
    ps.add_argument("--metro", required=True, choices=SCRAPE_REGIONS, metavar="REGION")
    ps.set_defaults(func=cmd_professionals_scrape)

    pn = sub.add_parser("professionals-nppes",
                        help="Pull Indian providers from the free CMS NPPES registry (by US state)")
    pn.add_argument("--state", required=True, help="2-letter US state, e.g. NJ, TX, CA")
    pn.add_argument("--limit", type=int, default=200, help="Max results per surname (<=200)")
    pn.set_defaults(func=cmd_professionals_nppes)

    sub.add_parser("professionals-process", help="Process raw professionals -> canonical").set_defaults(
        func=cmd_professionals_process)
    sub.add_parser("professionals-stats", help="Professional row counts & coverage").set_defaults(
        func=cmd_professionals_stats)

    pq = sub.add_parser("professionals-query", help="Query professionals as the MCP tools do")
    pq.add_argument("--city")
    pq.add_argument("--state")
    pq.add_argument("--type", help="doctors | dentist | clinic | pharmacy")
    pq.add_argument("--text", help="semantic search")
    pq.add_argument("--lat", type=float)
    pq.add_argument("--lng", type=float)
    pq.add_argument("--radius", type=float, default=15.0)
    pq.add_argument("--limit", type=int, default=10)
    pq.set_defaults(func=cmd_professionals_query)

    # ---- Phase 2: salons vertical ----
    ss = sub.add_parser("salons-scrape", help="Scrape Indian beauty salons (threading/henna)")
    ss.add_argument("--metro", required=True, choices=SCRAPE_REGIONS, metavar="REGION")
    ss.set_defaults(func=cmd_salons_scrape)

    sub.add_parser("salons-process", help="Process raw salons -> canonical").set_defaults(
        func=cmd_salons_process)
    sub.add_parser("salons-stats", help="Salon row counts & coverage").set_defaults(
        func=cmd_salons_stats)

    sq = sub.add_parser("salons-query", help="Query salons as the MCP tools do")
    sq.add_argument("--city")
    sq.add_argument("--state")
    sq.add_argument("--tag", help="e.g. threading, henna, bridal")
    sq.add_argument("--text", help="semantic search")
    sq.add_argument("--lat", type=float)
    sq.add_argument("--lng", type=float)
    sq.add_argument("--radius", type=float, default=15.0)
    sq.add_argument("--limit", type=int, default=10)
    sq.set_defaults(func=cmd_salons_query)

    # ---- Batch verticals: apparel / sweets / studios / services (identical CLI) ----
    for _v in _BATCH_VERTICALS:
        bs = sub.add_parser(f"{_v}-scrape", help=f"Scrape Indian {_v}")
        bs.add_argument("--metro", required=True, choices=SCRAPE_REGIONS, metavar="REGION")
        bs.set_defaults(func=cmd_bv_scrape, vertical=_v)
        sub.add_parser(f"{_v}-process", help=f"Process raw {_v} -> canonical").set_defaults(
            func=cmd_bv_process, vertical=_v)
        sub.add_parser(f"{_v}-stats", help=f"{_v} row counts & coverage").set_defaults(
            func=cmd_bv_stats, vertical=_v)
        bq = sub.add_parser(f"{_v}-query", help=f"Query {_v} as the MCP tools do")
        bq.add_argument("--city"); bq.add_argument("--state")
        bq.add_argument("--tag"); bq.add_argument("--text", help="semantic search")
        bq.add_argument("--lat", type=float); bq.add_argument("--lng", type=float)
        bq.add_argument("--radius", type=float, default=15.0)
        bq.add_argument("--limit", type=int, default=10)
        bq.set_defaults(func=cmd_bv_query, vertical=_v)

    # ---- Phase 2: events vertical (automated iCal ingestion, admin-approved) ----
    ed = sub.add_parser("events-discover", help="Scan org websites for iCal calendar feeds")
    ed.add_argument("--limit", type=int, default=30)
    ed.set_defaults(func=cmd_events_discover)
    sub.add_parser("events-scrape", help="Ingest events from configured iCal feeds").set_defaults(
        func=cmd_events_scrape)
    sub.add_parser("events-process", help="Process raw events -> approval routing").set_defaults(
        func=cmd_events_process)
    sub.add_parser("events-stats", help="Event counts (approved/pending/upcoming/past)").set_defaults(
        func=cmd_events_stats)
    sub.add_parser("events-approvals", help="List events pending admin approval").set_defaults(
        func=cmd_events_approvals)
    ea = sub.add_parser("events-approve"); ea.add_argument("id", type=int)
    ea.set_defaults(func=cmd_events_approve)
    er = sub.add_parser("events-reject"); er.add_argument("id", type=int)
    er.set_defaults(func=cmd_events_reject)

    eq = sub.add_parser("events-query", help="Query upcoming events (as the MCP tool does)")
    eq.add_argument("--city")
    eq.add_argument("--state")
    eq.add_argument("--category")
    eq.add_argument("--text")
    eq.add_argument("--include-past", action="store_true", dest="include_past")
    eq.add_argument("--limit", type=int, default=10)
    eq.set_defaults(func=cmd_events_query)

    sub.add_parser("stats", help="Show row counts & coverage").set_defaults(func=cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    from .osm import OverpassError
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except OverpassError as exc:
        print(f"Overpass is rate-limiting / unavailable right now ({exc}).\n"
              "Wait a few minutes and retry, space scrapes out, or just let the worker scrape "
              "on its schedule (it retries automatically).")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
