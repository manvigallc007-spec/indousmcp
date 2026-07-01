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


def test_nearest_first_orders_by_distance_regardless_of_relevance():
    base = (40.0, -74.0)
    rows = [
        _row(id=1, name="Far Biryani House", match_score=0.95, lat=40.6, lng=-74.0),   # ~41 mi
        _row(id=2, name="Close Biryani Corner", match_score=0.4, lat=40.04, lng=-74.0),  # ~3 mi
    ]
    out = ranking.rerank(rows, "biryani", point=base, nearest_first=True)
    assert out[0]["id"] == 2  # nearest wins even with lower relevance (distance doesn't matter)


def test_nearest_first_still_lets_exact_name_lead():
    base = (40.0, -74.0)
    rows = [
        _row(id=1, name="Tasty Biryani", match_score=0.4, lat=40.02, lng=-74.0),       # closest, not exact
        _row(id=2, name="Mughlai Express", match_score=0.6, lat=41.0, lng=-74.0),      # far, exact name
    ]
    out = ranking.rerank(rows, "mughlai express", point=base, nearest_first=True)
    assert out[0]["id"] == 2  # an exact-name match still leads, even under nearest-first


def test_verified_label():
    assert ranking.verified_label(_NOW) == "verified today"
    assert "days ago" in ranking.verified_label(_NOW - dt.timedelta(days=5))
    assert ranking.verified_label(None) is None


def test_trust_score_rewards_above_baseline_only():
    assert ranking.trust_score({"confidence_score": 0.5}) == 0.0        # baseline -> neutral
    assert ranking.trust_score({"confidence_score": 1.0}) == 1.0
    assert abs(ranking.trust_score({"confidence_score": 0.9}) - 0.8) < 1e-9
    assert ranking.trust_score({"confidence_score": 0.2}) == 0.0        # below baseline -> neutral
    assert ranking.trust_score({}) == 0.0                              # unknown -> neutral, never a penalty


def test_higher_confidence_breaks_ties():
    rows = [
        _row(id=1, name="Spice", confidence_score=0.5),
        _row(id=2, name="Spice", confidence_score=0.95),
    ]
    out = ranking.rerank(rows, "curry", point=None)
    assert out[0]["id"] == 2  # equal relevance -> better-sourced (higher-confidence) wins


def test_confidence_never_beats_relevance():
    rows = [
        _row(id=1, name="Mughlai Express", match_score=0.4, confidence_score=0.5),  # exact, low conf
        _row(id=2, name="Spice Garden", match_score=0.95, confidence_score=1.0),    # max conf, not exact
    ]
    out = ranking.rerank(rows, "mughlai express", point=None)
    assert out[0]["id"] == 1  # exact-name relevance still dominates the trust nudge


def test_featured_outranks_confidence_nudge():
    # Hierarchy: Featured (W=1.0) is a stronger tiebreak than the trust nudge (max 0.6).
    rows = [
        _row(id=1, name="Spice", is_featured=True),          # +1.0
        _row(id=2, name="Spice", confidence_score=1.0),      # +0.6
    ]
    out = ranking.rerank(rows, "curry", point=None)
    assert out[0]["id"] == 1
