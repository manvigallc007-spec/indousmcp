"""Rating-as-a-ranking-signal: community rating preferred, min-review gate kills 1-review 5.0s,
and a 'best/top-rated' query weights rating more. Pure functions, no DB."""

from indo_usa_mcp import ranking as r


def test_is_superlative():
    assert r._is_superlative("best biryani in town")
    assert r._is_superlative("which salon has the highest rated")
    assert r._is_superlative("top rated sweet shop")
    assert not r._is_superlative("biryani near me")
    assert not r._is_superlative("")


def test_rating_score_min_review_gate():
    # one 5-star review must NOT produce a rating signal
    assert r.rating_score({"community_rating": 5.0, "community_rating_count": 1}) == 0.0
    # enough reviews -> positive signal
    assert r.rating_score({"community_rating": 5.0, "community_rating_count": 20}) > 0.0


def test_rating_score_prefers_community_over_web():
    row = {"community_rating": 4.8, "community_rating_count": 20,
           "rating": 3.2, "rating_count": 500}
    # uses community (4.8), not the lower web rating
    assert r.rating_score(row) > r.rating_score(
        {"rating": 3.2, "rating_count": 500})


def test_rating_score_web_fallback_and_curve():
    # no community -> falls back to web; 3.0 stars contributes ~0; 5.0 with full reviews -> ~1.0
    assert r.rating_score({"rating": 3.0, "rating_count": 50}) == 0.0
    assert abs(r.rating_score({"rating": 5.0, "rating_count": 50}) - 1.0) < 1e-6


def test_rerank_orders_by_rating_when_otherwise_equal():
    rows = [
        {"id": 1, "name": "Alpha", "community_rating": 4.0, "community_rating_count": 20},
        {"id": 2, "name": "Beta", "community_rating": 4.8, "community_rating_count": 20},
    ]
    out = r.rerank(rows, "")            # no query terms -> only rating differs
    assert [x["id"] for x in out] == [2, 1]


def test_low_review_five_star_loses_to_well_reviewed_four_star():
    rows = [
        {"id": 1, "name": "OneReviewWonder", "community_rating": 5.0, "community_rating_count": 1},
        {"id": 2, "name": "Established", "community_rating": 4.0, "community_rating_count": 30},
    ]
    out = r.rerank(rows, "")
    assert out[0]["id"] == 2            # the well-reviewed 4.0 beats the single-review 5.0


def test_superlative_query_boosts_rating_weight():
    row = {"name": "X", "community_rating": 4.6, "community_rating_count": 20}
    base = r.score_row(row, "", set(), 0.0, None, r.W_RATING)
    boosted = r.score_row(row, "", set(), 0.0, None, r.W_RATING * r.SUPERLATIVE_MULT)
    assert boosted > base
