"""Owner submissions: payment (paid_featured_days) applies ONLY at approval, never bypasses the gate;
paid-but-rejected is surfaced for refunds. Real dev DB, ZZTEST rows, try/finally."""

import indo_usa_mcp.embeddings as emb
from indo_usa_mcp import db, submissions


def _submit(name, **extra):
    payload = {"name": name, "city": "Plano", "state": "TX", "lat": 33.0, "lng": -96.7}
    payload.update(extra)
    return submissions.submit("restaurants", payload, contact_email="z@z.com")["id"]


def test_approve_applies_paid_featured_days(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)
    sid = _submit("ZZTEST Approve Paid")
    db.execute("UPDATE submissions SET paid_featured_days = 90 WHERE id = %s", (sid,))
    calls = {}
    monkeypatch.setattr("indo_usa_mcp.verticals.set_featured",
                        lambda vertical, rec_id, days=None: calls.update(v=vertical, id=rec_id, days=days))
    try:
        out = submissions.approve(sid)
        assert out["ok"]
        assert calls == {"v": "restaurants", "id": out["record_id"], "days": 90}
    finally:
        db.execute("DELETE FROM restaurants WHERE name = 'ZZTEST Approve Paid'")
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))


def test_approve_without_payment_skips_featuring(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)
    sid = _submit("ZZTEST Approve Free")
    called = []
    monkeypatch.setattr("indo_usa_mcp.verticals.set_featured",
                        lambda *a, **k: called.append(1))
    try:
        assert submissions.approve(sid)["ok"]
        assert not called                              # no payment -> never featured
    finally:
        db.execute("DELETE FROM restaurants WHERE name = 'ZZTEST Approve Free'")
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))


def test_reject_leaves_paid_flag_visible():
    sid = _submit("ZZTEST Reject Paid")
    db.execute("UPDATE submissions SET paid_featured_days = 30 WHERE id = %s", (sid,))
    try:
        submissions.reject(sid)
        row = db.query_one("SELECT status, paid_featured_days FROM submissions WHERE id = %s", (sid,))
        assert row["status"] == "rejected" and row["paid_featured_days"] == 30   # stays for the refund view
    finally:
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))


def test_list_paid_unresolved_only_rejected_and_paid():
    paid = _submit("ZZTEST Unresolved Paid")
    unpaid = _submit("ZZTEST Unresolved Unpaid")
    db.execute("UPDATE submissions SET status='rejected', paid_featured_days=30, "
               "stripe_session_id='cs_zz' WHERE id=%s", (paid,))
    db.execute("UPDATE submissions SET status='rejected' WHERE id=%s", (unpaid,))
    try:
        ids = {u["id"] for u in submissions.list_paid_unresolved()}
        assert paid in ids and unpaid not in ids
    finally:
        db.execute("DELETE FROM submissions WHERE id = ANY(%s)", ([paid, unpaid],))


def test_list_pending_includes_payment_columns():
    sid = _submit("ZZTEST Pending Cols")
    db.execute("UPDATE submissions SET paid_featured_days = 90, stripe_session_id = 'cs_c' WHERE id = %s", (sid,))
    try:
        row = next(r for r in submissions.list_pending() if r["id"] == sid)
        assert row["paid_featured_days"] == 90 and row["stripe_session_id"] == "cs_c"
    finally:
        db.execute("DELETE FROM submissions WHERE id = %s", (sid,))
