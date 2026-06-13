"""Hybrid ranking unit tests (pure scoring, no DB): exact>Featured, proximity, freshness."""

import datetime as dt

from indo_usa_mcp import ranking

_NOW = dt.datetime.now(dt.timezone.utc)


def _row(**kw):
    base = {"id": 0, "name": "", "tags": [], "lat": None, "lng": None,
            "is_featured": False, "last_seen_at": _NOW, "match_score": 0.0}
    base.update(kw)
    return base


def test_exact_name_beats_featured_and_closer():
    rows = [
        _row(id=1, name="Mughlai Express", match_score=0.4),                  # exact, plain
        _row(id=2, name="Spice Garden", is_featured=True, match_score=0.95),  # featured + high vector
        _row(id=3, name="Mughlai Palace", match_score=0.8, lat=40.0, lng=-74.0),  # near + similar
    ]
    out = ranking.rerank(rows, "mughlai express", point=(40.0, -74.0))
    assert out[0]["id"] == 1  # exact name wins over Featured and a closer similar listing


def test_single_word_is_not_exact():
    # "dosa" must NOT be an exact match for "Dosa Hut" (only keyword overlap).
    assert ranking._name_exact("dosa", {"dosa"}, "dosa hut") == 0.0
    assert ranking._name_exact("dosa hut", {"dosa", "hut"}, "dosa hut") == 1.0


def test_closer_ranks_higher():
    base = (40.0, -74.0)
    rows = [
        _row(id=1, name="A2B", lat=40.30, lng=-74.0),   # ~20 mi
        _row(id=2, name="A2B", lat=40.03, lng=-74.0),   # ~2 mi
    ]
    out = ranking.rerank(rows, "vegetarian", point=base)
    assert out[0]["id"] == 2 and out[0]["distance_miles"] < out[1]["distance_miles"]


def test_fresher_ranks_higher():
    rows = [
        _row(id=1, name="Spice", last_seen_at=_NOW - dt.timedelta(days=100)),
        _row(id=2, name="Spice", last_seen_at=_NOW - dt.timedelta(days=2)),
    ]
    out = ranking.rerank(rows, "curry", point=None)
    assert out[0]["id"] == 2  # fresher wins, all else equal


def test_featured_breaks_ties():
    rows = [
        _row(id=1, name="Spice"),
        _row(id=2, name="Spice", is_featured=True),
    ]
    out = ranking.rerank(rows, "curry", point=None)
    assert out[0]["id"] == 2  # equal relevance -> Featured wins


def test_verified_label():
    assert ranking.verified_label(_NOW) == "verified today"
    assert "days ago" in ranking.verified_label(_NOW - dt.timedelta(days=5))
    assert ranking.verified_label(None) is None
