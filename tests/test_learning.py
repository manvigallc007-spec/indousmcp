"""Semantic answer cache: store/lookup + dedup, with embeddings disabled (mocked DB, no network)."""

import indo_usa_mcp.learning as L


def test_lookup_empty_query_is_none():
    assert L.lookup("") is None
    assert L.lookup("   ") is None


def test_store_then_lookup_roundtrip(monkeypatch):
    monkeypatch.setattr(L.embeddings, "enabled", lambda: False)
    mem: dict[str, str] = {}

    def fake_execute(sql, params=None):
        if "INSERT INTO answer_cache" in sql:
            mem[params[0]] = params[3]            # query_norm -> reply

    def fake_query_one(sql, params=None):
        if "WHERE query_norm" in sql:
            return {"id": 1, "reply": mem[params[0]]} if params[0] in mem else None
        return None
    monkeypatch.setattr(L.db, "execute", fake_execute)
    monkeypatch.setattr(L.db, "query_one", fake_query_one)

    L.store("What is Diwali?", "Diwali is the festival of lights.")
    assert L.lookup("what is   diwali?") == "Diwali is the festival of lights."  # normalized match
    assert L.lookup("something unrelated") is None


def test_store_ignores_empty_reply(monkeypatch):
    monkeypatch.setattr(L.embeddings, "enabled", lambda: False)
    called = {"n": 0}
    monkeypatch.setattr(L.db, "execute", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    L.store("q", "")
    assert called["n"] == 0   # nothing written for an empty answer
