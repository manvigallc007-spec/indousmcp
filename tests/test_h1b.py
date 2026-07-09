"""H-1B sponsors: per-employer aggregation, DB round-trip, chat intent, and the /employers page."""

from collections import Counter

from starlette.testclient import TestClient

import indo_usa_mcp.assistant as a
import indo_usa_mcp.h1b as h1b
import indo_usa_mcp.labor as labor
from indo_usa_mcp import db
from indo_usa_mcp.web.app import app


def test_aggregate_builds_employer_detail(monkeypatch):
    rows = [
        {"VISA_CLASS": "H-1B", "CASE_STATUS": "Certified", "EMPLOYER_NAME": "Acme Corp",
         "SOC_TITLE": "Software Developer", "WAGE_RATE_OF_PAY_FROM": "120000",
         "WAGE_UNIT_OF_PAY": "Year", "WORKSITE_STATE": "TX", "WORKSITE_CITY": "Austin"},
        {"VISA_CLASS": "H-1B", "CASE_STATUS": "Certified - Withdrawn", "EMPLOYER_NAME": "ACME  CORP",
         "SOC_TITLE": "Data Scientist", "WAGE_RATE_OF_PAY_FROM": "140000",
         "WAGE_UNIT_OF_PAY": "Year", "WORKSITE_STATE": "TX", "WORKSITE_CITY": "Dallas"},
        {"VISA_CLASS": "E-3", "CASE_STATUS": "Certified", "EMPLOYER_NAME": "Skip Inc"},   # non-H1B
        {"VISA_CLASS": "H-1B", "CASE_STATUS": "Denied", "EMPLOYER_NAME": "Nope"},          # not certified
    ]
    monkeypatch.setattr(labor, "_iter_rows", lambda p: iter(rows))
    agg = labor._aggregate("x")
    assert agg["total"] == 2                              # only certified H-1B rows
    assert agg["employers"]["ACME CORP"] == 2            # name normalized (upper, collapsed spaces)
    d = agg["emp_detail"]["ACME CORP"]
    assert sorted(d["wages"]) == [120000.0, 140000.0]
    assert d["states"]["TX"] == 2 and d["cities"]["Austin"] == 1


def test_to_sponsors_and_search_roundtrip():
    db.execute("DELETE FROM h1b_sponsors WHERE employer LIKE 'ZZTEST %'")
    agg = {
        "employers": Counter({"ZZTEST INFOSYS": 500, "ZZTEST TCS": 300}),
        "emp_detail": {
            "ZZTEST INFOSYS": {"wages": [90000, 110000, 130000],
                               "titles": Counter({"Software Developer": 5, "Consultant": 2}),
                               "states": Counter({"TX": 10, "NJ": 3}), "cities": Counter({"Plano": 4})},
            "ZZTEST TCS": {"wages": [80000], "titles": Counter({"Consultant": 2}),
                           "states": Counter({"NY": 5}), "cities": Counter()},
        }}
    try:
        assert labor._to_sponsors(agg, "2025") == 2
        top = h1b.search_sponsors(q="ZZTEST INFOSYS")
        assert top and top[0]["certified"] == 500 and top[0]["median_wage"] == 110000
        assert "TX" in top[0]["top_states"] and "Software Developer" in top[0]["top_titles"]
        by_state = h1b.search_sponsors(state="TX")
        assert any(r["employer"] == "ZZTEST INFOSYS" for r in by_state)
        assert all(r["employer"] != "ZZTEST TCS" for r in by_state)   # TCS worksite is NY, not TX
    finally:
        db.execute("DELETE FROM h1b_sponsors WHERE employer LIKE 'ZZTEST %'")


# --- admin moderation: pause/suspend + soft-delete + scoped edit ---
def _seed_sponsor():
    db.execute("DELETE FROM h1b_sponsors WHERE employer = 'ZZTEST ADMIN CORP'")
    row = db.query_one(
        "INSERT INTO h1b_sponsors (employer, display_name, certified) "
        "VALUES ('ZZTEST ADMIN CORP', 'ZZTest Admin Corp', 42) RETURNING id")
    return row["id"]


def test_h1b_set_active_and_deleted_roundtrip():
    sid = _seed_sponsor()
    try:
        s = h1b.get_sponsor(sid)
        assert s["is_active"] is True and s["deleted_at"] is None
        h1b.set_active(sid, False)
        assert h1b.get_sponsor(sid)["is_active"] is False
        h1b.set_active(sid, True)
        assert h1b.get_sponsor(sid)["is_active"] is True
        h1b.set_deleted(sid, True)
        assert h1b.get_sponsor(sid)["deleted_at"] is not None
        h1b.set_deleted(sid, False)
        assert h1b.get_sponsor(sid)["deleted_at"] is None
    finally:
        db.execute("DELETE FROM h1b_sponsors WHERE id = %s", (sid,))


def test_h1b_apply_edits_updates_allowed_fields_only():
    sid = _seed_sponsor()
    try:
        out = h1b.apply_edits(sid, {"display_name": "New Name", "employer": "HACKED",
                                    "certified": 999999, "top_titles": ["Engineer"]})
        assert sorted(out["fields"]) == ["display_name", "top_titles"]
        s = h1b.get_sponsor(sid)
        assert s["display_name"] == "New Name" and s["employer"] == "ZZTEST ADMIN CORP"
        assert s["certified"] == 42 and s["top_titles"] == ["Engineer"]
    finally:
        db.execute("DELETE FROM h1b_sponsors WHERE id = %s", (sid,))


def test_search_sponsors_excludes_paused():
    sid = _seed_sponsor()
    try:
        assert h1b.search_sponsors(q="ZZTEST ADMIN CORP")
        h1b.set_active(sid, False)
        assert h1b.search_sponsors(q="ZZTEST ADMIN CORP") == []
        h1b.set_active(sid, True)
        assert h1b.search_sponsors(q="ZZTEST ADMIN CORP")
    finally:
        db.execute("DELETE FROM h1b_sponsors WHERE id = %s", (sid,))


def test_to_sponsors_does_not_reset_pause():
    # Regression: labor._to_sponsors' ON CONFLICT upsert must not clobber the admin pause flag.
    db.execute("DELETE FROM h1b_sponsors WHERE employer = 'ZZTEST REIMPORT CORP'")
    agg = {"employers": Counter({"ZZTEST REIMPORT CORP": 10}),
          "emp_detail": {"ZZTEST REIMPORT CORP": {"wages": [], "titles": Counter(),
                                                    "states": Counter(), "cities": Counter()}}}
    try:
        labor._to_sponsors(agg, "2025")
        row = db.query_one("SELECT id FROM h1b_sponsors WHERE employer = 'ZZTEST REIMPORT CORP'")
        h1b.set_active(row["id"], False)
        labor._to_sponsors(agg, "2025")   # re-import, same employer key
        assert h1b.get_sponsor(row["id"])["is_active"] is False
    finally:
        db.execute("DELETE FROM h1b_sponsors WHERE employer = 'ZZTEST REIMPORT CORP'")


def test_is_h1b_query():
    assert a._is_h1b_query("which companies sponsor h1b")
    assert a._is_h1b_query("h-1b visa sponsors in tx")
    assert not a._is_h1b_query("indian restaurant near me")


def test_h1b_reply_cards(monkeypatch):
    monkeypatch.setattr(h1b, "search_sponsors",
                        lambda q=None, state=None, limit=12: [
                            {"employer": "INFOSYS", "display_name": "Infosys", "certified": 500,
                             "median_wage": 110000, "top_titles": ["Software Developer"],
                             "top_states": ["TX", "NJ"]}])
    out = a._h1b_reply("who sponsors h1b in tx", {})
    assert out["provider"] == "h1b"
    c = out["cards"][0]
    assert c["name"] == "Infosys" and c["vertical"] == "employers"
    assert "500 certified" in c["description"] and "TX" in c["features"]


def test_employers_page(monkeypatch):
    monkeypatch.setattr(h1b, "search_sponsors",
                        lambda q=None, state=None, limit=60: [
                            {"employer": "INFOSYS", "display_name": "Infosys", "certified": 500,
                             "median_wage": 110000, "top_titles": ["Software Developer", "Consultant"],
                             "top_states": ["TX", "NJ"]}])
    r = TestClient(app).get("/employers")
    assert r.status_code == 200
    assert "Infosys" in r.text and "certified H-1B" in r.text and "Department of Labor" in r.text
