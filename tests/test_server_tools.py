"""Agent-first MCP tools: the new festival/knowledge/submission/detail tools, cross-vertical
submit_correction, and the security gate that keeps internal write-tools off the default endpoint."""

import os
import subprocess
import sys

from indo_usa_mcp import server


def _tool_names():
    return set(server.mcp._tool_manager._tools.keys())


def test_new_agent_tools_registered():
    for t in ("get_festival_dates", "search_knowledge", "submit_listing",
              "get_movie_details", "get_h1b_sponsor_details"):
        assert t in _tool_names(), t


def test_internal_write_tools_gated_off_by_default():
    # draft_claim_outreach / find_unclaimed_restaurants create claims + outreach drafts -> must NOT be
    # exposed on the anonymous public endpoint unless explicitly enabled.
    names = _tool_names()
    assert "draft_claim_outreach" not in names
    assert "find_unclaimed_restaurants" not in names


def test_gate_controls_internal_tool_registration():
    # The flag is read at import time, so verify both states in fresh subprocesses (no DB needed to
    # import the server / register tools).
    code = ("from indo_usa_mcp import server;"
            "print('draft_claim_outreach' in server.mcp._tool_manager._tools)")
    off = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "MCP_INTERNAL_TOOLS": "0"})
    on = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                        env={**os.environ, "MCP_INTERNAL_TOOLS": "1"})
    assert off.returncode == 0 and on.returncode == 0, (off.stderr, on.stderr)
    assert off.stdout.strip().splitlines()[-1] == "False"
    assert on.stdout.strip().splitlines()[-1] == "True"


def test_get_festival_dates_query_and_upcoming():
    one = server.get_festival_dates("diwali")
    assert one["results"] and "diwali" in one["results"][0]["name"].lower()
    assert one["results"][0]["days_until"] >= 0 and one["note"]           # ISO date + confirm-locally note
    assert "T" not in one["results"][0]["date"]                            # date-only ISO (no time)
    many = server.get_festival_dates("", 4)
    assert len(many["results"]) <= 4


def test_search_knowledge_shape():
    out = server.search_knowledge("H-1B visa sponsorship", limit=3)
    assert set(out.keys()) == {"count", "results"} and out["count"] == len(out["results"])


def test_submit_correction_rejects_non_restaurant_vertical():
    out = server.submit_correction(1, "phone", "+19990000", vertical="temples")
    assert out["ok"] is False and out["error"] == "not_supported" and out["vertical"] == "temples"


def test_submit_listing_rejects_events_and_requires_name():
    assert server.submit_listing("events", "X")["error"] == "bad_vertical"
    assert server.submit_listing("restaurants", "")["error"] == "name_required"


def test_detail_tools_return_not_found_for_missing_id():
    assert server.get_movie_details(999_999_999)["error"] == "not_found"
    assert server.get_h1b_sponsor_details(999_999_999)["error"] == "not_found"
