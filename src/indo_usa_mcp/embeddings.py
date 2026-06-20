"""Pluggable text embeddings for semantic restaurant search.

Providers (set EMBEDDING_PROVIDER):
  * "hashing"               -- deterministic feature-hashing, zero dependencies (default).
                               Lexical, not deeply semantic, but runs anywhere and keeps
                               the vector path exercised end-to-end.
  * "sentence_transformers" -- real semantic embeddings via all-MiniLM-L6-v2 (384-dim).
                               Opt-in: `pip install sentence-transformers` (pulls torch).
  * "none"                  -- disable embeddings; search falls back to trigram.

All providers emit L2-normalized vectors of length settings.embedding_dim, so cosine
distance (`<=>` in pgvector) is a clean similarity. Vectors are bound to Postgres as a
text literal cast to ::vector, avoiding any extra driver dependency.
"""

from __future__ import annotations

import functools
import hashlib
import math
import re

from .config import settings

# Fields that best characterise a restaurant for similarity.
_TEXT_FIELDS = ("name", "cuisine_type", "region_tag", "city", "state", "dietary_tags")

# Structured facets folded into EVERY embedding (on top of the prose) so faceted free-text queries
# — "vegetarian andhra in plano", "telugu speaking dentist", "halal sweets near edison" — match on
# the vector, not just keywords. Scalar type fields + list fields, across all verticals.
_ATTR_SCALARS = ("cuisine_type", "region_tag", "city", "state", "price_range", "profession_type",
                 "speciality", "store_type", "service_type", "studio_type", "salon_type",
                 "religion", "denomination", "deity", "category", "org_type", "legal_type",
                 "edu_type", "realestate_type", "finance_type")
_ATTR_LISTS = ("dietary_tags", "languages", "tags")


def _attributes(record: dict) -> str:
    bits: list[str] = []
    for field in _ATTR_SCALARS:
        v = record.get(field)
        if v:
            bits.append(str(v).replace("_", " "))
    for field in _ATTR_LISTS:
        v = record.get(field)
        if isinstance(v, (list, tuple)):
            bits.extend(str(x).replace("_", " ") for x in v if x)
    return " ".join(bits)


# --------------------------------------------------------------------- providers
class HashingEmbedder:
    """Feature-hashing over word + character-trigram tokens. Deterministic, dep-free."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokens(text):
            idx, sign = _hash_token(token)
            vec[idx % self.dim] += sign
        return _l2_normalize(vec)


class FastEmbedEmbedder:
    """Real semantic embeddings via fastembed (ONNX, no torch). BAAI/bge-small-en = 384-dim."""

    def __init__(self, model_name: str, dim: int) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - optional install
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=fastembed requires `pip install fastembed`.") from exc
            self._model = TextEmbedding(self.model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        vec = next(iter(self._load().embed([text or ""])))
        return [float(x) for x in vec]


class SentenceTransformerEmbedder:
    """Real semantic embeddings. Lazily loads the model on first use."""

    def __init__(self, model_name: str, dim: int) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - depends on optional install
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=sentence_transformers requires "
                    "`pip install sentence-transformers`."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._load()
        vec = model.encode(text or "", normalize_embeddings=True)
        return [float(x) for x in vec]


# ---------------------------------------------------------------------- helpers
def _tokens(text: str) -> list[str]:
    text = (text or "").lower()
    words = re.findall(r"[a-z0-9]+", text)
    grams: list[str] = []
    for w in words:
        grams.append(w)
        padded = f"#{w}#"
        for i in range(len(padded) - 2):
            grams.append(padded[i : i + 3])
    return grams


def _hash_token(token: str) -> tuple[int, int]:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big")
    sign = 1 if digest[4] & 1 else -1
    return idx, sign


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


@functools.lru_cache(maxsize=1)
def _get_embedder():
    provider = settings.embedding_provider.lower()
    if provider == "none":
        return None
    if provider == "fastembed":
        return FastEmbedEmbedder(settings.fastembed_model, settings.embedding_dim)
    if provider == "sentence_transformers":
        return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_dim)
    return HashingEmbedder(settings.embedding_dim)


# ------------------------------------------------------------------- public API
def enabled() -> bool:
    return _get_embedder() is not None


def embed(text: str) -> list[float]:
    embedder = _get_embedder()
    if embedder is None:
        raise RuntimeError("Embeddings are disabled (EMBEDDING_PROVIDER=none).")
    return embedder.embed(text)


def text_for(record: dict) -> str:
    """Text to embed: the prose description plus the structured facets (cuisine, region, location,
    price, dietary, languages, tags, and vertical-specific type fields), so semantic search matches
    on all of them. Falls back to a field blob when there's no description."""
    attrs = _attributes(record)
    if record.get("description"):
        return (record["description"] + (" " + attrs if attrs else "")).strip()
    name = str(record.get("name") or "").strip()
    text = (name + (" " + attrs if attrs else "")).strip()
    if text:
        return text
    parts: list[str] = []
    for field in _TEXT_FIELDS:
        value = record.get(field)
        if isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def to_vector_literal(vec: list[float]) -> str:
    """pgvector text form: '[0.1,0.2,...]' (bind with ::vector)."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
