"""LLM-polished grounded content: generation gating/grounding + listing-page display. No network."""

from starlette.testclient import TestClient

import indo_usa_mcp.enrich_llm as el
from indo_usa_mcp.web import reviews as rv
from indo_usa_mcp.web.app import app


def _row(**over):
    base = {"id": 1, "name": "Spice Hut", "city": "Plano", "state": "TX", "region_tag": "South Indian",
            "cuisine_type": "South Indian", "description": "templated text", "tags": None,
            "languages": ["Telugu"], "address_full": "1 Main St", "lat": 33.0, "lng": -96.7,
            "phone": None, "website": None, "is_claimed": True, "is_featured": False,
            "rating": None, "rating_count": None, "community_rating": None, "community_rating_count": 0,
            "photo_url": None}
    base.update(over)
    return base


def test_review_block_filters_and_caps():
    items = [{"body": "Great dosa"}, {"body": "  "}, {"body": "Slow service"}, {"body": None}]
    block = el._review_block(items)
    assert block == "- Great dosa\n- Slow service"


def test_hash_changes_with_input():
    assert el._hash("a", "b") == el._hash("a", "b")
    assert el._hash("a", "b") != el._hash("a", "c")


def test_enrich_listing_noop_when_llm_inactive(monkeypatch):
    monkeypatch.setattr(el.assistant, "llm_active", lambda: False)
    assert el.enrich_listing("restaurants", _row(), []) is None


def test_enrich_listing_generates_grounded_content(monkeypatch):
    monkeypatch.setattr(el.assistant, "llm_active", lambda: True)

    def fake_complete(system, user):
        assert "FACTS:" in user or "REVIEWS:" in user            # grounded prompt
        return "Polished description." if "editor" in system else "Diners praise the dosa."

    monkeypatch.setattr(el.assistant, "complete_text", fake_complete)
    monkeypatch.setattr(el.db, "query_one", lambda *a, **k: None)   # no prior ai_content
    import indo_usa_mcp.embeddings as emb
    monkeypatch.setattr(emb, "enabled", lambda: False)             # skip the re-embed
    executed = []
    monkeypatch.setattr(el.db, "execute", lambda sql, params=None: executed.append((sql, params)))

    out = el.enrich_listing("restaurants", _row(),
                            [{"body": "Great dosa"}, {"body": "Good filter coffee"}])
    assert out == {"description": "Polished description.", "review_summary": "Diners praise the dosa."}
    assert any("INSERT INTO ai_content" in sql for sql, _ in executed)


def test_enrich_listing_skips_unchanged(monkeypatch):
    from indo_usa_mcp import describe
    monkeypatch.setattr(el.assistant, "llm_active", lambda: True)
    row = _row()
    facts = describe.describe("restaurants", row)
    src = el._hash(facts, "")                                      # no reviews -> empty block
    monkeypatch.setattr(el.db, "query_one", lambda *a, **k: {"source_hash": src})
    # complete_text must NOT be called when inputs are unchanged
    monkeypatch.setattr(el.assistant, "complete_text",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")))
    assert el.enrich_listing("restaurants", row, []) is None


def test_listing_page_prefers_ai_content(monkeypatch):
    import indo_usa_mcp.enrich_llm as elmod
    monkeypatch.setattr(rv, "_fetch", lambda v, i: _row())
    monkeypatch.setattr(rv.reviews_mod, "list_for_listing", lambda *a, **k: [])
    monkeypatch.setattr(elmod, "get", lambda v, i: {"description": "Family-run South Indian spot.",
                                                    "review_summary": "Reviewers love the dosa."})
    r = TestClient(app).get("/listing/restaurants/1")
    assert r.status_code == 200
    assert "Family-run South Indian spot." in r.text      # AI description preferred
    assert "templated text" not in r.text                 # over the templated one
    assert "Reviewers love the dosa." in r.text           # 'what people say' callout
