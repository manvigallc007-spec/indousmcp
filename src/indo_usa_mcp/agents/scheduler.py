"""Simple in-process scheduler (blueprint's 'scheduler + worker').

Runs due agents on their interval in a loop. Intended to run as a single long-lived
process on the VPS (alongside, or instead of, OS cron). Defaults come from each agent's
``default_interval_s`` but can be overridden per agent.

    python -m indo_usa_mcp.agents.scheduler            # run forever
    python -m indo_usa_mcp.agents.scheduler --once     # one due-check pass, then exit
"""

from __future__ import annotations

import argparse
import time

from .. import db
from .registry import AGENTS
from .runner import run_agent

# Sensible default cadence (seconds). Cleaner runs often; scrapers/outreach daily.
DEFAULT_SCHEDULE = {name: agent.default_interval_s for name, agent in AGENTS.items()}

# Order matters within a tick: scrape -> clean -> enrich -> monitor.
_RUN_ORDER = [
    "scraper", "cleaner", "enrichment", "feedback", "approval_assistant",
    "temple_scraper", "temple_cleaner",
    "discovery", "outreach", "monitoring", "submission",
]

# How often the loop wakes to check what's due.
TICK_SECONDS = 60


def run_loop(once: bool = False, schedule: dict[str, int] | None = None) -> None:
    schedule = schedule or DEFAULT_SCHEDULE
    last_run: dict[str, float] = {}

    # Don't race ahead of whichever process applies migrations.
    db.wait_for_schema()

    while True:
        now = time.monotonic()
        for name in _RUN_ORDER:
            if name not in schedule:
                continue
            interval = schedule[name]
            if name not in last_run or (now - last_run[name]) >= interval:
                print(f"[scheduler] running agent '{name}'")
                outcome = run_agent(name)
                print(f"[scheduler]   -> {outcome['status']} ({outcome['duration_ms']}ms)")
                last_run[name] = now
        if once:
            return
        time.sleep(TICK_SECONDS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diaspora agent scheduler")
    p.add_argument("--once", action="store_true", help="Run all due agents once, then exit")
    args = p.parse_args(argv)
    run_loop(once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
