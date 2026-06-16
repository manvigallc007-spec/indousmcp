"""A named category scopes the search to just that vertical (item 5). No DB: search fns are stubbed."""

import indo_usa_mcp.assistant as A
from indo_usa_mcp import verticals


def _stub(key, calls):
    def f(*a, **k):
        calls[key] = True
        return {"results": [], "ranking": "test"}
    return f


def test_named_category_scopes_to_that_vertical(monkeypatch):
    assert A._guess_vertical("restaurants in plano") == "restaurants"
    calls: dict = {}
    monkeypatch.setattr(verticals, "search_all", _stub("all", calls))
    monkeypatch.setattr(verticals.VERTICALS["restaurants"]["queries"],
                        "search_restaurants_by_text", _stub("rest", calls))
    A._run_search({"query": "restaurants in plano"}, filters={}, geo=None)
    assert calls.get("rest") is True and "all" not in calls   # only restaurants searched


def test_typed_category_overrides_a_conflicting_chip(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(verticals, "search_all", _stub("all", calls))
    monkeypatch.setattr(verticals.VERTICALS["restaurants"]["queries"],
                        "search_restaurants_by_text", _stub("rest", calls))
    # Temple chip set, but the message asks for restaurants -> restaurants win
    A._run_search({"query": "best biryani"}, filters={"vertical": "temples"}, geo=None)
    assert calls.get("rest") is True


def test_chip_still_applies_when_no_category_named(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(verticals, "search_all", _stub("all", calls))
    monkeypatch.setattr(verticals.VERTICALS["temples"]["queries"],
                        "search_temples_by_text", _stub("temple", calls))
    A._run_search({"query": "near me"}, filters={"vertical": "temples"}, geo=None)
    assert calls.get("temple") is True and "all" not in calls
