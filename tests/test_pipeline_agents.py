"""The 5 pipeline agents that make curation + vectorization autonomous (no manual CLI).

Pure/mocked — no DB or network. Verifies each agent is registered AND actually scheduled
(in _RUN_ORDER, not just AGENTS — being in AGENTS alone means it never runs), and that each
run() delegates to the right reusable pipeline function.
"""

import indo_usa_mcp.assistant as assistant
import indo_usa_mcp.enrich_llm as enrich_llm
import indo_usa_mcp.verticals as verticals
from indo_usa_mcp.agents import AGENTS
from indo_usa_mcp.agents import definitions as d
from indo_usa_mcp.agents.scheduler import DEFAULT_SCHEDULE, _RUN_ORDER
from indo_usa_mcp.pipeline import ingest
from indo_usa_mcp.pipeline.scrapers import socrata

_NEW = ["llm_enrichment", "curation", "geo_backfill", "embedding_backfill", "socrata_scraper"]


def test_new_agents_registered_scheduled_and_ordered():
    for name in _NEW:
        assert name in AGENTS, f"{name} not registered"
        assert name in DEFAULT_SCHEDULE and DEFAULT_SCHEDULE[name] > 0
        # Being in AGENTS is not enough: the scheduler only runs names in _RUN_ORDER.
        assert name in _RUN_ORDER, f"{name} registered but never runs (missing from _RUN_ORDER)"


def test_movies_now_actually_runs():
    # Regression: MoviesAgent was in AGENTS but missing from _RUN_ORDER (silently never ran).
    assert "movies" in _RUN_ORDER


def test_agent_names_unique():
    names = [a.name for a in d.ALL_AGENTS]
    assert len(names) == len(set(names))


def test_curation_after_cleaning_and_before_lifecycle():
    # curate the canonical layer only after the cleaners have populated it.
    order = {n: i for i, n in enumerate(_RUN_ORDER)}
    assert order["cleaner"] < order["curation"] < order["embedding_backfill"]
    # embedding backfill runs last of the chain, to catch anything llm_enrichment re-embedded/added.
    assert order["llm_enrichment"] < order["embedding_backfill"]
    # socrata feeds the raw layer, so it must run before the cleaner promotes raw -> canonical.
    assert order["socrata_scraper"] < order["cleaner"]


# --------------------------------------------------------------- delegation (mocked)
def test_llm_enrichment_delegates_with_daily_batch(monkeypatch):
    seen = {}
    monkeypatch.setattr(enrich_llm, "run_all",
                        lambda limit_per=30: seen.update(limit_per=limit_per) or {"ok": 1})
    out = d.LlmEnrichmentAgent().run()
    assert seen["limit_per"] == 30 and out == {"ok": 1}


def test_llm_enrichment_noops_without_llm(monkeypatch):
    # The real enrich_llm.run_all path: gated on assistant.llm_active() -> skip, no DB touched.
    monkeypatch.setattr(assistant, "llm_active", lambda: False)
    out = d.LlmEnrichmentAgent().run()
    assert out and all(v.get("skipped") == "llm_inactive" for v in out.values())


def test_curation_runs_dedupe_and_non_usa_live(monkeypatch):
    calls = {}
    monkeypatch.setattr(verticals, "dedupe_listings",
                        lambda dry_run=True: calls.update(dedupe=dry_run) or {"merged": 3})
    monkeypatch.setattr(verticals, "purge_non_usa",
                        lambda dry_run=True: calls.update(purge=dry_run) or {"purged": 2})
    out = d.CurationAgent().run()
    assert calls == {"dedupe": False, "purge": False}          # applies, not dry-run
    assert out == {"duplicates": {"merged": 3}, "non_usa": {"purged": 2}}


def test_geo_backfill_delegates(monkeypatch):
    seen = {}
    monkeypatch.setattr(verticals, "backfill_coords",
                        lambda limit=200: seen.update(limit=limit) or {"geocoded": 5})
    out = d.GeoBackfillAgent().run()
    assert seen["limit"] == 200 and out == {"geocoded": 5}


def test_embedding_backfill_only_missing(monkeypatch):
    seen = {}
    monkeypatch.setattr(ingest, "backfill_embeddings",
                        lambda only_missing=True: seen.update(om=only_missing) or {"embedded": 4})
    out = d.EmbeddingBackfillAgent().run()
    assert seen["om"] is True and out == {"embedded": 4}


def test_socrata_agent_iterates_sources_and_isolates_errors(monkeypatch):
    monkeypatch.setattr(socrata, "SOCRATA_SOURCES", {"a": {}, "b": {}})

    def _imp(key):
        if key == "b":
            raise RuntimeError("boom")
        return {"added": 1, "key": key}

    monkeypatch.setattr(socrata, "import_source", _imp)
    out = d.SocrataScraperAgent().run()
    assert out["a"] == {"added": 1, "key": "a"}
    assert "error" in out["b"] and "boom" in out["b"]["error"]  # one bad source doesn't kill the rest
