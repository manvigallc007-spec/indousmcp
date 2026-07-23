"""In-house articles: LLM-written roundups grounded in real headlines, with citations. Covers the
output parser, generation (LLM + news mocked), the /articles + /article pages, the portal section,
and agent registration. Real dev DB, ZZTEST rows, try/finally; no network."""

from starlette.testclient import TestClient

from indo_usa_mcp import articles, db, news
from indo_usa_mcp.agents.registry import AGENTS
from indo_usa_mcp.agents.scheduler import _RUN_ORDER
from indo_usa_mcp.web.app import app

_client = TestClient(app)

_LLM_OUT = (
    "TITLE: What's new for Indian students on H-1B\n"
    "DEK: A quick look at this week's visa headlines.\n"
    "BODY:\n"
    "Several outlets reported movement on H-1B and green-card processing this week, with implications "
    "for Indian professionals in the US. The headlines point to policy discussion rather than final "
    "rules.\n\n"
    "For the specifics — dates, eligibility and any official guidance — readers should follow the "
    "linked sources, which carry the full detail.")

_HEADS = [
    {"title": "H-1B rule update floated", "url": "https://ex.com/zztest-a1", "source": "Visa Wire"},
    {"title": "Green card backlog latest", "url": "https://ex.com/zztest-a2", "source": "The Times"},
    {"title": "Students weigh options", "url": "https://ex.com/zztest-a3", "source": "Campus Daily"},
    {"title": "Employers respond", "url": "https://ex.com/zztest-a4", "source": "Biz Report"},
]


def _cleanup():
    db.execute("DELETE FROM articles WHERE slug LIKE 'what-s-new-for-indian-students%' "
               "OR title LIKE 'ZZTEST%'")


# --------------------------------------------------------------- parser
def test_parse_requires_title_and_body():
    assert articles._parse("TITLE: Only a title") is None            # no body
    t, d, b = articles._parse(_LLM_OUT)
    assert t.startswith("What's new") and d and "H-1B" in b


# --------------------------------------------------------------- generation (mocked LLM + news)
def test_generate_for_stores_grounded_article_with_sources(monkeypatch):
    monkeypatch.setattr(articles.assistant, "llm_active", lambda: True)
    monkeypatch.setattr(articles.assistant, "complete_text", lambda s, u: _LLM_OUT)
    monkeypatch.setattr(articles.news, "latest", lambda limit=12, category=None: _HEADS)
    monkeypatch.setattr(articles.settings, "articles_enabled", True)
    try:
        made = articles.generate_for("immigration")
        assert made and made["category"] == "immigration"
        got = articles.get(made["slug"])
        assert got and got["body"] and got["dek"]
        # every cited source is preserved (grounding), so the page can list them
        urls = {s["url"] for s in got["sources"]}
        assert {"https://ex.com/zztest-a1", "https://ex.com/zztest-a4"} <= urls
    finally:
        _cleanup()


def test_generate_needs_enough_headlines(monkeypatch):
    monkeypatch.setattr(articles.assistant, "llm_active", lambda: True)
    monkeypatch.setattr(articles.assistant, "complete_text", lambda s, u: _LLM_OUT)
    monkeypatch.setattr(articles.news, "latest", lambda limit=12, category=None: _HEADS[:2])
    monkeypatch.setattr(articles.settings, "articles_enabled", True)
    assert articles.generate_for("immigration") is None              # < _MIN_HEADLINES -> skip


def test_generate_noop_when_llm_off(monkeypatch):
    monkeypatch.setattr(articles.assistant, "llm_active", lambda: False)
    monkeypatch.setattr(articles.settings, "articles_enabled", True)
    assert articles.generate_for("immigration") is None
    assert articles.generate_due()["created"] == 0


# --------------------------------------------------------------- pages
def test_article_page_shows_body_sources_and_ai_disclaimer(monkeypatch):
    monkeypatch.setattr(articles.assistant, "llm_active", lambda: True)
    monkeypatch.setattr(articles.assistant, "complete_text", lambda s, u: _LLM_OUT)
    monkeypatch.setattr(articles.news, "latest", lambda limit=12, category=None: _HEADS)
    monkeypatch.setattr(articles.settings, "articles_enabled", True)
    try:
        made = articles.generate_for("immigration")
        r = _client.get(f"/article/{made['slug']}")
        assert r.status_code == 200
        assert "Sources" in r.text and "ex.com/zztest-a1" in r.text
        assert "AI-written summary" in r.text                          # honesty disclaimer present
        assert _client.get("/articles").status_code == 200
        assert _client.get("/articles?cat=immigration").status_code == 200
    finally:
        _cleanup()


# --------------------------------------------------------------- agent wiring
def test_articles_agent_registered_and_scheduled():
    assert "articles" in AGENTS and "articles" in _RUN_ORDER
    # news must run before articles (roundups summarize fresh headlines)
    assert _RUN_ORDER.index("news") < _RUN_ORDER.index("articles")
