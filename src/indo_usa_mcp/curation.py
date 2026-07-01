"""One-command curation sweep for acquired data.

After acquiring data from a source (OSM, IRS, NPPES, Socrata, consulates, submissions...), the same
cleanup steps should run: merge duplicates (incl. cross-source), remove records physically outside
the USA, and suppress genuinely-unusable rows. These are DB-only + reversible (soft-delete), so this
sweep is safe to run often. The heavier ENRICHMENT (enhance-data, backfill-geo, backfill-embeddings)
stays as separate steps because it's slow/network-bound. dry_run=True only reports what would change.
"""

from __future__ import annotations

from typing import Any


def run(apply: bool = False) -> dict[str, Any]:
    """Run (or, with apply=False, preview) the cleanup curation sweep + a quality snapshot."""
    from . import quality, verticals
    dry = not apply
    out: dict[str, Any] = {"mode": "apply" if apply else "dry-run"}
    out["duplicates"] = verticals.dedupe_listings(dry_run=dry)
    out["non_usa"] = verticals.purge_non_usa(dry_run=dry)
    out["low_quality"] = quality.suppress_low_quality(dry_run=dry)
    out["quality"] = quality.scan_all()
    if apply:
        out["next"] = ("finish enrichment with: enhance-data · backfill-geo · "
                       "backfill-embeddings --all")
    return out
