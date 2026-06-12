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


def cmd_professionals_scrape(args: argparse.Namespace) -> None:
    print(f"Scraping professionals for region={args.metro} ...")
    n = professionals.scrape_to_raw(args.metro)
    print(f"Upserted {n} raw professional observation(s).")


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
    # ---- Phase 2: professionals vertical ----
    ps = sub.add_parser("professionals-scrape", help="Scrape Indian doctors/dentists/clinics")
    ps.add_argument("--metro", required=True, choices=SCRAPE_REGIONS, metavar="REGION")
    ps.set_defaults(func=cmd_professionals_scrape)

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
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
