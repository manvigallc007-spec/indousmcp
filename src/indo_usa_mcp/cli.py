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
from .pipeline import ingest, outreach, seed
from .pipeline.scrapers import SCRAPERS
from .pipeline.scrapers.metros import METROS


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


def cmd_stats(_: argparse.Namespace) -> None:
    _print(queries.stats())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="diaspora", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Apply SQL migrations").set_defaults(func=cmd_init_db)

    sp = sub.add_parser("scrape", help="Run a scraper into restaurant_raw")
    sp.add_argument("--metro", required=True, choices=sorted(METROS))
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

    sub.add_parser("stats", help="Show row counts & coverage").set_defaults(func=cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
