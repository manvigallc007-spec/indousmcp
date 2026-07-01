"""create_record records real provenance (source_name + confidence), not a flat 'admin'."""

import indo_usa_mcp.embeddings as emb
import indo_usa_mcp.verticals as verticals
from indo_usa_mcp import db


def _make(monkeypatch, name, **kw):
    monkeypatch.setattr(emb, "enabled", lambda: False)          # skip embedding (no model load)
    db.execute("DELETE FROM services WHERE name = %s", (name,))
    return verticals.create_record(
        "services", {"name": name, "city": "Testville", "state": "TX", "lat": 32.0, "lng": -96.0,
                     "service_type": "consulate"}, **kw)


def test_create_record_records_source_and_confidence(monkeypatch):
    name = "ZZTest Consulate Provenance"
    try:
        res = _make(monkeypatch, name, source="consulate", confidence=0.9)
        assert res.get("ok"), res
        row = db.query_one("SELECT source_name, source_id, confidence_score FROM services "
                           "WHERE id = %s", (res["id"],))
        assert row["source_name"] == "consulate"
        assert row["source_id"].startswith("consulate/")
        assert abs(float(row["confidence_score"]) - 0.9) < 1e-6
    finally:
        db.execute("DELETE FROM services WHERE name = %s", (name,))


def test_create_record_defaults_to_admin(monkeypatch):
    name = "ZZTest Admin Provenance"
    try:
        res = _make(monkeypatch, name)                          # no source -> admin, confidence 0.7
        assert res.get("ok"), res
        row = db.query_one("SELECT source_name, confidence_score FROM services WHERE id = %s",
                           (res["id"],))
        assert row["source_name"] == "admin"
        assert abs(float(row["confidence_score"]) - 0.7) < 1e-6
    finally:
        db.execute("DELETE FROM services WHERE name = %s", (name,))
