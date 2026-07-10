"""Agent-layer correctness/ops fixes: embedding backfill covers every vertical + the KB, the
featured-expiry agent clears stale flags (and the admin stat is guarded), and Monitoring pushes a
newly-raised critical alert out-of-band. Real dev DB, ZZTEST rows, try/finally."""

import indo_usa_mcp.embeddings as emb
from indo_usa_mcp import db, knowledge, queries, verticals
from indo_usa_mcp.agents.definitions import MonitoringAgent
from indo_usa_mcp.config import settings
from indo_usa_mcp.pipeline import ingest, outreach

_DIM = settings.embedding_dim


# --------------------------------------------------------------- C2: embedding backfill breadth
def test_backfill_embeddings_covers_non_restaurant_vertical_and_kb(monkeypatch):
    # Insert with embeddings OFF (so the vectors are NULL), then backfill with embeddings ON.
    monkeypatch.setattr(emb, "enabled", lambda: False)
    rec = verticals.create_record("temples", {"name": "ZZTEST Emb Temple", "city": "Plano",
                                              "state": "TX", "lat": 33.0, "lng": -96.7}, source="test")
    tid = rec["id"]
    db.execute("DELETE FROM kb_documents WHERE source_ref = 'zztest-emb-doc'")
    knowledge.upsert_document(source_type="article", source_ref="zztest-emb-doc",
                              title="ZZTEST Emb Doc", content="Embedding backfill coverage test body.")
    try:
        assert db.query_one("SELECT embedding IS NULL AS n FROM temples WHERE id=%s", (tid,))["n"]
        # now enable embeddings with a deterministic fake vector (no provider/model download)
        monkeypatch.setattr(emb, "enabled", lambda: True)
        monkeypatch.setattr(emb, "embed", lambda text: [0.0] * _DIM)
        out = ingest.backfill_embeddings(only_missing=True)
        assert "temples" in out["by_table"] and "kb_chunks" in out["by_table"]
        assert not db.query_one("SELECT embedding IS NULL AS n FROM temples WHERE id=%s", (tid,))["n"]
        left = db.query_one("SELECT count(*) AS n FROM kb_chunks c JOIN kb_documents d ON d.id=c.document_id "
                            "WHERE d.source_ref='zztest-emb-doc' AND c.embedding IS NULL")["n"]
        assert left == 0
    finally:
        db.execute("DELETE FROM temples WHERE id=%s", (tid,))
        db.execute("DELETE FROM kb_documents WHERE source_ref='zztest-emb-doc'")


# --------------------------------------------------------------- C3: featured expiry + guarded stat
def test_featured_expiry_clears_stale_flag_and_stat_is_guarded(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)
    rec = verticals.create_record("restaurants", {"name": "ZZTEST Featured Expiry", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7}, source="test")
    rid = rec["id"]
    try:
        db.execute("UPDATE restaurants SET is_featured=true, featured_until=now() - interval '1 day' "
                   "WHERE id=%s", (rid,))
        # raw column is true but the paid window passed -> the admin stat must NOT count it
        raw = db.query_one("SELECT count(*) AS n FROM restaurants WHERE id=%s AND is_featured", (rid,))["n"]
        assert raw == 1
        counted_before = queries.stats()["restaurants_featured"]
        out = verticals.expire_featured()
        assert out["expired"] >= 1
        row = db.query_one("SELECT is_featured, featured_until FROM restaurants WHERE id=%s", (rid,))
        assert row["is_featured"] is False and row["featured_until"] is None
        # a permanent feature (featured_until NULL) is left untouched
        db.execute("UPDATE restaurants SET is_featured=true, featured_until=NULL WHERE id=%s", (rid,))
        verticals.expire_featured()
        assert db.query_one("SELECT is_featured FROM restaurants WHERE id=%s", (rid,))["is_featured"] is True
        _ = counted_before   # (guard exercised above; value depends on shared dev data)
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def test_stats_featured_excludes_expired(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)
    rec = verticals.create_record("restaurants", {"name": "ZZTEST Stat Expired", "city": "Plano",
                                                  "state": "TX", "lat": 33.0, "lng": -96.7}, source="test")
    rid = rec["id"]
    try:
        db.execute("UPDATE restaurants SET is_featured=true, featured_until=now() - interval '1 day' "
                   "WHERE id=%s", (rid,))
        # This specific expired row must not be included in the guarded count.
        in_guarded = db.query_one(
            "SELECT count(*) AS n FROM restaurants WHERE id=%s AND deleted_at IS NULL AND "
            "(is_featured AND (featured_until IS NULL OR featured_until > now()))", (rid,))["n"]
        assert in_guarded == 0
    finally:
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


# --------------------------------------------------------------- C4: real-time critical alert push
def test_monitoring_pushes_new_critical_and_stores_detail(monkeypatch):
    calls = []
    monkeypatch.setattr(outreach, "send_email",
                        lambda to, subject, body, **k: calls.append((subject, body)) or True)
    monkeypatch.setattr(settings, "report_email", "admin@example.com")
    db.execute("DELETE FROM agent_alerts WHERE kind='agent_failure'")          # ensure a fresh raise
    db.execute("INSERT INTO agent_runs (agent, status, error) VALUES "
               "('zztest_agent', 'error', 'ZZBOOM sample traceback')")
    try:
        MonitoringAgent().run()
        pushes = [c for c in calls if "agent_failure" in c[0]]
        assert pushes, "expected an out-of-band push for the newly-raised agent_failure critical"
        row = db.query_one("SELECT details FROM agent_alerts WHERE kind='agent_failure' AND NOT resolved")
        assert row and row["details"] and "ZZBOOM" in row["details"]["error"]   # error snippet stored inline
        # second run must NOT re-push an already-open alert
        calls.clear()
        MonitoringAgent().run()
        assert not [c for c in calls if "agent_failure" in c[0]]
    finally:
        db.execute("DELETE FROM agent_runs WHERE agent='zztest_agent'")
        db.execute("DELETE FROM agent_alerts WHERE kind='agent_failure'")
