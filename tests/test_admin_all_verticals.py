"""Proves modify/delete/pause actually works across EVERY vertical (not just restaurants, which is
what's normally exercised) -- added because that coverage was previously only "proven by reading the
code" (_VKEYS = list(verticals.VERTICALS) is registry-driven), never by a test. Real local dev DB,
ZZTEST-prefixed disposable rows, try/finally cleanup."""

import pytest

import indo_usa_mcp.embeddings as emb
from indo_usa_mcp import db, verticals

_NON_EVENT_VERTICALS = [v for v in verticals.VERTICALS if v != "events"]


@pytest.mark.parametrize("vertical", _NON_EVENT_VERTICALS)
def test_crud_roundtrip_for_every_vertical(monkeypatch, vertical):
    monkeypatch.setattr(emb, "enabled", lambda: False)   # no model load; not what this test checks
    table = verticals._table(vertical)
    name = "ZZTEST All-Verticals Row"
    db.execute(f"DELETE FROM {table} WHERE name = %s", (name,))
    res = verticals.create_record(
        vertical, {"name": name, "city": "Plano", "state": "TX", "lat": 33.02, "lng": -96.7},
        source="test")
    assert res.get("ok"), (vertical, res)
    rec_id = res["id"]
    try:
        row = verticals.get_record(vertical, rec_id)
        assert row["is_active"] is True and row["deleted_at"] is None

        # modify
        cfg = verticals.VERTICALS[vertical]
        editable = [f for f in cfg["edit_fields"] if f in ("phone", "website", "region_tag")]
        if editable:
            field = editable[0]
            out = verticals.apply_edits(vertical, rec_id, {field: "ZZTEST-edited-value"})
            assert out["ok"]
            assert verticals.get_record(vertical, rec_id)[field] == "ZZTEST-edited-value"

        # pause / suspend
        verticals.set_active(vertical, rec_id, False)
        assert verticals.get_record(vertical, rec_id)["is_active"] is False
        verticals.set_active(vertical, rec_id, True)
        assert verticals.get_record(vertical, rec_id)["is_active"] is True

        # delete / restore
        verticals.set_deleted(vertical, rec_id, True)
        assert verticals.get_record(vertical, rec_id)["deleted_at"] is not None
        verticals.set_deleted(vertical, rec_id, False)
        assert verticals.get_record(vertical, rec_id)["deleted_at"] is None
    finally:
        db.execute(f"DELETE FROM {table} WHERE id = %s", (rec_id,))


def test_events_admin_crud(monkeypatch):
    # Events aren't admin-creatable via create_record (agent-managed), but the generic
    # apply_edits/set_active/set_deleted path -- driven by the same VERTICALS registry -- must still
    # work on an event row once one exists (e.g. ingested by the events pipeline).
    monkeypatch.setattr(emb, "enabled", lambda: False)
    name = "ZZTEST Event Row"
    db.execute("DELETE FROM events WHERE name = %s", (name,))
    row = db.query_one(
        "INSERT INTO events (name, natural_key, city, state, lat, lng, source_name, confidence_score) "
        "VALUES (%s, %s, 'Plano', 'TX', 33.02, -96.7, 'test', 0.9) RETURNING id",
        (name, f"zztest-event-{name}"))
    rec_id = row["id"]
    try:
        assert verticals.get_record("events", rec_id)["is_active"] is True

        out = verticals.apply_edits("events", rec_id, {"category": "festival"})
        assert out["ok"]
        assert verticals.get_record("events", rec_id)["category"] == "festival"

        verticals.set_active("events", rec_id, False)
        assert verticals.get_record("events", rec_id)["is_active"] is False
        verticals.set_active("events", rec_id, True)
        assert verticals.get_record("events", rec_id)["is_active"] is True

        verticals.set_deleted("events", rec_id, True)
        assert verticals.get_record("events", rec_id)["deleted_at"] is not None
        verticals.set_deleted("events", rec_id, False)
        assert verticals.get_record("events", rec_id)["deleted_at"] is None
    finally:
        db.execute("DELETE FROM events WHERE id = %s", (rec_id,))
