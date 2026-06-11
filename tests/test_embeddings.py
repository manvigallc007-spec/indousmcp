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
    lit = embeddings.to_vector_literal([0.1, -0.2, 0.3])
    assert lit.startswith("[") and lit.endswith("]")
    assert lit == "[0.100000,-0.200000,0.300000]"


def test_text_for_includes_tags_and_region():
    blob = embeddings.text_for(
        {"name": "Edison Spice Route", "region_tag": "Gujarati",
         "dietary_tags": ["vegetarian", "jain"], "city": "Edison"}
    )
    assert "Gujarati" in blob and "jain" in blob and "Edison" in blob
