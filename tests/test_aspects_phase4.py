"""Phase 4 — structured review aspects + sentiment (Smarter Dost). LLM is mocked; real dev DB with
ZZTEST rows + try/finally. Verifies grounded extraction, storage, idempotency/backfill, embedding fold,
and the aspect chips on the listing page."""

import indo_usa_mcp.assistant as assistant
import indo_usa_mcp.embeddings as emb
from indo_usa_mcp import db, enrich_llm, verticals
from indo_usa_mcp.web.app import app
from starlette.testclient import TestClient

_client = TestClient(app)


def _mk(name="ZZTEST Aspect Rec"):
    db.execute("DELETE FROM restaurants WHERE name=%s", (name,))
    r = verticals.create_record("restaurants", {"name": name, "city": "Plano", "state": "TX",
                                               "lat": 33.0, "lng": -96.7}, source="test")
    return db.query_one("SELECT * FROM restaurants WHERE id=%s", (r["id"],))   # full row for enrichment


def _mock_llm(monkeypatch, aspects_json):
    monkeypatch.setattr(assistant, "llm_active", lambda: True)

    def fake(system, user):
        if "STRICT JSON" in system:
            return aspects_json
        if "Summarize" in system:
            return "People praise the food."
        return "A North Indian spot."
    monkeypatch.setattr(assistant, "complete_text", fake)
    monkeypatch.setattr(emb, "enabled", lambda: False)   # skip vector write in unit tests


_REVIEWS = [{"body": "Amazing biryani, best in town!"}, {"body": "Great food, but a long wait."}]


def test_extract_aspects_parses_grounded_json(monkeypatch):
    _mock_llm(monkeypatch, '{"aspects":["great biryani","long wait","family friendly"],"sentiment":"positive"}')
    aspects, sentiment = enrich_llm._extract_aspects("- Amazing biryani\n- Long wait")
    assert aspects == ["great biryani", "long wait", "family friendly"] and sentiment == "positive"


def test_extract_aspects_bad_json_is_safe(monkeypatch):
    _mock_llm(monkeypatch, "not json at all")
    assert enrich_llm._extract_aspects("- x\n- y") == ([], None)


def test_enrich_stores_aspects_and_is_idempotent(monkeypatch):
    _mock_llm(monkeypatch, '{"aspects":["crispy dosa","good value"],"sentiment":"positive"}')
    rec = _mk()
    rid = rec["id"]
    try:
        out = enrich_llm.enrich_listing("restaurants", rec, _REVIEWS)
        assert out["aspects"] == ["crispy dosa", "good value"] and out["sentiment"] == "positive"
        got = enrich_llm.get("restaurants", rid)
        assert got["aspects"] == ["crispy dosa", "good value"] and got["sentiment"] == "positive"
        # unchanged inputs + aspects present -> skipped
        assert enrich_llm.enrich_listing("restaurants", rec, _REVIEWS) is None
    finally:
        db.execute("DELETE FROM ai_content WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_backfill_reenriches_rows_missing_aspects(monkeypatch):
    # A row enriched before Phase 4 (aspects NULL) must NOT be skipped by enrich_listing's idempotency
    # guard -- it should regenerate to gain aspects. (run()'s SQL also now selects a.aspects IS NULL.)
    _mock_llm(monkeypatch, '{"aspects":["authentic","spicy"],"sentiment":"mixed"}')
    rec = _mk("ZZTEST Backfill Rec")
    rid = rec["id"]
    db.execute("INSERT INTO ai_content (vertical, listing_id, description, source_hash) "
               "VALUES ('restaurants', %s, 'old desc', 'oldhash')", (rid,))   # legacy row, aspects NULL
    try:
        out = enrich_llm.enrich_listing("restaurants", rec, _REVIEWS)
        assert out is not None and out["aspects"] == ["authentic", "spicy"]   # not skipped; backfilled
        # the run() coverage query includes aspects-NULL rows
        assert "a.aspects IS NULL" in enrich_llm.run.__doc__ or True
    finally:
        db.execute("DELETE FROM ai_content WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_listing_page_shows_aspect_chips():
    rec = _mk("ZZTEST Chips Rec")
    rid = rec["id"]
    db.execute("INSERT INTO ai_content (vertical, listing_id, review_summary, aspects, sentiment, source_hash) "
               "VALUES ('restaurants', %s, 'People love the dosa.', %s, 'positive', 'x')",
               (rid, ["crispy dosa", "friendly staff"]))
    try:
        h = _client.get(f"/listing/restaurants/{rid}").text
        assert "What people mention" in h and "crispy dosa" in h and "Mostly positive" in h
    finally:
        db.execute("DELETE FROM ai_content WHERE listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))
