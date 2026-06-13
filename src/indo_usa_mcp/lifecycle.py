"""Stale-data lifecycle — decay, don't delete.

The full ladder, none of it a hard delete on a single signal:
  1. Demote in ranking — handled automatically by the freshness penalty in ranking.py as
     `last_seen_at` ages (a record the scraper hasn't re-confirmed sinks).
  2. Deactivate — the per-vertical cleaners set is_active=false for unclaimed listings not seen
     in 60-150 days (out of default results, still queryable; reactivated on re-sight).
  3. Archive (here) — soft-delete (reversible) records unseen for a very long time (default
     180 days = dozens of missed scrape cycles, not a transient blip), never touching claimed
     or featured listings.
  4. Auto-restore — if the scraper re-sees an archived listing (its last_seen_at moves past the
     archive time), un-archive it.

Events are excluded (date-based; they have their own purge_old).
"""

from __future__ import annotations

from typing import Any

from . import db, verticals

_SKIP = {"events"}


def _verticals() -> list[str]:
    return [v for v in verticals.VERTICALS if v not in _SKIP]


def archive_stale(unseen_days: int = 180) -> dict[str, int]:
    """Soft-delete long-unseen, unclaimed, unfeatured listings, marked `auto_archived` so
    they can be safely auto-restored later (without touching admin/merge soft-deletes)."""
    out: dict[str, int] = {}
    for v in _verticals():
        t = verticals._table(v)
        rows = db.query(
            f"UPDATE {t} SET deleted_at = now(), is_active = false, auto_archived = true, "
            f"updated_at = now() "
            f"WHERE deleted_at IS NULL AND NOT is_claimed AND NOT is_featured "
            f"AND created_at < now() - (%s || ' days')::interval "
            f"AND (last_seen_at IS NULL OR last_seen_at < now() - (%s || ' days')::interval) "
            f"RETURNING id", (unseen_days, unseen_days))
        out[v] = len(rows)
    return out


def restore_reseen() -> dict[str, int]:
    """Un-archive listings the scraper has re-seen — but ONLY ones lifecycle auto-archived,
    so a re-seen admin/merge-deleted duplicate is never resurrected."""
    out: dict[str, int] = {}
    for v in _verticals():
        t = verticals._table(v)
        rows = db.query(
            f"UPDATE {t} SET deleted_at = NULL, is_active = true, auto_archived = false, "
            f"updated_at = now() "
            f"WHERE auto_archived AND deleted_at IS NOT NULL AND last_seen_at IS NOT NULL "
            f"AND last_seen_at > deleted_at RETURNING id")
        out[v] = len(rows)
    return out


def run(unseen_days: int = 180) -> dict[str, Any]:
    restored = restore_reseen()   # restore first, so a re-seen record isn't re-archived
    archived = archive_stale(unseen_days)
    return {"archived": archived, "restored": restored,
            "archived_total": sum(archived.values()), "restored_total": sum(restored.values())}
