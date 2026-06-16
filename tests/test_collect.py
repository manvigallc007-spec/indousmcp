"""`collect` CLI: scrapes every vertical for a state/metro + NPPES, then processes. No DB/network."""

import argparse

import indo_usa_mcp.agents as agents_mod
import indo_usa_mcp.cli as cli

_FAKE_AGENTS = {"scraper": 1, "temple_scraper": 1, "finance_scraper": 1, "nppes_scraper": 1,
                "event_scraper": 1, "cleaner": 1, "temple_cleaner": 1}


def _patch(monkeypatch):
    calls = []
    monkeypatch.setattr(agents_mod, "AGENTS", _FAKE_AGENTS)
    monkeypatch.setattr(agents_mod, "run_agent",
                        lambda name, **kw: calls.append((name, kw)) or {"status": "success", "result": {}})
    return calls


def test_collect_state_runs_all_verticals_and_nppes(monkeypatch):
    calls = _patch(monkeypatch)
    cli.cmd_collect(argparse.Namespace(metro=None, state="TX", all=False))
    names = [c[0] for c in calls]
    assert "scraper" in names and "temple_scraper" in names and "finance_scraper" in names
    assert "event_scraper" not in names                    # feed-based, skipped
    assert "nppes_scraper" in names                         # state-based, run for TX
    tx = {"dallas", "houston", "austin", "san_antonio"}
    assert set(dict(calls)["temple_scraper"]["metros"]) <= tx
    assert dict(calls)["nppes_scraper"]["states"] == ["TX"]
    assert "cleaner" in names and "temple_cleaner" in names  # processed after


def test_collect_metro_derives_state(monkeypatch):
    calls = _patch(monkeypatch)
    cli.cmd_collect(argparse.Namespace(metro="houston", state=None, all=False))
    assert dict(calls)["scraper"]["metros"] == ["houston"]
    assert dict(calls)["nppes_scraper"]["states"] == ["TX"]


def test_collect_unknown_metro_is_safe(monkeypatch):
    calls = _patch(monkeypatch)
    cli.cmd_collect(argparse.Namespace(metro="atlantis", state=None, all=False))
    assert calls == []                                     # nothing scraped for an unknown metro
