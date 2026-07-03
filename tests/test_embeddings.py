"""Unit tests for the embedding layer (hashing provider, no DB / no model download)."""

import math

from indo_usa_mcp import embeddings
from indo_usa_mcp.embeddings import HashingEmbedder


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))  # vectors are already L2-normalized


def test_hashing_embedder_dim_and_norm():
    emb = HashingEmbedder(dim=384)
    v = emb.embed("Saffron South Indian vegetarian")
    assert len(v) == 384
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)


def test_hashing_embedder_is_deterministic():
    emb = HashingEmbedder(dim=384)
    assert emb.embed("Punjabi dhaba Fremont") == emb.embed("Punjabi dhaba Fremont")


def test_similar_text_scores_higher_than_unrelated():
    emb = HashingEmbedder(dim=384)
    base = emb.embed("South Indian dosa vegetarian Sunnyvale")
    near = emb.embed("South Indian dosa idli vegetarian")
    far = emb.embed("Punjabi tandoori chicken halal Houston")
    assert _cos(base, near) > _cos(base, far)


def test_empty_text_is_safe():
    emb = HashingEmbedder(dim=384)
    v = emb.embed("")
    assert len(v) == 384  # zero vector, not normalized away


def test_to_vector_literal_format():
    vec = [0.1, -0.2, 0.3] + [0.0] * (embeddings.settings.embedding_dim - 3)
    lit = embeddings.to_vector_literal(vec)
    assert lit.startswith("[0.100000,-0.200000,0.300000,") and lit.endswith("0.000000]")


def test_to_vector_literal_rejects_wrong_dimension():
    # Regression: pgvector's ::vector cast doesn't validate this itself -- a mismatched-dimension
    # vector would otherwise silently store a corrupt vector instead of failing loudly.
    try:
        embeddings.to_vector_literal([0.1, 0.2, 0.3])
    except ValueError as exc:
        assert "3" in str(exc) and str(embeddings.settings.embedding_dim) in str(exc)
    else:
        raise AssertionError("expected ValueError for a wrong-dimension vector")


def test_text_for_includes_tags_and_region():
    blob = embeddings.text_for(
        {"name": "Edison Spice Route", "region_tag": "Gujarati",
         "dietary_tags": ["vegetarian", "jain"], "city": "Edison"}
    )
    assert "Gujarati" in blob and "jain" in blob and "Edison" in blob


# --- diagnose(): "is vectorization actually configured the way I think?" (mirrors llm-check) ---
def test_diagnose_off_when_provider_none(monkeypatch):
    # _get_embedder() is lru_cache'd, so setting embedding_provider alone won't move it once another
    # test has already resolved+cached a real embedder -- mock enabled() directly, like the other
    # diagnose tests below do, so this doesn't depend on suite ordering.
    monkeypatch.setattr(embeddings, "enabled", lambda: False)
    out = embeddings.diagnose()
    assert out["status"] == "off" and out["enabled"] is False


def test_diagnose_ok_reports_coverage(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "embedding_provider", "hashing")
    monkeypatch.setattr(embeddings, "enabled", lambda: True)
    monkeypatch.setattr(embeddings, "embed", lambda text: [0.0] * embeddings.settings.embedding_dim)
    from indo_usa_mcp import db, verticals
    monkeypatch.setattr(verticals, "VERTICALS", {"restaurants": {"table": "restaurants"}})
    monkeypatch.setattr(db, "query_one", lambda *a, **k: {"active": 10, "missing": 3})
    out = embeddings.diagnose()
    assert out["status"] == "ok" and out["actual_dim"] == embeddings.settings.embedding_dim
    assert out["coverage"] == {"restaurants": {"active": 10, "missing": 3}}
    assert "3 active listing" in out["hint"]


def test_diagnose_flags_dimension_mismatch(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "embedding_provider", "hashing")
    monkeypatch.setattr(embeddings, "enabled", lambda: True)
    monkeypatch.setattr(embeddings, "embed", lambda text: [0.0] * 10)   # wrong dim
    out = embeddings.diagnose()
    assert out["status"] == "error" and "10" in out["reason"]


def test_diagnose_reports_embedder_failure(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "embedding_provider", "hashing")
    monkeypatch.setattr(embeddings, "enabled", lambda: True)
    monkeypatch.setattr(embeddings, "embed",
                        lambda text: (_ for _ in ()).throw(RuntimeError("model load failed")))
    out = embeddings.diagnose()
    assert out["status"] == "error" and "model load failed" in out["error"]
