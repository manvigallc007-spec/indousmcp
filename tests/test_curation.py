"""One-command curation sweep: orchestrates dedupe + non-USA purge + low-quality suppression with
the right dry_run flag, plus a quality snapshot. Underlying functions are monkeypatched."""

import indo_usa_mcp.curation as curation
from indo_usa_mcp import quality, verticals


def _patch(monkeypatch, calls):
    monkeypatch.setattr(verticals, "dedupe_listings",
                        lambda dry_run: calls.update(dedupe=dry_run) or {"merged_groups": 0})
    monkeypatch.setattr(verticals, "purge_non_usa",
                        lambda dry_run: calls.update(nonusa=dry_run) or {"total": 0})
    monkeypatch.setattr(quality, "suppress_low_quality",
                        lambda dry_run: calls.update(lowq=dry_run) or {"total": 0})
    monkeypatch.setattr(quality, "scan_all", lambda: {"restaurants": {"total": 5}})


def test_curate_dry_run_previews_without_applying(monkeypatch):
    calls = {}
    _patch(monkeypatch, calls)
    out = curation.run(apply=False)
    assert out["mode"] == "dry-run"
    assert calls == {"dedupe": True, "nonusa": True, "lowq": True}   # all in dry-run
    assert out["quality"] == {"restaurants": {"total": 5}}
    assert "next" not in out


def test_curate_dry_run_executes_against_db():
    # No monkeypatch: exercises the REAL dedupe_listings / purge_non_usa / suppress_low_quality /
    # scan_all so a signature or SQL error (e.g. a shadowed function) can't slip through unnoticed.
    out = curation.run(apply=False)
    assert out["mode"] == "dry-run"
    for k in ("duplicates", "non_usa", "low_quality", "quality"):
        assert k in out


def test_curate_apply_runs_all_and_points_to_enrichment(monkeypatch):
    calls = {}
    _patch(monkeypatch, calls)
    out = curation.run(apply=True)
    assert out["mode"] == "apply"
    assert calls == {"dedupe": False, "nonusa": False, "lowq": False}   # actually applied
    assert "backfill-embeddings" in out["next"]


def test_curate_apply_executes_against_db():
    # No monkeypatch, apply=True: exercises the REAL dry_run=False code paths (the UPDATEs), not just
    # the SELECTs dry-run covers. Regression: dedupe_listings' apply path used to crash on a shadowed
    # _MERGE_FILL trying to bind a JSONB dict -- dry-run-only coverage never reached that line.
    out = curation.run(apply=True)
    assert out["mode"] == "apply"
    for k in ("duplicates", "non_usa", "low_quality", "quality"):
        assert k in out
