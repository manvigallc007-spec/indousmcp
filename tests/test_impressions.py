"""Tests for impression attribution + search_all qvec reuse (no DB)."""

from indo_usa_mcp import analytics


def test_impression_rows_for_list_tool():
    res = {"results": [{"id": 1}, {"id": 2}, {"no_id": True}]}
    rows = analytics._impression_rows("get_indian_restaurants", res)
    assert rows == [("restaurants", 1), ("restaurants", 2)]


def test_impression_rows_for_search_all_uses_each_vertical():
    res = {"results": [{"id": 5, "vertical": "temples"}, {"id": 9, "vertical": "salons"}]}
    assert analytics._impression_rows("search_all", res) == [("temples", 5), ("salons", 9)]


def test_impression_rows_for_details_tool():
    assert analytics._impression_rows("get_salon_details", {"id": 7}) == [("salons", 7)]


def test_non_data_tools_produce_no_impressions():
    assert analytics._impression_rows("submit_correction", {"ok": True}) == []
    assert analytics._impression_rows("draft_claim_outreach", {"drafted": 3}) == []


def test_search_functions_accept_precomputed_qvec():
    import inspect
    from indo_usa_mcp import queries
    from indo_usa_mcp.salons import queries as sq
    for fn in (queries.search_restaurants_by_text, sq.search_salons_by_text):
        assert "precomputed_qvec" in inspect.signature(fn).parameters
