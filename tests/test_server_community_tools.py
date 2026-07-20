"""Agent-first MCP tools for the community content: search_community_questions, get_community_answers,
get_today_highlights. Real dev DB, ZZTEST rows, try/finally; output must be JSON-serializable."""

import json

from indo_usa_mcp import db, qa, server

_E = "zztest_mcp_comm@example.com"


def _tool_names():
    return set(server.mcp._tool_manager._tools.keys())


def _clean():
    db.execute("DELETE FROM answers WHERE author_email=%s", (_E,))
    db.execute("DELETE FROM questions WHERE asker_email=%s", (_E,))


def test_community_tools_registered():
    for t in ("search_community_questions", "get_community_answers", "get_today_highlights"):
        assert t in _tool_names(), t


def test_search_and_get_answers():
    q = qa.create_question("ZZTEST where to find Telugu tiffin in Frisco TX?", asker_email=_E,
                           city="Frisco", state="TX")
    qa.add_answer(q["id"], "Tiffin Bhavan on Main St is great.", _E)
    try:
        s = server.search_community_questions("tiffin")
        assert s["count"] >= 1 and any(r["slug"] == q["slug"] for r in s["results"])
        a = server.get_community_answers(q["slug"])
        assert "Telugu tiffin" in a["title"] and len(a["answers"]) == 1
        assert a["answers"][0]["by"] in ("community", "Dost (AI)")
        assert server.get_community_answers("does-not-exist")["error"] == "not_found"
    finally:
        _clean()


def test_search_empty_query_returns_none():
    assert server.search_community_questions("")["count"] == 0


def test_today_highlights_json_serializable():
    out = server.get_today_highlights(city="Plano", state="TX", languages="Telugu,Hindi")
    json.dumps(out)                       # raises if any datetime leaked through
    assert "tithi" in out and "festival" in out and isinstance(out.get("events"), list)
    assert out["city"] == "Plano"
